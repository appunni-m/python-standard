"""Validated settings for application-token authentication."""

from __future__ import annotations

import re

from pydantic import BaseModel, ConfigDict, Field, field_validator

_HEADER_NAME = re.compile(r"^[!#$%&'*+.^_`|~0-9A-Za-z-]+$")


class AppTokenConfig(BaseModel):
    """Configure the token header, accepted application tokens, and path skips."""

    model_config = ConfigDict(extra="forbid")

    header_name: str = "X-App-Token"
    tokens: dict[str, str] = Field(default_factory=dict, repr=False)
    enabled: bool = True
    exclude_paths: set[str] = Field(default_factory=set)

    @field_validator("header_name")
    @classmethod
    def validate_header_name(cls, value: str) -> str:
        """Require a valid HTTP token header name."""
        name = value.strip()
        if not _HEADER_NAME.fullmatch(name):
            raise ValueError("header_name must be a valid HTTP field name")
        return name

    @field_validator("tokens")
    @classmethod
    def validate_tokens(cls, tokens: dict[str, str]) -> dict[str, str]:
        """Reject blank identities and tokens without disclosing token values."""
        seen: set[str] = set()
        for app_name, token in tokens.items():
            if not app_name.strip():
                raise ValueError("token application names cannot be empty")
            if not token.strip():
                raise ValueError(f"token for application {app_name!r} cannot be empty")
            if token in seen:
                raise ValueError("authentication tokens must be unique")
            seen.add(token)
        return tokens

    @field_validator("exclude_paths")
    @classmethod
    def validate_exclude_paths(cls, paths: set[str]) -> set[str]:
        """Require absolute request paths for exact and wildcard exclusions."""
        normalized = {path.strip() for path in paths}
        if any(not path.startswith("/") for path in normalized):
            raise ValueError("excluded paths must begin with '/'")
        return normalized
