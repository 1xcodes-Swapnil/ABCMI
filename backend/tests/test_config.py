"""
Tests for ABCI-MI Core Configuration and Settings Management
"""

import pytest
from app.core.config import Settings, get_settings


def test_settings_initialization(test_settings: Settings) -> None:
    """Verify that settings are loaded with valid defaults and types."""
    assert test_settings.PROJECT_NAME == "ABCI-MI Backend API"
    assert test_settings.VERSION == "1.0.0"
    assert test_settings.API_V1_STR == "/api/v1"
    assert isinstance(test_settings.PORT, int)
    assert test_settings.PORT > 0


def test_database_url_generation() -> None:
    """Verify computed database URLs."""
    settings = Settings(
        POSTGRES_SERVER="db.example.com",
        POSTGRES_PORT=5432,
        POSTGRES_USER="testuser",
        POSTGRES_PASSWORD="testpassword",
        POSTGRES_DB="testdb",
    )
    assert settings.async_database_url == "postgresql+asyncpg://testuser:testpassword@db.example.com:5432/testdb"
    assert settings.sync_database_url == "postgresql+psycopg2://testuser:testpassword@db.example.com:5432/testdb"


def test_redis_url_generation() -> None:
    """Verify computed Redis connection URLs."""
    settings = Settings(
        REDIS_HOST="redis.example.com",
        REDIS_PORT=6379,
        REDIS_DB=1,
        REDIS_PASSWORD="secretpassword",
    )
    assert settings.redis_connection_url == "redis://:secretpassword@redis.example.com:6379/1"


def test_qdrant_url_generation() -> None:
    """Verify computed Qdrant REST connection URLs."""
    settings_http = Settings(
        QDRANT_HOST="qdrant.example.com",
        QDRANT_PORT=6333,
        QDRANT_HTTPS=False,
    )
    assert settings_http.qdrant_connection_url == "http://qdrant.example.com:6333"

    settings_https = Settings(
        QDRANT_HOST="qdrant.example.com",
        QDRANT_PORT=6333,
        QDRANT_HTTPS=True,
    )
    assert settings_https.qdrant_connection_url == "https://qdrant.example.com:6333"


def test_cors_origins_parsing() -> None:
    """Verify CORS origins parsing from string or list."""
    settings_comma = Settings(CORS_ORIGINS="http://localhost:3000, http://localhost:8000")
    assert settings_comma.CORS_ORIGINS == ["http://localhost:3000", "http://localhost:8000"]
