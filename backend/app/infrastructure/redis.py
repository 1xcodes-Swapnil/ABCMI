"""
ABCI-MI Redis Infrastructure
Configures Redis async client, connection pool, cache handlers, and health checks.
"""

import time
from typing import Any, Dict, Optional
import redis.asyncio as aioredis
from redis.asyncio.connection import ConnectionPool

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger("infrastructure.redis")

_redis_pool: Optional[ConnectionPool] = None
_redis_client: Optional[aioredis.Redis] = None


def init_redis_client() -> aioredis.Redis:
    """Initializes the Redis connection pool and async client instance."""
    global _redis_pool, _redis_client
    settings = get_settings()

    if _redis_client is None:
        logger.info(
            f"Initializing Redis connection pool for host {settings.REDIS_HOST}:{settings.REDIS_PORT} (DB {settings.REDIS_DB})"
        )
        _redis_pool = ConnectionPool.from_url(
            settings.redis_connection_url,
            max_connections=settings.REDIS_MAX_CONNECTIONS,
            socket_timeout=settings.REDIS_SOCKET_TIMEOUT,
            socket_connect_timeout=settings.REDIS_SOCKET_TIMEOUT,
            decode_responses=True,
        )
        _redis_client = aioredis.Redis(connection_pool=_redis_pool)

    return _redis_client


async def close_redis_client() -> None:
    """Closes Redis connections during application shutdown."""
    global _redis_pool, _redis_client
    if _redis_client is not None:
        logger.info("Closing Redis connections...")
        await _redis_client.close()
        _redis_client = None
    if _redis_pool is not None:
        await _redis_pool.disconnect()
        _redis_pool = None
        logger.info("Redis connections closed successfully.")


async def get_redis_client() -> aioredis.Redis:
    """Dependency for obtaining the async Redis client."""
    global _redis_client
    if _redis_client is None:
        init_redis_client()
    assert _redis_client is not None
    return _redis_client


async def check_redis_health() -> Dict[str, Any]:
    """
    Executes a PING command on Redis to verify connectivity and latency.
    Returns status, latency in ms, and error details if any.
    """
    settings = get_settings()
    start_time = time.perf_counter()

    try:
        client = await get_redis_client()
        pong = await client.ping()
        latency_ms = round((time.perf_counter() - start_time) * 1000, 2)

        if pong is True or pong == b"PONG" or pong == "PONG":
            return {
                "status": "healthy",
                "latency_ms": latency_ms,
                "host": settings.REDIS_HOST,
                "port": settings.REDIS_PORT,
                "error": None,
            }
        else:
            return {
                "status": "unhealthy",
                "latency_ms": latency_ms,
                "host": settings.REDIS_HOST,
                "port": settings.REDIS_PORT,
                "error": "Unexpected PING response",
            }
    except Exception as e:
        latency_ms = round((time.perf_counter() - start_time) * 1000, 2)
        logger.debug(f"Redis health check failed: {str(e)}")
        return {
            "status": "unhealthy",
            "latency_ms": latency_ms,
            "host": settings.REDIS_HOST,
            "port": settings.REDIS_PORT,
            "error": str(e),
        }
