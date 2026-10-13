"""ASGI integration checks for configuration, routes, logging, and lifecycle."""

import asyncio
import logging

import pytest
from httpx import ASGITransport, AsyncClient, Response
from std.service import ServiceState

from consumer_app.main import create_app


def test_order_api_uses_yaml_placeholders_and_managed_worker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Exercise the real ASGI lifespan and the order-processing workflow."""
    monkeypatch.setenv("APP_NAME", "Sample Store")
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("APPLICATION__NAME", "This direct Pydantic environment path is ignored")

    app = create_app()

    async def exercise() -> tuple[
        Response,
        Response,
        Response,
        ServiceState,
        ServiceState,
        Response,
    ]:
        async with app.router.lifespan_context(app):
            running_state = app.state.order_worker.state
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
            ) as client:
                metadata = await client.get("/metadata")
                created = await client.post(
                    "/api/v1/orders",
                    json={"customer_reference": "customer-42", "amount_cents": 2_500},
                )
                order = created.json()
                await asyncio.wait_for(app.state.pending_orders.join(), timeout=1)
                fetched = await client.get(f"/api/v1/orders/{order['id']}")
                health = await client.get("/health")
        stopped_state = app.state.order_worker.state
        return metadata, created, fetched, running_state, stopped_state, health

    metadata, created, fetched, running_state, stopped_state, health = asyncio.run(exercise())

    assert metadata.status_code == 200
    assert metadata.json() == {"name": "Sample Store", "environment": "test"}
    assert created.status_code == 201
    assert created.headers["x-process-time"].endswith("ms")
    assert fetched.status_code == 200
    assert fetched.json()["status"] == "processed"
    assert health.status_code == 200
    assert health.json() == {
        "status": "healthy",
        "details": {"orders": {"status": "healthy", "store": "in-memory"}},
    }
    assert running_state is ServiceState.RUNNING
    assert stopped_state is ServiceState.STOPPED
    assert logging.getLogger().level == logging.WARNING


def test_create_order_maps_expected_business_error_to_422(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The HTTP boundary translates the configured order limit into a client error."""
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("ORDERS_MAXIMUM_AMOUNT_CENTS", "100")
    app = create_app()

    async def request_limit_error() -> Response:
        async with (
            app.router.lifespan_context(app),
            AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
            ) as client,
        ):
            return await client.post(
                "/api/v1/orders",
                json={"customer_reference": "customer-42", "amount_cents": 101},
            )

    response = asyncio.run(request_limit_error())

    assert response.status_code == 422
    assert response.json()["detail"] == "amount exceeds the configured maximum of 100 cents"
