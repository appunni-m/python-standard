"""Thin HTTP routes that delegate application behavior to injected services."""

from fastapi import APIRouter

from example_app.modules.health.schemas import HealthResponse
from example_app.modules.health.service import HealthService


def create_router(health_service: HealthService) -> APIRouter:
    """Create API routes using dependencies assembled by the application root."""
    router = APIRouter()

    @router.get("/health", response_model=HealthResponse)
    async def get_health() -> HealthResponse:
        """Return the health service's status document."""
        result = health_service.check()
        return HealthResponse(status=result.status, application=result.application)

    return router
