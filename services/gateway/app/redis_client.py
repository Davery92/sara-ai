# services/gateway/app/redis_client.py
import os
import logging
import redis.asyncio as redis

logger = logging.getLogger(__name__)

_redis: redis.Redis | None = None

async def get_redis() -> redis.Redis | None:
    """
    Returns a Redis client, creating and connecting it if necessary.
    Returns None if connection fails.
    """
    global _redis
    
    if _redis is None:
        try:
            host = os.getenv("REDIS_HOST", "localhost")
            port = os.getenv("REDIS_PORT", "6379")
            
            _redis = redis.from_url(
                f"redis://{host}:{port}",
                encoding="utf-8",
                decode_responses=True,
                socket_timeout=5,
                socket_connect_timeout=5,
            )
            
            # Test connection with ping
            await _redis.ping()
            logger.debug("Connected to Redis successfully")
        except Exception as e:
            logger.warning(f"Could not connect to Redis: {e}")
            _redis = None
            return None
    
    # Double-check connection is still alive
    try:
        if _redis:
            await _redis.ping()
            return _redis
    except Exception as e:
        logger.warning(f"Lost connection to Redis: {e}")
        _redis = None
    
    return None