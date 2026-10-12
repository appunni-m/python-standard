"""ASGI integration tests for the example application factory."""

import asyncio

import pytest
from httpx import ASGITransport, AsyncClient, Response

from example_app.main import create_app


def test_health_route_uses_yaml_environment_placeholder(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_NAME", "Test API")
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("HEARTBEAT_ENABLED", "false")

    async def request_health() -> Response:
        app = create_app()
        async with (
            app.router.lifespan_context(app),
            AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
            ) as client,
        ):
            return await client.get("/health")

    response = asyncio.run(request_health())

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "application": "Test API"}
