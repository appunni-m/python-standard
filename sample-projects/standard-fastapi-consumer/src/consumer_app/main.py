"""Composition root for settings, logging, services, and ASGI routes."""

import asyncio
from uuid import UUID

import uvicorn
from fastapi import FastAPI
from std.fastapi import (
    APIConfig,
    Environment,
    FastAPISetup,
    LoggingMiddleware,
    create_health_endpoint,
    settings_dependency,
)
from std.logging import LoggingEnvironment, configure_logging

from consumer_app.core.settings import Settings
from consumer_app.modules.application.api.routes import create_router as create_application_router
from consumer_app.modules.application.config import ApplicationSettings
from consumer_app.modules.orders.api.routes import create_router as create_orders_router
from consumer_app.modules.orders.repository import InMemoryOrderRepository
from consumer_app.modules.orders.service import OrderService
from consumer_app.modules.orders.worker import OrderProcessingWorker


def _api_environment(environment: LoggingEnvironment) -> Environment:
    """Map logging profiles to the FastAPI integration's deployment enum."""
    if environment in (LoggingEnvironment.DEVELOPMENT, LoggingEnvironment.TEST):
        return Environment.DEV
    if environment is LoggingEnvironment.STAGING:
        return Environment.STAGE
    return Environment.PROD


def _create_app(settings: Settings) -> FastAPI:
    """Assemble one app from already-validated settings and constructed services."""
    application: ApplicationSettings = settings.application
    configure_logging(
        settings.logging,
        environment=application.environment,
        service_name=application.name,
    )

    repository = InMemoryOrderRepository()
    pending_orders: asyncio.Queue[UUID] = asyncio.Queue()
    order_service = OrderService(repository, pending_orders, settings.orders)
    worker = OrderProcessingWorker(pending_orders, repository)
    setup = FastAPISetup(
        APIConfig(
            title=application.name,
            description="An order API demonstrating Standard's application patterns.",
            version="1.0.0",
            env=_api_environment(application.environment),
            host=application.host,
            port=application.port,
            debug=application.debug,
            reload=False,
        ),
        services=(worker,),
    )
    app = setup.create_fastapi_app()
    app.state.settings = settings
    app.state.order_worker = worker
    app.state.pending_orders = pending_orders
    app.add_middleware(LoggingMiddleware, include_client=False)
    app.include_router(create_application_router(settings_dependency(Settings)))
    app.include_router(create_orders_router(order_service))
    create_health_endpoint(app, checks=[("orders", order_service.health_check)])
    return app


def create_app(settings: Settings | None = None) -> FastAPI:
    """Create the ASGI application, loading settings only at this composition root."""
    if settings is None:
        # YAML supplies validated settings fields; Pydantic's generated signature cannot see them.
        settings = Settings()  # type: ignore[call-arg]
    return _create_app(settings)


def main() -> None:
    """Start the sample API with the host and port from its YAML-backed settings."""
    settings = Settings()  # type: ignore[call-arg]  # YAML supplies these validated values.
    app = _create_app(settings)
    uvicorn.run(app, host=settings.application.host, port=settings.application.port)
