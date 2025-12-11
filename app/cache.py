import asyncio
import json
import random
from collections.abc import Awaitable
from collections.abc import Callable
from typing import Any

from app import redis_client as redis_module
from app.config import settings


async def cache_set(key: str, value: Any, expire: int = settings.cache_ttl):
    client = redis_module.redis_client
    if not client:
        return None
    data = json.dumps(value, default=str)
    await client.set(key, data, ex=expire)


async def cache_get(key: str) -> Any | None:
    client = redis_module.redis_client
    if not client:
        return None
    data = await client.get(key)
    if not data:
        return None
    return json.loads(data)


async def cache_delete(key: str):
    client = redis_module.redis_client
    if client:
        await client.delete(key)


async def fetch_with_stampede_protection(
    key: str, fetch_func: Callable[[], Awaitable[Any]], expire: int = settings.cache_ttl
) -> Any:
    client = redis_module.redis_client

    if client:
        cached_data = await cache_get(key)
        if cached_data is not None:
            return cached_data
    else:
        return await fetch_func()

    lock_key = f"lock:{key}"
    is_lock_acquired = await client.set(lock_key, "1", nx=True, ex=10)

    if is_lock_acquired:
        try:
            fresh_data = await fetch_func()
            await cache_set(key, fresh_data, expire=expire)
            return fresh_data
        finally:
            await client.delete(lock_key)

    retries = 5
    for _ in range(retries):
        await asyncio.sleep(random.uniform(0.1, 0.3))
        cached_data = await cache_get(key)
        if cached_data is not None:
            return cached_data

    return await fetch_func()


class CacheInvalidationMixin:
    def get_cache_keys_to_invalidate(self) -> list[str]:
        return []
