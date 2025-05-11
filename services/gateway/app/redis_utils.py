import json, os, asyncio
from .redis_client import get_redis  # existing helper

HOT_MSG_LIMIT = int(os.getenv("HOT_MSG_LIMIT", 200))
REDIS_CONV_TTL = int(os.getenv("REDIS_CONV_TTL_MIN", 60)) * 60  # seconds

async def push_chat_chunk(room_id: str, chunk: dict):
    """LPUSH → cap length → reset TTL in one pipeline."""
    r = await get_redis()
    if r is None:          # fallback during tests / degraded mode
        return
    key = f"room:{room_id}:messages"
    data = json.dumps(chunk)
    async with r.pipeline(transaction=False) as pipe:
        pipe.lpush(key, data)
        pipe.ltrim(key, 0, HOT_MSG_LIMIT - 1)
        pipe.expire(key, REDIS_CONV_TTL)
        await pipe.execute()
