"""
SKW Knowledge Object Models & Lifecycle Enumerations
Defines canonical data structures and lifecycle states for the Semantic Knowledge Workspace.
"""

from enum import Enum
from typing import Any, Dict, List, Optional
import uuid
from datetime import datetime


class SKWLifecycleState(str, Enum):
    """
    Authoritative lifecycle states for Knowledge Objects in the Semantic Knowledge Workspace
    as defined by the SKW Knowledge Object Lifecycle architecture.
    """
    CREATED = "created"
    VALIDATING = "validating"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    INDEXED = "indexed"
    PUBLISHED = "published"
    SHARED = "shared"
    RETRIEVED = "retrieved"
    UPDATED = "updated"
    VERSIONED = "versioned"
    EXPIRED = "expired"
    ARCHIVED = "archived"
    INVALID = "invalid"


class SKWKnowledgeType(str, Enum):
    """Standardized knowledge types supported by ABCI-MI AI producers."""
    TRANSCRIPT = "transcript"
    SPEAKER = "speaker"
    LANGUAGE = "language"
    TIMESTAMP = "timestamp"
    CONTEXT = "context"
    TOPIC = "topic"
    DECISION = "decision"
    ACTION_ITEM = "action_item"
    MEETING_INSIGHT = "meeting_insight"
    ANALYTICS = "analytics"
    VERIFIED_KNOWLEDGE = "verified_knowledge"
    SEMANTIC_RELATIONSHIP = "semantic_relationship"


class CanonicalKnowledgeObject:
    """
    Canonical in-memory representation of a Knowledge Object within the Semantic Knowledge Workspace.
    Maps cleanly to the persistence ERD while supporting rich semantic payload, provenance, and metadata.
    """
    def __init__(
        self,
        knowledge_id: Optional[uuid.UUID] = None,
        meeting_id: Optional[uuid.UUID] = None,
        object_type: str = SKWKnowledgeType.DECISION.value,
        source_module: str = "system",
        confidence_score: Optional[float] = None,
        version: int = 1,
        lifecycle_state: SKWLifecycleState = SKWLifecycleState.CREATED,
        content: str = "",
        title: Optional[str] = None,
        provenance: Optional[Dict[str, Any]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        payload: Optional[Dict[str, Any]] = None,
        created_at: Optional[datetime] = None,
        updated_at: Optional[datetime] = None,
    ) -> None:
        self.knowledge_id = knowledge_id or uuid.uuid4()
        self.meeting_id = meeting_id or uuid.uuid4()
        self.object_type = object_type
        self.source_module = source_module
        self.confidence_score = confidence_score
        self.version = version
        self.lifecycle_state = lifecycle_state
        self.content = content
        self.title = title
        self.provenance = provenance or {}
        self.metadata = metadata or {}
        self.payload = payload or {}
        self.created_at = created_at or datetime.utcnow()
        self.updated_at = updated_at or datetime.utcnow()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "knowledge_id": str(self.knowledge_id),
            "meeting_id": str(self.meeting_id),
            "object_type": self.object_type,
            "source_module": self.source_module,
            "confidence_score": self.confidence_score,
            "version": self.version,
            "lifecycle_state": self.lifecycle_state.value if hasattr(self.lifecycle_state, "value") else self.lifecycle_state,
            "content": self.content,
            "title": self.title,
            "provenance": self.provenance,
            "metadata": self.metadata,
            "payload": self.payload,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }
