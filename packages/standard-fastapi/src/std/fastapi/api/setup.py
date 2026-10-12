"""Compose a FastAPI application from explicit configuration and services."""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping, Sequence

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from std.fastapi.api.config import APIConfig, Environment
from std.fastapi.api.lifecycle import LifecycleManager
from std.logging import LoggingConfig, configure_logging
from std.service import BackgroundServiceProtocol


class FastAPISetup:
    """Build a FastAPI app with metadata, CORS, logging, and service lifespan."""

    def __init__(
        self,
        api_config: APIConfig,
        log_config: LoggingConfig | Mapping[str, object] | None = None,
        setup_handler: Callable[[], Awaitable[Sequence[BackgroundServiceProtocol]]] | None = None,
        *,
        services: Sequence[BackgroundServiceProtocol] = (),
    ) -> None:
        """Store application settings and constructed background services."""
        self.api_config = api_config
        self.log_config = log_config
        self.lifecycle_manager = LifecycleManager(services, setup_handler=setup_handler)

    def create_fastapi_app(self) -> FastAPI:
        """Create a configured FastAPI instance with injected service lifespan."""
        if self.log_config is not None:
            environment = {
                Environment.DEV: "development",
                Environment.STAGE: "staging",
                Environment.PROD: "production",
            }[self.api_config.env]
            configure_logging(self.log_config, environment=environment)

        app = FastAPI(
            title=self.api_config.title,
            description=self.api_config.description,
            version=self.api_config.version,
            debug=self.api_config.debug,
            lifespan=self.lifecycle_manager.fastapi_lifespan(),
        )
        app.add_middleware(
            CORSMiddleware,
            allow_origins=self.api_config.cors_origins,
            allow_credentials=self.api_config.cors_credentials,
            allow_methods=self.api_config.cors_methods,
            allow_headers=self.api_config.cors_headers,
        )
        return app
