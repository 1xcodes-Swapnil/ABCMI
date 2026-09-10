#!/usr/bin/env python3
"""
ABCI-MI Infrastructure Readiness Checker
Polls PostgreSQL, Redis, and Qdrant until they are available or timeout expires.
"""

import asyncio
import os
import sys
import time

# Ensure backend root is on Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.core.config import get_settings
from app.infrastructure.database import check_database_health
from app.infrastructure.qdrant import check_qdrant_health
from app.infrastructure.redis import check_redis_health


async def wait_for_services(timeout_seconds: int = 60, interval_seconds: float = 2.0) -> bool:
    """Waits for PostgreSQL, Redis, and Qdrant services to become healthy."""
    settings = get_settings()
    print(f"Waiting up to {timeout_seconds}s for infrastructure services to be ready...")
    print(f" - PostgreSQL: {settings.POSTGRES_SERVER}:{settings.POSTGRES_PORT} (DB: {settings.POSTGRES_DB})")
    print(f" - Redis:      {settings.REDIS_HOST}:{settings.REDIS_PORT}")
    print(f" - Qdrant:     {settings.QDRANT_HOST}:{settings.QDRANT_PORT}")

    start_time = time.time()

    while time.time() - start_time < timeout_seconds:
        db_res = await check_database_health()
        redis_res = await check_redis_health()
        qdrant_res = await check_qdrant_health()

        db_ok = db_res.get("status") == "healthy"
        redis_ok = redis_res.get("status") == "healthy"
        qdrant_ok = qdrant_res.get("status") == "healthy"

        print(
            f"[{int(time.time() - start_time):02d}s] "
            f"Postgres: {'✓ OK' if db_ok else '✗ Waiting'} | "
            f"Redis: {'✓ OK' if redis_ok else '✗ Waiting'} | "
            f"Qdrant: {'✓ OK' if qdrant_ok else '✗ Waiting'}"
        )

        if db_ok and redis_ok and qdrant_ok:
            print("All infrastructure dependencies are healthy and reachable!")
            return True

        await asyncio.sleep(interval_seconds)

    print("Timed out waiting for infrastructure services.")
    return False


if __name__ == "__main__":
    success = asyncio.run(wait_for_services())
    sys.exit(0 if success else 1)
