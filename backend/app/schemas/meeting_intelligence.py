"""
Pydantic Schemas for Meeting Intelligence (Phase 4.21)
Defines DTOs for Decisions, Topics, Insights, Summaries, Facts, and Hypotheses.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional
import uuid
from pydantic import Field

from app.schemas.base import CoreBaseModel, TimestampSchema


class DecisionResponse(TimestampSchema):
    """Frontend-safe DTO for a recorded meeting decision."""

    id: uuid.UUID
    meeting_id: uuid.UUID
    title: Optional[str] = None
    content: str
    status: str
    confidence: Optional[float] = None
    is_low_confidence: bool = False
    requires_verification: bool = False
    alternatives: Optional[List[str]] = Field(default_factory=list)
    impact: Optional[str] = None
    rationales: Optional[List[str]] = Field(default_factory=list)
    version: int = 1
    provenance: Optional[Dict[str, Any]] = Field(default_factory=dict)
    created_at: datetime
    updated_at: Optional[datetime] = None


class DecisionListResponse(CoreBaseModel):
    """Paginated list of meeting decisions."""

    items: List[DecisionResponse] = Field(default_factory=list)
    total: int
    limit: int
    offset: int


class TopicResponse(TimestampSchema):
    """Frontend-safe DTO for an extracted meeting topic."""

    id: uuid.UUID
    meeting_id: uuid.UUID
    title: str
    description: Optional[str] = None
    keywords: List[str] = Field(default_factory=list)
    start_time_ms: Optional[int] = None
    end_time_ms: Optional[int] = None
    confidence: Optional[float] = None
    version: int = 1
    provenance: Optional[Dict[str, Any]] = Field(default_factory=dict)
    created_at: datetime
    updated_at: Optional[datetime] = None


class TopicListResponse(CoreBaseModel):
    """Paginated list of extracted topics."""

    items: List[TopicResponse] = Field(default_factory=list)
    total: int
    limit: int
    offset: int


class InsightResponse(TimestampSchema):
    """Frontend-safe DTO for a transcript or context insight."""

    id: uuid.UUID
    meeting_id: uuid.UUID
    insight_type: str
    title: Optional[str] = None
    content: str
    sentiment: Optional[str] = None
    confidence: Optional[float] = None
    is_low_confidence: bool = False
    requires_verification: bool = False
    version: int = 1
    provenance: Optional[Dict[str, Any]] = Field(default_factory=dict)
    created_at: datetime
    updated_at: Optional[datetime] = None


class InsightListResponse(CoreBaseModel):
    """Paginated list of meeting insights."""

    items: List[InsightResponse] = Field(default_factory=list)
    total: int
    limit: int
    offset: int


class SummarySection(CoreBaseModel):
    """Individual section of a structured meeting summary."""

    heading: str
    content: str
    key_points: List[str] = Field(default_factory=list)


class SummaryResponse(TimestampSchema):
    """Frontend-safe DTO for meeting executive/structured summary."""

    id: uuid.UUID
    meeting_id: uuid.UUID
    title: Optional[str] = "Executive Summary"
    content: str
    sections: List[SummarySection] = Field(default_factory=list)
    key_takeaways: List[str] = Field(default_factory=list)
    confidence: Optional[float] = None
    version: int = 1
    provenance: Optional[Dict[str, Any]] = Field(default_factory=dict)
    created_at: datetime
    updated_at: Optional[datetime] = None


class FactResponse(TimestampSchema):
    """Frontend-safe DTO for verified or extracted facts."""

    id: uuid.UUID
    meeting_id: uuid.UUID
    statement: str
    category: Optional[str] = None
    confidence: Optional[float] = None
    is_verified: bool = False
    version: int = 1
    provenance: Optional[Dict[str, Any]] = Field(default_factory=dict)
    created_at: datetime
    updated_at: Optional[datetime] = None


class FactListResponse(CoreBaseModel):
    """Paginated list of facts."""

    items: List[FactResponse] = Field(default_factory=list)
    total: int
    limit: int
    offset: int


class HypothesisResponse(TimestampSchema):
    """Frontend-safe DTO for extracted hypotheses or working assumptions."""

    id: uuid.UUID
    meeting_id: uuid.UUID
    statement: str
    supporting_evidence: List[str] = Field(default_factory=list)
    confidence: Optional[float] = None
    status: str = "proposed"
    version: int = 1
    provenance: Optional[Dict[str, Any]] = Field(default_factory=dict)
    created_at: datetime
    updated_at: Optional[datetime] = None


class HypothesisListResponse(CoreBaseModel):
    """Paginated list of hypotheses."""

    items: List[HypothesisResponse] = Field(default_factory=list)
    total: int
    limit: int
    offset: int
