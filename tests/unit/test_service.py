from __future__ import annotations

import asyncio
import math
from collections.abc import Coroutine
from typing import Any, TypeVar

import pytest

from std.service import (
    BackgroundService,
    BackgroundServiceError,
    BackgroundServiceProtocol,
    Service,
    ServiceState,
)

_Result = TypeVar("_Result")


def run(coroutine: Coroutine[Any, Any, _Result]) -> _Result:
    return asyncio.run(coroutine)


class RecordingService(Service):
    """Service double that records lifecycle hook calls."""

    def __init__(
        self,
        *,
        start_error: Exception | None = None,
        stop_error: Exception | None = None,
        health_error: Exception | None = None,
    ) -> None:
        super().__init__()
        self.start_error = start_error
        self.stop_error = stop_error
        self.health_error = health_error
        self.start_count = 0
        self.stop_count = 0

    async def _start(self) -> None:
        self.start_count += 1
        if self.start_error is not None:
            raise self.start_error

    async def _stop(self) -> None:
        self.stop_count += 1
        if self.stop_error is not None:
            raise self.stop_error

    async def _health_check(self) -> bool:
        if self.health_error is not None:
            raise self.health_error
        return True


class WaitingWorker(BackgroundService):
    """Worker that waits for its cooperative shutdown signal."""

    def __init__(self, *, shutdown_timeout: float | None = 0.05) -> None:
        super().__init__(shutdown_timeout=shutdown_timeout)
        self.started = asyncio.Event()
        self.exited = asyncio.Event()

    async def run(self) -> None:
        """Wait until shutdown is requested."""
        self.started.set()
        await self.stop_event.wait()
        self.exited.set()


class FailingWorker(BackgroundService):
    """Worker that fails immediately after it starts."""

    async def run(self) -> None:
        """Raise a representative worker failure."""
        raise ValueError("worker failed")


def test_service_lifecycle_is_idempotent_and_restartable() -> None:
    async def scenario() -> None:
        service = RecordingService()

        assert service.name == "RecordingService"
        assert service.state is ServiceState.IDLE
        assert await service.is_healthy() is False

        await service.start()
        await service.start()
        assert service.state is ServiceState.RUNNING
        assert service.start_count == 1
        assert await service.is_healthy() is True

        await service.stop()
        await service.stop()
        assert service.state is ServiceState.STOPPED
        assert service.stop_count == 1

        await service.start()
        assert service.state is ServiceState.RUNNING
        assert service.start_count == 2

    run(scenario())


def test_service_context_manager_starts_and_stops() -> None:
    async def scenario() -> None:
        service = RecordingService()
        async with service as entered:
            assert entered is service
            assert service.state is ServiceState.RUNNING
        assert service.state is ServiceState.STOPPED

    run(scenario())


def test_service_start_failure_can_be_cleaned_up() -> None:
    async def scenario() -> None:
        service = RecordingService(start_error=ValueError("startup failed"))
        with pytest.raises(ValueError, match="startup failed"):
            await service.start()
        assert service.state is ServiceState.FAILED

        await service.stop()
        assert service.state is ServiceState.STOPPED
        assert service.stop_count == 1

    run(scenario())


def test_service_stop_failure_can_be_retried() -> None:
    async def scenario() -> None:
        service = RecordingService(stop_error=ValueError("shutdown failed"))
        await service.start()
        with pytest.raises(ValueError, match="shutdown failed"):
            await service.stop()
        assert service.state is ServiceState.FAILED

        service.stop_error = None
        await service.stop()
        assert service.state is ServiceState.STOPPED
        assert service.stop_count == 2

    run(scenario())


def test_service_health_check_errors_return_false() -> None:
    async def scenario() -> None:
        service = RecordingService(health_error=RuntimeError("probe failed"))
        await service.start()
        assert await service.is_healthy() is False

    run(scenario())


def test_service_rejects_invalid_lifecycle_transitions() -> None:
    async def scenario() -> None:
        service = RecordingService()
        service._state = ServiceState.STARTING
        with pytest.raises(RuntimeError, match="Cannot start service"):
            await service.start()
        with pytest.raises(RuntimeError, match="Cannot stop service"):
            await service.stop()

    run(scenario())


def test_concurrent_start_calls_run_the_hook_once() -> None:
    async def scenario() -> None:
        entered = asyncio.Event()
        release = asyncio.Event()

        class SlowService(RecordingService):
            async def _start(self) -> None:
                self.start_count += 1
                entered.set()
                await release.wait()

        service = SlowService()
        first = asyncio.create_task(service.start())
        await entered.wait()
        second = asyncio.create_task(service.start())
        release.set()
        await asyncio.gather(first, second)
        assert service.start_count == 1
        assert service.state is ServiceState.RUNNING

    run(scenario())


def test_cancelled_start_leaves_a_cleanable_failed_service() -> None:
    async def scenario() -> None:
        entered = asyncio.Event()
        release = asyncio.Event()

        class SlowService(RecordingService):
            async def _start(self) -> None:
                entered.set()
                await release.wait()

        service = SlowService()
        task = asyncio.create_task(service.start())
        await entered.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert service.state is ServiceState.FAILED
        await service.stop()
        assert service.state is ServiceState.STOPPED

    run(scenario())


def test_background_service_stops_gracefully_and_restarts() -> None:
    async def scenario() -> None:
        worker = WaitingWorker()
        await worker.start()
        await worker.started.wait()
        assert worker.state is ServiceState.RUNNING
        assert await worker.is_healthy() is True

        await worker.stop()
        assert worker.stop_event.is_set()
        assert worker.exited.is_set()
        assert worker.state is ServiceState.STOPPED
        assert worker.failure is None

        await worker.start()
        await worker.started.wait()
        await worker.stop()
        assert worker.state is ServiceState.STOPPED

    run(scenario())


def test_background_service_reports_worker_failure_and_cleans_up() -> None:
    async def scenario() -> None:
        worker = FailingWorker(shutdown_timeout=0.05)
        await worker.start()
        await asyncio.sleep(0)
        assert worker.state is ServiceState.FAILED
        assert isinstance(worker.failure, ValueError)
        assert await worker.is_healthy() is False

        with pytest.raises(BackgroundServiceError) as raised:
            await worker.wait()
        assert isinstance(raised.value.__cause__, ValueError)
        await worker.stop()
        assert worker.state is ServiceState.STOPPED
        with pytest.raises(BackgroundServiceError):
            await worker.wait()

    run(scenario())


def test_background_service_unexpected_return_is_a_failure() -> None:
    class ReturningWorker(BackgroundService):
        async def run(self) -> None:
            return

    async def scenario() -> None:
        worker = ReturningWorker(shutdown_timeout=0.05)
        await worker.start()
        await asyncio.sleep(0)
        assert worker.state is ServiceState.FAILED
        assert isinstance(worker.failure, RuntimeError)
        with pytest.raises(BackgroundServiceError, match="failed"):
            await worker.wait()
        await worker.stop()

    run(scenario())


def test_background_service_cancels_a_worker_after_grace_period() -> None:
    class UncooperativeWorker(BackgroundService):
        def __init__(self) -> None:
            super().__init__(shutdown_timeout=0.02)
            self.started = asyncio.Event()
            self.cancelled = asyncio.Event()

        async def run(self) -> None:
            self.started.set()
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                self.cancelled.set()
                raise

    async def scenario() -> None:
        worker = UncooperativeWorker()
        await worker.start()
        await worker.started.wait()
        await worker.stop()
        assert worker.cancelled.is_set()
        assert worker.state is ServiceState.STOPPED

    run(scenario())


def test_background_service_stop_can_retry_timed_out_cancellation() -> None:
    class SlowCancellationWorker(BackgroundService):
        def __init__(self) -> None:
            super().__init__(shutdown_timeout=0.01)
            self.started = asyncio.Event()
            self.release = asyncio.Event()

        async def run(self) -> None:
            self.started.set()
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                await self.release.wait()

    async def scenario() -> None:
        worker = SlowCancellationWorker()
        await worker.start()
        await worker.started.wait()
        with pytest.raises(TimeoutError, match="did not finish cancellation"):
            await worker.stop()
        assert worker.state is ServiceState.FAILED

        worker.release.set()
        await worker.stop()
        assert worker.state is ServiceState.STOPPED

    run(scenario())


def test_background_service_records_unexpected_task_cancellation() -> None:
    async def scenario() -> None:
        worker = WaitingWorker()
        await worker.start()
        await worker.started.wait()
        assert worker._worker_task is not None
        worker._worker_task.cancel()

        with pytest.raises(BackgroundServiceError) as raised:
            await worker.wait()
        assert isinstance(raised.value.__cause__, RuntimeError)
        assert worker.state is ServiceState.FAILED
        await worker.stop()

    run(scenario())


@pytest.mark.parametrize("timeout", [-1.0, math.inf, -math.inf, math.nan])
def test_background_service_rejects_invalid_shutdown_timeout(timeout: float) -> None:
    with pytest.raises(ValueError, match="shutdown_timeout"):
        WaitingWorker(shutdown_timeout=timeout)


def test_background_service_allows_no_timeout_and_protocol_is_runtime_checkable() -> None:
    worker = WaitingWorker(shutdown_timeout=None)
    assert isinstance(worker, BackgroundServiceProtocol)


def test_service_state_is_a_string_enum() -> None:
    assert ServiceState.RUNNING == "running"
    assert str(ServiceState.STOPPED) == "stopped"
