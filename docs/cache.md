# Redis cache and locks

`standard-cache` provides `std.cache` without adding Redis dependencies to the
core `standard` installation.

The source package is built and tested. PyPI availability and trusted publisher
setup for this add-on have not been verified; use the install command below
after a release is published.

## Install

```console
python -m pip install standard-cache
```

## Connect and close

Create one client in application startup, inject it where needed, and close it
during shutdown. `connect()` pings Redis and is safe to call more than once.

```python
from std.cache import RedisClient, RedisConfig

cache = RedisClient(
    RedisConfig(
        host="redis.internal",
        port=6379,
        db=0,
        username="app",
        password="from-your-secret-store",
        key_prefix="catalog:",
    )
)
await cache.connect()
try:
    await cache.set("product:42", {"name": "notebook"}, ttl=300)
    product = await cache.get("product:42")
finally:
    await cache.close()
```

`RedisConfig` defaults to localhost, port `6379`, database `0`, no TLS, five
second socket and connect timeouts, 50 connections, decoded responses, and no
key prefix. Set `ssl=True` to use a TLS connection. The password is omitted
from the config representation.

`RedisClient` is also an asynchronous context manager:

```python
async with RedisClient(RedisConfig(key_prefix="catalog:")) as cache:
    await cache.set("status", {"ready": True})
```

The lower-level async client is available as `cache.client` after `connect()`.
Access before connecting raises `RuntimeError`. Use the helper methods for
prefix-aware keys and JSON values.

## Values, keys, and expiry

`set()` JSON-encodes values other than `bytes`; strings are JSON-encoded too,
so values such as `"123"`, `"true"`, and `"null"` come back as strings rather
than being mistaken for numbers, booleans, or `None`. Bytes are stored as raw
Redis bytes. With the default `decode_responses=True`, Redis returns valid UTF-8
bytes as strings; use `decode_responses=False` when the caller needs byte values
back. `get()` decodes JSON when possible and returns raw values written directly
through Redis when decoding fails. JSON values must be serializable by Python's
`json` module.

`get(key, default)` returns the default on a missing key or a Redis read error.
This is convenient for cache lookups; use the underlying client directly when
an application needs to distinguish an unavailable cache from a miss. A
cached `None` is preserved by the decorators and is distinct from a missing
key. `ttl` returns Redis's normal `-1` (no expiry) and `-2` (missing key)
values. TTL values passed to `set` and `expire` must be positive whole seconds.

`RedisConfig.key_prefix` is applied by all helper methods. `scan_keys(pattern,
count=100)` returns matching keys without that prefix. `flush_pattern()` scans
then deletes the matching keys; use a narrow pattern because matching is
Redis glob syntax. `set(..., nx=True)` only creates a missing key and
`set(..., xx=True)` only replaces an existing key. Setting both is rejected.

Convenience methods `get`, `set`, `delete`, `exists`, `expire`, `ttl`,
`increment`, `decrement`, `scan_keys`, and `ping` use safe fallback values for
Redis command failures and log the error type without logging keys or values.
`connect()` raises when its initial ping fails. Do not use a fail-soft cache
result as the source of truth for a durable application record.

## Cache functions

`cached` uses a key built from the function module, qualified name, positional
arguments, and sorted keyword arguments. Long keys are replaced with a SHA-256
digest. A custom key builder receives `(function, args, kwargs)`; an optional
`key_prefix` is prepended to the resulting key.

```python
from std.cache import cached

@cached(cache, ttl=300, key_prefix="product")
async def get_product(product_id: int) -> dict[str, str]:
    return await load_product(product_id)

# After changing the product:
await get_product.cache_invalidate(42)
```

`cache_aside` offers an argument-only `key_func` for explicit keys:

```python
from std.cache import cache_aside

@cache_aside(cache, ttl=60, key_func=lambda product_id: f"product:{product_id}")
def get_product_summary(product_id: int) -> dict[str, str]:
    return load_product_summary(product_id)
```

Both decorators preserve whether the function is synchronous or asynchronous.
They treat cache read/write failures as misses or failed writes and still run
the wrapped function. Function exceptions pass through unchanged. A cached
`None` is treated as a hit.

For synchronous decorated functions, the client lazily creates a synchronous
Redis pool. Close it with `cache.close_sync()` or a synchronous context manager:

```python
with RedisClient() as sync_cache:
    @cached(sync_cache, ttl=30)
    def lookup(code: str) -> str:
        return load_lookup(code)

    value = lookup("A-42")
```

## Distributed locks

`DistributedLock` uses Redis `SET NX EX` with a unique token. Release and lease
renewal compare that token atomically, so an expired owner cannot remove a new
owner's lock. This coordinates work through one Redis primary; it is not a
multi-primary Redlock implementation.

```python
from std.cache import DistributedLock

async with DistributedLock(cache, "rebuild-index", timeout=30, auto_renewal=True):
    await rebuild_index()
```

The lease expires after `timeout` seconds unless `auto_renewal=True`. A lock
object can also be acquired manually:

```python
lock = DistributedLock(cache, "daily-report", timeout=20)
if await lock.acquire(blocking=False):
    try:
        await create_report()
    finally:
        await lock.release()
```

`acquire(blocking=True, timeout=...)` retries until it acquires the lock or the
wait timeout expires. Its timeout is a maximum wait duration; the constructor's
timeout is the lock lease duration. `is_locked()` is asynchronous. The
compatibility `locked` property performs a blocking Redis request, so use
`await lock.is_locked()` from async code.

`with_lock(cache, name, timeout=10, blocking=True)` decorates synchronous or
asynchronous functions and releases the lease even when a function raises. If
`blocking=False`, contention raises `RuntimeError` before the function runs.

## Verification

Unit tests use in-memory Redis doubles. The Redis Testcontainers E2E test checks
JSON and TTL behavior, sync and async decorators, lock expiry, contention, and
token-safe release:

```console
make test-e2e
```
