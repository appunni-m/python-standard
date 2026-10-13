"""Application workflow for accepting and querying orders."""

import asyncio
import logging
from datetime import UTC, datetime
from uuid import UUID, uuid4

from consumer_app.modules.orders.config import OrdersSettings
from consumer_app.modules.orders.models import Order, OrderStatus
from consumer_app.modules.orders.repository import OrderRepository

logger = logging.getLogger(__name__)


class MaximumOrderAmountExceeded(ValueError):
    """Raised when an order exceeds the configured amount limit."""


class OrderService:
    """Coordinate order validation, persistence, and background work enqueueing."""

    def __init__(
        self,
        repository: OrderRepository,
        pending_orders: asyncio.Queue[UUID],
        settings: OrdersSettings,
    ) -> None:
        """Receive persistence, queue, and feature settings through injection."""
        self._repository = repository
        self._pending_orders = pending_orders
        self._settings = settings

    async def create_order(self, customer_reference: str, amount_cents: int) -> Order:
        """Validate, store, and enqueue one order for background processing."""
        if amount_cents > self._settings.maximum_amount_cents:
            raise MaximumOrderAmountExceeded(
                f"amount exceeds the configured maximum of "
                f"{self._settings.maximum_amount_cents} cents"
            )

        order = Order(
            id=uuid4(),
            customer_reference=customer_reference,
            amount_cents=amount_cents,
            currency=self._settings.currency,
            status=OrderStatus.QUEUED,
            created_at=datetime.now(UTC),
        )
        self._repository.add(order)
        await self._pending_orders.put(order.id)
        logger.info("Order accepted", extra={"order.id": str(order.id)})
        return order

    def get_order(self, order_id: UUID) -> Order | None:
        """Return an order when it exists."""
        return self._repository.get(order_id)

    def list_orders(self) -> list[Order]:
        """Return all accepted orders in creation order."""
        return self._repository.list_all()

    async def health_check(self) -> dict[str, str]:
        """Report that the sample's in-memory order store is reachable."""
        return {"status": "healthy", "store": "in-memory"}
