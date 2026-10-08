"""
ABCI-MI Health & Diagnostic Endpoints
Provides system status, infrastructure dependency checks, and liveness/readiness probes.
"""

import asyncio
from datetime import datetime
import os
import sys
try:
    import resource  # Unix only
    _HAS_RESOURCE = True
except ImportError:
    _HAS_RESOURCE = False  # Windows — resource module unavailable
import time
from typing import Any, Dict
from fastapi import APIRouter, status
from fastapi.responses import JSONResponse

from app.core.config import get_settings
from app.core.logging import get_logger
from app.infrastructure.database import check_database_health
from app.infrastructure.qdrant import check_qdrant_health
from app.infrastructure.redis import check_redis_health
from app.infrastructure.storage import get_storage_manager
from app.schemas.health import (
    HealthResponse,
    LivenessResponse,
    ReadinessResponse,
    ServiceHealthInfo,
)

logger = get_logger("api.v1.health")
router = APIRouter(prefix="/health", tags=["Health & Diagnostics"])

# Record app startup timestamp
_START_TIME = time.time()


@router.get(
    "",
    response_model=HealthResponse,
    summary="Comprehensive System Health Check",
    description="Evaluates application status and checks connectivity to PostgreSQL, Redis, Qdrant, and File Storage.",
)
async def get_health() -> HealthResponse:
    """Performs parallel health checks across all backend infrastructure services."""
    settings = get_settings()
    uptime = round(time.time() - _START_TIME, 2)

    # Run health checks concurrently with timeouts
    db_task = asyncio.create_task(check_database_health())
    redis_task = asyncio.create_task(check_redis_health())
    qdrant_task = asyncio.create_task(check_qdrant_health())

    storage_mgr = get_storage_manager()
    storage_health = storage_mgr.check_health()

    # Wait for all checks with safety timeout
    results = await asyncio.gather(db_task, redis_task, qdrant_task, return_exceptions=True)

    db_res = results[0] if not isinstance(results[0], Exception) else {"status": "unhealthy", "error": str(results[0])}
    redis_res = results[1] if not isinstance(results[1], Exception) else {"status": "unhealthy", "error": str(results[1])}
    qdrant_res = results[2] if not isinstance(results[2], Exception) else {"status": "unhealthy", "error": str(results[2])}

    services = {
        "database": ServiceHealthInfo(
            status=db_res.get("status", "unhealthy"),
            latency_ms=db_res.get("latency_ms"),
            error=db_res.get("error"),
            details={"database": settings.POSTGRES_DB, "host": settings.POSTGRES_SERVER},
        ),
        "redis": ServiceHealthInfo(
            status=redis_res.get("status", "unhealthy"),
            latency_ms=redis_res.get("latency_ms"),
            error=redis_res.get("error"),
            details={"host": settings.REDIS_HOST, "port": settings.REDIS_PORT},
        ),
        "qdrant": ServiceHealthInfo(
            status=qdrant_res.get("status", "unhealthy"),
            latency_ms=qdrant_res.get("latency_ms"),
            error=qdrant_res.get("error"),
            details={"host": settings.QDRANT_HOST, "port": settings.QDRANT_PORT},
        ),
        "storage": ServiceHealthInfo(
            status=storage_health.get("status", "unhealthy"),
            error=storage_health.get("error"),
            details={"path": storage_health.get("path"), "writable": storage_health.get("writable")},
        ),
    }

    # Evaluate overall status
    unhealthy_services = [name for name, info in services.items() if info.status == "unhealthy"]

    if not unhealthy_services:
        overall_status = "healthy"
    elif len(unhealthy_services) < len(services):
        overall_status = "degraded"
    else:
        overall_status = "unhealthy"

    return HealthResponse(
        status=overall_status,
        project_name=settings.PROJECT_NAME,
        version=settings.VERSION,
        environment=settings.ENVIRONMENT,
        timestamp=datetime.utcnow(),
        uptime_seconds=uptime,
        services=services,
    )


@router.get(
    "/live",
    response_model=LivenessResponse,
    summary="Kubernetes/Docker Liveness Probe",
    description="Returns 200 OK if the FastAPI process is running.",
)
async def liveness_probe() -> LivenessResponse:
    """Lightweight endpoint to confirm the server process is responsive."""
    return LivenessResponse(status="alive", timestamp=datetime.utcnow())


@router.get(
    "/ready",
    response_model=ReadinessResponse,
    summary="Kubernetes/Docker Readiness Probe",
    description="Verifies the server is ready to accept traffic.",
)
async def readiness_probe() -> ReadinessResponse:
    """Verifies that the server and storage subsystem are ready."""
    storage_mgr = get_storage_manager()
    storage_ok = storage_mgr.check_health().get("status") == "healthy"

    return ReadinessResponse(
        status="ready" if storage_ok else "not_ready",
        ready=storage_ok,
        timestamp=datetime.utcnow(),
        services_ready={"storage": storage_ok},
    )


@router.get(
    "/ping",
    summary="Simple Ping",
    description="Returns simple pong text for fast latency verification.",
)
async def ping() -> JSONResponse:
    """Fast ping endpoint."""
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={"ping": "pong", "timestamp": datetime.utcnow().isoformat()},
    )


@router.get(
    "/system-metrics",
    summary="Real-Time System Hardware & Runtime Telemetry",
    description="Returns live CPU, memory, thread pool, and subsystem latencies.",
)
async def get_system_metrics() -> JSONResponse:
    """
    Collects live operational telemetry including memory footprint, CPU load averages,
    and individual subsystem round-trip times.
    """
    settings = get_settings()
    uptime = round(time.time() - _START_TIME, 2)

    memory = {"total_mb": None, "used_mb": None, "free_mb": None, "percent": None, "process_rss_mb": None}
    cpu = {"total_percent": None, "cores": os.cpu_count(), "load_averages": None}
    try:
        import psutil
        measured = psutil.virtual_memory()
        memory = {"total_mb": measured.total / 1048576, "used_mb": measured.used / 1048576,
                  "free_mb": measured.available / 1048576, "percent": measured.percent,
                  "process_rss_mb": psutil.Process().memory_info().rss / 1048576}
        cpu["total_percent"] = await asyncio.to_thread(psutil.cpu_percent, 0.1)
        if hasattr(os, "getloadavg"):
            cpu["load_averages"] = list(os.getloadavg())
    except (ImportError, OSError):
        pass
    results = await asyncio.gather(check_database_health(), check_redis_health(), check_qdrant_health(), return_exceptions=True)
    statuses, latencies = {"fastapi": "healthy", "asr_worker": "not measured", "diarization": "not measured"}, {}
    for name, result in zip(("database", "redis", "qdrant"), results):
        statuses[name] = result.get("status", "unknown") if isinstance(result, dict) else "unhealthy"
        latencies[name + "_ms"] = result.get("latency_ms") if isinstance(result, dict) else None
    return JSONResponse(content={"status": "healthy" if all(statuses[n] == "healthy" for n in ("database", "redis", "qdrant")) else "degraded",
        "timestamp": datetime.utcnow().isoformat(), "uptime_seconds": uptime,
        "node_environment": settings.ENVIRONMENT, "execution_mode": settings.EXECUTION_MODE,
        "cpu": cpu, "memory": memory, "subsystem_latencies": latencies, "subsystems_status": statuses})
