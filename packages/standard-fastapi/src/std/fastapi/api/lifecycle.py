"""Coordinate injected background services with an ASGI application lifespan."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator, Awaitable, Callable, Sequence
from contextlib import AbstractAsyncContextManager, asynccontextmanager

from fastapi import FastAPI
from std.service import BackgroundServiceProtocol, ServiceState

logger = logging.getLogger(__name__)
SetupHandler = Callable[[], Awaitable[Sequence[BackgroundServiceProtocol]]]


class LifecycleManager:
    """Start services in order and stop them in reverse order.

    A service's stop hook is invoked even when its startup fails, allowing it
    to release resources acquired before the failure. Shutdown attempts every
    cleanup hook and groups errors after all services have been visited.
    """

    def __init__(
        self,
        services: Sequence[BackgroundServiceProtocol] = (),
        *,
        setup_handler: SetupHandler | None = None,
    ) -> None:
        """Create a manager for supplied services and an optional async factory."""
        self._services = list(services)
        if len({id(service) for service in self._services}) != len(self._services):
            raise ValueError("the same service instance cannot be registered twice")
        self._setup_handler = setup_handler
        self._active_services: list[BackgroundServiceProtocol] = []
        self._state = ServiceState.IDLE
        self._lock = asyncio.Lock()

    @property
    def status(self) -> ServiceState:
        """Return the lifecycle manager's current state."""
        return self._state

    def add_service(self, service: BackgroundServiceProtocol) -> None:
        """Register a service before startup."""
        if self._state in (ServiceState.STARTING, ServiceState.RUNNING, ServiceState.STOPPING):
            raise RuntimeError("services cannot be added while the lifecycle manager is active")
        if any(existing is service for existing in self._services):
            raise ValueError("the same service instance cannot be registered twice")
        self._services.append(service)

    def set_setup_handler(
        self,
        handler: SetupHandler,
    ) -> None:
        """Set an async factory for services created at application startup."""
        if self._state in (ServiceState.STARTING, ServiceState.RUNNING, ServiceState.STOPPING):
            raise RuntimeError("the setup handler cannot change while the manager is active")
        self._setup_handler = handler

    async def start(self) -> None:
        """Start registered and dynamically created services in order."""
        async with self._lock:
            if self._state is ServiceState.RUNNING:
                return
            if self._state in (ServiceState.STARTING, ServiceState.STOPPING):
                raise RuntimeError(f"cannot start lifecycle manager in state {self._state}")

            self._state = ServiceState.STARTING
            started: list[BackgroundServiceProtocol] = []
            cleanup_failures: list[BackgroundServiceProtocol] = []
            try:
                dynamic = await self._setup_handler() if self._setup_handler else ()
                services = [*self._services, *dynamic]
                if len({id(service) for service in services}) != len(services):
                    raise ValueError("the same service instance cannot be started twice")

                for service in services:
                    try:
                        await service.start()
                    except BaseException as startup_error:
                        cleanup_failures = await self._cleanup_after_start_failure(
                            service, started, startup_error
                        )
                        raise
                    started.append(service)
            except BaseException:
                self._active_services = list(reversed(cleanup_failures))
                self._state = ServiceState.FAILED
                raise

            self._active_services = started
            self._state = ServiceState.RUNNING
            logger.info("Started %d background services", len(started))

    async def stop(self) -> None:
        """Stop every active service in reverse order, attempting all cleanups."""
        async with self._lock:
            if self._state in (ServiceState.IDLE, ServiceState.STOPPED):
                return
            if self._state is ServiceState.STOPPING:
                return

            self._state = ServiceState.STOPPING
            errors: list[Exception] = []
            failed_services: list[BackgroundServiceProtocol] = []
            try:
                for service in reversed(self._active_services):
                    try:
                        await service.stop()
                    except Exception as error:
                        errors.append(error)
                        failed_services.append(service)
                        logger.exception("Failed to stop background service")
            except BaseException:
                self._state = ServiceState.FAILED
                raise

            self._active_services = list(reversed(failed_services))
            if errors:
                self._state = ServiceState.FAILED
                raise ExceptionGroup("one or more services failed to stop", errors)
            self._state = ServiceState.STOPPED
            logger.info("Stopped all background services")

    @asynccontextmanager
    async def lifespan(self) -> AsyncIterator[None]:
        """Run the managed services for the duration of an async context."""
        await self.start()
        try:
            yield
        finally:
            await self.stop()

    def fastapi_lifespan(
        self,
        setup_handler: SetupHandler | None = None,
    ) -> Callable[[FastAPI], AbstractAsyncContextManager[None]]:
        """Return an ASGI lifespan callable for :class:`FastAPI`."""
        if setup_handler is not None:
            self.set_setup_handler(setup_handler)

        @asynccontextmanager
        async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
            async with self.lifespan():
                yield

        return lifespan

    async def _cleanup_after_start_failure(
        self,
        failed_service: BackgroundServiceProtocol,
        started_services: list[BackgroundServiceProtocol],
        startup_error: BaseException,
    ) -> list[BackgroundServiceProtocol]:
        """Clean the failing service and every earlier service in reverse order."""
        cleanup_failures: list[BackgroundServiceProtocol] = []
        for service in (failed_service, *reversed(started_services)):
            try:
                await service.stop()
            except BaseException as cleanup_error:
                cleanup_failures.append(service)
                startup_error.add_note(
                    f"cleanup failed for {type(service).__name__}: {type(cleanup_error).__name__}"
                )
                logger.error(
                    "Cleanup failed for a background service after startup failure",
                    exc_info=(
                        type(cleanup_error),
                        cleanup_error,
                        cleanup_error.__traceback__,
                    ),
                )
        return cleanup_failures
