"""
Ask ABCI-MI Query Interface Pydantic Schemas (Phase 4.23)
Defines query request, retrieval configuration, answer status, source attribution,
and structured query response models.
"""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
import uuid
from pydantic import Field, model_validator

from app.schemas.base import CoreBaseModel, TimestampSchema


class QueryRetrievalMode(str, Enum):
    """Supported knowledge retrieval modes."""
    STRUCTURED = "structured"
    SEMANTIC = "semantic"
    HYBRID = "hybrid"


class QueryAnswerStatus(str, Enum):
    """Status classification of the synthesized query answer."""
    ANSWERED = "answered"
    INSUFFICIENT_CONTEXT = "insufficient_context"
    REQUIRES_VERIFICATION = "requires_verification"
    UNAUTHORIZED = "unauthorized"
    INVALID_QUERY = "invalid_query"
    PROCESSING = "processing"
    FAILED = "failed"


class QueryKnowledgeType(str, Enum):
    """Knowledge object types queryable in the system."""
    ACTION_ITEM = "action_item"
    DECISION = "decision"
    TOPIC = "topic"
    SUMMARY = "summary"
    FACT = "fact"
    HYPOTHESIS = "hypothesis"
    TRANSCRIPT_INSIGHT = "transcript_insight"
    TRANSLATION = "translation"


# -----------------------------------------------------------------------------
# Request Schemas
# -----------------------------------------------------------------------------


class QueryRequest(CoreBaseModel):
    """Natural-language query intake request."""
    query: str = Field(
        ...,
        min_length=1,
        max_length=2000,
        description="The natural language question to ask ABCI-MI.",
        examples=["What decisions were made regarding Qdrant in our recent architecture meetings?"],
    )
    scope: Optional[str] = Field(
        default=None,
        description="Explicit query scope: 'meeting', 'project', or 'cross_meeting'. Inferred if omitted.",
    )
    meeting_id: Optional[uuid.UUID] = Field(
        default=None,
        description="Optional meeting ID to narrow query scope to a specific meeting.",
    )
    project_id: Optional[uuid.UUID] = Field(
        default=None,
        description="Optional project ID to narrow query scope to meetings within a project workspace.",
    )
    date_from: Optional[datetime] = Field(
        default=None,
        description="Optional start date/time filter for historical meetings/knowledge.",
    )
    date_to: Optional[datetime] = Field(
        default=None,
        description="Optional end date/time filter for historical meetings/knowledge.",
    )
    knowledge_types: Optional[List[str]] = Field(
        default=None,
        description="Optional list of knowledge object types to filter (e.g. ['action_item', 'decision']).",
    )
    search_mode: Optional[QueryRetrievalMode] = Field(
        default=None,
        description="Retrieval search mode alias: 'structured', 'semantic', or 'hybrid'.",
    )
    retrieval_mode: QueryRetrievalMode = Field(
        default=QueryRetrievalMode.HYBRID,
        description="Retrieval mode: 'structured', 'semantic', or 'hybrid'. Default is 'hybrid'.",
    )
    max_results: Optional[int] = Field(
        default=None,
        ge=1,
        le=100,
        description="Maximum results alias for limit.",
    )
    limit: int = Field(
        default=10,
        ge=1,
        le=100,
        description="Maximum number of authoritative source knowledge objects to retrieve and analyze.",
    )
    min_confidence: Optional[float] = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Optional minimum confidence threshold for retrieved knowledge.",
    )
    require_verification: Optional[bool] = Field(
        default=None,
        description="Optional flag to force human verification requirement in response.",
    )
    correlation_id: Optional[str] = Field(
        default=None,
        description="Optional client tracing / correlation ID.",
    )
    request_id: Optional[str] = Field(
        default=None,
        description="Optional client request ID for tracing and idempotency.",
    )

    @model_validator(mode="after")
    def validate_and_normalize_scope(self) -> "QueryRequest":
        # Synchronize search_mode and retrieval_mode without re-triggering validation loops
        if self.search_mode is not None and self.retrieval_mode != self.search_mode:
            object.__setattr__(self, "retrieval_mode", self.search_mode)
        elif self.search_mode is None:
            object.__setattr__(self, "search_mode", self.retrieval_mode)

        # Synchronize max_results and limit
        if self.max_results is not None and self.limit != self.max_results:
            object.__setattr__(self, "limit", self.max_results)
        elif self.max_results is None:
            object.__setattr__(self, "max_results", self.limit)

        # Validate / infer scope
        if self.scope:
            scope_val = self.scope.lower()
            if scope_val not in {"meeting", "project", "cross_meeting"}:
                raise ValueError("scope must be one of: 'meeting', 'project', 'cross_meeting'")
            if scope_val == "meeting" and not self.meeting_id:
                raise ValueError("meeting_id is required when scope is 'meeting'")
            if scope_val == "project" and not self.project_id:
                raise ValueError("project_id is required when scope is 'project'")
            if self.scope != scope_val:
                object.__setattr__(self, "scope", scope_val)
        else:
            if self.meeting_id:
                object.__setattr__(self, "scope", "meeting")
            elif self.project_id:
                object.__setattr__(self, "scope", "project")
            else:
                object.__setattr__(self, "scope", "cross_meeting")

        return self


# -----------------------------------------------------------------------------
# Source Attribution & Metadata
# -----------------------------------------------------------------------------


class QuerySourceKnowledgeObject(CoreBaseModel):
    """Authoritative source knowledge object supporting an answer."""
    knowledge_id: str = Field(..., description="Unique ID of the source KnowledgeObject")
    source_id: Optional[str] = Field(default=None, description="Alias for knowledge_id")
    meeting_id: Optional[str] = Field(default=None, description="Associated meeting ID")
    meeting_title: Optional[str] = Field(default=None, description="Title of the associated meeting")
    project_id: Optional[str] = Field(default=None, description="Associated project ID if applicable")
    object_type: str = Field(..., description="Knowledge type (e.g. decision, action_item, summary)")
    source_type: Optional[str] = Field(default=None, description="Alias for object_type")
    title: Optional[str] = Field(default=None, description="Title or headline of the source object")
    content: Optional[str] = Field(default=None, description="Body content of the source object")
    source_segments: Optional[List[str]] = Field(
        default=None,
        description="Referenced transcript segment IDs if applicable",
    )
    confidence: Optional[float] = Field(default=None, description="Confidence score of source object")
    relevance_score: Optional[float] = Field(default=None, description="Relevance score to query")
    version: int = Field(default=1, description="Object version")
    lifecycle_state: Optional[str] = Field(default=None, description="Lifecycle status (active, validated, etc.)")
    provenance: Dict[str, Any] = Field(default_factory=dict, description="Source provenance metadata")
    payload: Dict[str, Any] = Field(default_factory=dict, description="Object specific payload attributes")

    @model_validator(mode="after")
    def sync_aliases(self) -> "QuerySourceKnowledgeObject":
        if not self.source_id:
            self.source_id = self.knowledge_id
        if not self.source_type:
            self.source_type = self.object_type
        return self


class QuerySourceMeeting(CoreBaseModel):
    """Meeting referenced in the synthesized query response."""
    meeting_id: str = Field(..., description="Meeting unique ID")
    title: str = Field(..., description="Meeting title")
    status: Optional[str] = Field(default=None, description="Meeting status")
    start_time: Optional[datetime] = Field(default=None, description="Meeting start or scheduled time")


class QuerySourceProject(CoreBaseModel):
    """Project workspace referenced in the synthesized query response."""
    project_id: str = Field(..., description="Project unique ID")
    name: str = Field(..., description="Project workspace name")


# -----------------------------------------------------------------------------
# Response Schema
# -----------------------------------------------------------------------------


class QueryResponse(TimestampSchema):
    """Authoritative structured answer response to a natural language query."""
    query_id: str = Field(..., description="Unique query execution identifier")
    correlation_id: Optional[str] = Field(default=None, description="Correlation identifier for tracing")
    request_id: Optional[str] = Field(default=None, description="Client request identifier")
    query: str = Field(..., description="Original user natural language query")
    scope: str = Field(default="meeting", description="Resolved query scope ('meeting', 'project', 'cross_meeting')")
    meeting_id: Optional[str] = Field(default=None, description="Scoped meeting ID if applicable")
    project_id: Optional[str] = Field(default=None, description="Scoped project ID if applicable")
    answer: str = Field(..., description="Synthesized grounded answer text")
    status: QueryAnswerStatus = Field(
        ...,
        description="Answer status: 'answered', 'insufficient_context', 'requires_verification', etc.",
    )
    confidence: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Overall confidence score in the synthesized answer",
    )
    retrieval_mode: str = Field(..., description="Retrieval mode utilized for knowledge search")
    search_mode: Optional[str] = Field(default=None, description="Alias for retrieval_mode")
    is_low_confidence: bool = Field(default=False, description="True if answer confidence is below threshold (< 0.75)")
    requires_verification: bool = Field(
        default=False,
        description="True if answer or supporting sources require human verification",
    )
    sources: List[QuerySourceKnowledgeObject] = Field(
        default_factory=list,
        description="List of authoritative Knowledge Objects used to synthesize the answer",
    )
    source_meetings: List[QuerySourceMeeting] = Field(
        default_factory=list,
        description="Unique meetings providing context for this answer",
    )
    source_projects: List[QuerySourceProject] = Field(
        default_factory=list,
        description="Unique projects providing context for this answer",
    )
    provenance: Dict[str, Any] = Field(
        default_factory=dict,
        description="Complete execution provenance including answer provider, match counts, and filters applied",
    )

    @model_validator(mode="after")
    def sync_response_aliases(self) -> "QueryResponse":
        if not self.search_mode:
            object.__setattr__(self, "search_mode", self.retrieval_mode)
        return self

    @property
    def confidence_score(self) -> float:
        return self.confidence


class QueryHistoryListResponse(CoreBaseModel):
    """Paginated list of historical queries."""
    items: List[QueryResponse] = Field(default_factory=list, description="Historical queries")
    total: int = Field(..., ge=0, description="Total count of matching queries")
    limit: int = Field(..., ge=1, description="Page limit")
    offset: int = Field(..., ge=0, description="Page offset")
