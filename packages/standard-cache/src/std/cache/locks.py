"""Redis-backed distributed locks and sync/async lock decorators."""

from __future__ import annotations

import asyncio
import inspect
import logging
import math
import time
import uuid
from collections.abc import Awaitable, Callable
from contextlib import suppress
from functools import wraps
from typing import Any, TypeVar, cast

from .client import RedisClient

logger = logging.getLogger(__name__)
F = TypeVar("F", bound=Callable[..., Any])
_RELEASE_SCRIPT = """
if redis.call("get", KEYS[1]) == ARGV[1] then
    return redis.call("del", KEYS[1])
else
    return 0
end
"""
_RENEW_SCRIPT = """
if redis.call("get", KEYS[1]) == ARGV[1] then
    return redis.call("expire", KEYS[1], ARGV[2])
else
    return 0
end
"""
_POLL_INTERVAL_SECONDS = 0.1


def _validate_lock(lock_name: str, timeout: int) -> None:
    """Validate a lock name and its Redis lease duration."""
    if not isinstance(lock_name, str) or not lock_name.strip():
        raise ValueError("lock_name must be a non-empty string")
    if isinstance(timeout, bool) or not isinstance(timeout, int) or timeout < 1:
        raise ValueError("timeout must be a positive integer")


class DistributedLock:
    """A token-checked Redis lock with optional lease renewal.

    Lock acquisition uses Redis ``SET NX EX`` and release compares the unique
    token atomically before deleting the key. A lease expiry therefore cannot
    let an old holder release a newer holder's lock.
    """

    def __init__(
        self,
        client: RedisClient,
        lock_name: str,
        timeout: int = 10,
        auto_renewal: bool = False,
    ) -> None:
        """Create a lock manager; the Redis lock is acquired only by :meth:`acquire`."""
        _validate_lock(lock_name, timeout)
        if not isinstance(auto_renewal, bool):
            raise ValueError("auto_renewal must be a boolean")
        self.client = client
        self.lock_name = f"lock:{lock_name}"
        self.timeout = timeout
        self.auto_renewal = auto_renewal
        self._lock_value = str(uuid.uuid4())
        self._renewal_task: asyncio.Task[None] | None = None

    async def acquire(self, blocking: bool = True, timeout: float | None = None) -> bool:
        """Acquire the lock, optionally retrying until a wait timeout expires."""
        if not isinstance(blocking, bool):
            raise ValueError("blocking must be a boolean")
        if timeout is not None and (
            isinstance(timeout, bool)
            or not isinstance(timeout, (int, float))
            or not math.isfinite(timeout)
            or timeout < 0
        ):
            raise ValueError("timeout must be a non-negative number or None")
        loop = asyncio.get_running_loop()
        started = loop.time()
        while True:
            full_key = self.client._get_key(self.lock_name)
            acquired = await cast(
                Awaitable[str | None],
                self.client.client.set(
                    full_key,
                    self._lock_value.encode("ascii"),
                    ex=self.timeout,
                    nx=True,
                ),
            )
            if acquired:
                if self.auto_renewal:
                    self._renewal_task = asyncio.create_task(self._renew_loop())
                logger.debug("Acquired Redis lock")
                return True
            if not blocking:
                return False
            if timeout is not None:
                remaining = timeout - (loop.time() - started)
                if remaining <= 0:
                    return False
                await asyncio.sleep(min(_POLL_INTERVAL_SECONDS, remaining))
            else:
                await asyncio.sleep(_POLL_INTERVAL_SECONDS)

    async def release(self) -> bool:
        """Release the lock only if its unique token still owns the Redis key."""
        task = self._renewal_task
        self._renewal_task = None
        if task is not None and task is not asyncio.current_task():
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task

        try:
            result = await cast(
                Awaitable[int],
                self.client.client.eval(
                    _RELEASE_SCRIPT,
                    1,
                    self.client._get_key(self.lock_name),
                    self._lock_value,
                ),
            )
        except Exception as error:
            logger.warning("Redis lock release failed (%s)", type(error).__name__)
            return False
        released = bool(result)
        if not released:
            logger.debug("Redis lock was not released because its token no longer owns it")
        return released

    async def is_locked(self) -> bool:
        """Check asynchronously whether any process currently holds this lock name."""
        return await self.client.exists(self.lock_name) > 0

    @property
    def locked(self) -> bool:
        """Synchronously check whether any process currently holds this lock name.

        This compatibility property performs a blocking Redis request. Prefer
        :meth:`is_locked` from asynchronous code.
        """
        try:
            return bool(self.client._get_sync_client().exists(self.client._get_key(self.lock_name)))
        except Exception as error:
            logger.warning("Redis lock status check failed (%s)", type(error).__name__)
            return False

    async def _renew_loop(self) -> None:
        """Extend the lease while the Redis token still belongs to this lock."""
        interval = self.timeout / 3
        try:
            while True:
                await asyncio.sleep(interval)
                renewed = await cast(
                    Awaitable[int],
                    self.client.client.eval(
                        _RENEW_SCRIPT,
                        1,
                        self.client._get_key(self.lock_name),
                        self._lock_value,
                        self.timeout,
                    ),
                )
                if not renewed:
                    logger.debug("Redis lock renewal stopped after ownership changed")
                    return
        except asyncio.CancelledError:
            raise
        except Exception as error:
            logger.warning("Redis lock renewal failed (%s)", type(error).__name__)

    async def __aenter__(self) -> bool:
        """Acquire this lock when entering an asynchronous context manager."""
        if not await self.acquire():
            raise RuntimeError(f"Failed to acquire lock: {self.lock_name}")
        return True

    async def __aexit__(self, exc_type: object, exc: object, traceback: object) -> bool:
        """Release the lock on exit without suppressing an exception from the body."""
        await self.release()
        return False


def with_lock(
    client: RedisClient,
    lock_name: str,
    timeout: int = 10,
    blocking: bool = True,
) -> Callable[[F], F]:
    """Run a synchronous or asynchronous function while holding a Redis lock.

    When ``blocking`` is false, the wrapper raises :class:`RuntimeError` if
    another holder owns the lock. The lock is released even when the function
    raises.
    """
    _validate_lock(lock_name, timeout)
    if not isinstance(blocking, bool):
        raise ValueError("blocking must be a boolean")

    def decorate(func: F) -> F:
        if inspect.iscoroutinefunction(func):

            @wraps(func)
            async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
                lock = DistributedLock(client, lock_name, timeout=timeout)
                if not await lock.acquire(blocking=blocking):
                    raise RuntimeError(f"Failed to acquire lock: {lock.lock_name}")
                try:
                    return await func(*args, **kwargs)
                finally:
                    await lock.release()

            return cast(F, async_wrapper)

        @wraps(func)
        def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
            full_key = client._get_key(f"lock:{lock_name}")
            lock_value = str(uuid.uuid4())
            redis_client = client._get_sync_client()
            while True:
                acquired = redis_client.set(
                    full_key, lock_value.encode("ascii"), ex=timeout, nx=True
                )
                if acquired:
                    break
                if not blocking:
                    raise RuntimeError(f"Failed to acquire lock: lock:{lock_name}")
                time.sleep(_POLL_INTERVAL_SECONDS)

            try:
                return func(*args, **kwargs)
            finally:
                try:
                    redis_client.eval(_RELEASE_SCRIPT, 1, full_key, lock_value)
                except Exception as error:
                    logger.warning("Redis lock release failed (%s)", type(error).__name__)

        return cast(F, sync_wrapper)

    return decorate
