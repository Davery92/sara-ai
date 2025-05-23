# services/gateway/app/redis_client.py
import os
import logging
import redis.asyncio as redis
import asyncio

logger = logging.getLogger(__name__)

_redis: redis.Redis | None = None
_redis_lock = asyncio.Lock()

async def get_redis() -> redis.Redis | None:
    """
    Returns a Redis client, creating and connecting it if necessary.
    Ensures connection is alive or re-establishes it.
    Returns None if connection fails after retries.
    """
    global _redis
    
    # Use a lock to prevent multiple coroutines from trying to connect simultaneously
    async with _redis_lock:
        if _redis is not None:
            try:
                # Attempt to ping to check if connection is still alive
                await _redis.ping()
                # logger.debug("Redis client is already connected and responsive.")
                return _redis
            except (redis.ConnectionError, redis.TimeoutError, Exception) as e:
                logger.warning(f"Existing Redis connection is broken: {e}. Attempting to reconnect.")
                _redis = None # Mark as broken, so a new connection is established
        
        # If _redis is None (first call or broken connection), attempt to establish it
        if _redis is None:
            max_retries = 5
            initial_delay = 1 # seconds
            for attempt in range(max_retries):
                try:
                    host = os.getenv("REDIS_HOST", "redis")
                    port = os.getenv("REDIS_PORT", "6379")
                    
                    redis_url = f"redis://{host}:{port}"
                    logger.info(f"Attempt {attempt + 1}/{max_retries}: Connecting to Redis at {redis_url}")
                    
                    new_redis_client = redis.from_url(
                        redis_url,
                        encoding="utf-8",
                        decode_responses=True,
                        socket_timeout=5,
                        socket_connect_timeout=5,
                        retry_on_timeout=True, # Enable automatic retry on timeout
                        health_check_interval=10 # Regularly check connection health
                    )
                    
                    await new_redis_client.ping() # Test connection
                    _redis = new_redis_client
                    logger.info("Successfully connected to Redis.")
                    return _redis
                except (redis.ConnectionError, redis.TimeoutError, Exception) as e:
                    logger.warning(f"Redis connection attempt {attempt + 1} failed: {e}")
                    if attempt < max_retries - 1:
                        await asyncio.sleep(initial_delay * (2 ** attempt)) # Exponential backoff
                    else:
                        logger.error("Failed to connect to Redis after multiple retries. Redis client will be unavailable.")
                        _redis = None # Ensure it's None if all retries fail
                        return None
        
        return _redis # Should be connected client or None if connection failed