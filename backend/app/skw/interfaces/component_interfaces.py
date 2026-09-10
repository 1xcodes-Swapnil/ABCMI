"""
SKW Component Interfaces & Protocols
Defines independent contracts for all architectural components in the Semantic Knowledge Workspace.
"""

from typing import Any, Dict, List, Optional, Protocol, Sequence, runtime_checkable
import uuid
from app.skw.models.knowledge_object import CanonicalKnowledgeObject, SKWLifecycleState
from app.skw.schemas.knowledge_object import KnowledgeObjectCreate, KnowledgeObjectUpdate


@runtime_checkable
class KnowledgeIngestionService(Protocol):
    """Interface for receiving and initial processing of raw knowledge artifacts from producers."""
    async def ingest_raw_knowledge(self, meeting_id: uuid.UUID, raw_data: Dict[str, Any]) -> CanonicalKnowledgeObject: ...


@runtime_checkable
class KnowledgeValidator(Protocol):
    """Interface for validating knowledge objects against schema and domain rules."""
    async def validate_object(self, obj: CanonicalKnowledgeObject) -> bool: ...


@runtime_checkable
class KnowledgeEnrichmentService(Protocol):
    """Interface for adding contextual, metadata, and provenance enrichment to knowledge objects."""
    async def enrich_object(self, obj: CanonicalKnowledgeObject, context: Dict[str, Any]) -> CanonicalKnowledgeObject: ...


@runtime_checkable
class KnowledgeRepository(Protocol):
    """Interface for durable persistence of Knowledge Objects."""
    async def save(self, obj: CanonicalKnowledgeObject) -> CanonicalKnowledgeObject: ...
    async def get_by_id(self, knowledge_id: uuid.UUID) -> Optional[CanonicalKnowledgeObject]: ...
    async def list_by_meeting(self, meeting_id: uuid.UUID, skip: int = 0, limit: int = 100) -> Sequence[CanonicalKnowledgeObject]: ...


@runtime_checkable
class SemanticIndexer(Protocol):
    """Interface for vector embedding and indexing knowledge objects into Qdrant."""
    async def index_knowledge_object(self, obj: CanonicalKnowledgeObject) -> str: ...
    async def remove_index(self, knowledge_id: uuid.UUID) -> bool: ...


@runtime_checkable
class VersionManager(Protocol):
    """Interface for managing immutable versions and revisions of Knowledge Objects."""
    async def create_revision(self, knowledge_id: uuid.UUID, update_data: KnowledgeObjectUpdate) -> CanonicalKnowledgeObject: ...
    async def get_version_history(self, knowledge_id: uuid.UUID) -> Sequence[CanonicalKnowledgeObject]: ...


@runtime_checkable
class KnowledgePublisher(Protocol):
    """Interface for publishing verified knowledge events to consumers/subscribers."""
    async def publish_knowledge_event(self, event_type: str, obj: CanonicalKnowledgeObject) -> bool: ...


@runtime_checkable
class KnowledgeQueryEngine(Protocol):
    """Interface for semantic querying and retrieval across knowledge objects."""
    async def semantic_search(self, query: str, meeting_id: Optional[uuid.UUID] = None, limit: int = 10) -> List[CanonicalKnowledgeObject]: ...


@runtime_checkable
class SKWKnowledgeInterface(Protocol):
    """
    Interface exposed by SKW to consumers like the Adaptive Blackboard
    for contextual knowledge retrieval across structured, semantic, and hybrid dimensions.
    """
    async def request_structured_knowledge(
        self,
        meeting_id: Optional[uuid.UUID] = None,
        object_type: Optional[str] = None,
        source_module: Optional[str] = None,
        min_confidence: Optional[float] = None,
        version: Optional[int] = None,
        lifecycle_state: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
        auth_context: Optional[Dict[str, Any]] = None,
        correlation_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]: ...

    async def request_semantic_knowledge(
        self,
        query: str,
        meeting_id: Optional[uuid.UUID] = None,
        object_type: Optional[str] = None,
        source_module: Optional[str] = None,
        min_confidence: Optional[float] = None,
        version: Optional[int] = None,
        lifecycle_state: Optional[str] = None,
        limit: int = 10,
        auth_context: Optional[Dict[str, Any]] = None,
        correlation_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]: ...

    async def request_hybrid_knowledge(
        self,
        query: str,
        meeting_id: Optional[uuid.UUID] = None,
        object_type: Optional[str] = None,
        source_module: Optional[str] = None,
        min_confidence: Optional[float] = None,
        version: Optional[int] = None,
        lifecycle_state: Optional[str] = None,
        limit: int = 10,
        auth_context: Optional[Dict[str, Any]] = None,
        correlation_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]: ...
