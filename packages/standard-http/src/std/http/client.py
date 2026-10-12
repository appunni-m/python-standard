"""Async HTTP client with authentication, retries, and Pydantic response helpers."""

from __future__ import annotations

import asyncio
import logging
import math
import random
from collections.abc import Mapping, Sequence
from typing import Any, TypeVar

import httpx
from pydantic import BaseModel, ValidationError

from std.http.auth import ApiKeyAuth, AuthBase, BearerAuth
from std.http.config import AuthConfig, RetryConfig

ModelT = TypeVar("ModelT", bound=BaseModel)
_UNSET = object()
_logger = logging.getLogger(__name__)


class HttpClientError(Exception):
    """A sanitized HTTP client failure with optional status and response context."""

    def __init__(
        self,
        message: str,
        status_code: int | None = None,
        response: httpx.Response | None = None,
    ) -> None:
        """Create an error without rendering request URLs, headers, or exception text."""
        super().__init__(message)
        self.status_code = status_code
        self.response = response


class _LegacyAuth(httpx.Auth):
    """Adapt the historical one-request auth-flow contract to HTTPX auth."""

    def __init__(self, auth: AuthBase) -> None:
        self._auth = auth

    def auth_flow(self, request: httpx.Request) -> Any:
        yield self._auth.auth_flow(request)


class HttpClient:
    """Reusable asynchronous HTTP client with explicit retry and cleanup behavior.

    ``retries`` accepts the historical integer form, interpreted as total attempts.
    ``RetryConfig`` offers method, status, exception, backoff, and jitter controls.
    """

    def __init__(
        self,
        base_url: str = "",
        timeout: float | httpx.Timeout | None = 10.0,
        retries: int | RetryConfig | None = None,
        auth_config: AuthConfig | None = None,
        default_headers: Mapping[str, str] | None = None,
        verify_ssl: bool = True,
        follow_redirects: bool = True,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        """Configure an HTTP client; the underlying connection pool is created lazily."""
        if isinstance(retries, bool):
            raise TypeError("retries cannot be a boolean")
        if isinstance(retries, int):
            if retries < 0:
                raise ValueError("retries cannot be negative")
            self.retry_config = RetryConfig(max_attempts=max(1, retries))
        elif isinstance(retries, RetryConfig):
            self.retry_config = retries
        elif retries is None:
            self.retry_config = RetryConfig()
        else:
            raise TypeError("retries must be an integer, RetryConfig, or None")

        if timeout is not None and not isinstance(timeout, httpx.Timeout):
            if isinstance(timeout, bool) or not isinstance(timeout, (int, float)):
                raise TypeError("timeout must be a number, HTTPX Timeout, or None")
            if not math.isfinite(timeout) or timeout < 0:
                raise ValueError("timeout must be finite and non-negative")
            timeout = httpx.Timeout(float(timeout))
        if not isinstance(base_url, str):
            raise TypeError("base_url must be a string")
        if not isinstance(verify_ssl, bool) or not isinstance(follow_redirects, bool):
            raise TypeError("verify_ssl and follow_redirects must be booleans")

        self.base_url = base_url
        self.timeout = timeout
        self.auth_config = auth_config or AuthConfig()
        self.default_headers = dict(default_headers or {})
        self.verify_ssl = verify_ssl
        self.follow_redirects = follow_redirects
        self._transport = transport
        self._client: httpx.AsyncClient | None = None
        self._client_lock = asyncio.Lock()

    async def __aenter__(self) -> HttpClient:
        """Open the underlying HTTPX client and return this wrapper."""
        await self._ensure_client()
        return self

    async def __aexit__(self, exc_type: Any, exc_value: Any, traceback: Any) -> None:
        """Close the underlying connection pool when leaving an async context."""
        await self.close()

    @property
    async def client(self) -> httpx.AsyncClient:
        """Return the lazily created HTTPX client for advanced use."""
        return await self._ensure_client()

    async def _ensure_client(self) -> httpx.AsyncClient:
        """Create exactly one HTTPX client when concurrent requests start together."""
        if self._client is not None:
            return self._client
        async with self._client_lock:
            if self._client is None:
                try:
                    self._client = httpx.AsyncClient(
                        base_url=self.base_url,
                        timeout=self.timeout,
                        verify=self.verify_ssl,
                        follow_redirects=self.follow_redirects,
                        headers=self.default_headers,
                        transport=self._transport,
                    )
                except Exception:
                    raise HttpClientError("HTTP client initialization failed") from None
            return self._client

    async def close(self) -> None:
        """Close the connection pool; calling this method repeatedly is safe."""
        async with self._client_lock:
            client = self._client
            self._client = None
            if client is not None:
                try:
                    await client.aclose()
                except Exception:
                    raise HttpClientError("HTTP client cleanup failed") from None

    async def request(
        self,
        method: str,
        url: str,
        headers: Mapping[str, str] | None = None,
        **kwargs: Any,
    ) -> httpx.Response:
        """Send a request and return its response, including non-success statuses."""
        if not isinstance(method, str) or not method.strip():
            raise ValueError("method must be a non-empty string")
        if not isinstance(url, str) or not url:
            raise ValueError("url must be a non-empty string")

        normalized_method = method.strip().upper()
        request_kwargs = dict(kwargs)
        per_request_auth = request_kwargs.pop("auth", _UNSET)
        auth = self.auth_config.auth if per_request_auth is _UNSET else per_request_auth
        client = await self._ensure_client()
        attempts = self.retry_config.max_attempts
        replayable = _request_body_is_replayable(request_kwargs)
        refreshed = False

        for attempt in range(attempts):
            try:
                request = client.build_request(
                    normalized_method,
                    url,
                    headers=headers,
                    **request_kwargs,
                )
                response = await client.send(request, auth=_as_httpx_auth(auth))
            except Exception as error:
                if (
                    attempt + 1 < attempts
                    and replayable
                    and normalized_method in self.retry_config.retry_methods
                    and _is_retryable_exception(error, self.retry_config)
                ):
                    _logger.warning(
                        "HTTP %s request failed with %s; retrying attempt %d of %d",
                        normalized_method,
                        type(error).__name__,
                        attempt + 2,
                        attempts,
                    )
                    await self._sleep_before_retry(attempt)
                    continue
                raise HttpClientError(
                    f"HTTP {normalized_method} request failed after {attempt + 1} attempt(s)"
                ) from None

            if (
                response.status_code == 401
                and not refreshed
                and self.auth_config.refresh_callback is not None
                and attempt + 1 < attempts
                and replayable
                and normalized_method in self.retry_config.retry_methods
            ):
                try:
                    replacement = self.auth_config.refresh_callback()
                    auth = _replace_auth_secret(auth, replacement)
                except Exception:
                    await response.aclose()
                    raise HttpClientError(
                        "HTTP authentication refresh failed",
                        status_code=401,
                        response=response,
                    ) from None
                refreshed = True
                await response.aclose()
                _logger.info(
                    "HTTP %s authentication was refreshed after status 401", normalized_method
                )
                continue

            if (
                attempt + 1 < attempts
                and replayable
                and normalized_method in self.retry_config.retry_methods
                and response.status_code in self.retry_config.retry_statuses
            ):
                _logger.warning(
                    "HTTP %s returned status %d; retrying attempt %d of %d",
                    normalized_method,
                    response.status_code,
                    attempt + 2,
                    attempts,
                )
                await response.aclose()
                await self._sleep_before_retry(attempt)
                continue
            return response

        raise HttpClientError(
            f"HTTP {normalized_method} request failed after {attempts} attempt(s)"
        )

    async def get(
        self, url: str, headers: Mapping[str, str] | None = None, **kwargs: Any
    ) -> httpx.Response:
        """Send a GET request."""
        return await self.request("GET", url, headers, **kwargs)

    async def post(
        self, url: str, headers: Mapping[str, str] | None = None, **kwargs: Any
    ) -> httpx.Response:
        """Send a POST request."""
        return await self.request("POST", url, headers, **kwargs)

    async def put(
        self, url: str, headers: Mapping[str, str] | None = None, **kwargs: Any
    ) -> httpx.Response:
        """Send a PUT request."""
        return await self.request("PUT", url, headers, **kwargs)

    async def patch(
        self, url: str, headers: Mapping[str, str] | None = None, **kwargs: Any
    ) -> httpx.Response:
        """Send a PATCH request."""
        return await self.request("PATCH", url, headers, **kwargs)

    async def delete(
        self, url: str, headers: Mapping[str, str] | None = None, **kwargs: Any
    ) -> httpx.Response:
        """Send a DELETE request."""
        return await self.request("DELETE", url, headers, **kwargs)

    async def get_model(
        self,
        url: str,
        response_model: type[ModelT],
        headers: Mapping[str, str] | None = None,
        **kwargs: Any,
    ) -> ModelT:
        """Send GET and validate its JSON response as a Pydantic model."""
        return await self._send_model("GET", url, response_model, headers, **kwargs)

    async def post_model(
        self,
        url: str,
        response_model: type[ModelT],
        headers: Mapping[str, str] | None = None,
        **kwargs: Any,
    ) -> ModelT:
        """Send POST and validate its JSON response as a Pydantic model."""
        return await self._send_model("POST", url, response_model, headers, **kwargs)

    async def put_model(
        self,
        url: str,
        response_model: type[ModelT],
        headers: Mapping[str, str] | None = None,
        **kwargs: Any,
    ) -> ModelT:
        """Send PUT and validate its JSON response as a Pydantic model."""
        return await self._send_model("PUT", url, response_model, headers, **kwargs)

    async def patch_model(
        self,
        url: str,
        response_model: type[ModelT],
        headers: Mapping[str, str] | None = None,
        **kwargs: Any,
    ) -> ModelT:
        """Send PATCH and validate its JSON response as a Pydantic model."""
        return await self._send_model("PATCH", url, response_model, headers, **kwargs)

    async def delete_model(
        self,
        url: str,
        response_model: type[ModelT],
        headers: Mapping[str, str] | None = None,
        **kwargs: Any,
    ) -> ModelT:
        """Send DELETE and validate its JSON response as a Pydantic model."""
        return await self._send_model("DELETE", url, response_model, headers, **kwargs)

    async def _send_model(
        self,
        method: str,
        url: str,
        response_model: type[ModelT],
        headers: Mapping[str, str] | None,
        **kwargs: Any,
    ) -> ModelT:
        """Validate a successful JSON response without leaking response details in errors."""
        response = await self.request(method, url, headers, **kwargs)
        if not response.is_success:
            raise HttpClientError(
                f"HTTP {method} returned status {response.status_code}",
                status_code=response.status_code,
                response=response,
            )
        try:
            payload = response.json()
            return response_model.model_validate(payload)
        except (ValueError, ValidationError):
            raise HttpClientError(
                f"HTTP {method} response did not match {response_model.__name__}",
                status_code=response.status_code,
                response=response,
            ) from None

    async def _sleep_before_retry(self, attempt: int) -> None:
        """Sleep for exponential backoff capped at one minute."""
        factor = self.retry_config.backoff_factor
        if factor == 0:
            return
        delay = min(factor * (2 ** min(attempt, 60)), 60.0)
        if self.retry_config.jitter:
            delay = min(delay * random.uniform(0.5, 1.5), 60.0)
        await asyncio.sleep(delay)


def _as_httpx_auth(auth: Any) -> httpx.Auth | None:
    """Adapt the legacy auth handler to HTTPX while accepting native HTTPX auth."""
    if auth is None:
        return None
    if isinstance(auth, httpx.Auth):
        return auth
    auth_flow = getattr(auth, "auth_flow", None)
    if callable(auth_flow):
        return _LegacyAuth(auth)
    raise TypeError("auth must implement httpx.Auth or AuthBase.auth_flow")


def _replace_auth_secret(auth: Any, secret: str) -> Any:
    """Return a supported auth handler containing a refreshed token or API key."""
    if not isinstance(secret, str) or not secret.strip():
        raise ValueError("authentication refresh returned an empty secret")
    if isinstance(auth, BearerAuth):
        return BearerAuth(secret)
    if isinstance(auth, ApiKeyAuth):
        return ApiKeyAuth(secret, header_name=auth.header_name, prefix=auth.prefix)
    raise TypeError("authentication refresh requires BearerAuth or ApiKeyAuth")


def _is_retryable_exception(error: Exception, config: RetryConfig) -> bool:
    """Retry transport errors by default and additional configured exception types."""
    if isinstance(error, httpx.TransportError):
        return True
    return bool(config.retry_exceptions) and isinstance(error, tuple(config.retry_exceptions))


def _request_body_is_replayable(kwargs: Mapping[str, Any]) -> bool:
    """Avoid replaying generators and open streams that are exhausted by the first send."""
    return all(_value_is_replayable(value) for value in kwargs.values())


def _value_is_replayable(value: Any) -> bool:
    """Return whether a request argument can be safely used to build a second request."""
    if value is None or isinstance(value, (str, bytes, bytearray, memoryview, int, float, bool)):
        return True
    if isinstance(value, BaseModel):
        return _value_is_replayable(value.model_dump())
    if hasattr(value, "read"):
        return False
    if isinstance(value, Mapping):
        return all(_value_is_replayable(item) for item in value.values())
    if isinstance(value, Sequence):
        return all(_value_is_replayable(item) for item in value)
    return False
