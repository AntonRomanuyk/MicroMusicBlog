from redis.asyncio import Redis

from app.config import settings

redis_client: Redis | None = None


async def init_redis():
    global redis_client
    redis_client = Redis.from_url(settings.redis_url,
                                  encoding="utf-8",
                                  decode_responses=True,
                                  max_connections=settings.redis_max_connections)


async def close_redis():
    if redis_client:
        await redis_client.aclose()