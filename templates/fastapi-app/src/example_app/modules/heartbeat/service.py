"""Optional heartbeat background service and its settings model."""

import asyncio
import logging

from example_app.core.services import BackgroundService

logger = logging.getLogger(__name__)


class HeartbeatService(BackgroundService):
    """Log a periodic heartbeat to demonstrate injected service lifecycle."""

    def __init__(self, application_name: str, interval_seconds: int) -> None:
        """Create the worker with validated startup configuration."""
        super().__init__(name="example-app-heartbeat")
        self._application_name = application_name
        self._interval_seconds = interval_seconds

    async def run(self) -> None:
        """Log periodically until the application requests shutdown."""
        while not self.stop_event.is_set():
            logger.info("Background heartbeat running for %s", self._application_name)
            try:
                await asyncio.wait_for(self.stop_event.wait(), timeout=self._interval_seconds)
            except TimeoutError:
                continue
