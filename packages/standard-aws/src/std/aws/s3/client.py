"""Async S3 object operations with typed serialization helpers."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Mapping
from contextlib import asynccontextmanager
from io import BytesIO
from pathlib import Path
from typing import Any, BinaryIO, TypeVar, cast

from pydantic import BaseModel, ConfigDict, Field

from .._client import open_client
from ..auth.credentials import CredentialProvider, DefaultCredentialProvider

T = TypeVar("T", bound=BaseModel)


class _BufferedBody:
    """In-memory async stream for a detached, already-consumed GetObject response."""

    def __init__(self, body: bytes) -> None:
        self._stream = BytesIO(body)

    async def read(self, amount: int = -1) -> bytes:
        """Read bytes using the asynchronous response-body interface."""
        return self._stream.read(amount)

    async def close(self) -> None:
        """Close the in-memory stream."""
        self._stream.close()

    async def __aenter__(self) -> _BufferedBody:
        """Return this buffered response stream."""
        return self

    async def __aexit__(self, *_: object) -> None:
        """Close this buffered response stream."""
        await self.close()


class S3ClientConfig(BaseModel):
    """Bucket, region, and optional compatible-service endpoint settings."""

    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)

    bucket_name: str = Field(min_length=1, max_length=255)
    region: str | None = Field(default=None, min_length=1)
    endpoint_url: str | None = None


class S3Client:
    """Async S3 client for object uploads, downloads, listing, and deletion."""

    def __init__(
        self,
        config: S3ClientConfig,
        credential_provider: CredentialProvider | None = None,
    ) -> None:
        """Create an S3 client facade; network clients are opened per operation."""
        self.config = config
        self.credential_provider = credential_provider or DefaultCredentialProvider()

    @asynccontextmanager
    async def get_client(self) -> Any:
        """Yield an aioboto3 S3 client and close it when the context exits."""
        async with open_client(
            "s3",
            region=self.config.region,
            endpoint_url=self.config.endpoint_url,
            credential_provider=self.credential_provider,
        ) as client:
            yield client

    async def upload_file(
        self,
        local_path: str | Path,
        s3_key: str,
        extra_args: Mapping[str, Any] | None = None,
    ) -> bool:
        """Upload a local file and return ``True`` after successful completion."""
        if not s3_key:
            raise ValueError("s3_key must not be empty")
        async with self.get_client() as client:
            await client.upload_file(
                str(local_path), self.config.bucket_name, s3_key, ExtraArgs=dict(extra_args or {})
            )
        return True

    async def upload_fileobj(
        self,
        fileobj: BinaryIO,
        s3_key: str,
        extra_args: Mapping[str, Any] | None = None,
    ) -> bool:
        """Upload a binary file-like object without taking ownership of it."""
        if not s3_key:
            raise ValueError("s3_key must not be empty")
        if not callable(getattr(fileobj, "read", None)):
            raise TypeError("fileobj must provide read()")
        async with self.get_client() as client:
            await client.upload_fileobj(
                fileobj, self.config.bucket_name, s3_key, ExtraArgs=dict(extra_args or {})
            )
        return True

    async def download_file(self, s3_key: str, local_path: str | Path) -> bool:
        """Download an object to a local path and return ``True`` on success."""
        if not s3_key:
            raise ValueError("s3_key must not be empty")
        async with self.get_client() as client:
            await client.download_file(self.config.bucket_name, s3_key, str(local_path))
        return True

    async def list_objects(
        self,
        prefix: str = "",
        delimiter: str = "",
        max_keys: int = 1000,
    ) -> list[str]:
        """Return up to ``max_keys`` object keys, following continuation tokens."""
        if not 1 <= max_keys <= 1000:
            raise ValueError("max_keys must be between 1 and 1000")
        keys: list[str] = []
        token: str | None = None
        async with self.get_client() as client:
            while len(keys) < max_keys:
                kwargs: dict[str, Any] = {
                    "Bucket": self.config.bucket_name,
                    "Prefix": prefix,
                    "MaxKeys": min(1000, max_keys - len(keys)),
                }
                if delimiter:
                    kwargs["Delimiter"] = delimiter
                if token:
                    kwargs["ContinuationToken"] = token
                response = await client.list_objects_v2(**kwargs)
                keys.extend(item["Key"] for item in response.get("Contents", []))
                token = response.get("NextContinuationToken")
                if not response.get("IsTruncated") or not token:
                    break
        return keys[:max_keys]

    async def get_object(self, s3_key: str) -> dict[str, Any]:
        """Return S3 metadata and a buffered async ``Body`` stream.

        The service client is closed before this method returns, so this helper
        buffers the body in memory. Use :meth:`open_object` for large objects.
        """
        if not s3_key:
            raise ValueError("s3_key must not be empty")
        async with self.open_object(s3_key) as response:
            body = await response["Body"].read()
            detached = dict(response)
        detached["Body"] = _BufferedBody(bytes(body))
        return detached

    @asynccontextmanager
    async def open_object(self, s3_key: str) -> AsyncIterator[dict[str, Any]]:
        """Stream one object while keeping its S3 client open for the context."""
        if not s3_key:
            raise ValueError("s3_key must not be empty")
        async with self.get_client() as client:
            response = cast(
                dict[str, Any],
                await client.get_object(Bucket=self.config.bucket_name, Key=s3_key),
            )
            try:
                yield response
            finally:
                stream = response.get("Body")
                close = getattr(stream, "close", None)
                if close is not None:
                    result = close()
                    if hasattr(result, "__await__"):
                        await result

    async def get_object_body(self, s3_key: str) -> bytes:
        """Read an object's complete response stream and close it on success or failure."""
        async with self.open_object(s3_key) as response:
            body = await response["Body"].read()
            return body if isinstance(body, bytes) else bytes(body)

    async def get_object_as_bytes(self, s3_key: str) -> bytes:
        """Return the object's body as bytes."""
        return await self.get_object_body(s3_key)

    async def get_object_as_string(self, s3_key: str, encoding: str = "utf-8") -> str:
        """Decode the object's body with the selected encoding."""
        return (await self.get_object_body(s3_key)).decode(encoding)

    async def get_object_as_json(self, s3_key: str) -> Any:
        """Parse the object body as JSON, returning any JSON value."""
        return json.loads(await self.get_object_as_string(s3_key))

    async def get_object_as_model(self, s3_key: str, model_class: type[T]) -> T:
        """Validate an object's JSON value using a Pydantic model."""
        return model_class.model_validate(await self.get_object_as_json(s3_key))

    async def put_object(
        self,
        s3_key: str,
        body: bytes | str | BinaryIO,
        content_type: str | None = None,
        metadata: Mapping[str, str] | None = None,
    ) -> dict[str, Any]:
        """Write a byte, string, or binary stream as an S3 object."""
        if not s3_key:
            raise ValueError("s3_key must not be empty")
        kwargs: dict[str, Any] = {
            "Bucket": self.config.bucket_name,
            "Key": s3_key,
            "Body": body.encode("utf-8") if isinstance(body, str) else body,
        }
        if content_type is not None:
            kwargs["ContentType"] = content_type
        if metadata is not None:
            kwargs["Metadata"] = dict(metadata)
        async with self.get_client() as client:
            return cast(dict[str, Any], await client.put_object(**kwargs))

    async def delete_object(self, s3_key: str) -> dict[str, Any]:
        """Delete one object and return the AWS response."""
        if not s3_key:
            raise ValueError("s3_key must not be empty")
        async with self.get_client() as client:
            return cast(
                dict[str, Any],
                await client.delete_object(Bucket=self.config.bucket_name, Key=s3_key),
            )

    async def delete_objects(self, s3_keys: list[str]) -> dict[str, Any]:
        """Delete keys in S3's 1000-key batches and aggregate per-key results."""
        if not s3_keys:
            return {"Deleted": [], "Errors": []}
        if any(not key for key in s3_keys):
            raise ValueError("s3_keys must not contain empty keys")
        deleted: list[dict[str, Any]] = []
        errors: list[dict[str, Any]] = []
        async with self.get_client() as client:
            for start in range(0, len(s3_keys), 1000):
                response = await client.delete_objects(
                    Bucket=self.config.bucket_name,
                    Delete={"Objects": [{"Key": key} for key in s3_keys[start : start + 1000]]},
                )
                deleted.extend(response.get("Deleted", []))
                errors.extend(response.get("Errors", []))
        return {"Deleted": deleted, "Errors": errors}

    async def get_presigned_url(
        self,
        s3_key: str,
        expires_in: int = 3600,
        http_method: str = "GET",
    ) -> str:
        """Generate a GET, PUT, or DELETE presigned URL."""
        if not s3_key:
            raise ValueError("s3_key must not be empty")
        if not 1 <= expires_in <= 604800:
            raise ValueError("expires_in must be between 1 and 604800 seconds")
        method_map = {"GET": "get_object", "PUT": "put_object", "DELETE": "delete_object"}
        normalized_method = http_method.upper()
        if normalized_method not in method_map:
            raise ValueError("http_method must be GET, PUT, or DELETE")
        async with self.get_client() as client:
            url = client.generate_presigned_url(
                method_map[normalized_method],
                Params={"Bucket": self.config.bucket_name, "Key": s3_key},
                ExpiresIn=expires_in,
                HttpMethod=normalized_method,
            )
            if hasattr(url, "__await__"):
                url = await url
            return str(url)

    async def copy_object(
        self,
        source_key: str,
        target_key: str,
        source_bucket: str | None = None,
        metadata: Mapping[str, str] | None = None,
        metadata_directive: str = "COPY",
    ) -> dict[str, Any]:
        """Copy an object in this bucket or from another bucket."""
        if not source_key or not target_key:
            raise ValueError("source_key and target_key must not be empty")
        directive = metadata_directive.upper()
        if directive not in {"COPY", "REPLACE"}:
            raise ValueError("metadata_directive must be COPY or REPLACE")
        kwargs: dict[str, Any] = {
            "CopySource": {"Bucket": source_bucket or self.config.bucket_name, "Key": source_key},
            "Bucket": self.config.bucket_name,
            "Key": target_key,
            "MetadataDirective": directive,
        }
        if metadata is not None:
            if directive != "REPLACE":
                raise ValueError("metadata can be supplied only when metadata_directive is REPLACE")
            kwargs["Metadata"] = dict(metadata)
        async with self.get_client() as client:
            return cast(dict[str, Any], await client.copy_object(**kwargs))


__all__ = ["S3Client", "S3ClientConfig"]
