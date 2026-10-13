"""Focused tests for the order application workflow."""

import asyncio
from uuid import UUID

import pytest

from consumer_app.modules.orders.config import OrdersSettings
from consumer_app.modules.orders.models import Order
from consumer_app.modules.orders.repository import InMemoryOrderRepository
from consumer_app.modules.orders.service import MaximumOrderAmountExceeded, OrderService


def test_create_order_persists_and_enqueues_work() -> None:
    """Creating a valid order stores it and emits its ID for a worker."""
    repository = InMemoryOrderRepository()
    pending_orders: asyncio.Queue[UUID] = asyncio.Queue()
    service = OrderService(repository, pending_orders, OrdersSettings(maximum_amount_cents=10_000))

    async def create() -> tuple[Order, UUID]:
        order = await service.create_order("customer-42", 2_500)
        queued_id = await pending_orders.get()
        pending_orders.task_done()
        return order, queued_id

    order, queued_id = asyncio.run(create())

    assert order.id == queued_id
    assert repository.get(order.id) == order
    assert order.currency == "USD"


def test_create_order_rejects_amount_above_feature_limit() -> None:
    """The service enforces the feature limit before writing or enqueueing."""
    repository = InMemoryOrderRepository()
    pending_orders: asyncio.Queue[UUID] = asyncio.Queue()
    service = OrderService(repository, pending_orders, OrdersSettings(maximum_amount_cents=100))

    async def create() -> None:
        await service.create_order("customer-42", 101)

    with pytest.raises(MaximumOrderAmountExceeded):
        asyncio.run(create())

    assert repository.list_all() == []
    assert pending_orders.empty()
