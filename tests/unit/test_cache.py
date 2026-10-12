"""Unit coverage for the optional Redis cache package."""

from __future__ import annotations

import asyncio
import fnmatch
import inspect
import time
from typing import Any

import pytest

from std.cache import (
    DistributedLock,
    RedisClient,
    RedisConfig,
    cache_aside,
    cached,
    with_lock,
)


class MemoryRedis:
    """Small Redis protocol double with expiration and atomic lock scripts."""

    def __init__(self, *, decode_responses: bool = True) -> None:
        self.decode_responses = decode_responses
        self.values: dict[str, bytes] = {}
        self.expires: dict[str, float] = {}
        self.closed = False
        self.fail: set[str] = set()

    def _purge(self, key: str) -> None:
        expiry = self.expires.get(key)
        if expiry is not None and expiry <= time.monotonic():
            self.values.pop(key, None)
            self.expires.pop(key, None)

    def _value(self, value: bytes) -> str | bytes:
        return value.decode("utf-8") if self.decode_responses else value

    async def ping(self) -> bool:
        """Return a healthy response unless the test configures a connection failure."""
        if "ping" in self.fail:
            raise ConnectionError("unreachable")
        return True

    async def aclose(self) -> None:
        """Record that the fake async connection was closed."""
        self.closed = True

    async def get(self, key: str) -> str | bytes | None:
        """Return one stored value or simulate a Redis read failure."""
        if "get" in self.fail:
            raise ConnectionError("unreachable")
        self._purge(key)
        value = self.values.get(key)
        return self._value(value) if value is not None else None

    async def set(
        self,
        key: str,
        value: str | bytes,
        *,
        ex: int | None = None,
        nx: bool = False,
        xx: bool = False,
    ) -> bytes | None:
        """Store a value while honoring Redis expiry and conditional flags."""
        if "set" in self.fail:
            raise ConnectionError("unreachable")
        self._purge(key)
        exists = key in self.values
        if (nx and exists) or (xx and not exists):
            return None
        self.values[key] = value if isinstance(value, bytes) else value.encode("utf-8")
        if ex is None:
            self.expires.pop(key, None)
        else:
            self.expires[key] = time.monotonic() + ex
        return b"OK"

    async def delete(self, *keys: str) -> int:
        """Delete the provided keys and return the number that existed."""
        if "delete" in self.fail:
            raise ConnectionError("unreachable")
        count = 0
        for key in keys:
            self._purge(key)
            if key in self.values:
                self.values.pop(key)
                self.expires.pop(key, None)
                count += 1
        return count

    async def exists(self, *keys: str) -> int:
        """Count the keys currently present in the fake store."""
        if "exists" in self.fail:
            raise ConnectionError("unreachable")
        return sum(1 for key in keys if self._exists(key))

    def _exists(self, key: str) -> bool:
        self._purge(key)
        return key in self.values

    async def expire(self, key: str, ttl: int) -> bool:
        """Assign a new expiry to an existing key."""
        if "expire" in self.fail:
            raise ConnectionError("unreachable")
        if not self._exists(key):
            return False
        self.expires[key] = time.monotonic() + ttl
        return True

    async def ttl(self, key: str) -> int:
        """Return the Redis-style remaining expiry value for a key."""
        if "ttl" in self.fail:
            raise ConnectionError("unreachable")
        if not self._exists(key):
            return -2
        expiry = self.expires.get(key)
        return max(0, int(expiry - time.monotonic())) if expiry is not None else -1

    async def incrby(self, key: str, amount: int) -> int:
        """Increment a stored integer and return its new value."""
        if "incrby" in self.fail:
            raise ConnectionError("unreachable")
        current = int((await self.get(key)) or "0")
        result = current + amount
        self.values[key] = str(result).encode()
        self.expires.pop(key, None)
        return result

    async def decrby(self, key: str, amount: int) -> int:
        """Decrement a stored integer and return its new value."""
        if "decrby" in self.fail:
            raise ConnectionError("unreachable")
        return await self.incrby(key, -amount)

    async def scan(self, cursor: int, *, match: str, count: int) -> tuple[int, list[str | bytes]]:
        """Return a page of keys matching the requested Redis glob."""
        if "scan" in self.fail:
            raise ConnectionError("unreachable")
        keys = sorted(key for key in self.values if fnmatch.fnmatch(key, match))
        batch = keys[cursor : cursor + count]
        next_cursor = cursor + len(batch)
        if next_cursor >= len(keys):
            return 0, [self._value(key.encode()) for key in batch]
        return next_cursor, [self._value(key.encode()) for key in batch]

    async def eval(self, script: str, _numkeys: int, key: str, token: str, *args: Any) -> int:
        """Execute the lock release or renewal script against the fake store."""
        self._purge(key)
        current = self.values.get(key)
        if current != token.encode():
            return 0
        if 'redis.call("del"' in script:
            self.values.pop(key, None)
            self.expires.pop(key, None)
            return 1
        self.expires[key] = time.monotonic() + int(args[0])
        return 1


class SyncMemoryRedis:
    """Synchronous Redis subset sharing data with the async test double."""

    def __init__(self, server: MemoryRedis) -> None:
        self.server = server
        self.closed = False

    def get(self, key: str) -> str | bytes | None:
        """Return one stored value through the sync Redis interface."""
        self.server._purge(key)
        value = self.server.values.get(key)
        return self.server._value(value) if value is not None else None

    def set(
        self, key: str, value: str | bytes, *, ex: int | None = None, nx: bool = False
    ) -> bytes | None:
        """Store one value through the sync Redis interface."""
        if "set" in self.server.fail:
            raise ConnectionError("unreachable")
        self.server._purge(key)
        if nx and key in self.server.values:
            return None
        self.server.values[key] = value if isinstance(value, bytes) else value.encode()
        if ex is not None:
            self.server.expires[key] = time.monotonic() + ex
        else:
            self.server.expires.pop(key, None)
        return b"OK"

    def delete(self, key: str) -> int:
        """Delete one key and return whether it was present."""
        return int(key in self.server.values and self.server.values.pop(key, None) is not None)

    def exists(self, key: str) -> int:
        """Return one when the key exists in the shared fake store."""
        return int(self.server._exists(key))

    def eval(self, script: str, _numkeys: int, key: str, token: str) -> int:
        """Run the fake lock release script with its ownership check."""
        current = self.server.values.get(key)
        if current != token.encode():
            return 0
        if 'redis.call("del"' in script:
            self.server.values.pop(key, None)
            self.server.expires.pop(key, None)
            return 1
        return 0

    def close(self) -> None:
        """Record that the sync Redis connection was closed."""
        self.closed = True


def make_client(
    *, prefix: str = "", decode_responses: bool = True
) -> tuple[RedisClient, MemoryRedis]:
    """Build a configured client backed by the in-memory Redis double."""
    client = RedisClient(RedisConfig(key_prefix=prefix, decode_responses=decode_responses))
    redis = MemoryRedis(decode_responses=decode_responses)
    client._client = redis  # type: ignore[assignment]
    client._get_sync_client = lambda: SyncMemoryRedis(redis)  # type: ignore[method-assign]
    return client, redis


def test_public_exports_are_explicit() -> None:
    from std import cache

    assert cache.__all__ == [
        "DistributedLock",
        "RedisClient",
        "RedisConfig",
        "cache_aside",
        "cached",
        "with_lock",
    ]


def test_redis_config_defaults_validation_and_secret_repr() -> None:
    config = RedisConfig(password="hidden")
    assert config.host == "localhost"
    assert config.port == 6379
    assert config.key_prefix == ""
    assert "hidden" not in repr(config)

    for kwargs in (
        {"host": " "},
        {"username": 4},
        {"password": 4},
        {"port": True},
        {"port": 65536},
        {"db": -1},
        {"max_connections": 0},
        {"socket_timeout": float("nan")},
        {"socket_connect_timeout": 0},
    ):
        with pytest.raises(ValueError):
            RedisConfig(**kwargs)  # type: ignore[arg-type]


def test_client_requires_connection_and_validates_keys() -> None:
    client = RedisClient()
    with pytest.raises(RuntimeError, match="Call connect"):
        _ = client.client
    with pytest.raises(ValueError, match="non-empty"):
        client._get_key("")


def test_client_connect_is_idempotent_and_closes_on_shutdown(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = RedisClient()
    redis = MemoryRedis()
    sync_redis = SyncMemoryRedis(redis)
    client._sync_client = sync_redis  # type: ignore[assignment]
    monkeypatch.setattr(client, "_make_async_client", lambda: redis)

    async def scenario() -> None:
        await client.connect()
        first = client.client
        await client.connect()
        assert client.client is first
        await client.close()
        assert redis.closed
        assert sync_redis.closed
        with pytest.raises(RuntimeError, match="Call connect"):
            _ = client.client

    asyncio.run(scenario())


def test_async_context_manager_connects_and_closes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = RedisClient()
    redis = MemoryRedis()
    monkeypatch.setattr(client, "_make_async_client", lambda: redis)

    async def scenario() -> None:
        async with client as connected:
            assert connected is client
            assert client.client is redis
        assert redis.closed

    asyncio.run(scenario())


def test_sync_context_manager_closes_sync_pool() -> None:
    client = RedisClient()
    sync_redis = SyncMemoryRedis(MemoryRedis())
    client._sync_client = sync_redis  # type: ignore[assignment]

    with client as connected:
        assert connected is client

    assert sync_redis.closed


def test_connect_failure_closes_unpublished_client(monkeypatch: pytest.MonkeyPatch) -> None:
    client = RedisClient()
    redis = MemoryRedis()
    redis.fail.add("ping")
    monkeypatch.setattr(client, "_make_async_client", lambda: redis)

    async def scenario() -> None:
        with pytest.raises(ConnectionError):
            await client.connect()
        assert redis.closed
        with pytest.raises(RuntimeError, match="Call connect"):
            _ = client.client

    asyncio.run(scenario())


def test_client_json_string_ttl_conditions_prefix_and_helpers() -> None:
    client, _ = make_client(prefix="app:")

    async def scenario() -> None:
        assert await client.set("text", "123")
        assert await client.get("text") == "123"
        assert await client.set("none", None, ttl=5)
        assert await client.get("none", "missing") is None
        assert await client.set("data", {"x": [1, True]})
        assert await client.get("data") == {"x": [1, True]}

        assert await client.set("conditional", "first", nx=True)
        assert not await client.set("conditional", "second", nx=True)
        assert await client.set("conditional", "second", xx=True)
        assert await client.get("conditional") == "second"
        with pytest.raises(ValueError, match="cannot both"):
            await client.set("conditional", "value", nx=True, xx=True)
        with pytest.raises(ValueError, match="must be booleans"):
            await client.set("conditional", "value", nx="yes")  # type: ignore[arg-type]
        with pytest.raises(ValueError, match="positive integer"):
            await client.set("conditional", "value", ttl=0)

        assert await client.increment("counter", 2) == 2
        assert await client.decrement("counter") == 1
        assert await client.ttl("absent") == -2
        assert await client.expire("counter", 5)
        assert await client.ttl("counter") > 0
        assert await client.exists("counter", "absent") == 1
        assert await client.scan_keys("*")
        assert await client.flush_pattern("counter") == 1
        assert await client.get("counter") is None
        assert await client.ping()
        assert await client.delete("text", "none", "data") == 3

    asyncio.run(scenario())


def test_client_returns_raw_non_json_and_bytes_when_decode_is_disabled() -> None:
    client, redis = make_client(decode_responses=False)
    redis.values["raw"] = b"plain"
    redis.values["json"] = b'{"answer":42}'

    async def scenario() -> None:
        assert await client.get("raw") == b"plain"
        assert await client.get("json") == {"answer": 42}
        assert await client.set("stored-bytes", b"abc")
        assert await client.get("stored-bytes") == b"abc"

    asyncio.run(scenario())


def test_client_redis_errors_use_documented_fallbacks() -> None:
    client, redis = make_client()
    redis.fail.update(
        {
            "get",
            "set",
            "delete",
            "exists",
            "expire",
            "ttl",
            "incrby",
            "decrby",
            "scan",
            "ping",
        }
    )

    async def scenario() -> None:
        assert await client.get("key", "fallback") == "fallback"
        assert not await client.set("key", "value")
        assert await client.delete("key") == 0
        assert await client.exists("key") == 0
        assert not await client.expire("key", 1)
        assert await client.ttl("key") == -2
        assert await client.increment("key") == 0
        assert await client.decrement("key") == 0
        assert await client.scan_keys("*") == []
        assert await client.flush_pattern("*") == 0
        assert not await client.ping()

    asyncio.run(scenario())


def test_tls_connection_uses_redis_ssl_options() -> None:
    client = RedisClient(RedisConfig(ssl=True))
    redis = client._make_async_client()
    try:
        assert redis.connection_pool.connection_class.__name__ == "SSLConnection"
    finally:
        asyncio.run(redis.aclose())


def test_cached_supports_sync_async_none_and_invalidation(monkeypatch: pytest.MonkeyPatch) -> None:
    client, _ = make_client()
    calls = {"sync": 0, "async": 0}

    @cached(client, ttl=10, key_prefix="manual")
    def sync_value(code: str) -> str:
        calls["sync"] += 1
        return code.upper()

    @cached(client, ttl=10, key_builder=lambda func, args, kwargs: f"special:{args[0]}")
    async def async_none(code: str) -> None:
        calls["async"] += 1
        return None

    assert not inspect.iscoroutinefunction(sync_value)
    assert inspect.iscoroutinefunction(async_none)
    assert sync_value("a") == "A"
    assert sync_value("a") == "A"
    assert calls["sync"] == 1
    assert sync_value.cache_invalidate("a")
    assert sync_value("a") == "A"
    assert calls["sync"] == 2

    async def scenario() -> None:
        await async_none("x")
        await async_none("x")
        assert calls["async"] == 1
        assert await async_none.cache_invalidate("x")
        await async_none("x")
        assert calls["async"] == 2

    asyncio.run(scenario())


def test_cache_aside_supports_sync_and_async_custom_keys() -> None:
    client, _ = make_client()
    calls = 0

    @cache_aside(client, ttl=3, key_func=lambda value: f"lookup:{value}")
    def sync_lookup(value: int) -> dict[str, int]:
        nonlocal calls
        calls += 1
        return {"value": value}

    assert sync_lookup(7) == {"value": 7}
    assert sync_lookup(7) == {"value": 7}
    assert calls == 1

    async_calls = 0

    @cache_aside(client, ttl=3)
    async def async_lookup(value: int) -> int:
        nonlocal async_calls
        async_calls += 1
        return value

    async def scenario() -> None:
        assert await async_lookup(8) == 8
        assert await async_lookup(8) == 8
        assert async_calls == 1

    asyncio.run(scenario())


def test_cache_decorators_fail_open_and_validate_inputs() -> None:
    client, redis = make_client()
    redis.fail.add("get")
    calls = 0

    @cached(client)
    async def compute() -> int:
        nonlocal calls
        calls += 1
        return 5

    async def scenario() -> None:
        assert await compute() == 5
        assert await compute() == 5
        assert calls == 2

    asyncio.run(scenario())

    with pytest.raises(ValueError, match="positive integer"):
        cached(client, ttl=0)
    with pytest.raises(ValueError, match="positive integer"):
        cache_aside(client, ttl=-1)


def test_generated_keys_are_deterministic_and_bounded() -> None:
    def sample(value: Any) -> Any:
        return value

    from std.cache.decorators import _generate_cache_key

    first = _generate_cache_key(sample, (), {"value": {"b": 2, "a": 1}})
    second = _generate_cache_key(sample, (), {"value": {"a": 1, "b": 2}})
    long_key = _generate_cache_key(sample, ("x" * 500,), {})
    assert first == second
    assert len(long_key) <= 200
    assert "sample" in long_key


def test_distributed_lock_expiry_contention_and_token_checked_release() -> None:
    client, redis = make_client(prefix="app:")

    async def scenario() -> None:
        first = DistributedLock(client, "resource", timeout=2)
        second = DistributedLock(client, "resource", timeout=2)
        assert await first.acquire(blocking=False)
        assert await first.is_locked()
        assert first.locked
        assert not await second.acquire(blocking=False)
        assert not await second.acquire(timeout=0.02)

        key = client._get_key(first.lock_name)
        redis.expires[key] = time.monotonic() - 1
        assert await second.acquire(blocking=False)
        assert not await first.release()
        assert await second.release()
        assert not await second.is_locked()
        assert not first.locked

    asyncio.run(scenario())


def test_lock_wait_timeout_must_be_finite() -> None:
    client, _ = make_client()
    lock = DistributedLock(client, "valid", timeout=1)

    async def scenario() -> None:
        for timeout in (float("nan"), float("inf"), -1, True):
            with pytest.raises(ValueError, match="timeout"):
                await lock.acquire(timeout=timeout)  # type: ignore[arg-type]

    asyncio.run(scenario())


def test_distributed_lock_auto_renewal_and_context_release() -> None:
    client, redis = make_client()

    async def scenario() -> None:
        lock = DistributedLock(client, "renew", timeout=1, auto_renewal=True)
        async with lock as acquired:
            assert acquired
            assert lock._renewal_task is not None
            key = client._get_key(lock.lock_name)
            redis.expires[key] = time.monotonic() + 0.35
            await asyncio.sleep(0.4)
            assert redis.expires[key] > time.monotonic() + 0.5
        assert not await lock.is_locked()
        assert lock._renewal_task is None

    asyncio.run(scenario())


def test_with_lock_async_and_sync_release_on_exception() -> None:
    client, _ = make_client()

    @with_lock(client, "async-task", timeout=2, blocking=False)
    async def async_work() -> str:
        raise LookupError("work failed")

    @with_lock(client, "sync-task", timeout=2, blocking=False)
    def sync_work() -> str:
        raise LookupError("work failed")

    async def scenario() -> None:
        with pytest.raises(LookupError, match="work failed"):
            await async_work()
        assert await client.exists("lock:async-task") == 0

    asyncio.run(scenario())
    with pytest.raises(LookupError, match="work failed"):
        sync_work()


def test_lock_configuration_rejects_invalid_values() -> None:
    client = RedisClient()
    for name, timeout in (("", 1), ("valid", 0), ("valid", True)):
        with pytest.raises(ValueError):
            DistributedLock(client, name, timeout=timeout)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="positive integer"):
        with_lock(client, "valid", timeout=0)


def test_lock_acquisition_propagates_redis_errors() -> None:
    client, redis = make_client()
    redis.fail.add("set")
    lock = DistributedLock(client, "unavailable", timeout=1)

    @with_lock(client, "sync-unavailable", timeout=1, blocking=False)
    def sync_work() -> str:
        return "should not run"

    async def scenario() -> None:
        with pytest.raises(ConnectionError, match="unreachable"):
            await lock.acquire(blocking=False)

    asyncio.run(scenario())
    with pytest.raises(ConnectionError, match="unreachable"):
        sync_work()
