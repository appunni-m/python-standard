"""Thin HTTP routes for the orders feature."""

from uuid import UUID

from fastapi import APIRouter, HTTPException, status

from consumer_app.modules.orders.schemas import CreateOrderRequest, OrderResponse
from consumer_app.modules.orders.service import MaximumOrderAmountExceeded, OrderService


def create_router(service: OrderService) -> APIRouter:
    """Build order routes around an explicitly injected application service."""
    router = APIRouter(prefix="/api/v1/orders", tags=["orders"])

    @router.post("", response_model=OrderResponse, status_code=status.HTTP_201_CREATED)
    async def create_order(payload: CreateOrderRequest) -> OrderResponse:
        """Accept a new order or map the expected business limit error."""
        try:
            order = await service.create_order(payload.customer_reference, payload.amount_cents)
        except MaximumOrderAmountExceeded as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
        return OrderResponse.from_order(order)

    @router.get("", response_model=list[OrderResponse])
    async def list_orders() -> list[OrderResponse]:
        """Return accepted orders without reaching into persistence directly."""
        return [OrderResponse.from_order(order) for order in service.list_orders()]

    @router.get("/{order_id}", response_model=OrderResponse)
    async def get_order(order_id: UUID) -> OrderResponse:
        """Return one order or a not-found response."""
        order = service.get_order(order_id)
        if order is None:
            raise HTTPException(status_code=404, detail="Order not found")
        return OrderResponse.from_order(order)

    return router
