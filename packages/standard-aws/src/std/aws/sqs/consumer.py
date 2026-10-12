"""Managed long-polling consumer for SQS queues."""

from __future__ import annotations

import asyncio
import logging
from contextlib import suppress
from typing import TypeVar

from pydantic import BaseModel

from std.service import BackgroundService

from ..auth.credentials import CredentialProvider
from .client import MessageHandler, SQSClient, SQSConfig, SQSProcessMessageResult

T = TypeVar("T", bound=BaseModel)
logger = logging.getLogger(__name__)


class SQSConsumer(BackgroundService):
    """BackgroundService that polls a queue and processes messages in batches."""

    def __init__(
        self,
        queue_url: str,
        region: str,
        handler: MessageHandler,
        max_messages: int = 10,
        wait_time: int = 20,
        visibility_timeout: int = 30,
        endpoint_url: str | None = None,
        credential_provider: CredentialProvider | None = None,
        polling_interval: float = 0.1,
        model_class: type[T] | None = None,
        auto_delete: bool = True,
        retry_delay: float = 5.0,
        *,
        shutdown_timeout: float | None = 30.0,
    ) -> None:
        """Configure one queue worker with bounded polling and shutdown behavior."""
        super().__init__(name="SQSConsumer", shutdown_timeout=shutdown_timeout)
        if not 1 <= max_messages <= 10:
            raise ValueError("max_messages must be between 1 and 10")
        if not 0 <= wait_time <= 20:
            raise ValueError("wait_time must be between 0 and 20")
        if not 0 <= visibility_timeout <= 43200:
            raise ValueError("visibility_timeout must be between 0 and 43200")
        if polling_interval < 0 or retry_delay < 0:
            raise ValueError("polling_interval and retry_delay must not be negative")
        self.handler = handler
        self.max_messages = max_messages
        self.wait_time = wait_time
        self.visibility_timeout = visibility_timeout
        self.polling_interval = polling_interval
        self.retry_delay = retry_delay
        self.model_class = model_class
        self.auto_delete = auto_delete
        self.client = SQSClient(
            SQSConfig(queue_url=queue_url, region=region, endpoint_url=endpoint_url),
            credential_provider,
        )

    async def run(self) -> None:
        """Poll until the service stop signal is set, recovering from transient errors."""
        while not self.stop_event.is_set():
            delay: float = 0.0
            try:
                results = await self.process_batch(self.max_messages)
                if results:
                    succeeded = sum(result["success"] for result in results)
                    logger.info(
                        "SQS batch processed: %d succeeded, %d failed",
                        succeeded,
                        len(results) - succeeded,
                    )
                    delay = 0
                else:
                    delay = self.polling_interval
            except asyncio.CancelledError:
                raise
            except Exception as error:
                logger.warning("SQS polling failed (%s); retrying", type(error).__name__)
                delay = self.retry_delay
            if delay > 0:
                with suppress(TimeoutError):
                    await asyncio.wait_for(self.stop_event.wait(), timeout=delay)

    async def process_batch(self, batch_size: int = 10) -> list[SQSProcessMessageResult]:
        """Process one message batch; useful for deterministic jobs and tests."""
        if not 1 <= batch_size <= 10:
            raise ValueError("batch_size must be between 1 and 10")
        return await self.client.process_messages(
            handler=self.handler,
            max_number_of_messages=batch_size,
            wait_time_seconds=self.wait_time,
            visibility_timeout=self.visibility_timeout,
            model_class=self.model_class,
            auto_delete=self.auto_delete,
        )


__all__ = ["SQSConsumer"]
