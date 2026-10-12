"""FastAPI application, authentication, health, lifecycle, and logging tools."""

try:
    import fastapi as _fastapi  # noqa: F401
except ImportError as error:  # pragma: no cover - broken optional installation
    raise ImportError(
        "FastAPI integration requires the FastAPI dependency; install "
        "`standard-fastapi` or `standard[fastapi]`. From a checkout run "
        "`python -m pip install -e . -e packages/standard-fastapi`."
    ) from error

from std.fastapi.api import APIConfig, APIService, Environment, FastAPISetup, LifecycleManager
from std.fastapi.auth import (
    AppTokenAuth,
    AppTokenConfig,
    TokenAuthMiddleware,
    add_api_key_security_scheme,
    apply_token_auth_middleware,
    setup_app_token_auth,
    setup_token_auth,
)
from std.fastapi.dependencies import settings_dependency
from std.fastapi.health import (
    HealthCheck,
    HealthCheckFunc,
    HealthResponse,
    create_health_endpoint,
)
from std.fastapi.logging import LoggingMiddleware

__all__ = [
    "APIConfig",
    "APIService",
    "AppTokenAuth",
    "AppTokenConfig",
    "Environment",
    "FastAPISetup",
    "HealthCheck",
    "HealthCheckFunc",
    "HealthResponse",
    "LifecycleManager",
    "LoggingMiddleware",
    "TokenAuthMiddleware",
    "add_api_key_security_scheme",
    "apply_token_auth_middleware",
    "create_health_endpoint",
    "settings_dependency",
    "setup_app_token_auth",
    "setup_token_auth",
]
