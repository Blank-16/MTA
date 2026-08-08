import logging

import redis.asyncio as aioredis

from app.core.config import settings

logger = logging.getLogger(__name__)

_redis: aioredis.Redis | None = None


async def init_redis() -> None:
    global _redis
    _redis = aioredis.from_url(
        str(settings.redis_url),
        encoding="utf-8",
        decode_responses=True,
        socket_connect_timeout=5,
        socket_timeout=5,
    )
    try:
        await _redis.ping()
        logger.info("Redis connection established")
    except Exception as exc:
        logger.critical("Redis connection failed: %s", exc, exc_info=True)
        raise


async def close_redis() -> None:
    global _redis
    if _redis is not None:
        await _redis.aclose()
        _redis = None
        logger.info("Redis connection closed")


def get_redis() -> aioredis.Redis:
    if _redis is None:
        raise RuntimeError("Redis not initialised — call init_redis() at startup")
    return _redis


async def redis_health_check() -> bool:
    try:
        await get_redis().ping()
        return True
    except Exception as exc:
        logger.error("Redis health check failed: %s", exc)
        return False
