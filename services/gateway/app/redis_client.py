# services/gateway/app/redis_client.py

import os
import redis.asyncio as redis

_redis: redis.Redis | None = None

async def get_redis() -> redis.Redis:
    global _redis
    if _redis is None:
        host = os.getenv("REDIS_HOST", "redis")
        port = os.getenv("REDIS_PORT", "6379")
        _redis = redis.from_url(
            f"redis://{host}:{port}",
            encoding="utf-8",
            decode_responses=True
        )
    return _redis
