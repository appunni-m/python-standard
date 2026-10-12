"""Typed configuration for HTTP request retries and authentication."""

from collections.abc import Callable
from math import isfinite
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class RetryConfig(BaseModel):
    """Control which HTTP responses and errors are retried."""

    model_config = ConfigDict(validate_assignment=True)

    max_attempts: int = Field(
        default=3, ge=1, description="Maximum total attempts, including the first"
    )
    retry_statuses: list[int] = Field(
        default_factory=lambda: [500, 502, 503, 504],
        description="HTTP status codes eligible for a retry",
    )
    retry_methods: list[str] = Field(
        default_factory=lambda: ["GET", "HEAD", "PUT", "DELETE", "OPTIONS", "TRACE"],
        description="HTTP methods eligible for a retry",
    )
    backoff_factor: float = Field(default=0.5, ge=0, description="Base delay in seconds")
    jitter: bool = Field(default=True, description="Apply bounded random jitter to retry delays")
    retry_exceptions: list[type[BaseException]] = Field(
        default_factory=list,
        description="Additional exception classes eligible for retries",
    )

    @field_validator("retry_statuses")
    @classmethod
    def validate_retry_statuses(cls, values: list[int]) -> list[int]:
        """Require valid HTTP status codes and remove duplicates in input order."""
        unique_values: list[int] = []
        for status in values:
            if isinstance(status, bool) or not 100 <= status <= 599:
                raise ValueError("retry statuses must be integers from 100 through 599")
            if status not in unique_values:
                unique_values.append(status)
        return unique_values

    @field_validator("retry_methods")
    @classmethod
    def normalize_retry_methods(cls, values: list[str]) -> list[str]:
        """Normalize method names and reject empty values."""
        methods: list[str] = []
        for method in values:
            if not method or not method.strip():
                raise ValueError("retry methods cannot be empty")
            normalized = method.strip().upper()
            if normalized not in methods:
                methods.append(normalized)
        return methods

    @field_validator("retry_exceptions")
    @classmethod
    def validate_retry_exceptions(
        cls, values: list[type[BaseException]]
    ) -> list[type[BaseException]]:
        """Require exception classes rather than instances or arbitrary objects."""
        for exception_type in values:
            if not isinstance(exception_type, type) or not issubclass(
                exception_type, BaseException
            ):
                raise ValueError("retry_exceptions must contain exception classes")
        return values

    @field_validator("backoff_factor")
    @classmethod
    def validate_backoff_factor(cls, value: float) -> float:
        """Require a finite delay factor so a bad config cannot stall requests."""
        if not isfinite(value):
            raise ValueError("backoff_factor must be finite")
        return value


class AuthConfig(BaseModel):
    """Collect an authentication handler and optional token-refresh settings."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    auth: Any | None = Field(
        default=None,
        repr=False,
        description="Authentication object compatible with HTTPX or AuthBase",
    )
    refresh_token: str | None = Field(
        default=None,
        repr=False,
        description="Refresh token retained for a caller-provided refresh callback",
    )
    refresh_callback: Callable[[], str] | None = Field(
        default=None,
        repr=False,
        description="Synchronous callback that returns a replacement bearer or API key",
    )
