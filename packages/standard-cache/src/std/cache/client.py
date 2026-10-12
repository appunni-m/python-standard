"""Async and sync Redis client helpers with JSON values and key prefixes."""

from __future__ import annotations

import asyncio
import json
import logging
import math
import threading
from collections.abc import Awaitable
from dataclasses import dataclass, field
from typing import Any, cast

from redis import Redis as SyncRedis
from redis.asyncio import Redis as AsyncRedis

logger = logging.getLogger(__name__)


@dataclass
class RedisConfig:
    """Connection settings shared by the asynchronous and synchronous Redis clients."""

    host: str = "localhost"
    port: int = 6379
    db: int = 0
    password: str | None = field(default=None, repr=False)
    username: str | None = None
    ssl: bool = False
    socket_timeout: float = 5.0
    socket_connect_timeout: float = 5.0
    max_connections: int = 50
    decode_responses: bool = True
    key_prefix: str = ""

    def __post_init__(self) -> None:
        """Reject invalid connection values before a socket is opened."""
        if not isinstance(self.host, str) or not self.host.strip():
            raise ValueError("host must be a non-empty string")
        if self.username is not None and not isinstance(self.username, str):
            raise ValueError("username must be a string or None")
        if self.password is not None and not isinstance(self.password, str):
            raise ValueError("password must be a string or None")
        if (
            isinstance(self.port, bool)
            or not isinstance(self.port, int)
            or not 1 <= self.port <= 65535
        ):
            raise ValueError("port must be an integer between 1 and 65535")
        if isinstance(self.db, bool) or not isinstance(self.db, int) or self.db < 0:
            raise ValueError("db must be a non-negative integer")
        if isinstance(self.max_connections, bool) or not isinstance(self.max_connections, int):
            raise ValueError("max_connections must be a positive integer")
        if self.max_connections < 1:
            raise ValueError("max_connections must be a positive integer")
        if not isinstance(self.ssl, bool):
            raise ValueError("ssl must be a boolean")
        if not isinstance(self.decode_responses, bool):
            raise ValueError("decode_responses must be a boolean")
        if not isinstance(self.key_prefix, str):
            raise ValueError("key_prefix must be a string")
        for name, value in (
            ("socket_timeout", self.socket_timeout),
            ("socket_connect_timeout", self.socket_connect_timeout),
        ):
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(value)
                or value <= 0
            ):
                raise ValueError(f"{name} must be a positive number")


class RedisClient:
    """Wrap Redis commands with JSON serialization, key prefixing, and fail-soft helpers.

    Call :meth:`connect` once during asynchronous application startup and :meth:`close`
    during shutdown. Synchronous decorators use a separate lazily opened connection;
    close it with :meth:`close_sync` or by using the client as a synchronous context
    manager.
    """

    def __init__(self, config: RedisConfig | None = None) -> None:
        """Create a client manager without opening a Redis connection."""
        self.config = config or RedisConfig()
        self._client: AsyncRedis | None = None
        self._sync_client: SyncRedis | None = None
        self._lifecycle_lock = asyncio.Lock()
        self._sync_lock = threading.Lock()

    async def connect(self) -> None:
        """Open and ping the asynchronous Redis connection; repeated calls are safe."""
        async with self._lifecycle_lock:
            if self._client is not None:
                return
            candidate = self._make_async_client()
            try:
                await cast(Awaitable[bool], candidate.ping())
            except Exception:
                await candidate.aclose()
                logger.exception("Redis connection check failed")
                raise
            self._client = candidate
            logger.info("Connected to Redis")

    async def close(self) -> None:
        """Close both Redis connection pools and reset the manager for reuse."""
        async with self._lifecycle_lock:
            client = self._client
            self._client = None
            try:
                if client is not None:
                    await client.aclose()
            finally:
                self.close_sync()
        logger.info("Redis connection pools closed")

    def close_sync(self) -> None:
        """Close the synchronous pool used by decorators on regular functions."""
        with self._sync_lock:
            client = self._sync_client
            self._sync_client = None
        if client is not None:
            client.close()

    async def __aenter__(self) -> RedisClient:
        """Connect on entry to an asynchronous context manager."""
        await self.connect()
        return self

    async def __aexit__(self, exc_type: object, exc: object, traceback: object) -> None:
        """Close connection pools on exit from an asynchronous context manager."""
        await self.close()

    def __enter__(self) -> RedisClient:
        """Return this manager for synchronous decorator use."""
        if self._client is not None:
            raise RuntimeError("Use 'async with' after opening the asynchronous Redis client")
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        """Close the synchronous decorator connection on context exit."""
        self.close_sync()

    @property
    def client(self) -> AsyncRedis:
        """Return the connected asynchronous Redis client."""
        if self._client is None:
            raise RuntimeError("Redis client not connected. Call connect() first.")
        return self._client

    def _get_key(self, key: str) -> str:
        """Return a validated key with the configured prefix applied."""
        if not isinstance(key, str) or not key:
            raise ValueError("key must be a non-empty string")
        return f"{self.config.key_prefix}{key}"

    async def get(self, key: str, default: Any = None) -> Any:
        """Read a value, decoding JSON and returning ``default`` on misses or Redis errors."""
        full_key = self._get_key(key)
        try:
            value = await self.client.get(full_key)
        except Exception as error:
            logger.warning("Redis GET failed (%s)", type(error).__name__)
            return default
        if value is None:
            return default
        return self._decode_value(value)

    async def set(
        self,
        key: str,
        value: Any,
        ttl: int | None = None,
        nx: bool = False,
        xx: bool = False,
    ) -> bool:
        """Write JSON-compatible values with optional expiry and Redis NX/XX conditions."""
        full_key = self._get_key(key)
        self._validate_ttl(ttl)
        if not isinstance(nx, bool) or not isinstance(xx, bool):
            raise ValueError("nx and xx must be booleans")
        if nx and xx:
            raise ValueError("nx and xx cannot both be true")
        try:
            encoded = value if isinstance(value, bytes) else json.dumps(value, ensure_ascii=False)
            result = await self.client.set(full_key, encoded, ex=ttl, nx=nx, xx=xx)
            return bool(result)
        except Exception as error:
            logger.warning("Redis SET failed (%s)", type(error).__name__)
            return False

    async def delete(self, *keys: str) -> int:
        """Delete keys after applying the configured prefix; return zero on Redis errors."""
        if not keys:
            return 0
        full_keys = [self._get_key(key) for key in keys]
        try:
            return int(await self.client.delete(*full_keys))
        except Exception as error:
            logger.warning("Redis DELETE failed (%s)", type(error).__name__)
            return 0

    async def exists(self, *keys: str) -> int:
        """Return the number of supplied keys that exist, or zero on Redis errors."""
        if not keys:
            return 0
        full_keys = [self._get_key(key) for key in keys]
        try:
            return int(await self.client.exists(*full_keys))
        except Exception as error:
            logger.warning("Redis EXISTS failed (%s)", type(error).__name__)
            return 0

    async def expire(self, key: str, ttl: int) -> bool:
        """Set a positive whole-second expiry for an existing key."""
        full_key = self._get_key(key)
        self._validate_ttl(ttl)
        if ttl is None:
            raise ValueError("ttl must be a positive integer")
        try:
            return bool(await self.client.expire(full_key, ttl))
        except Exception as error:
            logger.warning("Redis EXPIRE failed (%s)", type(error).__name__)
            return False

    async def ttl(self, key: str) -> int:
        """Return remaining lifetime, using Redis values ``-1`` and ``-2`` unchanged."""
        full_key = self._get_key(key)
        try:
            return int(await self.client.ttl(full_key))
        except Exception as error:
            logger.warning("Redis TTL failed (%s)", type(error).__name__)
            return -2

    async def increment(self, key: str, amount: int = 1) -> int:
        """Atomically add ``amount`` to a Redis integer key; return zero on Redis errors."""
        full_key = self._get_key(key)
        self._validate_amount(amount)
        try:
            return int(await self.client.incrby(full_key, amount))
        except Exception as error:
            logger.warning("Redis INCRBY failed (%s)", type(error).__name__)
            return 0

    async def decrement(self, key: str, amount: int = 1) -> int:
        """Atomically subtract ``amount`` from a Redis integer key; return zero on Redis errors."""
        full_key = self._get_key(key)
        self._validate_amount(amount)
        try:
            return int(await self.client.decrby(full_key, amount))
        except Exception as error:
            logger.warning("Redis DECRBY failed (%s)", type(error).__name__)
            return 0

    async def scan_keys(self, pattern: str = "*", count: int = 100) -> list[str]:
        """Return matching keys without the configured prefix, using Redis SCAN."""
        if not isinstance(pattern, str):
            raise ValueError("pattern must be a string")
        if isinstance(count, bool) or not isinstance(count, int) or count < 1:
            raise ValueError("count must be a positive integer")
        full_pattern = f"{self.config.key_prefix}{pattern}"
        try:
            matches: list[str] = []
            cursor = 0
            while True:
                cursor, batch = await cast(
                    Awaitable[tuple[int, list[str | bytes]]],
                    self.client.scan(cursor, match=full_pattern, count=count),
                )
                for key in batch:
                    decoded_key = key.decode("utf-8") if isinstance(key, bytes) else key
                    if decoded_key.startswith(self.config.key_prefix):
                        decoded_key = decoded_key[len(self.config.key_prefix) :]
                    matches.append(decoded_key)
                if int(cursor) == 0:
                    return matches
        except Exception as error:
            logger.warning("Redis SCAN failed (%s)", type(error).__name__)
            return []

    async def flush_pattern(self, pattern: str) -> int:
        """Delete keys matching a pattern and return the number Redis actually removed."""
        keys = await self.scan_keys(pattern)
        return await self.delete(*keys) if keys else 0

    async def ping(self) -> bool:
        """Check the connected Redis server and return false if the ping fails."""
        try:
            return bool(await cast(Awaitable[bool], self.client.ping()))
        except Exception as error:
            logger.warning("Redis PING failed (%s)", type(error).__name__)
            return False

    def _sync_get(self, key: str, default: Any = None) -> Any:
        """Synchronous counterpart used by decorators on regular functions."""
        full_key = self._get_key(key)
        try:
            value = cast(str | bytes | None, self._get_sync_client().get(full_key))
        except Exception as error:
            logger.warning("Redis GET failed (%s)", type(error).__name__)
            return default
        if value is None:
            return default
        return self._decode_value(value)

    def _sync_set(self, key: str, value: Any, ttl: int | None = None, *, nx: bool = False) -> bool:
        """Synchronous counterpart used by cache and lock decorators."""
        full_key = self._get_key(key)
        self._validate_ttl(ttl)
        try:
            encoded = value if isinstance(value, bytes) else json.dumps(value, ensure_ascii=False)
            return bool(self._get_sync_client().set(full_key, encoded, ex=ttl, nx=nx))
        except Exception as error:
            logger.warning("Redis SET failed (%s)", type(error).__name__)
            return False

    def _sync_delete(self, key: str) -> bool:
        """Delete one key through the synchronous Redis pool."""
        full_key = self._get_key(key)
        try:
            return bool(self._get_sync_client().delete(full_key))
        except Exception as error:
            logger.warning("Redis DELETE failed (%s)", type(error).__name__)
            return False

    def _get_sync_client(self) -> SyncRedis:
        """Create or return the lazily opened synchronous Redis client."""
        with self._sync_lock:
            if self._sync_client is None:
                config = self.config
                self._sync_client = SyncRedis(
                    host=config.host,
                    port=config.port,
                    db=config.db,
                    password=config.password,
                    username=config.username,
                    ssl=config.ssl,
                    socket_timeout=config.socket_timeout,
                    socket_connect_timeout=config.socket_connect_timeout,
                    max_connections=config.max_connections,
                    decode_responses=config.decode_responses,
                )
            return self._sync_client

    def _make_async_client(self) -> AsyncRedis:
        """Build an asynchronous Redis client from validated configuration."""
        config = self.config
        return AsyncRedis(
            host=config.host,
            port=config.port,
            db=config.db,
            password=config.password,
            username=config.username,
            ssl=config.ssl,
            socket_timeout=config.socket_timeout,
            socket_connect_timeout=config.socket_connect_timeout,
            max_connections=config.max_connections,
            decode_responses=config.decode_responses,
        )

    @staticmethod
    def _decode_value(value: str | bytes) -> Any:
        """Decode a JSON value and leave values written by raw Redis clients intact."""
        try:
            return json.loads(value)
        except (json.JSONDecodeError, TypeError, UnicodeDecodeError):
            return value

    @staticmethod
    def _validate_ttl(ttl: int | None) -> None:
        """Validate an optional positive integer expiry."""
        if ttl is not None and (isinstance(ttl, bool) or not isinstance(ttl, int) or ttl < 1):
            raise ValueError("ttl must be a positive integer or None")

    @staticmethod
    def _validate_amount(amount: int) -> None:
        """Validate integer increment and decrement amounts."""
        if isinstance(amount, bool) or not isinstance(amount, int):
            raise ValueError("amount must be an integer")
