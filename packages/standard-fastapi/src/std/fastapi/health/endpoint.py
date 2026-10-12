"""Register a health endpoint backed by synchronous or asynchronous checks."""

from __future__ import annotations

import asyncio
import inspect
import logging
from collections.abc import Awaitable, Callable, Mapping
from typing import Any, cast

from pydantic import BaseModel, ConfigDict, Field

from fastapi import FastAPI

logger = logging.getLogger(__name__)
HealthCheckFunc = Callable[[], Any | Awaitable[Any]]


class HealthResponse(BaseModel):
    """JSON response containing the overall state and individual check values."""

    model_config = ConfigDict(extra="forbid")

    status: str = "healthy"
    details: dict[str, Any] = Field(default_factory=dict)


class HealthCheck:
    """Collect named checks and expose their aggregate result as an endpoint."""

    def __init__(self, app: FastAPI | None = None, path: str = "/health") -> None:
        """Create a health endpoint, optionally registering it on an app."""
        if not path.startswith("/"):
            raise ValueError("health endpoint path must begin with '/'")
        self.path = path
        self._checks: list[tuple[str, HealthCheckFunc]] = []
        self._registered_apps: set[int] = set()
        if app is not None:
            self.add_to_app(app)

    @property
    def checks(self) -> tuple[tuple[str, HealthCheckFunc], ...]:
        """Return the registered checks in execution order."""
        return tuple(self._checks)

    def add_check(self, name: str, check_func: HealthCheckFunc) -> None:
        """Register a named synchronous or asynchronous health check."""
        normalized_name = name.strip()
        if not normalized_name:
            raise ValueError("health check name cannot be empty")
        if not callable(check_func):
            raise TypeError("check_func must be callable")
        if any(existing == normalized_name for existing, _ in self._checks):
            raise ValueError(f"health check {normalized_name!r} is already registered")
        self._checks.append((normalized_name, check_func))

    def add_to_app(self, app: FastAPI, include_in_schema: bool = False) -> None:
        """Register the health route on an app once."""
        app_identity = id(app)
        if app_identity in self._registered_apps:
            raise ValueError("health endpoint is already registered on this app")
        self._registered_apps.add(app_identity)

        @app.get(
            self.path,
            response_model=HealthResponse,
            include_in_schema=include_in_schema,
            tags=["health"],
        )
        async def health_check() -> HealthResponse:
            details: dict[str, Any] = {}
            healthy = True
            for name, check_func in self._checks:
                try:
                    result = await self._execute(check_func)
                except Exception as error:
                    logger.warning("Health check %s failed (%s)", name, type(error).__name__)
                    result = {"status": "error", "error": type(error).__name__}
                details[name] = result
                if self._is_unhealthy(result):
                    healthy = False
            return HealthResponse(status="healthy" if healthy else "unhealthy", details=details)

    async def _execute(self, check_func: HealthCheckFunc) -> Any:
        if inspect.iscoroutinefunction(check_func):
            result = check_func()
        else:
            sync_check = cast(Callable[[], Any], check_func)
            result = await asyncio.get_running_loop().run_in_executor(None, sync_check)
        if inspect.isawaitable(result):
            return await result
        return result

    @staticmethod
    def _is_unhealthy(result: Any) -> bool:
        if result is False:
            return True
        if isinstance(result, Mapping):
            status = result.get("status")
            return isinstance(status, str) and status.casefold() in {
                "error",
                "unhealthy",
                "down",
            }
        return False


def create_health_endpoint(
    app: FastAPI,
    path: str = "/health",
    include_in_schema: bool = False,
    checks: list[tuple[str, HealthCheckFunc]] | None = None,
) -> HealthCheck:
    """Create a health manager, register initial checks, and attach its route."""
    health = HealthCheck(path=path)
    for name, check_func in checks or []:
        health.add_check(name, check_func)
    health.add_to_app(app, include_in_schema=include_in_schema)
    return health


__all__ = ["HealthCheck", "HealthCheckFunc", "HealthResponse", "create_health_endpoint"]
