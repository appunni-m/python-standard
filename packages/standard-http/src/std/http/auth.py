"""Authentication handlers compatible with the Standard HTTP client."""

from __future__ import annotations

import base64

import httpx


class AuthBase:
    """Base class for simple request-header authentication handlers."""

    def auth_flow(self, request: httpx.Request) -> httpx.Request:
        """Return the request unchanged; subclasses can add authentication headers."""
        return request


class BearerAuth(AuthBase):
    """Add a bearer token to the ``Authorization`` request header."""

    __slots__ = ("token",)

    def __init__(self, token: str) -> None:
        """Create bearer auth without including the secret in object representations."""
        if not isinstance(token, str) or not token.strip():
            raise ValueError("bearer token must be a non-empty string")
        self.token = token

    def auth_flow(self, request: httpx.Request) -> httpx.Request:
        """Set the bearer authorization header on a request."""
        request.headers["Authorization"] = f"Bearer {self.token}"
        return request

    def __repr__(self) -> str:
        """Return a representation that does not disclose the bearer token."""
        return "BearerAuth(token=[redacted])"


class BasicAuth(AuthBase):
    """Add HTTP Basic authentication using UTF-8 encoded credentials."""

    __slots__ = ("username", "password")

    def __init__(self, username: str, password: str) -> None:
        """Create Basic auth without exposing credentials in object representations."""
        if not isinstance(username, str) or not isinstance(password, str):
            raise TypeError("username and password must be strings")
        self.username = username
        self.password = password

    def auth_flow(self, request: httpx.Request) -> httpx.Request:
        """Set the Basic authorization header on a request."""
        credentials = f"{self.username}:{self.password}".encode()
        encoded = base64.b64encode(credentials).decode("ascii")
        request.headers["Authorization"] = f"Basic {encoded}"
        return request

    def __repr__(self) -> str:
        """Return a representation that does not disclose either credential."""
        return "BasicAuth(username=[redacted], password=[redacted])"


class ApiKeyAuth(AuthBase):
    """Add an API key to a configurable header, optionally with a prefix."""

    __slots__ = ("api_key", "header_name", "prefix")

    def __init__(
        self,
        api_key: str,
        header_name: str = "X-API-Key",
        prefix: str | None = None,
    ) -> None:
        """Create API-key auth with a custom header and optional value prefix."""
        if not isinstance(api_key, str) or not api_key.strip():
            raise ValueError("API key must be a non-empty string")
        if not isinstance(header_name, str) or not header_name.strip():
            raise ValueError("header name must be a non-empty string")
        if prefix is not None and not isinstance(prefix, str):
            raise TypeError("prefix must be a string or None")
        self.api_key = api_key
        self.header_name = header_name
        self.prefix = prefix

    def auth_flow(self, request: httpx.Request) -> httpx.Request:
        """Set the API-key header on a request."""
        value = f"{self.prefix} {self.api_key}" if self.prefix else self.api_key
        request.headers[self.header_name] = value
        return request

    def __repr__(self) -> str:
        """Return a representation that does not disclose the API key."""
        return (
            "ApiKeyAuth(api_key=[redacted], "
            f"header_name={self.header_name!r}, prefix={self.prefix!r})"
        )
