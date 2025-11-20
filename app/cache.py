import asyncio
import json
from typing import Any, Awaitable, Callable
from app.config import settings
from app.redis import redis_client



async def cache_set(key: str, value: Any, expire: int = settings.cache_TTL):
    if not redis_client:
        return None
    data = json.dumps(value, default=str)
    await redis_client.set(key, data, ex=expire)


async def cache_get(key: str) -> Any | None:
    if not redis_client:
        return None
    data = await redis_client.get(key)
    if not data:
        return None
    return json.loads(data)


async def cache_delete(key: str):
    if redis_client:
        await redis_client.delete(key)


async def fetch_with_stampede_protection(key: str, fetch_func: Callable[[], Awaitable[Any]], expire: int = settings.cache_TTL) -> Any:

    if redis_client:
        cached_data = await cache_get(key)
        if cached_data:
            return cached_data
    else:
        return await fetch_func()

    lock_key = f"lock:{key}"
    is_lock_acquired = await redis_client.set(lock_key, "1", nx=True, ex=10)

    if is_lock_acquired:
        try:
            fresh_data = await fetch_func()

            await cache_set(key, fresh_data, expire=expire)
            return fresh_data
        finally:
            await redis_client.delete(lock_key)

    else:
        retries = 5
        for _ in range(retries):
            await asyncio.sleep(0.2)
            cached_data = await cache_get(key)
            if cached_data:
                return cached_data

        return await fetch_func()


class CacheInvalidationMixin:

    def get_cache_keys_to_invalidate(self) -> list[str]:
        return []
