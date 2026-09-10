"""
ABCI-MI PostgreSQL Database Infrastructure
Configures SQLAlchemy Async & Sync engines, session factories, and health checks.
"""

import time
from typing import Any, AsyncGenerator, Dict, Optional
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger("infrastructure.database")


class Base(DeclarativeBase):
    """Base declarative class for all SQLAlchemy ORM models."""
    pass


# Global engine and sessionmaker instances
async_engine: Optional[AsyncEngine] = None
async_session_factory: Optional[async_sessionmaker[AsyncSession]] = None


def init_database() -> AsyncEngine:
    """Initializes the async SQLAlchemy engine and sessionmaker."""
    global async_engine, async_session_factory
    settings = get_settings()

    if async_engine is None:
        logger.info(
            f"Initializing PostgreSQL async engine for host {settings.POSTGRES_SERVER}:{settings.POSTGRES_PORT} (DB: {settings.POSTGRES_DB})"
        )
        async_engine = create_async_engine(
            settings.async_database_url,
            pool_size=settings.DATABASE_POOL_SIZE,
            max_overflow=settings.DATABASE_MAX_OVERFLOW,
            pool_timeout=settings.DATABASE_POOL_TIMEOUT,
            pool_recycle=settings.DATABASE_POOL_RECYCLE,
            pool_pre_ping=True,
            echo=settings.DEBUG and settings.ENVIRONMENT == "development",
        )
        async_session_factory = async_sessionmaker(
            bind=async_engine,
            class_=AsyncSession,
            expire_on_commit=False,
            autoflush=False,
        )

    return async_engine


async def close_database_connections() -> None:
    """Disposes of the database engine connection pool during application shutdown."""
    global async_engine, async_session_factory
    if async_engine is not None:
        logger.info("Closing PostgreSQL connection pool...")
        await async_engine.dispose()
        async_engine = None
        async_session_factory = None
        logger.info("PostgreSQL connection pool closed successfully.")


async def get_async_db() -> AsyncGenerator[AsyncSession, None]:
    """Dependency for obtaining an asynchronous database session."""
    global async_session_factory
    if async_session_factory is None:
        init_database()

    assert async_session_factory is not None, "Database session factory is not initialized."

    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def check_database_health() -> Dict[str, Any]:
    """
    Executes a lightweight query (SELECT 1) against PostgreSQL to verify connectivity and latency.
    Returns a dictionary with status, latency in milliseconds, and error details if any.
    """
    settings = get_settings()
    start_time = time.perf_counter()

    try:
        if async_engine is None:
            init_database()

        assert async_engine is not None, "Engine initialization failed."

        async with async_engine.connect() as conn:
            # Execute quick test query with short timeout
            result = await conn.execute(text("SELECT 1"))
            val = result.scalar()

            latency_ms = round((time.perf_counter() - start_time) * 1000, 2)
            if val == 1:
                return {
                    "status": "healthy",
                    "latency_ms": latency_ms,
                    "database": settings.POSTGRES_DB,
                    "host": settings.POSTGRES_SERVER,
                    "error": None,
                }
            else:
                return {
                    "status": "unhealthy",
                    "latency_ms": latency_ms,
                    "database": settings.POSTGRES_DB,
                    "host": settings.POSTGRES_SERVER,
                    "error": "Unexpected query result",
                }
    except Exception as e:
        latency_ms = round((time.perf_counter() - start_time) * 1000, 2)
        logger.debug(f"PostgreSQL health check failed: {str(e)}")
        return {
            "status": "unhealthy",
            "latency_ms": latency_ms,
            "database": settings.POSTGRES_DB,
            "host": settings.POSTGRES_SERVER,
            "error": str(e),
        }
