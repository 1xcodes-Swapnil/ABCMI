"""
Admin, Audit, and Security Pydantic Schemas (Phase 4.25)
Defines request, response, and filter DTOs for Admin users/roles/system status,
immutable Audit logs, and Security telemetry.
"""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
import uuid
from pydantic import Field

from app.schemas.base import CoreBaseModel, TimestampSchema


# =============================================================================
# Role and Permission Schemas
# =============================================================================

class RoleDefinitionResponse(CoreBaseModel):
    """Schema representing an application RBAC role with permissions."""
    role: str = Field(..., description="Role identifier (e.g., admin, security_officer, security_auditor, host, member)")
    name: str = Field(..., description="Human-readable role title")
    description: str = Field(..., description="Role description and scope of authority")
    permissions: List[str] = Field(default_factory=list, description="Granted permission capabilities")
    is_administrative: bool = Field(default=False, description="Whether role has administrative/security privileges")


class RoleListResponse(CoreBaseModel):
    """List of all supported application roles."""
    roles: List[RoleDefinitionResponse] = Field(..., description="Available application roles")
    total: int = Field(..., description="Total available roles")


# =============================================================================
# Admin User Management Schemas
# =============================================================================

class AdminUserResponse(TimestampSchema):
    """Safe administrative representation of a registered user."""
    id: uuid.UUID = Field(..., description="User unique identifier")
    email: str = Field(..., description="User email address")
    full_name: str = Field(..., description="Full display name")
    role: str = Field(..., description="Assigned role")
    status: str = Field(..., description="Account status (active, suspended, deactivated)")
    is_active: bool = Field(..., description="Whether user account is active")
    preferences: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Sanitized preferences")
    hosted_meetings_count: Optional[int] = Field(default=0, description="Total hosted meetings count")


class AdminUserListResponse(CoreBaseModel):
    """Paginated list of users for administrative querying."""
    items: List[AdminUserResponse] = Field(..., description="List of user profiles")
    total: int = Field(..., description="Total matched users")
    limit: int = Field(..., description="Pagination limit")
    offset: int = Field(..., description="Pagination offset")


# =============================================================================
# System Status & Diagnostic Schemas
# =============================================================================

class ServiceComponentStatus(CoreBaseModel):
    """Sanitized health and connectivity status of an infrastructure service."""
    status: str = Field(..., description="Component status: healthy, degraded, or unhealthy")
    latency_ms: Optional[float] = Field(default=None, description="Round-trip latency in milliseconds")
    error: Optional[str] = Field(default=None, description="Sanitized error description if degraded or unhealthy")


class EventBusStatus(CoreBaseModel):
    """Operational status of the centralized Redis event bus."""
    mode: str = Field(..., description="Execution mode: distributed or local_fallback")
    is_distributed: bool = Field(..., description="Whether connected to distributed broker")
    production_ready: bool = Field(..., description="Whether infrastructure satisfies production deployment readiness")
    total_handlers: int = Field(default=0, description="Active registered event subscriber handlers count")


class AdminSystemStatusResponse(CoreBaseModel):
    """Aggregated system operational and infrastructure status."""
    status: str = Field(..., description="Overall system health status: healthy, degraded, or unhealthy")
    environment: str = Field(..., description="Runtime environment: development, test, staging, production")
    version: str = Field(..., description="Application version")
    uptime_seconds: float = Field(..., description="Total system uptime in seconds")
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="Evaluation timestamp")
    database: ServiceComponentStatus = Field(..., description="PostgreSQL database operational status")
    redis: ServiceComponentStatus = Field(..., description="Redis cache/pubsub connectivity status")
    qdrant: ServiceComponentStatus = Field(..., description="Qdrant vector engine operational status")
    storage: ServiceComponentStatus = Field(..., description="Local storage availability status")
    event_bus: EventBusStatus = Field(..., description="Event bus operational readiness")


# =============================================================================
# Audit Log Schemas
# =============================================================================

class AuditOutcome(str, Enum):
    """Audit action outcome status."""
    SUCCESS = "success"
    FAILURE = "failure"
    DENIED = "denied"
    ERROR = "error"


class AuditSeverity(str, Enum):
    """Audit log severity classification."""
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"
    SECURITY = "security"


class AuditCategory(str, Enum):
    """Audit category classification."""
    ADMIN = "admin"
    SECURITY = "security"
    AUTH = "auth"
    ACCESS_CONTROL = "access_control"
    MEETING = "meeting"
    PROJECT = "project"
    SYSTEM = "system"
    DATA_ACCESS = "data_access"


class AuditLogCreate(CoreBaseModel):
    """Payload for creating an immutable audit log record."""
    tenant_id: str = Field(..., description="Tenant workspace ID")
    user_id: Optional[uuid.UUID] = Field(default=None, description="Optional actor user ID")
    event_type: str = Field(..., description="Audit event type (e.g. auth.login.success, security.access_denied)")
    category: str = Field(default="system", description="Audit category")
    severity: str = Field(default="info", description="Severity level")
    action: str = Field(..., description="Action performed or attempted")
    outcome: str = Field(default="success", description="Action outcome: success, failure, denied, error")
    resource_type: str = Field(default="system", description="Target resource type")
    resource_id: Optional[str] = Field(default=None, description="Target resource ID (UUID or external string)")
    meeting_id: Optional[uuid.UUID] = Field(default=None, description="Associated meeting ID")
    project_id: Optional[uuid.UUID] = Field(default=None, description="Associated project ID")
    correlation_id: Optional[str] = Field(default=None, description="Correlation identifier")
    request_id: Optional[str] = Field(default=None, description="HTTP request identifier")
    event_id: Optional[str] = Field(default=None, description="Stable event idempotency identifier")
    ip_address: Optional[str] = Field(default=None, description="Sanitized client IP address")
    user_agent: Optional[str] = Field(default=None, description="Sanitized user agent string")
    details: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Sanitized event details")
    metadata: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Sanitized event metadata")


class AuditLogResponse(TimestampSchema):
    """Safe, immutable audit log representation."""
    id: uuid.UUID = Field(..., description="Audit log entry unique ID")
    tenant_id: str = Field(..., description="Tenant workspace ID")
    user_id: Optional[uuid.UUID] = Field(default=None, description="Actor user ID")
    event_type: str = Field(..., description="Audit event type")
    category: str = Field(..., description="Audit domain category")
    severity: str = Field(..., description="Severity level")
    action: str = Field(..., description="Action performed")
    outcome: str = Field(..., description="Outcome: success, failure, denied, error")
    resource_type: str = Field(..., description="Resource type")
    resource_id: Optional[str] = Field(default=None, description="Resource identifier")
    meeting_id: Optional[uuid.UUID] = Field(default=None, description="Associated meeting ID")
    project_id: Optional[uuid.UUID] = Field(default=None, description="Associated project ID")
    correlation_id: Optional[str] = Field(default=None, description="Correlation ID")
    request_id: Optional[str] = Field(default=None, description="Request ID")
    event_id: Optional[str] = Field(default=None, description="Event idempotency ID")
    ip_address: Optional[str] = Field(default=None, description="Client IP address")
    user_agent: Optional[str] = Field(default=None, description="Client User Agent")
    details: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Sanitized details")
    metadata: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Sanitized metadata")


class AuditLogListResponse(CoreBaseModel):
    """Paginated list response of audit log entries."""
    items: List[AuditLogResponse] = Field(..., description="Audit log records")
    total: int = Field(..., description="Total matched audit logs")
    limit: int = Field(..., description="Pagination limit")
    offset: int = Field(..., description="Pagination offset")


# =============================================================================
# Security Telemetry & Aggregation Schemas
# =============================================================================

class SecuritySummaryResponse(CoreBaseModel):
    """Aggregated security metrics over an evaluation window."""
    tenant_id: str = Field(..., description="Tenant workspace ID")
    window_days: int = Field(..., description="Evaluated time window in days")
    start_date: datetime = Field(..., description="Window start timestamp")
    end_date: datetime = Field(..., description="Window end timestamp")
    authentication_failures: int = Field(default=0, description="Total failed authentication attempts")
    authorization_failures: int = Field(default=0, description="Total authorization/RBAC failures")
    access_denials: int = Field(default=0, description="Total cross-tenant and resource access denials")
    security_alerts: int = Field(default=0, description="Total security events and alerts generated")
    affected_users: int = Field(default=0, description="Count of distinct affected users")
    affected_resources: int = Field(default=0, description="Count of distinct targeted resources")


class AccessDenialEventResponse(TimestampSchema):
    """Specialized DTO for access denial and authorization failure events."""
    id: uuid.UUID = Field(..., description="Audit event identifier")
    tenant_id: str = Field(..., description="Tenant workspace ID")
    user_id: Optional[uuid.UUID] = Field(default=None, description="Actor user ID")
    event_type: str = Field(..., description="Denial event type")
    action: str = Field(..., description="Attempted action")
    resource_type: str = Field(..., description="Target resource type")
    resource_id: Optional[str] = Field(default=None, description="Target resource ID")
    meeting_id: Optional[uuid.UUID] = Field(default=None, description="Associated meeting ID")
    project_id: Optional[uuid.UUID] = Field(default=None, description="Associated project ID")
    correlation_id: Optional[str] = Field(default=None, description="Correlation ID")
    reason: Optional[str] = Field(default=None, description="Sanitized reason for denial")


class AccessDenialListResponse(CoreBaseModel):
    """Paginated list of access denials."""
    items: List[AccessDenialEventResponse] = Field(..., description="Access denial audit entries")
    total: int = Field(..., description="Total access denials matched")
    limit: int = Field(..., description="Pagination limit")
    offset: int = Field(..., description="Pagination offset")
