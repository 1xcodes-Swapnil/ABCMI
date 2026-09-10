"""
ABCI-MI (Adaptive Blackboard & Collaboration Intelligence for Multilingual Interaction)
FastAPI Main Application Entry Point
"""

from contextlib import asynccontextmanager
from typing import AsyncGenerator
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.v1.router import api_v1_router
from app.core.config import get_settings
from app.core.exceptions import register_exception_handlers
from app.core.logging import get_logger, setup_logging
from app.infrastructure.database import close_database_connections, init_database
from app.infrastructure.qdrant import close_qdrant_client, init_qdrant_client
from app.infrastructure.redis import close_redis_client, init_redis_client
from app.infrastructure.storage import get_storage_manager

# Initialize application settings and logger
settings = get_settings()
setup_logging(settings.LOG_LEVEL)
logger = get_logger("main")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """
    Lifecycle manager for FastAPI application.
    Initializes infrastructure connections on startup and ensures clean disposal on shutdown.
    """
    logger.info(f"Starting {settings.PROJECT_NAME} v{settings.VERSION} [{settings.ENVIRONMENT}]")

    # 1. Initialize Storage Directories
    try:
        storage_mgr = get_storage_manager()
        logger.info(f"Storage subsystem ready at {storage_mgr.base_path}")
    except Exception as e:
        logger.warning(f"Storage subsystem initialization warning: {e}")

    # 2. Lazy / Non-blocking infrastructure client preparation
    try:
        init_database()
        logger.info("PostgreSQL engine initialized.")
    except Exception as e:
        logger.warning(f"PostgreSQL connection initialization deferred/failed: {e}")

    try:
        init_redis_client()
        logger.info("Redis client initialized.")
    except Exception as e:
        logger.warning(f"Redis client initialization deferred/failed: {e}")

    try:
        init_qdrant_client()
        logger.info("Qdrant client initialized.")
    except Exception as e:
        logger.warning(f"Qdrant client initialization deferred/failed: {e}")

    logger.info("ABCI-MI Backend startup complete. Ready to receive requests.")

    yield

    # Shutdown sequence
    logger.info("Initiating ABCI-MI Backend graceful shutdown...")

    # Close infrastructure connections
    try:
        await close_database_connections()
    except Exception as e:
        logger.error(f"Error during PostgreSQL connection cleanup: {e}")

    try:
        await close_redis_client()
    except Exception as e:
        logger.error(f"Error during Redis connection cleanup: {e}")

    try:
        await close_qdrant_client()
    except Exception as e:
        logger.error(f"Error during Qdrant client cleanup: {e}")

    logger.info("ABCI-MI Backend shutdown completed successfully.")


def create_application() -> FastAPI:
    """Application factory that constructs and configures the FastAPI instance."""
    app = FastAPI(
        title=settings.PROJECT_NAME,
        version=settings.VERSION,
        description=settings.DESCRIPTION,
        openapi_url=f"{settings.API_V1_STR}/openapi.json" if settings.DEBUG else None,
        docs_url=f"{settings.API_V1_STR}/docs" if settings.DEBUG else None,
        redoc_url=f"{settings.API_V1_STR}/redoc" if settings.DEBUG else None,
        lifespan=lifespan,
    )

    # Configure CORS
    cors_origins = settings.CORS_ORIGINS
    if isinstance(cors_origins, str):
        cors_origins = [cors_origins]

    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Register Global Error & Exception Handlers
    register_exception_handlers(app)

    # Mount API Routers
    app.include_router(api_v1_router, prefix=settings.API_V1_STR)

    # Root endpoint
    @app.get("/", tags=["Root"])
    async def root() -> JSONResponse:
        return JSONResponse(
            content={
                "project": settings.PROJECT_NAME,
                "version": settings.VERSION,
                "environment": settings.ENVIRONMENT,
                "status": "running",
                "api_docs": f"{settings.API_V1_STR}/docs" if settings.DEBUG else "Disabled in production",
                "health_check": f"{settings.API_V1_STR}/health",
            }
        )

    return app


app = create_application()

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.DEBUG,
    )
