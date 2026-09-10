"""
Notification Pydantic Schemas (Phase 4.24)
Defines request, response, filter, category, and severity schemas for user and tenant notifications.
"""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
import uuid
from pydantic import Field

from app.schemas.base import CoreBaseModel, TimestampSchema


class NotificationCategory(str, Enum):
    """Notification domain categories."""
    MEETING = "meeting"
    PROCESSING = "processing"
    KNOWLEDGE = "knowledge"
    REPORT = "report"
    SYSTEM = "system"
    SECURITY = "security"


class NotificationSeverity(str, Enum):
    """Notification severity levels."""
    INFO = "info"
    SUCCESS = "success"
    WARNING = "warning"
    ERROR = "error"
    SECURITY = "security"


class NotificationCreate(CoreBaseModel):
    """Schema for direct or mapped creation of a notification."""
    tenant_id: str = Field(..., description="Target tenant workspace ID")
    user_id: Optional[uuid.UUID] = Field(default=None, description="Optional target user ID (None for tenant broadcast)")
    event_type: str = Field(..., description="Underlying system event name (e.g. MeetingCompleted)")
    category: NotificationCategory = Field(..., description="Notification functional category")
    title: str = Field(..., min_length=1, max_length=255, description="Notification headline")
    description: str = Field(..., min_length=1, description="Sanitized human-readable notification details")
    severity: NotificationSeverity = Field(default=NotificationSeverity.INFO, description="Notification severity")
    meeting_id: Optional[uuid.UUID] = Field(default=None, description="Associated meeting ID")
    project_id: Optional[uuid.UUID] = Field(default=None, description="Associated project workspace ID")
    resource_id: Optional[str] = Field(default=None, description="Target resource or entity identifier")
    correlation_id: Optional[str] = Field(default=None, description="Tracing correlation identifier")
    event_id: Optional[str] = Field(default=None, description="Source event ID for deduplication")
    metadata: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Supplementary non-sensitive attributes")


class NotificationResponse(TimestampSchema):
    """Frontend-safe DTO representation of a notification."""
    id: uuid.UUID = Field(..., description="Notification unique identifier")
    tenant_id: str = Field(..., description="Tenant workspace ID")
    user_id: Optional[uuid.UUID] = Field(default=None, description="Target user ID")
    event_type: str = Field(..., description="Event type identifier")
    category: NotificationCategory = Field(..., description="Notification category")
    title: str = Field(..., description="Notification title")
    description: str = Field(..., description="Notification message body")
    severity: NotificationSeverity = Field(..., description="Severity level")
    is_read: bool = Field(default=False, description="Read/unread status")
    meeting_id: Optional[uuid.UUID] = Field(default=None, description="Associated meeting ID")
    project_id: Optional[uuid.UUID] = Field(default=None, description="Associated project ID")
    resource_id: Optional[str] = Field(default=None, description="Referenced resource ID")
    correlation_id: Optional[str] = Field(default=None, description="Correlation ID for distributed tracing")
    event_id: Optional[str] = Field(default=None, description="Originating event ID")
    read_at: Optional[datetime] = Field(default=None, description="Timestamp when marked as read")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Metadata dictionary")


class NotificationListResponse(CoreBaseModel):
    """Paginated list of notifications with unread statistics."""
    items: List[NotificationResponse] = Field(default_factory=list, description="List of notification records")
    total: int = Field(..., ge=0, description="Total matching notifications count")
    unread_count: int = Field(..., ge=0, description="Total unread notifications count for current scope")
    limit: int = Field(..., ge=1, description="Page limit")
    offset: int = Field(..., ge=0, description="Page offset")


class NotificationUnreadCountResponse(CoreBaseModel):
    """Unread notifications summary count."""
    unread_count: int = Field(..., ge=0, description="Total unread notifications count")
    tenant_id: str = Field(..., description="Tenant workspace identifier")
    user_id: Optional[uuid.UUID] = Field(default=None, description="Target user ID if scoped")


class NotificationBatchReadResponse(CoreBaseModel):
    """Response returned when marking all notifications as read."""
    status: str = Field(default="success")
    updated_count: int = Field(..., ge=0, description="Number of notifications marked as read")
    read_at: datetime = Field(..., description="Timestamp of batch read execution")


class RealtimeNotificationPayload(CoreBaseModel):
    """
    Formal backend real-time delivery payload contract for WebSocket/SSE gateways
    and distributed messaging brokers.
    Guarantees no raw ORM entities, secrets, or internal paths are broadcast.
    """
    event_type: str = Field(default="NotificationCreated", description="Event descriptor (e.g. NotificationCreated, NotificationUpdated)")
    id: uuid.UUID = Field(..., description="Unique notification identifier")
    tenant_id: str = Field(..., description="Tenant workspace ID")
    user_id: Optional[uuid.UUID] = Field(default=None, description="Target user ID or None for tenant broadcast")
    category: NotificationCategory = Field(..., description="Domain category")
    severity: NotificationSeverity = Field(..., description="Severity level")
    title: str = Field(..., description="Notification headline")
    description: str = Field(..., description="Sanitized notification body")
    is_read: bool = Field(default=False, description="Read state")
    meeting_id: Optional[uuid.UUID] = Field(default=None, description="Meeting ID or None if deleted/unassociated")
    project_id: Optional[uuid.UUID] = Field(default=None, description="Project ID or None if deleted/unassociated")
    resource_id: Optional[str] = Field(default=None, description="Normalized external or domain resource reference")
    correlation_id: Optional[str] = Field(default=None, description="Distributed correlation trace ID")
    event_id: Optional[str] = Field(default=None, description="Stable source event deduplication ID")
    created_at: datetime = Field(..., description="UTC creation timestamp")
    read_at: Optional[datetime] = Field(default=None, description="UTC read timestamp")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Sanitized supplementary metadata")


class NotificationCleanupRequest(CoreBaseModel):
    """Request parameters for retention cleanup execution."""
    retention_days: int = Field(default=30, ge=1, le=3650, description="Retention age threshold for standard notifications in days")
    security_retention_days: int = Field(default=365, ge=1, le=3650, description="Retention age threshold for security/audit notifications in days")
    include_unread: bool = Field(default=False, description="Whether to include unread notifications in cleanup")


class NotificationCleanupResponse(CoreBaseModel):
    """Result summary of a notification retention cleanup operation."""
    status: str = Field(default="success")
    deleted_count: int = Field(..., ge=0, description="Number of expired notifications deleted")
    retention_days_applied: int = Field(..., description="Standard retention threshold applied in days")
    security_retention_days_applied: int = Field(..., description="Security retention threshold applied in days")
    include_unread_applied: bool = Field(..., description="Whether unread notifications were included")
    executed_at: datetime = Field(..., description="UTC timestamp of cleanup completion")

