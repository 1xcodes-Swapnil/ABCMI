"""
Pydantic Schemas for Project & Cross-Meeting Intelligence (Phase 4.22)
Defines request, response, and aggregation models for projects and cross-meeting intelligence.
"""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
import uuid
from pydantic import Field

from app.schemas.action_item import ActionItemResponse
from app.schemas.base import CoreBaseModel, TimestampSchema
from app.schemas.meeting_intelligence import DecisionResponse, InsightResponse


class ProjectStatus(str, Enum):
    """Lifecycle status of a project/workspace."""

    ACTIVE = "active"
    ARCHIVED = "archived"
    COMPLETED = "completed"


# -----------------------------------------------------------------------------
# Project Base Schemas
# -----------------------------------------------------------------------------


class ProjectCreate(CoreBaseModel):
    """Request payload to create a new project/workspace."""

    name: str = Field(..., min_length=1, max_length=255, description="Project or workspace name")
    description: Optional[str] = Field(default=None, description="Project goals, scope, and description")
    status: ProjectStatus = Field(default=ProjectStatus.ACTIVE, description="Initial project status")
    settings: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Project-specific configuration")


class ProjectUpdate(CoreBaseModel):
    """Request payload to update project details."""

    name: Optional[str] = Field(default=None, min_length=1, max_length=255)
    description: Optional[str] = Field(default=None)
    status: Optional[ProjectStatus] = Field(default=None)
    settings: Optional[Dict[str, Any]] = Field(default=None)


class ProjectResponse(TimestampSchema):
    """Frontend-safe DTO for a project/workspace."""

    id: uuid.UUID
    tenant_id: str
    name: str
    description: Optional[str] = None
    status: ProjectStatus
    created_by: Optional[str] = None
    meeting_count: int = 0
    settings: Optional[Dict[str, Any]] = Field(default_factory=dict)
    created_at: datetime
    updated_at: Optional[datetime] = None


class ProjectListResponse(CoreBaseModel):
    """Paginated list of projects."""

    items: List[ProjectResponse] = Field(default_factory=list)
    total: int
    limit: int
    offset: int


# -----------------------------------------------------------------------------
# Project Meeting Association Schemas
# -----------------------------------------------------------------------------


class ProjectMeetingAssociationRequest(CoreBaseModel):
    """Request to associate a meeting with a project."""

    meeting_id: uuid.UUID = Field(..., description="ID of the meeting to associate")
    notes: Optional[str] = Field(default=None, description="Optional association context or notes")


class ProjectMeetingResponse(TimestampSchema):
    """DTO for an associated meeting within a project."""

    id: uuid.UUID
    project_id: uuid.UUID
    meeting_id: uuid.UUID
    meeting_title: str
    meeting_status: str
    meeting_start_time: Optional[datetime] = None
    added_by: Optional[str] = None
    notes: Optional[str] = None
    created_at: datetime


class ProjectMeetingListResponse(CoreBaseModel):
    """Paginated list of meetings associated with a project."""

    items: List[ProjectMeetingResponse] = Field(default_factory=list)
    total: int
    limit: int
    offset: int


# -----------------------------------------------------------------------------
# Cross-Meeting Intelligence Schemas
# -----------------------------------------------------------------------------


class CrossMeetingActionItemsSummary(CoreBaseModel):
    """Aggregated action items across all meetings in a project."""

    project_id: uuid.UUID
    total_action_items: int
    open_count: int
    in_progress_count: int
    completed_count: int
    cancelled_count: int
    critical_count: int
    high_count: int
    by_assignee: Dict[str, int] = Field(default_factory=dict)
    items: List[ActionItemResponse] = Field(default_factory=list)
    limit: int
    offset: int


class CrossMeetingDecisionItem(CoreBaseModel):
    """Decision with associated meeting context."""

    id: uuid.UUID
    meeting_id: uuid.UUID
    meeting_title: str
    title: Optional[str] = None
    content: str
    status: str
    confidence: Optional[float] = None
    is_low_confidence: bool = False
    requires_verification: bool = False
    alternatives: List[str] = Field(default_factory=list)
    impact: Optional[str] = None
    rationales: List[str] = Field(default_factory=list)
    created_at: datetime


class CrossMeetingDecisionsResponse(CoreBaseModel):
    """Aggregated decisions across meetings."""

    project_id: uuid.UUID
    total: int
    limit: int
    offset: int
    items: List[CrossMeetingDecisionItem] = Field(default_factory=list)


class RecurringTopicItem(CoreBaseModel):
    """Identified recurring topic across multiple meetings."""

    topic_name: str
    occurrence_count: int
    meeting_ids: List[uuid.UUID] = Field(default_factory=list)
    meeting_titles: List[str] = Field(default_factory=list)
    keywords: List[str] = Field(default_factory=list)
    first_seen: Optional[datetime] = None
    last_seen: Optional[datetime] = None
    average_confidence: float = 1.0


class RecurringTopicsResponse(CoreBaseModel):
    """List of identified recurring topics across project meetings."""

    project_id: uuid.UUID
    total_meetings_analyzed: int
    topics: List[RecurringTopicItem] = Field(default_factory=list)


class CrossMeetingInsightItem(CoreBaseModel):
    """Insight with associated meeting context."""

    id: uuid.UUID
    meeting_id: uuid.UUID
    meeting_title: str
    insight_type: str
    title: Optional[str] = None
    content: str
    sentiment: Optional[str] = None
    confidence: Optional[float] = None
    is_low_confidence: bool = False
    requires_verification: bool = False
    created_at: datetime


class CrossMeetingInsightsResponse(CoreBaseModel):
    """Aggregated insights and sentiment across project meetings."""

    project_id: uuid.UUID
    total: int
    limit: int
    offset: int
    sentiment_distribution: Dict[str, int] = Field(default_factory=dict)
    items: List[CrossMeetingInsightItem] = Field(default_factory=list)


class MeetingTimelineEntry(CoreBaseModel):
    """Chronological summary entry for a meeting in historical project context."""

    meeting_id: uuid.UUID
    title: str
    status: str
    date: Optional[datetime] = None
    decisions_count: int = 0
    action_items_count: int = 0
    open_action_items_count: int = 0
    summary_snippet: Optional[str] = None


class ProjectHistoricalContextResponse(CoreBaseModel):
    """Chronological historical progression of meetings and knowledge in a project."""

    project_id: uuid.UUID
    project_name: str
    total_meetings: int
    timeline: List[MeetingTimelineEntry] = Field(default_factory=list)
    recurring_themes: List[str] = Field(default_factory=list)


class ProjectSummaryResponse(CoreBaseModel):
    """High-level executive roll-up summary for an entire project/workspace."""

    project_id: uuid.UUID
    project_name: str
    total_meetings: int
    active_meetings: int
    executive_summary: str
    total_decisions: int
    total_action_items: int
    open_action_items: int
    completed_action_items: int
    sentiment_overview: Dict[str, int] = Field(default_factory=dict)
    key_decisions: List[CrossMeetingDecisionItem] = Field(default_factory=list)
    top_action_items: List[ActionItemResponse] = Field(default_factory=list)
    recurring_topics: List[RecurringTopicItem] = Field(default_factory=list)


class RelatedMeetingItem(CoreBaseModel):
    """A related meeting with similarity score and shared concepts."""

    meeting_id: uuid.UUID
    title: str
    date: Optional[datetime] = None
    shared_topics: List[str] = Field(default_factory=list)
    shared_keywords: List[str] = Field(default_factory=list)
    similarity_score: float
    reason: str


class RelatedMeetingsResponse(CoreBaseModel):
    """Related meetings for a given meeting context."""

    meeting_id: uuid.UUID
    total_related: int
    related_meetings: List[RelatedMeetingItem] = Field(default_factory=list)
