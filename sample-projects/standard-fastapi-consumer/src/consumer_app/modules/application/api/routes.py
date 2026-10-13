"""Routes exposing runtime application metadata."""

from typing import Annotated

from fastapi import APIRouter
from fastapi.params import Depends as DependsType

from consumer_app.core.settings import Settings


def create_router(settings_dependency: DependsType) -> APIRouter:
    """Build application routes that read the composition-root settings instance."""
    router = APIRouter(tags=["application"])

    @router.get("/metadata")
    async def metadata(
        settings: Annotated[Settings, settings_dependency],
    ) -> dict[str, str]:
        """Return non-secret application identity and environment metadata."""
        return {
            "name": settings.application.name,
            "environment": settings.application.environment.value,
        }

    return router
