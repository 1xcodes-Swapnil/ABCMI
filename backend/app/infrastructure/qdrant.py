"""
ABCI-MI Qdrant Vector Database Infrastructure
Configures Qdrant client for semantic memory, vector indexes, and health checks.
"""

import os
import time
from typing import Any, Dict, Optional
from qdrant_client import AsyncQdrantClient

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger("infrastructure.qdrant")

_qdrant_client: Optional[AsyncQdrantClient] = None


def init_qdrant_client() -> AsyncQdrantClient:
    """Initializes the AsyncQdrantClient instance."""
    global _qdrant_client
    settings = get_settings()

    if _qdrant_client is None:
        if os.getenv("PYTEST_CURRENT_TEST") or os.getenv("TESTING") == "true":
            logger.info("Initializing in-memory AsyncQdrantClient for testing")
            _qdrant_client = AsyncQdrantClient(location=":memory:")
        else:
            logger.info(
                f"Initializing Qdrant client for {settings.qdrant_connection_url} (gRPC: {settings.QDRANT_GRPC_PORT})"
            )
            try:
                _qdrant_client = AsyncQdrantClient(
                    url=settings.qdrant_connection_url,
                    port=settings.QDRANT_PORT,
                    grpc_port=settings.QDRANT_GRPC_PORT,
                    api_key=settings.QDRANT_API_KEY if settings.QDRANT_API_KEY else None,
                    timeout=settings.QDRANT_TIMEOUT,
                    check_compatibility=False,
                )
            except Exception as e:
                logger.warning(f"Failed to connect to Qdrant at {settings.qdrant_connection_url}, falling back to in-memory: {e}")
                _qdrant_client = AsyncQdrantClient(location=":memory:")

    return _qdrant_client


async def close_qdrant_client() -> None:
    """Closes Qdrant client connections during application shutdown."""
    global _qdrant_client
    if _qdrant_client is not None:
        logger.info("Closing Qdrant client connection...")
        try:
            await _qdrant_client.close()
        except Exception as e:
            logger.debug(f"Error during Qdrant client closure: {e}")
        _qdrant_client = None
        logger.info("Qdrant client closed successfully.")


async def get_qdrant_client() -> AsyncQdrantClient:
    """Dependency for obtaining the AsyncQdrantClient."""
    global _qdrant_client
    if _qdrant_client is None:
        init_qdrant_client()
    assert _qdrant_client is not None
    return _qdrant_client


async def check_qdrant_health() -> Dict[str, Any]:
    """
    Executes a collections query or health check against Qdrant to verify connectivity and latency.
    Returns status, latency in ms, and error details if any.
    """
    settings = get_settings()
    start_time = time.perf_counter()

    try:
        client = await get_qdrant_client()
        # Retrieve collections list to ensure connectivity
        collections_response = await client.get_collections()
        latency_ms = round((time.perf_counter() - start_time) * 1000, 2)

        return {
            "status": "healthy",
            "latency_ms": latency_ms,
            "host": settings.QDRANT_HOST,
            "port": settings.QDRANT_PORT,
            "collections_count": len(collections_response.collections),
            "error": None,
        }
    except Exception as e:
        latency_ms = round((time.perf_counter() - start_time) * 1000, 2)
        logger.debug(f"Qdrant health check failed: {str(e)}")
        return {
            "status": "unhealthy",
            "latency_ms": latency_ms,
            "host": settings.QDRANT_HOST,
            "port": settings.QDRANT_PORT,
            "error": str(e),
        }
