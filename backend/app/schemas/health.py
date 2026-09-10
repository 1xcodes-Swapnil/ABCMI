"""
ABCI-MI Health Schemas
Defines structured responses for system health, infrastructure readiness, and liveness probes.
"""

from datetime import datetime
from typing import Dict, Optional
from pydantic import Field

from app.schemas.base import CoreBaseModel


class ServiceHealthInfo(CoreBaseModel):
    """Health information for an individual subsystem or external service."""

    status: str = Field(..., description="Service status: healthy, unhealthy, degraded, or disabled")
    latency_ms: Optional[float] = Field(default=None, description="Response latency in milliseconds")
    error: Optional[str] = Field(default=None, description="Error message if unhealthy")
    details: Optional[Dict[str, object]] = Field(default=None, description="Additional diagnostic details")


class HealthResponse(CoreBaseModel):
    """Full health check response containing application metadata and service status."""

    status: str = Field(..., description="Overall system status: healthy, degraded, or unhealthy")
    project_name: str = Field(..., description="Project name")
    version: str = Field(..., description="Backend application version")
    environment: str = Field(..., description="Runtime environment: development, staging, production, test")
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="Health check evaluation timestamp")
    uptime_seconds: float = Field(..., description="Server uptime in seconds")
    services: Dict[str, ServiceHealthInfo] = Field(
        default_factory=dict,
        description="Health status of configured infrastructure dependencies",
    )


class LivenessResponse(CoreBaseModel):
    """Lightweight response for container orchestrator liveness probe."""

    status: str = Field(default="alive", description="Process liveness status")
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="Probe timestamp")


class ReadinessResponse(CoreBaseModel):
    """Container orchestrator readiness probe response."""

    status: str = Field(..., description="Readiness status: ready or not_ready")
    ready: bool = Field(..., description="Boolean readiness flag")
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="Probe timestamp")
    services_ready: Dict[str, bool] = Field(
        default_factory=dict,
        description="Summary readiness of key components",
    )
