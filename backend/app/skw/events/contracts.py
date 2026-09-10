"""
SKW Event Contracts & Strongly Typed Schemas
Defines strongly typed event models for all Semantic Knowledge Workspace lifecycle events.
"""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Union
import uuid
from pydantic import Field

from app.schemas.base import CoreBaseModel
from app.skw.models.knowledge_object import CanonicalKnowledgeObject, SKWLifecycleState


class SKWEventType(str, Enum):
    """Authoritative event type identifiers for SKW lifecycle events."""

    KNOWLEDGE_CREATED = "knowledge.created"
    KNOWLEDGE_VALIDATED = "knowledge.validated"
    KNOWLEDGE_INDEXED = "knowledge.indexed"
    KNOWLEDGE_PUBLISHED = "knowledge.published"
    KNOWLEDGE_UPDATED = "knowledge.updated"
    KNOWLEDGE_VERSIONED = "knowledge.versioned"
    KNOWLEDGE_ARCHIVED = "knowledge.archived"
    KNOWLEDGE_VALIDATION_FAILED = "knowledge.validation_failed"
    KNOWLEDGE_PROCESSING_FAILED = "knowledge.processing_failed"


class SKWBaseEvent(CoreBaseModel):
    """Base event model with metadata, correlation, and canonical object identifiers."""

    event_id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        description="Unique identifier for the event message",
    )
    event_type: SKWEventType = Field(
        ...,
        description="Authoritative event type classifier",
    )
    timestamp: datetime = Field(
        default_factory=datetime.utcnow,
        description="UTC event occurrence timestamp",
    )
    knowledge_id: uuid.UUID = Field(
        ...,
        description="Identifier of the knowledge object",
    )
    meeting_id: uuid.UUID = Field(
        ...,
        description="Meeting context identifier",
    )
    object_type: str = Field(
        ...,
        description="Knowledge object classification (e.g. decision, action_item)",
    )
    source_module: str = Field(
        ...,
        description="Producer module or agent",
    )
    version: int = Field(
        default=1,
        ge=1,
        description="Knowledge object version number",
    )
    lifecycle_state: str = Field(
        ...,
        description="Lifecycle state at time of event",
    )
    correlation_id: Optional[str] = Field(
        default=None,
        description="Distributed request or trace correlation identifier",
    )


class KnowledgeCreatedEvent(SKWBaseEvent):
    """Emitted when a new Knowledge Object is created in SKW."""

    event_type: SKWEventType = Field(default=SKWEventType.KNOWLEDGE_CREATED)
    content: str = Field(..., description="Knowledge object text content")
    title: Optional[str] = Field(default=None, description="Optional title or headline")
    confidence_score: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    metadata: Dict[str, Any] = Field(default_factory=dict)
    provenance: Dict[str, Any] = Field(default_factory=dict)
    payload: Dict[str, Any] = Field(default_factory=dict)


class KnowledgeValidatedEvent(SKWBaseEvent):
    """Emitted when a Knowledge Object passes structural and domain validation."""

    event_type: SKWEventType = Field(default=SKWEventType.KNOWLEDGE_VALIDATED)
    is_valid: bool = Field(default=True)
    validated_at: datetime = Field(default_factory=datetime.utcnow)
    validation_rules_applied: List[str] = Field(default_factory=list)


class KnowledgeIndexedEvent(SKWBaseEvent):
    """Emitted when a Knowledge Object vector embedding is indexed into Qdrant."""

    event_type: SKWEventType = Field(default=SKWEventType.KNOWLEDGE_INDEXED)
    qdrant_point_id: str = Field(..., description="Qdrant point identifier")
    vector_size: int = Field(default=384, description="Embedding dimension")
    collection_name: str = Field(default="abci_knowledge_objects")
    indexed_at: datetime = Field(default_factory=datetime.utcnow)


class KnowledgePublishedEvent(SKWBaseEvent):
    """Emitted when a verified Knowledge Object is released to consumers."""

    event_type: SKWEventType = Field(default=SKWEventType.KNOWLEDGE_PUBLISHED)
    published_at: datetime = Field(default_factory=datetime.utcnow)
    publisher: str = Field(default="system")
    channels: List[str] = Field(default_factory=lambda: ["events:knowledge"])


class KnowledgeUpdatedEvent(SKWBaseEvent):
    """Emitted when Knowledge Object content or metadata is updated."""

    event_type: SKWEventType = Field(default=SKWEventType.KNOWLEDGE_UPDATED)
    previous_version: int = Field(default=1, ge=1)
    updated_fields: List[str] = Field(default_factory=list)
    changes_summary: Optional[Dict[str, Any]] = Field(default=None)


class KnowledgeVersionedEvent(SKWBaseEvent):
    """Emitted when a new immutable version is branched/created."""

    event_type: SKWEventType = Field(default=SKWEventType.KNOWLEDGE_VERSIONED)
    previous_version: int = Field(default=1, ge=1)
    new_version: int = Field(default=2, ge=1)
    parent_id: Optional[uuid.UUID] = Field(default=None)


class KnowledgeArchivedEvent(SKWBaseEvent):
    """Emitted when a Knowledge Object transitions to archived or expired."""

    event_type: SKWEventType = Field(default=SKWEventType.KNOWLEDGE_ARCHIVED)
    archived_at: datetime = Field(default_factory=datetime.utcnow)
    reason: Optional[str] = Field(default=None)


class KnowledgeValidationFailedEvent(SKWBaseEvent):
    """Emitted when Knowledge Object schema or rule validation fails."""

    event_type: SKWEventType = Field(default=SKWEventType.KNOWLEDGE_VALIDATION_FAILED)
    error_code: str = Field(default="VALIDATION_FAILED")
    error_message: str = Field(...)
    errors: List[str] = Field(default_factory=list)


class KnowledgeProcessingFailedEvent(SKWBaseEvent):
    """Emitted when indexing, enrichment, or downstream processing fails."""

    event_type: SKWEventType = Field(default=SKWEventType.KNOWLEDGE_PROCESSING_FAILED)
    pipeline_stage: str = Field(..., description="Stage where failure occurred (e.g. indexing, enrichment)")
    error_code: str = Field(default="PROCESSING_FAILED")
    error_message: str = Field(...)
    details: Optional[Dict[str, Any]] = Field(default=None)


# Union type of all concrete SKW events for generic processing
SKWEvent = Union[
    KnowledgeCreatedEvent,
    KnowledgeValidatedEvent,
    KnowledgeIndexedEvent,
    KnowledgePublishedEvent,
    KnowledgeUpdatedEvent,
    KnowledgeVersionedEvent,
    KnowledgeArchivedEvent,
    KnowledgeValidationFailedEvent,
    KnowledgeProcessingFailedEvent,
]
