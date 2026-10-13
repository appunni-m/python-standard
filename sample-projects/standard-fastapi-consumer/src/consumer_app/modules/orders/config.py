"""Order-specific configuration owned by the orders feature."""

from pydantic import BaseModel, Field


class OrdersSettings(BaseModel):
    """Currency and amount limit applied by the order workflow."""

    currency: str = Field(default="USD", min_length=3, max_length=3, pattern="^[A-Z]{3}$")
    maximum_amount_cents: int = Field(default=250_000, gt=0)
