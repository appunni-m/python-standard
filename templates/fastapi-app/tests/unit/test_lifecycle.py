from __future__ import annotations

import asyncio

import pytest
from fastapi import FastAPI

from example_app.core.services import BackgroundService, ServiceState
from example_app.lifecycle import create_lifespan


class TrackingWorker(BackgroundService):
    """Background service that records startup and shutdown ordering."""

    def __init__(
        self,
        name: str,
        events: list[str],
        *,
        fail_start: bool = False,
    ) -> None:
        super().__init__(name=name, shutdown_timeout=0.05)
        self.events = events
        self.fail_start = fail_start

    async def _start(self) -> None:
        self.events.append(f"start:{self.name}")
        if self.fail_start:
            raise RuntimeError(f"failed to start {self.name}")
        await super()._start()

    async def _stop(self) -> None:
        self.events.append(f"stop:{self.name}")
        await super()._stop()

    async def run(self) -> None:
        """Wait until the lifecycle requests shutdown."""
        await self.stop_event.wait()


def test_lifespan_stops_services_in_reverse_start_order() -> None:
    async def scenario() -> None:
        events: list[str] = []
        first = TrackingWorker("first", events)
        second = TrackingWorker("second", events)
        lifespan = create_lifespan([first, second])

        async with lifespan(FastAPI()):
            assert first.state is ServiceState.RUNNING
            assert second.state is ServiceState.RUNNING

        assert events == [
            "start:first",
            "start:second",
            "stop:second",
            "stop:first",
        ]
        assert first.state is ServiceState.STOPPED
        assert second.state is ServiceState.STOPPED

    asyncio.run(scenario())


def test_lifespan_cleans_partial_start_and_previously_started_services() -> None:
    async def scenario() -> None:
        events: list[str] = []
        first = TrackingWorker("first", events)
        failing = TrackingWorker("failing", events, fail_start=True)
        lifespan = create_lifespan([first, failing])

        with pytest.raises(RuntimeError, match="failed to start failing"):
            async with lifespan(FastAPI()):
                pytest.fail("lifespan must not yield after failed startup")

        assert events == [
            "start:first",
            "start:failing",
            "stop:failing",
            "stop:first",
        ]
        assert first.state is ServiceState.STOPPED
        assert failing.state is ServiceState.STOPPED

    asyncio.run(scenario())
