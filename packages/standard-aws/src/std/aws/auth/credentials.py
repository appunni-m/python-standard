"""Async credential providers backed by explicit values and the AWS SDK chain."""

from __future__ import annotations

import asyncio
import os
from abc import ABC, abstractmethod
from importlib import import_module
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class AWSCredentials(BaseModel):
    """AWS access credentials with secret fields hidden from representations."""

    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)

    access_key_id: str = Field(min_length=1, description="AWS access key ID")
    secret_access_key: str = Field(min_length=1, repr=False, description="AWS secret access key")
    session_token: str | None = Field(default=None, repr=False)
    region: str | None = None

    @field_validator("session_token", "region")
    @classmethod
    def _reject_empty_optional_values(cls, value: str | None) -> str | None:
        if value == "":
            return None
        return value

    def to_dict(self) -> dict[str, str]:
        """Return keyword arguments accepted by the AWS SDK client factory."""
        values = {
            "aws_access_key_id": self.access_key_id,
            "aws_secret_access_key": self.secret_access_key,
        }
        if self.session_token is not None:
            values["aws_session_token"] = self.session_token
        if self.region is not None:
            values["region_name"] = self.region
        return values


class CredentialProvider(ABC):
    """Interface for asynchronous AWS credential lookup."""

    @abstractmethod
    async def get_credentials(self) -> AWSCredentials | None:
        """Return credentials, or ``None`` to use the SDK's default chain."""


class ExplicitCredentialProvider(CredentialProvider):
    """Return credentials configured directly by the application."""

    def __init__(
        self,
        access_key_id: str,
        secret_access_key: str,
        session_token: str | None = None,
        region: str | None = None,
    ) -> None:
        """Validate and retain static credentials for this provider."""
        self._credentials = AWSCredentials(
            access_key_id=access_key_id,
            secret_access_key=secret_access_key,
            session_token=session_token,
            region=region,
        )

    async def get_credentials(self) -> AWSCredentials:
        """Return the configured credentials."""
        return self._credentials


class EnvironmentCredentialProvider(CredentialProvider):
    """Read credentials from the standard AWS environment variables."""

    async def get_credentials(self) -> AWSCredentials | None:
        """Return credentials only when both access-key variables are present."""
        access_key_id = os.getenv("AWS_ACCESS_KEY_ID")
        secret_access_key = os.getenv("AWS_SECRET_ACCESS_KEY")
        if not access_key_id or not secret_access_key:
            return None
        return AWSCredentials(
            access_key_id=access_key_id,
            secret_access_key=secret_access_key,
            session_token=os.getenv("AWS_SESSION_TOKEN"),
            region=os.getenv("AWS_DEFAULT_REGION") or os.getenv("AWS_REGION"),
        )


class ProfileCredentialProvider(CredentialProvider):
    """Resolve one named profile through the AWS SDK shared configuration chain."""

    def __init__(self, profile_name: str = "default") -> None:
        """Select the profile name read by the AWS SDK."""
        if not profile_name.strip():
            raise ValueError("profile_name must not be empty")
        self.profile_name = profile_name.strip()

    async def get_credentials(self) -> AWSCredentials | None:
        """Resolve profile credentials off the event loop, including SSO/process providers."""
        return await asyncio.to_thread(self._resolve_credentials)

    def _resolve_credentials(self) -> AWSCredentials | None:
        try:
            boto3: Any = import_module("boto3")
        except ImportError as error:  # pragma: no cover - package installation dependent
            raise ImportError(
                "AWS credential lookup requires boto3; install `standard-aws`."
            ) from error
        try:
            session = boto3.Session(profile_name=self.profile_name)
            credentials = session.get_credentials()
            if credentials is None:
                return None
            frozen = credentials.get_frozen_credentials()
            return AWSCredentials(
                access_key_id=frozen.access_key,
                secret_access_key=frozen.secret_key,
                session_token=frozen.token,
                region=session.region_name,
            )
        except Exception as error:
            if type(error).__name__ == "ProfileNotFound":
                return None
            raise


class DefaultCredentialProvider(CredentialProvider):
    """Resolve the AWS SDK default chain, optionally pinning a named profile."""

    def __init__(self, profile_name: str | None = None) -> None:
        """Use the normal AWS SDK chain unless a profile name is supplied."""
        if profile_name is not None and not profile_name.strip():
            raise ValueError("profile_name must not be empty")
        self.profile_name = profile_name.strip() if profile_name is not None else None

    async def get_credentials(self) -> AWSCredentials | None:
        """Return current credentials from the SDK chain without blocking the event loop."""
        return await asyncio.to_thread(self._resolve_credentials)

    def _resolve_credentials(self) -> AWSCredentials | None:
        try:
            boto3: Any = import_module("boto3")
        except ImportError as error:  # pragma: no cover - package installation dependent
            raise ImportError(
                "AWS credential lookup requires boto3; install `standard-aws`."
            ) from error
        try:
            session = (
                boto3.Session(profile_name=self.profile_name)
                if self.profile_name is not None
                else boto3.Session()
            )
            credentials = session.get_credentials()
            if credentials is None:
                return None
            frozen = credentials.get_frozen_credentials()
            return AWSCredentials(
                access_key_id=frozen.access_key,
                secret_access_key=frozen.secret_key,
                session_token=frozen.token,
                region=session.region_name,
            )
        except Exception as error:
            if type(error).__name__ == "ProfileNotFound":
                return None
            raise
