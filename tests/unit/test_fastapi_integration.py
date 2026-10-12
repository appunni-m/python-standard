from __future__ import annotations

import asyncio
import logging
import threading
from collections.abc import Sequence
from typing import Any

import pytest
from fastapi import Depends, FastAPI, Request
from fastapi.responses import JSONResponse
from httpx import ASGITransport, AsyncClient, Response
from pydantic import ValidationError

from std.fastapi import (
    APIConfig,
    APIService,
    AppTokenAuth,
    AppTokenConfig,
    Environment,
    FastAPISetup,
    HealthCheck,
    HealthResponse,
    LifecycleManager,
    LoggingMiddleware,
    TokenAuthMiddleware,
    add_api_key_security_scheme,
    apply_token_auth_middleware,
    create_health_endpoint,
    setup_token_auth,
)
from std.service import BackgroundService, ServiceState


def request(
    app: FastAPI, method: str, path: str, *, headers: dict[str, str] | None = None
) -> Response:
    async def scenario() -> Response:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            return await client.request(method, path, headers=headers)

    return asyncio.run(scenario())


class DummyService:
    """Small lifecycle double for manager ordering and failure cases."""

    def __init__(
        self,
        name: str,
        events: list[str],
        *,
        start_error: Exception | None = None,
        stop_error: Exception | None = None,
    ) -> None:
        self.name = name
        self.events = events
        self.start_error = start_error
        self.stop_error = stop_error
        self.state = ServiceState.IDLE

    async def start(self) -> None:
        """Record the start call and apply an optional injected failure."""
        self.events.append(f"start:{self.name}")
        if self.start_error is not None:
            raise self.start_error
        self.state = ServiceState.RUNNING

    async def stop(self) -> None:
        """Record the stop call and apply an optional injected failure."""
        self.events.append(f"stop:{self.name}")
        if self.stop_error is not None:
            raise self.stop_error
        self.state = ServiceState.STOPPED

    async def is_healthy(self) -> bool:
        """Report whether this service double reached the running state."""
        return self.state is ServiceState.RUNNING


class TrackingWorker(BackgroundService):
    """Worker for app setup tests that records when it runs and stops."""

    def __init__(self, events: list[str]) -> None:
        super().__init__(name="tracked", shutdown_timeout=0.05)
        self.events = events

    async def run(self) -> None:
        """Run until the shared service lifecycle requests shutdown."""
        self.events.append("run")
        await self.stop_event.wait()


def test_api_config_validates_server_and_cors_values() -> None:
    config = APIConfig(env="prod", port=8443, cors_origins=[" https://example.com "])
    assert config.env is Environment.PROD
    assert config.host == "0.0.0.0"
    assert config.cors_origins == ["https://example.com"]
    with pytest.raises(ValidationError):
        APIConfig(port=0)
    with pytest.raises(ValidationError):
        APIConfig(workers=0)
    with pytest.raises(ValidationError, match="host cannot be empty"):
        APIConfig(host="  ")
    with pytest.raises(ValidationError, match="CORS entries cannot be empty"):
        APIConfig(cors_origins=[""])


def test_api_service_registers_routes_on_injected_application() -> None:
    app = FastAPI()

    class HealthAPI(APIService):
        def _setup_routes(self) -> None:
            @self.app.get("/status")
            async def status() -> dict[str, str]:
                return {"status": "ok"}

    HealthAPI(app, name="health")
    assert request(app, "GET", "/status").json() == {"status": "ok"}


def test_fastapi_setup_configures_metadata_cors_and_lifecycle() -> None:
    async def scenario() -> None:
        events: list[str] = []
        worker = TrackingWorker(events)

        async def setup() -> Sequence[TrackingWorker]:
            return [worker]

        setup_helper = FastAPISetup(
            APIConfig(
                title="Example service",
                description="A test API",
                version="2.3.4",
                cors_origins=["https://client.example"],
            ),
            setup_handler=setup,
        )
        app = setup_helper.create_fastapi_app()

        @app.get("/ready")
        async def ready() -> dict[str, bool]:
            return {"ready": True}

        async with app.router.lifespan_context(app):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                assert (await client.get("/ready")).json() == {"ready": True}
                preflight = await client.options(
                    "/ready",
                    headers={
                        "Origin": "https://client.example",
                        "Access-Control-Request-Method": "GET",
                    },
                )
            assert preflight.status_code == 200
            assert preflight.headers["access-control-allow-origin"] == "https://client.example"
            assert worker.state is ServiceState.RUNNING

        assert worker.state is ServiceState.STOPPED
        assert events == ["run"]
        assert setup_helper.lifecycle_manager.status is ServiceState.STOPPED

    asyncio.run(scenario())


def test_fastapi_setup_maps_environment_to_logging_preset(monkeypatch: pytest.MonkeyPatch) -> None:
    configurations: list[tuple[object, str]] = []

    def configure(config: object, *, environment: str) -> None:
        configurations.append((config, environment))

    monkeypatch.setattr("std.fastapi.api.setup.configure_logging", configure)
    FastAPISetup(APIConfig(env=Environment.STAGE), {"format": "json"}).create_fastapi_app()
    assert configurations == [({"format": "json"}, "staging")]


def test_lifecycle_manager_starts_and_stops_in_dependency_order() -> None:
    async def scenario() -> None:
        events: list[str] = []
        first = DummyService("first", events)
        second = DummyService("second", events)
        manager = LifecycleManager([first, second])

        await manager.start()
        await manager.start()
        assert manager.status is ServiceState.RUNNING
        await manager.stop()
        await manager.stop()

        assert events == ["start:first", "start:second", "stop:second", "stop:first"]
        assert manager.status is ServiceState.STOPPED

    asyncio.run(scenario())


def test_lifecycle_manager_cleans_partial_start_and_can_restart() -> None:
    async def scenario() -> None:
        events: list[str] = []
        first = DummyService("first", events)
        failing = DummyService("failing", events, start_error=RuntimeError("startup"))
        manager = LifecycleManager([first, failing])

        with pytest.raises(RuntimeError, match="startup"):
            await manager.start()
        assert events == [
            "start:first",
            "start:failing",
            "stop:failing",
            "stop:first",
        ]
        assert manager.status is ServiceState.FAILED

        failing.start_error = None
        await manager.start()
        assert manager.status is ServiceState.RUNNING
        await manager.stop()
        assert manager.status is ServiceState.STOPPED

    asyncio.run(scenario())


def test_lifecycle_manager_keeps_startup_error_when_cleanup_fails() -> None:
    async def scenario() -> None:
        events: list[str] = []
        first = DummyService("first", events, stop_error=RuntimeError("cleanup"))
        failing = DummyService("failing", events, start_error=ValueError("startup"))
        manager = LifecycleManager([first, failing])

        with pytest.raises(ValueError, match="startup") as raised:
            await manager.start()
        assert any("cleanup failed" in note for note in getattr(raised.value, "__notes__", []))
        assert events == ["start:first", "start:failing", "stop:failing", "stop:first"]
        first.stop_error = None
        await manager.stop()
        assert manager.status is ServiceState.STOPPED

    asyncio.run(scenario())


def test_lifecycle_manager_aggregates_shutdown_errors() -> None:
    async def scenario() -> None:
        events: list[str] = []
        first = DummyService("first", events, stop_error=ValueError("first cleanup"))
        second = DummyService("second", events, stop_error=RuntimeError("second cleanup"))
        manager = LifecycleManager([first, second])
        await manager.start()

        with pytest.raises(ExceptionGroup) as raised:
            await manager.stop()

        assert len(raised.value.exceptions) == 2
        assert events == ["start:first", "start:second", "stop:second", "stop:first"]
        assert manager.status is ServiceState.FAILED

        first.stop_error = None
        second.stop_error = None
        await manager.stop()
        assert events[-2:] == ["stop:second", "stop:first"]
        assert manager.status is ServiceState.STOPPED

    asyncio.run(scenario())


def test_lifecycle_manager_setup_handler_runs_each_start() -> None:
    async def scenario() -> None:
        calls = 0
        events: list[str] = []

        async def setup() -> Sequence[DummyService]:
            nonlocal calls
            calls += 1
            return [DummyService(f"dynamic-{calls}", events)]

        manager = LifecycleManager(setup_handler=setup)
        await manager.start()
        await manager.stop()
        await manager.start()
        await manager.stop()
        assert calls == 2
        assert events == [
            "start:dynamic-1",
            "stop:dynamic-1",
            "start:dynamic-2",
            "stop:dynamic-2",
        ]

    asyncio.run(scenario())


def test_lifecycle_manager_rejects_duplicate_or_late_registration() -> None:
    async def scenario() -> None:
        events: list[str] = []
        service = DummyService("one", events)
        with pytest.raises(ValueError, match="twice"):
            LifecycleManager([service, service])
        manager = LifecycleManager([service])
        await manager.start()
        with pytest.raises(RuntimeError, match="cannot be added"):
            manager.add_service(DummyService("late", events))
        await manager.stop()

    asyncio.run(scenario())


def test_dependency_and_middleware_authenticate_custom_headers() -> None:
    config = AppTokenConfig(
        header_name="X-Client-Key",
        tokens={"billing": "very-secret-value"},
        exclude_paths={"/public/*"},
    )
    assert "very-secret-value" not in repr(config)

    app = FastAPI()
    auth = AppTokenAuth(config)

    @app.get("/dependency")
    async def dependency_route(app_name: str | None = Depends(auth)) -> dict[str, str | None]:
        return {"app": app_name}

    apply_token_auth_middleware(app, config)

    @app.get("/middleware")
    async def middleware_route(request: Request) -> dict[str, str]:
        return {"app": request.state.app_name}

    @app.get("/public/status")
    async def public_route() -> dict[str, bool]:
        return {"public": True}

    assert request(app, "GET", "/dependency").status_code == 401
    assert request(app, "GET", "/dependency", headers={"X-Client-Key": "wrong"}).status_code == 401
    assert request(
        app, "GET", "/dependency", headers={"X-Client-Key": "very-secret-value"}
    ).json() == {"app": "billing"}
    assert request(
        app, "GET", "/middleware", headers={"X-Client-Key": "very-secret-value"}
    ).json() == {"app": "billing"}
    assert request(app, "GET", "/public/status").json() == {"public": True}

    assert app.user_middleware[0].cls is TokenAuthMiddleware
    assert app.openapi()["components"]["securitySchemes"]["APIKeyHeader"]["name"] == (
        "X-Client-Key"
    )


def test_auth_custom_handlers_and_disabled_mode() -> None:
    async def missing(_request: Any) -> JSONResponse:
        return JSONResponse({"reason": "credentials required"}, status_code=418)

    async def invalid(_request: Any, _token: str) -> JSONResponse:
        return JSONResponse({"reason": "credentials rejected"}, status_code=403)

    app = FastAPI()
    apply_token_auth_middleware(
        app,
        AppTokenConfig(tokens={"worker": "token"}),
        on_missing_token=missing,
        on_invalid_token=invalid,
    )

    @app.get("/protected")
    async def protected() -> dict[str, bool]:
        return {"ok": True}

    assert request(app, "GET", "/protected").status_code == 418
    assert request(app, "GET", "/protected", headers={"X-App-Token": "bad"}).status_code == 403
    assert request(app, "GET", "/protected", headers={"X-App-Token": "token"}).status_code == 200

    disabled_app = FastAPI()
    apply_token_auth_middleware(disabled_app, AppTokenConfig(enabled=False))

    @disabled_app.get("/open")
    async def open_route() -> dict[str, bool]:
        return {"open": True}

    assert request(disabled_app, "GET", "/open").status_code == 200


def test_auth_config_rejects_bad_headers_tokens_and_paths() -> None:
    with pytest.raises(ValidationError, match="valid HTTP field name"):
        AppTokenConfig(header_name="Bad Header")
    with pytest.raises(ValidationError, match="cannot be empty"):
        AppTokenConfig(tokens={"worker": " "})
    with pytest.raises(ValidationError, match="must be unique"):
        AppTokenConfig(tokens={"one": "same", "two": "same"})
    with pytest.raises(ValidationError, match="begin with"):
        AppTokenConfig(exclude_paths={"health"})


def test_openapi_auth_scheme_can_be_added_after_openapi_was_generated() -> None:
    app = FastAPI()
    app.openapi()
    add_api_key_security_scheme(app, "X-Token")
    schema = app.openapi()
    assert schema["components"]["securitySchemes"]["APIKeyHeader"]["name"] == "X-Token"
    assert {"APIKeyHeader": []} in schema["security"]


def test_health_endpoint_runs_sync_async_checks_and_sanitizes_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = FastAPI()
    health = HealthCheck(path="/healthz")
    caller_thread: list[int] = []
    executor_calls: list[object] = []

    async def run_sync_inline(
        _loop: asyncio.AbstractEventLoop,
        executor: object,
        function: Any,
        *args: object,
    ) -> Any:
        executor_calls.append(executor)
        return function(*args)

    monkeypatch.setattr(asyncio.BaseEventLoop, "run_in_executor", run_sync_inline)

    def check_sync() -> dict[str, object]:
        caller_thread.append(threading.get_ident())
        return {"status": "connected", "count": 3}

    async def check_async() -> dict[str, str]:
        await asyncio.sleep(0)
        return {"status": "ok"}

    def check_failure() -> dict[str, str]:
        raise RuntimeError("private database password")

    health.add_check("database", check_sync)
    health.add_check("cache", check_async)
    health.add_check("private", check_failure)
    health.add_to_app(app, include_in_schema=True)

    response = request(app, "GET", "/healthz")

    assert response.status_code == 200
    assert response.json() == {
        "status": "unhealthy",
        "details": {
            "database": {"status": "connected", "count": 3},
            "cache": {"status": "ok"},
            "private": {"status": "error", "error": "RuntimeError"},
        },
    }
    assert caller_thread == [threading.get_ident()]
    assert executor_calls == [None, None]
    assert any(getattr(route, "path", None) == "/healthz" for route in app.routes)
    assert HealthResponse(status="healthy").details == {}


def test_health_check_validation_and_factory() -> None:
    app = FastAPI()
    with pytest.raises(ValueError, match="begin with"):
        HealthCheck(path="health")

    async def check_database() -> dict[str, str]:
        return {"status": "down"}

    health = create_health_endpoint(
        app,
        checks=[("database", check_database)],
    )
    with pytest.raises(ValueError, match="already registered"):
        health.add_to_app(app)
    with pytest.raises(ValueError, match="cannot be empty"):
        health.add_check(" ", lambda: {})
    with pytest.raises(ValueError, match="already registered"):
        health.add_check("database", lambda: {})
    with pytest.raises(TypeError, match="must be callable"):
        health.add_check("not-callable", None)  # type: ignore[arg-type]

    response = request(app, "GET", "/health")
    assert response.json()["status"] == "unhealthy"


def test_logging_middleware_adds_timing_header_and_structured_fields(caplog) -> None:
    app = FastAPI()
    app.add_middleware(LoggingMiddleware, include_client=False)

    @app.get("/items")
    async def list_items() -> dict[str, list[int]]:
        return {"items": [1, 2]}

    with caplog.at_level(logging.INFO, logger="std.fastapi.logging.middleware"):
        response = request(app, "GET", "/items")

    assert response.status_code == 200
    assert response.headers["X-Process-Time"].endswith("ms")
    records = [
        record for record in caplog.records if record.name == "std.fastapi.logging.middleware"
    ]
    assert any(getattr(record, "http.method", None) == "GET" for record in records)
    assert any(getattr(record, "http.status_code", None) == 200 for record in records)


def test_logging_middleware_logs_and_reraises_request_errors(caplog) -> None:
    app = FastAPI()
    app.add_middleware(LoggingMiddleware, include_client=False)

    @app.get("/fail")
    async def fail() -> None:
        raise RuntimeError("endpoint failed")

    with (
        caplog.at_level(logging.ERROR, logger="std.fastapi.logging.middleware"),
        pytest.raises(RuntimeError, match="endpoint failed"),
    ):
        request(app, "GET", "/fail")

    assert any(record.message == "HTTP request failed" for record in caplog.records)


def test_dependency_helper_returns_auth_identity_and_exclusion() -> None:
    app = FastAPI()
    dependency = setup_token_auth(
        app,
        AppTokenConfig(tokens={"worker": "token"}, exclude_paths={"/open"}),
    )

    @app.get("/who")
    async def who(app_name: str | None = Depends(dependency)) -> dict[str, str | None]:
        return {"app": app_name}

    @app.get("/open")
    async def open_route(app_name: str | None = Depends(dependency)) -> dict[str, str | None]:
        return {"app": app_name}

    assert request(app, "GET", "/who", headers={"X-App-Token": "token"}).json() == {"app": "worker"}
    assert request(app, "GET", "/open").json() == {"app": None}
