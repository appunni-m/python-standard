"""Async SQS queue operations, message serialization, and batch processing."""

from __future__ import annotations

import asyncio
import inspect
import json
from collections.abc import Awaitable, Mapping, Sequence
from contextlib import asynccontextmanager
from typing import Any, Protocol, TypedDict, TypeVar, cast

from pydantic import BaseModel, ConfigDict, Field

from .._client import open_client
from ..auth.credentials import CredentialProvider, DefaultCredentialProvider

T = TypeVar("T", bound=BaseModel)
SQSBody = str | Mapping[str, Any] | BaseModel


class SQSMessage(TypedDict, total=False):
    """SQS message fields returned by ``receive_message``."""

    MessageId: str
    ReceiptHandle: str
    Body: str
    Attributes: dict[str, str]
    MessageAttributes: dict[str, dict[str, Any]]
    MD5OfBody: str
    _parsed: Any
    _parse_error: str


class MessageHandler(Protocol):
    """Sync or async callable accepted by SQS message processing."""

    def __call__(self, message: SQSMessage) -> Any | Awaitable[Any]:
        """Handle one received SQS message."""


class SQSProcessMessageResult(TypedDict):
    """Outcome for one message handled by :meth:`SQSClient.process_messages`."""

    message: SQSMessage
    success: bool
    error: str | None
    deleted: bool


class SQSConfig(BaseModel):
    """Queue URL, region, and optional compatible-service endpoint."""

    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)

    queue_url: str = Field(min_length=1)
    region: str | None = Field(default=None, min_length=1)
    endpoint_url: str | None = None


class SQSClient:
    """Async client for sending, receiving, processing, and deleting SQS messages."""

    def __init__(
        self,
        config: SQSConfig,
        credential_provider: CredentialProvider | None = None,
    ) -> None:
        """Create a queue client; each operation gets a separately closed SDK client."""
        self.config = config
        self.credential_provider = credential_provider or DefaultCredentialProvider()

    @asynccontextmanager
    async def get_client(self) -> Any:
        """Yield an aioboto3 SQS client and close it when the context exits."""
        async with open_client(
            "sqs",
            region=self.config.region,
            endpoint_url=self.config.endpoint_url,
            credential_provider=self.credential_provider,
        ) as client:
            yield client

    async def create_queue(
        self,
        queue_name: str,
        attributes: Mapping[str, str] | None = None,
    ) -> str:
        """Create a queue and return its URL."""
        normalized = queue_name.strip()
        if not 1 <= len(normalized) <= 80:
            raise ValueError("queue_name must contain between 1 and 80 characters")
        async with self.get_client() as client:
            response = await client.create_queue(
                QueueName=normalized,
                Attributes=dict(attributes or {}),
            )
        return cast(str, response["QueueUrl"])

    async def send_message(
        self,
        message: SQSBody,
        message_attributes: Mapping[str, Mapping[str, Any]] | None = None,
        delay_seconds: int | None = None,
    ) -> dict[str, Any]:
        """Send a string, mapping, or Pydantic model as one message."""
        kwargs: dict[str, Any] = {
            "QueueUrl": self.config.queue_url,
            "MessageBody": self._serialize_message(message),
        }
        if message_attributes:
            kwargs["MessageAttributes"] = {
                key: dict(value) for key, value in message_attributes.items()
            }
        if delay_seconds is not None:
            self._validate_delay(delay_seconds)
            kwargs["DelaySeconds"] = delay_seconds
        async with self.get_client() as client:
            return cast(dict[str, Any], await client.send_message(**kwargs))

    async def send_message_batch(
        self,
        messages: Sequence[SQSBody],
        message_attributes: Sequence[Mapping[str, Mapping[str, Any]]] | None = None,
        delay_seconds: int | None = None,
    ) -> dict[str, Any]:
        """Send one SQS batch of 1–10 messages and return the raw success/error result."""
        if not 1 <= len(messages) <= 10:
            raise ValueError("messages must contain between 1 and 10 items")
        if message_attributes is not None and len(message_attributes) != len(messages):
            raise ValueError("message_attributes must have one entry per message")
        if delay_seconds is not None:
            self._validate_delay(delay_seconds)
        entries: list[dict[str, Any]] = []
        for index, message in enumerate(messages):
            entry: dict[str, Any] = {
                "Id": str(index),
                "MessageBody": self._serialize_message(message),
            }
            if message_attributes and message_attributes[index]:
                entry["MessageAttributes"] = {
                    key: dict(value) for key, value in message_attributes[index].items()
                }
            if delay_seconds is not None:
                entry["DelaySeconds"] = delay_seconds
            entries.append(entry)
        async with self.get_client() as client:
            response = await client.send_message_batch(
                QueueUrl=self.config.queue_url, Entries=entries
            )
            return cast(dict[str, Any], response)

    async def receive_message(
        self,
        max_number_of_messages: int = 1,
        wait_time_seconds: int | None = None,
        visibility_timeout: int | None = None,
        model_class: type[T] | None = None,
    ) -> list[SQSMessage]:
        """Receive at most ten messages and optionally attach validated model data."""
        if not 1 <= max_number_of_messages <= 10:
            raise ValueError("max_number_of_messages must be between 1 and 10")
        if wait_time_seconds is not None and not 0 <= wait_time_seconds <= 20:
            raise ValueError("wait_time_seconds must be between 0 and 20")
        if visibility_timeout is not None and not 0 <= visibility_timeout <= 43200:
            raise ValueError("visibility_timeout must be between 0 and 43200")
        kwargs: dict[str, Any] = {
            "QueueUrl": self.config.queue_url,
            "MaxNumberOfMessages": max_number_of_messages,
            "MessageAttributeNames": ["All"],
            "AttributeNames": ["All"],
        }
        if wait_time_seconds is not None:
            kwargs["WaitTimeSeconds"] = wait_time_seconds
        if visibility_timeout is not None:
            kwargs["VisibilityTimeout"] = visibility_timeout
        async with self.get_client() as client:
            response = cast(dict[str, Any], await client.receive_message(**kwargs))
        messages: list[SQSMessage] = response.get("Messages", [])
        if model_class is not None:
            for message in messages:
                try:
                    message["_parsed"] = model_class.model_validate_json(message["Body"])
                except (KeyError, ValueError, TypeError) as error:
                    message["_parse_error"] = type(error).__name__
        return messages

    async def delete_message(self, receipt_handle: str) -> dict[str, Any]:
        """Delete one message by its current receipt handle."""
        if not receipt_handle:
            raise ValueError("receipt_handle must not be empty")
        async with self.get_client() as client:
            return cast(
                dict[str, Any],
                await client.delete_message(
                    QueueUrl=self.config.queue_url,
                    ReceiptHandle=receipt_handle,
                ),
            )

    async def delete_message_batch(self, entries: Sequence[Mapping[str, str]]) -> dict[str, Any]:
        """Delete one batch containing between one and ten SQS messages."""
        if not 1 <= len(entries) <= 10:
            raise ValueError("entries must contain between 1 and 10 items")
        normalized: list[dict[str, str]] = []
        seen: set[str] = set()
        for entry in entries:
            entry_id = entry.get("Id", "")
            receipt_handle = entry.get("ReceiptHandle", "")
            if not entry_id or not receipt_handle:
                raise ValueError("each entry must include Id and ReceiptHandle")
            if entry_id in seen:
                raise ValueError("entry Id values must be unique")
            seen.add(entry_id)
            normalized.append({"Id": entry_id, "ReceiptHandle": receipt_handle})
        async with self.get_client() as client:
            return cast(
                dict[str, Any],
                await client.delete_message_batch(
                    QueueUrl=self.config.queue_url,
                    Entries=normalized,
                ),
            )

    async def purge_queue(self) -> dict[str, Any]:
        """Request that SQS remove all messages from the queue."""
        async with self.get_client() as client:
            return cast(dict[str, Any], await client.purge_queue(QueueUrl=self.config.queue_url))

    async def process_messages(
        self,
        handler: MessageHandler,
        max_number_of_messages: int = 10,
        wait_time_seconds: int | None = None,
        visibility_timeout: int | None = None,
        model_class: type[T] | None = None,
        auto_delete: bool = True,
    ) -> list[SQSProcessMessageResult]:
        """Receive a batch, run sync or async handlers, then optionally delete successes."""
        messages = await self.receive_message(
            max_number_of_messages=max_number_of_messages,
            wait_time_seconds=wait_time_seconds,
            visibility_timeout=visibility_timeout,
            model_class=model_class,
        )
        results: list[SQSProcessMessageResult] = []
        for message in messages:
            result: SQSProcessMessageResult = {
                "message": message,
                "success": False,
                "error": None,
                "deleted": False,
            }
            try:
                if inspect.iscoroutinefunction(handler) or inspect.iscoroutinefunction(
                    type(handler).__call__
                ):
                    handler_result = handler(message)
                else:
                    handler_result = await asyncio.to_thread(handler, message)
                if inspect.isawaitable(handler_result):
                    await handler_result
                result["success"] = True
                if auto_delete:
                    receipt_handle = message.get("ReceiptHandle")
                    if not receipt_handle:
                        raise ValueError("received message has no ReceiptHandle")
                    await self.delete_message(receipt_handle)
                    result["deleted"] = True
            except Exception as error:
                result["success"] = False
                result["error"] = str(error)
            results.append(result)
        return results

    @staticmethod
    def _serialize_message(message: SQSBody) -> str:
        if isinstance(message, BaseModel):
            return message.model_dump_json()
        if isinstance(message, Mapping):
            return json.dumps(message, ensure_ascii=False, allow_nan=False)
        if isinstance(message, str):
            return message
        raise TypeError("message must be a string, mapping, or Pydantic model")

    @staticmethod
    def _validate_delay(delay_seconds: int) -> None:
        if isinstance(delay_seconds, bool) or not 0 <= delay_seconds <= 900:
            raise ValueError("delay_seconds must be between 0 and 900")


__all__ = ["SQSClient", "SQSConfig", "SQSMessage", "SQSProcessMessageResult"]
