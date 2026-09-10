"""
ABCI-MI Core Configuration
Manages environment variables, infrastructure connection parameters, and runtime settings.
"""

from functools import lru_cache
import json
from typing import List, Optional, Union
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    # -------------------------------------------------------------------------
    # Application & Server Information
    # -------------------------------------------------------------------------
    PROJECT_NAME: str = "ABCI-MI Backend API"
    VERSION: str = "1.0.0"
    DESCRIPTION: str = (
        "Adaptive Blackboard & Collaboration Intelligence for "
        "Multilingual Interaction and Meeting Intelligence API"
    )
    API_V1_STR: str = "/api/v1"
    ENVIRONMENT: str = "development"  # development, staging, production, test
    DEBUG: bool = True
    LOG_LEVEL: str = "INFO"
    HOST: str = "0.0.0.0"
    PORT: int = 8000

    # CORS settings
    CORS_ORIGINS: Union[List[str], str] = ["*"]

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def assemble_cors_origins(cls, v: Union[str, List[str]]) -> List[str]:
        if isinstance(v, str) and not v.startswith("["):
            return [i.strip() for i in v.split(",") if i.strip()]
        elif isinstance(v, str) and v.startswith("["):
            try:
                parsed = json.loads(v)
                if isinstance(parsed, list):
                    return parsed
            except Exception:
                pass
        elif isinstance(v, list):
            return v
        return ["*"]

    # -------------------------------------------------------------------------
    # PostgreSQL Configuration
    # -------------------------------------------------------------------------
    POSTGRES_SERVER: str = "localhost"
    POSTGRES_PORT: int = 5432
    POSTGRES_USER: str = "postgres"
    POSTGRES_PASSWORD: str = "postgres_password"
    POSTGRES_DB: str = "abcimi_db"
    DATABASE_POOL_SIZE: int = 10
    DATABASE_MAX_OVERFLOW: int = 20
    DATABASE_POOL_TIMEOUT: int = 30
    DATABASE_POOL_RECYCLE: int = 1800

    # Optional explicit overrides
    DATABASE_URL_ASYNC: Optional[str] = None
    DATABASE_URL_SYNC: Optional[str] = None

    @property
    def async_database_url(self) -> str:
        """Returns the asyncpg connection string for SQLAlchemy async engine."""
        if self.DATABASE_URL_ASYNC:
            return self.DATABASE_URL_ASYNC
        return (
            f"postgresql+asyncpg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_SERVER}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )

    @property
    def sync_database_url(self) -> str:
        """Returns the psycopg2 connection string for migrations and sync utilities."""
        if self.DATABASE_URL_SYNC:
            return self.DATABASE_URL_SYNC
        return (
            f"postgresql+psycopg2://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_SERVER}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )

    # -------------------------------------------------------------------------
    # Redis Configuration (Cache, Ephemeral State, Event Bus)
    # -------------------------------------------------------------------------
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379
    REDIS_PASSWORD: Optional[str] = None
    REDIS_DB: int = 0
    REDIS_SOCKET_TIMEOUT: float = 5.0
    REDIS_MAX_CONNECTIONS: int = 50
    REDIS_URL: Optional[str] = None

    @property
    def redis_connection_url(self) -> str:
        """Returns the Redis connection URL."""
        if self.REDIS_URL:
            return self.REDIS_URL
        auth_part = f":{self.REDIS_PASSWORD}@" if self.REDIS_PASSWORD else ""
        return f"redis://{auth_part}{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}"

    # -------------------------------------------------------------------------
    # Qdrant Vector Storage Configuration (Semantic Memory & SKW)
    # -------------------------------------------------------------------------
    QDRANT_HOST: str = "localhost"
    QDRANT_PORT: int = 6333
    QDRANT_GRPC_PORT: int = 6334
    QDRANT_API_KEY: Optional[str] = None
    QDRANT_HTTPS: bool = False
    QDRANT_TIMEOUT: float = 10.0
    QDRANT_URL: Optional[str] = None

    @property
    def qdrant_connection_url(self) -> str:
        """Returns the Qdrant REST URL."""
        if self.QDRANT_URL:
            return self.QDRANT_URL
        protocol = "https" if self.QDRANT_HTTPS else "http"
        return f"{protocol}://{self.QDRANT_HOST}:{self.QDRANT_PORT}"

    # -------------------------------------------------------------------------
    # Storage & File Path Configuration
    # -------------------------------------------------------------------------
    AUDIO_STORAGE_PATH: str = "./data/audio"
    MAX_UPLOAD_SIZE_MB: int = 500

    # -------------------------------------------------------------------------
    # AI Pipeline & Model Configuration (Phase 4.26)
    # -------------------------------------------------------------------------
    EXECUTION_MODE: str = "FIXTURE"  # REAL, FIXTURE, MOCK
    OPENMOSS_MODEL_ID: str = "OpenMOSS-Team/MOSS-Transcribe-Diarize"
    OPENMOSS_DEVICE: str = "cpu"  # cpu, cuda, auto
    OPENMOSS_CACHE_DIR: Optional[str] = None
    HF_TOKEN: Optional[str] = None

    # Long-Meeting Chunking & Audio Processing Configuration (Phase 4.26)
    AUDIO_CHUNK_DURATION_SECONDS: float = 600.0  # 10 minutes chunk duration
    AUDIO_CHUNK_OVERLAP_SECONDS: float = 30.0    # 30 seconds overlap window
    AUDIO_CHUNK_THRESHOLD_SECONDS: float = 600.0  # Audio duration threshold to trigger chunking
    AUDIO_CHUNK_CONCURRENCY: int = 1             # Bounded concurrency (default 1 sequential for VRAM safety)

    # -------------------------------------------------------------------------
    # Google Workspace & Google Meet Integration Configuration
    # -------------------------------------------------------------------------
    GOOGLE_CLIENT_ID: Optional[str] = None
    GOOGLE_CLIENT_SECRET: Optional[str] = None
    GOOGLE_REDIRECT_URI: Optional[str] = None
    GOOGLE_PROJECT_ID: Optional[str] = None
    GOOGLE_SCOPES: Union[List[str], str] = [
        "https://www.googleapis.com/auth/meetings.space.readonly",
        "https://www.googleapis.com/auth/meetings.space.created",
        "https://www.googleapis.com/auth/calendar.events.readonly",
    ]
    GOOGLE_MEET_MEDIA_API_ENDPOINT: Optional[str] = None
    GOOGLE_MEET_ENABLED: bool = True

    # -------------------------------------------------------------------------
    # Microsoft 365 & Microsoft Teams Integration Configuration
    # -------------------------------------------------------------------------
    MICROSOFT_CLIENT_ID: Optional[str] = None
    MICROSOFT_CLIENT_SECRET: Optional[str] = None
    MICROSOFT_TENANT_ID: Optional[str] = None
    MICROSOFT_REDIRECT_URI: Optional[str] = None
    MICROSOFT_GRAPH_SCOPES: Union[List[str], str] = [
        "OnlineMeetings.ReadWrite",
        "OnlineMeetingTranscript.Read.All",
        "Calls.JoinGroupCall.All",
        "Calls.AccessMedia.All",
    ]
    TEAMS_BOT_ENDPOINT: Optional[str] = None
    TEAMS_MEDIA_BOT_ENABLED: bool = False

    # -------------------------------------------------------------------------
    # Real Provider E2E Execution Flags
    # -------------------------------------------------------------------------
    RUN_REAL_GOOGLE_MEET_E2E: bool = False
    RUN_REAL_TEAMS_E2E: bool = False

    # -------------------------------------------------------------------------
    # Security Foundation & Token Verification Customization
    # -------------------------------------------------------------------------
    SECRET_KEY: str = "default-insecure-secret-key-change-in-production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24  # 24 hours
    JWT_SECRET_KEY: Optional[str] = None
    JWT_ISSUER: Optional[str] = None
    JWT_AUDIENCE: Optional[str] = None
    ALLOW_TEST_TOKENS: Optional[bool] = None  # If None: True in test/development, False in production/staging
    AUTH_API_KEYS: Union[List[str], str] = []

    @field_validator("AUTH_API_KEYS", mode="before")
    @classmethod
    def assemble_auth_api_keys(cls, v: Union[str, List[str]]) -> List[str]:
        if isinstance(v, str) and not v.startswith("["):
            return [i.strip() for i in v.split(",") if i.strip()]
        elif isinstance(v, str) and v.startswith("["):
            try:
                parsed = json.loads(v)
                if isinstance(parsed, list):
                    return [str(item).strip() for item in parsed if str(item).strip()]
            except Exception:
                pass
        elif isinstance(v, list):
            return [str(item).strip() for item in v if str(item).strip()]
        return []

    @property
    def test_tokens_enabled(self) -> bool:
        """Determines if development/test fixture tokens (e.g. 'admin-token') are permitted."""
        if self.ALLOW_TEST_TOKENS is not None:
            return bool(self.ALLOW_TEST_TOKENS)
        return self.ENVIRONMENT.lower() in {"development", "test"}

    @property
    def effective_jwt_secret(self) -> str:
        """Returns the active JWT signing key."""
        return self.JWT_SECRET_KEY or self.SECRET_KEY


@lru_cache()
def get_settings() -> Settings:
    """Cached accessor for application settings."""
    return Settings()
