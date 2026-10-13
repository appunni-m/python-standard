"""Order persistence boundary and in-memory sample implementation."""

from dataclasses import replace
from typing import Protocol
from uuid import UUID

from consumer_app.modules.orders.models import Order, OrderStatus


class OrderRepository(Protocol):
    """Operations the order workflow needs from its persistence boundary."""

    def add(self, order: Order) -> None:
        """Persist a newly accepted order."""

    def get(self, order_id: UUID) -> Order | None:
        """Return an order by identifier when it exists."""

    def list_all(self) -> list[Order]:
        """Return orders in creation order."""

    def mark_processed(self, order_id: UUID) -> None:
        """Mark a queued order as processed by the background worker."""


class InMemoryOrderRepository:
    """Small process-local repository used to keep the sample self-contained."""

    def __init__(self) -> None:
        """Create an empty order collection."""
        self._orders: dict[UUID, Order] = {}

    def add(self, order: Order) -> None:
        """Store an order without mutating the caller's domain object."""
        self._orders[order.id] = order

    def get(self, order_id: UUID) -> Order | None:
        """Look up one order by its unique identifier."""
        return self._orders.get(order_id)

    def list_all(self) -> list[Order]:
        """Return a snapshot of orders in insertion order."""
        return list(self._orders.values())

    def mark_processed(self, order_id: UUID) -> None:
        """Replace the stored immutable order with its processed state."""
        order = self._orders[order_id]
        self._orders[order_id] = replace(order, status=OrderStatus.PROCESSED)
