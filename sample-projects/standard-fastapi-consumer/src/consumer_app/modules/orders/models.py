"""Domain model for an accepted customer order."""

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from uuid import UUID


class OrderStatus(StrEnum):
    """Processing states exposed by the order API."""

    QUEUED = "queued"
    PROCESSED = "processed"


@dataclass(frozen=True, slots=True)
class Order:
    """An accepted order awaiting or completing background processing."""

    id: UUID
    customer_reference: str
    amount_cents: int
    currency: str
    status: OrderStatus
    created_at: datetime
