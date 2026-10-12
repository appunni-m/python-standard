"""Application composition root and ASGI application factory."""

from fastapi import FastAPI
from std.logging import configure_logging

from example_app.core.services import BackgroundService
from example_app.core.settings import Settings
from example_app.lifecycle import create_lifespan
from example_app.modules.health.api.routes import create_router as create_health_router
from example_app.modules.health.service import HealthService
from example_app.modules.heartbeat.service import HeartbeatService


def create_app() -> FastAPI:
    """Build one application instance and its shared dependencies."""
    settings = Settings()  # type: ignore[call-arg]  # YAML provides the validated field values.
    configure_logging(
        settings.logging,
        environment=settings.application.environment,
        service_name=settings.application.name,
    )

    health_service = HealthService(application_name=settings.application.name)
    background_services: list[BackgroundService] = []
    if settings.heartbeat.enabled:
        background_services.append(
            HeartbeatService(
                application_name=settings.application.name,
                interval_seconds=settings.heartbeat.interval_seconds,
            )
        )

    app = FastAPI(
        title=settings.application.name,
        lifespan=create_lifespan(background_services),
    )
    app.include_router(create_health_router(health_service))
    return app
