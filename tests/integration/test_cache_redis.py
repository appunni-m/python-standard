"""Redis end-to-end behavior against a real Redis Testcontainer."""

from __future__ import annotations

import asyncio
import os
from collections.abc import Iterator

import pytest

from std.cache import DistributedLock, RedisClient, RedisConfig, cache_aside, cached


@pytest.fixture(scope="module")
def redis_endpoint() -> Iterator[tuple[str, int]]:
    """Start Redis through Testcontainers or report Docker as unavailable."""
    import docker
    from testcontainers.community.redis import RedisContainer

    try:
        docker.from_env().ping()
    except Exception as error:
        if os.environ.get("STD_REQUIRE_DOCKER") == "1":
            pytest.fail(f"Docker is required for cache E2E: {type(error).__name__}", pytrace=False)
        pytest.skip(f"Docker is unavailable: {type(error).__name__}")

    with RedisContainer("redis:7-alpine") as container:
        host = container.get_container_host_ip()
        port = int(container.get_exposed_port(6379))
        yield host, port


@pytest.mark.e2e
@pytest.mark.integration
def test_redis_serialization_decorators_ttl_and_locks(
    redis_endpoint: tuple[str, int],
) -> None:
    """Exercise cache values, decorator call behavior, and lease safety on Redis."""
    host, port = redis_endpoint

    async def scenario() -> None:
        client = RedisClient(RedisConfig(host=host, port=port, key_prefix="std-cache-e2e:"))
        await client.connect()
        try:
            assert await client.ping()
            assert await client.set("mapping", {"ready": True}, ttl=10)
            assert await client.get("mapping") == {"ready": True}
            assert await client.set("numeric-string", "123")
            assert await client.get("numeric-string") == "123"
            assert await client.set("json-null", None)
            assert await client.get("json-null", "missing") is None

            assert await client.set("short-lived", "value", ttl=1)
            assert 0 <= await client.ttl("short-lived") <= 1
            await asyncio.sleep(1.1)
            assert await client.get("short-lived", "expired") == "expired"
            assert await client.ttl("short-lived") == -2

            async_calls = 0

            @cached(client, ttl=10, key_prefix="e2e")
            async def async_lookup(identifier: str) -> dict[str, str]:
                nonlocal async_calls
                async_calls += 1
                return {"identifier": identifier}

            assert await async_lookup("async") == {"identifier": "async"}
            assert await async_lookup("async") == {"identifier": "async"}
            assert async_calls == 1
            assert await async_lookup.cache_invalidate("async")
            assert await async_lookup("async") == {"identifier": "async"}
            assert async_calls == 2

            sync_calls = 0

            @cache_aside(client, ttl=10, key_func=lambda identifier: f"sync:{identifier}")
            def sync_lookup(identifier: str) -> str:
                nonlocal sync_calls
                sync_calls += 1
                return identifier.upper()

            assert sync_lookup("key") == "KEY"
            assert sync_lookup("key") == "KEY"
            assert sync_calls == 1

            first = DistributedLock(client, "expiring", timeout=1)
            second = DistributedLock(client, "expiring", timeout=1)
            assert await first.acquire(blocking=False)
            assert await first.is_locked()
            assert not await second.acquire(blocking=False)
            await asyncio.sleep(1.1)
            assert await second.acquire(blocking=False)
            assert not await first.release()
            assert await second.release()
            assert not await second.is_locked()

            renewing = DistributedLock(client, "renewing", timeout=1, auto_renewal=True)
            assert await renewing.acquire(blocking=False)
            await asyncio.sleep(1.3)
            assert await renewing.is_locked()
            assert await renewing.release()
            assert not await renewing.is_locked()
        finally:
            await client.close()

    asyncio.run(scenario())
