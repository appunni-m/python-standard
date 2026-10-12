"""Shared creation of short-lived async AWS SDK clients."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from importlib import import_module
from typing import Any

from .auth.credentials import CredentialProvider


@asynccontextmanager
async def open_client(
    service_name: str,
    *,
    region: str | None,
    endpoint_url: str | None,
    credential_provider: CredentialProvider,
) -> AsyncIterator[Any]:
    """Open an aioboto3 client with provider credentials and guaranteed cleanup."""
    try:
        aioboto3: Any = import_module("aioboto3")
    except ImportError as error:  # pragma: no cover - package installation dependent
        raise ImportError("AWS clients require aioboto3; install `standard-aws`.") from error

    session = aioboto3.Session()
    kwargs: dict[str, Any] = {}
    if endpoint_url is not None:
        kwargs["endpoint_url"] = endpoint_url
    credentials = await credential_provider.get_credentials()
    credential_kwargs: dict[str, str] = {}
    if credentials is not None:
        credential_kwargs = credentials.to_dict()
        credential_kwargs.pop("region_name", None)
    kwargs["region_name"] = (
        region
        or (credentials.region if credentials is not None else None)
        or getattr(session, "region_name", None)
        or "us-east-1"
    )
    kwargs.update(credential_kwargs)

    async with session.client(service_name, **kwargs) as client:
        yield client
