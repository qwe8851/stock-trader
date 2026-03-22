"""
Redis connection pool and helper utilities.
Used for caching and Pub/Sub price streaming.
"""
from typing import AsyncGenerator

import redis.asyncio as aioredis
from redis.asyncio import Redis

from core.config import settings
from core.logging import get_logger

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Connection pool (shared across the application)
# ---------------------------------------------------------------------------
_redis_pool: Redis | None = None


async def init_redis() -> None:
    """
    Create the Redis connection pool.
    Called once during application startup.
    """
    global _redis_pool
    _redis_pool = aioredis.from_url(
        settings.REDIS_URL,
        encoding="utf-8",
        decode_responses=True,
        max_connections=20,
    )
    # Verify connection
    await _redis_pool.ping()
    logger.info("Redis connection pool initialised", extra={"url": settings.REDIS_URL})


async def close_redis() -> None:
    """
    Close the Redis connection pool.
    Called once during application shutdown.
    """
    global _redis_pool
    if _redis_pool:
        await _redis_pool.aclose()
        _redis_pool = None
        logger.info("Redis connection pool closed")


def get_redis() -> Redis:
    """
    Return the shared Redis client.
    Raises RuntimeError if init_redis() has not been called yet.
    """
    if _redis_pool is None:
        raise RuntimeError("Redis pool not initialised. Call init_redis() first.")
    return _redis_pool


async def get_redis_dep() -> AsyncGenerator[Redis, None]:
    """FastAPI dependency that yields the shared Redis client."""
    yield get_redis()
