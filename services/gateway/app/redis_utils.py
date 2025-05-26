import json, os, asyncio, uuid, time
from .redis_client import get_redis  # existing helper
import logging # Add logging import

log = logging.getLogger("gateway.redis_utils") # Get logger for this module

HOT_MSG_LIMIT = int(os.getenv("HOT_MSG_LIMIT", 200))
REDIS_CONV_TTL = int(os.getenv("REDIS_CONV_TTL_MIN", 60)) * 60  # seconds

# async def push_chat_chunk(room_id: str, chunk: dict):
#     """LPUSH → cap length → reset TTL in one pipeline."""
#     r = await get_redis()
#     if r is None:          # fallback during tests / degraded mode
#         log.error("Redis client is None in push_chat_chunk. Cannot push.") # Added log
#         return
#     key = f"room:{room_id}:messages"
#     data = json.dumps(chunk)
#     
#     log.info(f"Attempting to push to Redis. Key: {key}, Data: {data[:50]}..., TTL: {REDIS_CONV_TTL}s") # Added log
#     try:
#         async with r.pipeline(transaction=False) as pipe:
#             pipe.lpush(key, data)
#             pipe.ltrim(key, 0, HOT_MSG_LIMIT - 1)
#             pipe.expire(key, REDIS_CONV_TTL)
#             await pipe.execute()
#         log.info(f"Successfully pushed and expired Redis key: {key}") # Added log
#     except Exception as e:
#         log.error(f"Error pushing to Redis key {key}: {e}", exc_info=True) # Added error log

async def push_unified_user_memory(user_id: str, room_id: str, role: str, text: str):
    r = await get_redis()
    if r is None:
        log.error("Redis client is None in push_unified_user_memory. Cannot push.")
        return

    # Key is now solely based on user_id
    key = f"user:{user_id}:messages"
    
    # Construct chunk with all relevant data
    chunk = {
        "id": str(uuid.uuid4()), # Generate a fresh ID for this chunk entry
        "room_id": room_id, # Keep room_id for context in the chunk data
        "user_id": user_id, # Store user_id in the chunk itself
        "role": role,
        "text": text,
        "ts": time.time(),
    }
    data = json.dumps(chunk)

    log.info(f"Attempting to push unified user memory. Key: {key}, Data: {data[:50]}..., TTL: {REDIS_CONV_TTL}s")
    try:
        async with r.pipeline(transaction=False) as pipe:
            pipe.lpush(key, data)
            pipe.ltrim(key, 0, HOT_MSG_LIMIT - 1)
            pipe.expire(key, REDIS_CONV_TTL) # Apply TTL to the unified list
            await pipe.execute()
        log.info(f"Successfully pushed unified user memory to Redis key: {key}")
    except Exception as e:
        log.error(f"Error pushing unified user memory to Redis key {key}: {e}", exc_info=True)
