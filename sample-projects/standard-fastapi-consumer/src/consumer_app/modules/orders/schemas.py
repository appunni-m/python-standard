"""Request and response models for the order HTTP boundary."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from consumer_app.modules.orders.models import Order, OrderStatus


class CreateOrderRequest(BaseModel):
    """Validated data required to create an order."""

    customer_reference: str = Field(min_length=1, max_length=80)
    amount_cents: int = Field(gt=0)


class OrderResponse(BaseModel):
    """Public representation of an order."""

    id: UUID
    customer_reference: str
    amount_cents: int
    currency: str
    status: OrderStatus
    created_at: datetime

    @classmethod
    def from_order(cls, order: Order) -> OrderResponse:
        """Translate the feature's domain model into its API response model."""
        return cls(
            id=order.id,
            customer_reference=order.customer_reference,
            amount_cents=order.amount_cents,
            currency=order.currency,
            status=order.status,
            created_at=order.created_at,
        )
