"""
Pydantic Schemas for Action Items (Phase 4.21)
Defines request, response, filter, and lifecycle schemas for meeting action items.
"""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
import uuid
from pydantic import Field, field_validator

from app.schemas.base import CoreBaseModel, TimestampSchema


class ActionItemStatus(str, Enum):
    """Lifecycle states for action items."""

    OPEN = "open"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class ActionItemPriority(str, Enum):
    """Priority levels for action items."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ActionItemCreate(CoreBaseModel):
    """Schema for manual or user-confirmed creation of an action item."""

    title: str = Field(..., min_length=1, max_length=255, description="Action item summary or title")
    description: Optional[str] = Field(default=None, description="Detailed description or context")
    status: ActionItemStatus = Field(default=ActionItemStatus.OPEN, description="Initial status")
    priority: ActionItemPriority = Field(default=ActionItemPriority.MEDIUM, description="Priority level")
    assignee: Optional[str] = Field(default=None, max_length=150, description="Assigned individual or team")
    due_date: Optional[str] = Field(default=None, description="Target completion date/time (ISO 8601 or date string)")
    source_segment_ids: Optional[List[str]] = Field(default_factory=list, description="Associated transcript segment references")
    correlation_id: Optional[str] = Field(default=None, description="Correlation identifier for tracing")


class ActionItemUpdate(CoreBaseModel):
    """Schema for updating fields of an action item."""

    title: Optional[str] = Field(default=None, min_length=1, max_length=255)
    description: Optional[str] = Field(default=None)
    status: Optional[ActionItemStatus] = Field(default=None)
    priority: Optional[ActionItemPriority] = Field(default=None)
    assignee: Optional[str] = Field(default=None, max_length=150)
    due_date: Optional[str] = Field(default=None)
    confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    correlation_id: Optional[str] = Field(default=None)


class ActionItemResponse(TimestampSchema):
    """Frontend-safe DTO for an action item."""

    id: uuid.UUID
    meeting_id: uuid.UUID
    title: str
    description: str
    status: ActionItemStatus
    priority: ActionItemPriority
    assignee: Optional[str] = None
    due_date: Optional[str] = None
    confidence: Optional[float] = None
    is_low_confidence: bool = False
    requires_verification: bool = False
    source_segments: List[str] = Field(default_factory=list)
    version: int = 1
    provenance: Optional[Dict[str, Any]] = Field(default_factory=dict)
    created_at: datetime
    updated_at: Optional[datetime] = None


class ActionItemListResponse(CoreBaseModel):
    """Paginated list of action items."""

    items: List[ActionItemResponse] = Field(default_factory=list)
    total: int
    limit: int
    offset: int
