"""
ABCI-MI Pytest Configuration and Test Fixtures
"""

import os
from typing import AsyncGenerator, Generator
import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy import event

# Set test environment flags
os.environ["ENVIRONMENT"] = "test"
os.environ["DEBUG"] = "true"
os.environ["LOG_LEVEL"] = "WARNING"
os.environ["AUDIO_STORAGE_PATH"] = "/tmp/abcimi_test_storage"

from app.core.config import Settings, get_settings
from app.infrastructure.database import Base
import app.models  # Register all ORM models
from app.main import app


@pytest.fixture(scope="session")
def test_settings() -> Settings:
    """Fixture providing cached application settings."""
    return get_settings()


@pytest.fixture
def client() -> Generator[TestClient, None, None]:
    """Provides a synchronous HTTP test client for the FastAPI application."""
    with TestClient(app=app, base_url="http://testserver") as test_client:
        yield test_client


@pytest_asyncio.fixture
async def async_db_engine() -> AsyncGenerator[AsyncEngine, None]:
    """Provides an isolated in-memory SQLite async engine with all tables created."""
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        echo=False,
        future=True,
    )

    @event.listens_for(engine.sync_engine, "connect")
    def _set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield engine

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture
async def db_session(async_db_engine: AsyncEngine) -> AsyncGenerator[AsyncSession, None]:
    """Provides an isolated AsyncSession bound to the in-memory test database."""
    session_factory = async_sessionmaker(
        bind=async_db_engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
    )
    async with session_factory() as session:
        yield session
        await session.rollback()
