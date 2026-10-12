# standard-cache

Redis caching helpers and distributed locks for the `standard` Python library.
The package name is `standard-cache`; Python imports are under `std.cache`.

The source package is built and tested. PyPI availability and publisher setup
for the add-on have not yet been verified.

After the first PyPI release, install it with:

```console
python -m pip install standard-cache
```

```python
from std.cache import RedisClient, RedisConfig, cached

cache = RedisClient(RedisConfig(host="localhost", key_prefix="shop:"))
await cache.connect()

@cached(cache, ttl=300)
async def get_product(product_id: int) -> dict[str, str]:
    return await load_product(product_id)

try:
    product = await get_product(42)
finally:
    await cache.close()
```

`RedisClient` supports JSON-compatible values, raw bytes, expiration, atomic
conditions, key scanning, and prefix-aware deletion. `cached` and `cache_aside`
preserve sync and async function behavior. `DistributedLock` and `with_lock`
provide lease-based locks with token-checked release. See the [cache guide](https://appunni-m.github.io/python-standard/cache/)
for lifecycle, serialization, failure, and locking behavior.
