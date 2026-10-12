"""Application lifecycle wiring for already-constructed background services."""

from collections.abc import AsyncIterator, Callable, Sequence
from contextlib import AbstractAsyncContextManager, AsyncExitStack, asynccontextmanager

from fastapi import FastAPI

from example_app.core.services import BackgroundService


def create_lifespan(
    background_services: Sequence[BackgroundService],
) -> Callable[[FastAPI], AbstractAsyncContextManager[None]]:
    """Create an ASGI lifespan that starts services and stops them in reverse order."""
    services = tuple(background_services)

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        async with AsyncExitStack() as stack:
            for service in services:
                stack.push_async_callback(service.stop)
                await service.start()
            yield

    return lifespan
