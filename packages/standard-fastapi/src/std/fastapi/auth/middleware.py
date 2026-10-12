"""API-token dependency, middleware, and OpenAPI security helpers."""

import hmac
from collections.abc import Awaitable, Callable
from fnmatch import fnmatchcase
from typing import Any

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.types import ASGIApp

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from std.fastapi.auth.config import AppTokenConfig

MissingTokenHandler = Callable[[Request], Awaitable[Response]]
InvalidTokenHandler = Callable[[Request, str], Awaitable[Response]]


class AppTokenAuth:
    """Authenticate requests from one configured header and return the app ID."""

    def __init__(self, settings: AppTokenConfig | None = None) -> None:
        """Use the supplied configuration or the secure default configuration."""
        self.settings = settings or AppTokenConfig()

    async def __call__(self, request: Request) -> str | None:
        """Return the matching app name or raise a 401 for a protected path."""
        if not self.settings.enabled or self.is_path_excluded(request.url.path):
            return None
        token = request.headers.get(self.settings.header_name)
        if token is None:
            raise HTTPException(status_code=401, detail="Missing authentication token")
        app_name = self.get_app_name(token)
        if app_name is None:
            raise HTTPException(status_code=401, detail="Invalid authentication token")
        return app_name

    def is_path_excluded(self, path: str) -> bool:
        """Return whether a path matches an exact or shell-style exclusion."""
        return any(fnmatchcase(path, pattern) for pattern in self.settings.exclude_paths)

    def get_app_name(self, token: str) -> str | None:
        """Return the identity associated with a token using constant-time checks."""
        supplied = token.encode("utf-8")
        matched_app: str | None = None
        for app_name, accepted in self.settings.tokens.items():
            if hmac.compare_digest(supplied, accepted.encode("utf-8")):
                matched_app = app_name
        return matched_app


class TokenAuthMiddleware(BaseHTTPMiddleware):
    """Require a configured API token for every non-excluded request."""

    def __init__(
        self,
        app: ASGIApp,
        settings: AppTokenConfig | None = None,
        on_missing_token: MissingTokenHandler | None = None,
        on_invalid_token: InvalidTokenHandler | None = None,
    ) -> None:
        """Store authentication settings and optional async response handlers."""
        super().__init__(app)
        self.auth = AppTokenAuth(settings)
        self.on_missing_token = on_missing_token
        self.on_invalid_token = on_invalid_token

    async def dispatch(
        self,
        request: Request,
        call_next: RequestResponseEndpoint,
    ) -> Response:
        """Validate credentials, set request identity, then continue the request."""
        settings = self.auth.settings
        if not settings.enabled or self.auth.is_path_excluded(request.url.path):
            return await call_next(request)

        token = request.headers.get(settings.header_name)
        if token is None:
            if self.on_missing_token is not None:
                return await self.on_missing_token(request)
            return JSONResponse({"error": "Missing authentication token"}, status_code=401)

        app_name = self.auth.get_app_name(token)
        if app_name is None:
            if self.on_invalid_token is not None:
                return await self.on_invalid_token(request, token)
            return JSONResponse({"error": "Invalid authentication token"}, status_code=401)

        request.state.app_name = app_name
        return await call_next(request)


def add_api_key_security_scheme(
    app: FastAPI,
    header_name: str,
    enabled: bool = True,
) -> None:
    """Add an API-key scheme and global security requirement to generated OpenAPI."""
    if not enabled:
        return

    original_openapi = app.openapi

    def openapi_with_api_key() -> dict[str, Any]:
        schema = original_openapi()
        components = schema.get("components")
        if not isinstance(components, dict):
            components = {}
            schema["components"] = components
        schemes = components.setdefault("securitySchemes", {})
        schemes["APIKeyHeader"] = {"type": "apiKey", "in": "header", "name": header_name}
        requirement: dict[str, list[str]] = {"APIKeyHeader": []}
        security = schema.get("security")
        if not isinstance(security, list):
            security = []
            schema["security"] = security
        if requirement not in security:
            security.append(requirement)
        app.openapi_schema = schema
        return schema

    # FastAPI has no setter for this override; direct assignment fails strict mypy.
    setattr(app, "openapi", openapi_with_api_key)  # noqa: B010
    if app.openapi_schema is not None:
        openapi_with_api_key()


def setup_token_auth(
    app: FastAPI,
    settings: AppTokenConfig | None = None,
) -> AppTokenAuth:
    """Register the OpenAPI security scheme and return a dependency handler."""
    config = settings or AppTokenConfig()
    add_api_key_security_scheme(app, config.header_name, config.enabled)
    return AppTokenAuth(config)


def apply_token_auth_middleware(
    app: FastAPI,
    settings: AppTokenConfig | None = None,
    on_missing_token: MissingTokenHandler | None = None,
    on_invalid_token: InvalidTokenHandler | None = None,
) -> None:
    """Install token authentication middleware and document its header scheme."""
    config = settings or AppTokenConfig()
    add_api_key_security_scheme(app, config.header_name, config.enabled)
    app.add_middleware(
        TokenAuthMiddleware,
        settings=config,
        on_missing_token=on_missing_token,
        on_invalid_token=on_invalid_token,
    )


setup_app_token_auth = setup_token_auth

__all__ = [
    "AppTokenAuth",
    "TokenAuthMiddleware",
    "add_api_key_security_scheme",
    "apply_token_auth_middleware",
    "setup_app_token_auth",
    "setup_token_auth",
]
