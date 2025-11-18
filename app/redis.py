import redis

from app.config import settings

redis_client: redis.Redis | None = None


def init_redis():
    global redis_client
    redis_client = redis.from_url(settings.redis_url,
                                  encoding="utf-8",
                                  decode_responses=True,
                                  max_connections=settings.redis_max_connections)


def close_redis():
    if redis_client:
        redis_client.close()