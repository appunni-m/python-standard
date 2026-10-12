"""Function decorators that add Redis caching to synchronous and asynchronous code."""

from __future__ import annotations

import hashlib
import inspect
import json
import logging
from collections.abc import Callable
from functools import wraps
from typing import Any, TypeVar, cast

from .client import RedisClient

logger = logging.getLogger(__name__)
F = TypeVar("F", bound=Callable[..., Any])
KeyBuilder = Callable[[Callable[..., Any], tuple[Any, ...], dict[str, Any]], str]
_CACHE_MISS = object()


def _generate_cache_key(
    func: Callable[..., Any], args: tuple[Any, ...], kwargs: dict[str, Any]
) -> str:
    """Build a deterministic key from a function identity and its arguments."""
    key_parts = [func.__module__, func.__qualname__]
    for argument in args:
        key_parts.append(_stable_argument(argument))
    for name in sorted(kwargs):
        key_parts.append(f"{name}={_stable_argument(kwargs[name])}")

    raw_key = ":".join(key_parts)
    if len(raw_key) <= 200:
        return f"cache:{raw_key}"
    digest = hashlib.sha256(raw_key.encode("utf-8", errors="backslashreplace")).hexdigest()
    return f"cache:{func.__name__[:64]}:{digest}"


def _stable_argument(value: Any) -> str:
    """Serialize JSON-compatible arguments consistently and fall back for custom objects."""
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)
    except (TypeError, ValueError):
        return str(value)


def _validate_ttl(ttl: int) -> None:
    """Reject invalid cache expiries at decoration time."""
    if isinstance(ttl, bool) or not isinstance(ttl, int) or ttl < 1:
        raise ValueError("ttl must be a positive integer")


def _key_with_prefix(
    func: Callable[..., Any],
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
    *,
    key_prefix: str | None,
    key_builder: KeyBuilder | None,
) -> str:
    """Build and validate one key for a cached function call."""
    key = (
        key_builder(func, args, kwargs)
        if key_builder is not None
        else _generate_cache_key(func, args, kwargs)
    )
    if not isinstance(key, str) or not key:
        raise ValueError("cache key builder must return a non-empty string")
    return f"{key_prefix}:{key}" if key_prefix else key


def _key_for_aside(
    func: Callable[..., Any],
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
    key_func: Callable[..., str] | None,
) -> str:
    """Build a cache-aside key from the optional argument-only key callback."""
    key = (
        key_func(*args, **kwargs)
        if key_func is not None
        else _generate_cache_key(func, args, kwargs)
    )
    if not isinstance(key, str) or not key:
        raise ValueError("key_func must return a non-empty string")
    return key


def cached(
    client: RedisClient,
    ttl: int = 3600,
    key_prefix: str | None = None,
    key_builder: KeyBuilder | None = None,
) -> Callable[[F], F]:
    """Cache function results, preserving whether the wrapped function is sync or async.

    Async functions use the asynchronous Redis pool. Regular functions use the
    synchronous pool and can be cleaned up with ``client.close_sync()``. Cache
    read and write failures are treated as misses so the original function still
    runs. The generated key can be removed with ``function.cache_invalidate(...)``.
    """
    _validate_ttl(ttl)
    if key_prefix is not None and not isinstance(key_prefix, str):
        raise ValueError("key_prefix must be a string or None")

    def decorate(func: F) -> F:
        if inspect.iscoroutinefunction(func):

            @wraps(func)
            async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
                key = _key_with_prefix(
                    func,
                    args,
                    kwargs,
                    key_prefix=key_prefix,
                    key_builder=key_builder,
                )
                try:
                    cached_value = await client.get(key, _CACHE_MISS)
                except Exception as error:
                    logger.warning("Cache read failed (%s)", type(error).__name__)
                    cached_value = _CACHE_MISS
                if cached_value is not _CACHE_MISS:
                    return cached_value

                result = await func(*args, **kwargs)
                try:
                    await client.set(key, result, ttl=ttl)
                except Exception as error:
                    logger.warning("Cache write failed (%s)", type(error).__name__)
                return result

            async def async_invalidate(*args: Any, **kwargs: Any) -> bool:
                """Invalidate this function's cached result for the supplied arguments."""
                key = _key_with_prefix(
                    func,
                    args,
                    kwargs,
                    key_prefix=key_prefix,
                    key_builder=key_builder,
                )
                try:
                    return await client.delete(key) > 0
                except Exception as error:
                    logger.warning("Cache invalidation failed (%s)", type(error).__name__)
                    return False

            cast(Any, async_wrapper).cache_invalidate = async_invalidate
            return cast(F, async_wrapper)

        @wraps(func)
        def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
            key = _key_with_prefix(
                func,
                args,
                kwargs,
                key_prefix=key_prefix,
                key_builder=key_builder,
            )
            cached_value = client._sync_get(key, _CACHE_MISS)
            if cached_value is not _CACHE_MISS:
                return cached_value

            result = func(*args, **kwargs)
            client._sync_set(key, result, ttl=ttl)
            return result

        def sync_invalidate(*args: Any, **kwargs: Any) -> bool:
            """Invalidate this function's cached result for the supplied arguments."""
            key = _key_with_prefix(
                func,
                args,
                kwargs,
                key_prefix=key_prefix,
                key_builder=key_builder,
            )
            return client._sync_delete(key)

        cast(Any, sync_wrapper).cache_invalidate = sync_invalidate
        return cast(F, sync_wrapper)

    return decorate


def cache_aside(
    client: RedisClient,
    ttl: int = 3600,
    key_func: Callable[..., str] | None = None,
) -> Callable[[F], F]:
    """Cache a function result with an optional argument-only key function.

    The decorated function retains its sync or async call behavior. Redis errors
    are treated as cache misses or failed writes, and a cached ``None`` remains
    distinguishable from a missing key.
    """
    _validate_ttl(ttl)

    def decorate(func: F) -> F:
        if inspect.iscoroutinefunction(func):

            @wraps(func)
            async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
                key = _key_for_aside(func, args, kwargs, key_func)
                try:
                    cached_value = await client.get(key, _CACHE_MISS)
                except Exception as error:
                    logger.warning("Cache read failed (%s)", type(error).__name__)
                    cached_value = _CACHE_MISS
                if cached_value is not _CACHE_MISS:
                    return cached_value

                result = await func(*args, **kwargs)
                try:
                    await client.set(key, result, ttl=ttl)
                except Exception as error:
                    logger.warning("Cache write failed (%s)", type(error).__name__)
                return result

            return cast(F, async_wrapper)

        @wraps(func)
        def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
            key = _key_for_aside(func, args, kwargs, key_func)
            cached_value = client._sync_get(key, _CACHE_MISS)
            if cached_value is not _CACHE_MISS:
                return cached_value
            result = func(*args, **kwargs)
            client._sync_set(key, result, ttl=ttl)
            return result

        return cast(F, sync_wrapper)

    return decorate
