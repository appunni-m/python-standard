"""Header token authentication for FastAPI dependencies and middleware."""

from std.fastapi.auth.config import AppTokenConfig
from std.fastapi.auth.middleware import (
    AppTokenAuth,
    TokenAuthMiddleware,
    add_api_key_security_scheme,
    apply_token_auth_middleware,
    setup_app_token_auth,
    setup_token_auth,
)

__all__ = [
    "AppTokenAuth",
    "AppTokenConfig",
    "TokenAuthMiddleware",
    "add_api_key_security_scheme",
    "apply_token_auth_middleware",
    "setup_app_token_auth",
    "setup_token_auth",
]
