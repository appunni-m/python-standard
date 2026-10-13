"""Managed background worker for order processing events."""

import asyncio
import logging
from uuid import UUID

from std.service import BackgroundService

from consumer_app.modules.orders.repository import OrderRepository

logger = logging.getLogger(__name__)


class OrderProcessingWorker(BackgroundService):
    """Consume queued order identifiers until application shutdown."""

    def __init__(
        self,
        pending_orders: asyncio.Queue[UUID],
        repository: OrderRepository,
    ) -> None:
        """Receive the queue and repository constructed by the composition root."""
        super().__init__(name="order-processing-worker", shutdown_timeout=2.0)
        self._pending_orders = pending_orders
        self._repository = repository

    async def run(self) -> None:
        """Mark queued orders processed and exit promptly when stopped."""
        while not self.stop_event.is_set():
            try:
                order_id = await asyncio.wait_for(self._pending_orders.get(), timeout=0.1)
            except TimeoutError:
                continue

            try:
                self._repository.mark_processed(order_id)
                logger.info("Order processed", extra={"order.id": str(order_id)})
            finally:
                self._pending_orders.task_done()
