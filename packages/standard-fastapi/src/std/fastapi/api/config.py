"""Validated server and application metadata for FastAPI."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator


class Environment(StrEnum):
    """Deployment environments supported by the FastAPI setup helper."""

    DEV = "dev"
    STAGE = "stage"
    PROD = "prod"

    def __str__(self) -> str:
        """Return the configuration value."""
        return self.value


class APIConfig(BaseModel):
    """Application metadata, server options, and CORS policy."""

    model_config = ConfigDict(extra="forbid")

    enabled: bool = Field(default=True, description="Whether the API is enabled")
    env: Environment = Field(default=Environment.DEV, description="Deployment environment")
    title: str = Field(default="Standard API", min_length=1)
    description: str = Field(default="API service")
    version: str = Field(default="1.0.0", min_length=1)
    host: str = Field(default="0.0.0.0", min_length=1)
    port: int = Field(default=8000, ge=1, le=65535)
    reload: bool = True
    workers: int = Field(default=1, ge=1)
    debug: bool = True
    cors_origins: list[str] = Field(default_factory=lambda: ["*"])
    cors_methods: list[str] = Field(default_factory=lambda: ["*"])
    cors_headers: list[str] = Field(default_factory=lambda: ["*"])
    cors_credentials: bool = True

    @field_validator("host")
    @classmethod
    def validate_host(cls, value: str) -> str:
        """Reject whitespace-only bind hosts."""
        host = value.strip()
        if not host:
            raise ValueError("host cannot be empty")
        return host

    @field_validator("cors_origins", "cors_methods", "cors_headers")
    @classmethod
    def validate_cors_values(cls, values: list[str]) -> list[str]:
        """Reject empty CORS entries and normalize surrounding whitespace."""
        normalized = [value.strip() for value in values]
        if any(not value for value in normalized):
            raise ValueError("CORS entries cannot be empty")
        return normalized
