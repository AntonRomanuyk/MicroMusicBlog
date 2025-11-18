import json
import time
from typing import Any, Callable
from app.config import settings
from app.redis import redis_client



def cache_set(key: str, value: Any, expire: int = settings.cache_TTL):
    if not redis_client:
        return
    data = json.dumps(value, default=str)
    redis_client.set(key, data, ex=expire)


def cache_get(key: str) -> Any | None:
    if not redis_client:
        return None
    data = redis_client.get(key)
    if not data:
        return None
    return json.loads(data)


def cache_delete(key: str):
    if redis_client:
        redis_client.delete(key)


def fetch_with_stampede_protection(key: str, fetch_func: Callable[[], Any], expire: int = settings.cache_TTL) -> Any:

    if redis_client:
        cached_data = cache_get(key)
        if cached_data:
            return cached_data
    else:
        return fetch_func()

    lock_key = f"lock:{key}"
    is_lock_acquired = redis_client.set(lock_key, "1", nx=True, ex=10)

    if is_lock_acquired:
        try:
            fresh_data = fetch_func()

            cache_set(key, fresh_data, expire=expire)
            return fresh_data
        finally:
            redis_client.delete(lock_key)

    else:
        retries = 5
        for _ in range(retries):
            time.sleep(0.2)
            cached_data = cache_get(key)
            if cached_data:
                return cached_data

        return fetch_func()


class CacheInvalidationMixin:

    def get_cache_keys_to_invalidate(self) -> list[str]:
        return []
