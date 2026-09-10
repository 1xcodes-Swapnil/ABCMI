"""
Knowledge Memory Engine (Phase 4.12C)
Integrates Knowledge Memory through existing SKW/Blackboard/ACE boundaries.
Guarantees zero direct access to PostgreSQL or Qdrant.
Supports structured, semantic, and hybrid contextual knowledge retrieval for cross-session meeting intelligence.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional
import uuid
from pydantic import Field

from app.core.exceptions import ForbiddenException, UnauthorizedException
from app.orchestration.skw_client import BlackboardSKWClient
from app.schemas.base import CoreBaseModel
from app.schemas.knowledge_object import ProvenanceMetadataSchema


class KnowledgeMemoryQueryRequest(CoreBaseModel):
    """Query payload for Knowledge Memory requests."""

    meeting_id: Optional[uuid.UUID] = None
    query: Optional[str] = None
    object_type: Optional[str] = None
    source_module: Optional[str] = None
    min_confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    version: Optional[int] = None
    lifecycle_state: Optional[str] = None
    search_mode: str = Field(
        default="hybrid",
        description="One of: structured, semantic, hybrid",
    )
    limit: int = Field(default=10, ge=1, le=100)
    auth_context: Optional[Dict[str, Any]] = None
    correlation_id: Optional[str] = None


class KnowledgeMemoryQueryResult(CoreBaseModel):
    """Result payload for Knowledge Memory requests."""

    meeting_id: Optional[uuid.UUID] = None
    query_mode: str
    results_count: int
    items: List[Dict[str, Any]] = Field(default_factory=list)
    correlation_id: Optional[str] = None
    provenance: ProvenanceMetadataSchema
    created_at: datetime = Field(default_factory=datetime.utcnow)


class KnowledgeMemoryEngine:
    """
    Knowledge Memory Engine Service.
    Acts as the high-level intelligence interface over BlackboardSKWClient.
    Enforces SKW/Blackboard isolation boundaries, ensuring no direct DB/Qdrant calls occur.
    """

    def __init__(self, skw_client: BlackboardSKWClient) -> None:
        self.skw_client = skw_client

    async def query_memory(
        self,
        request: KnowledgeMemoryQueryRequest,
    ) -> KnowledgeMemoryQueryResult:
        """
        Executes structured, semantic, or hybrid knowledge retrieval through BlackboardSKWClient.
        """
        if not request.auth_context:
            raise UnauthorizedException(
                message="Authentication context required for Knowledge Memory query",
                code="UNAUTHORIZED",
            )

        search_mode = request.search_mode.lower()
        items: List[Dict[str, Any]] = []

        if search_mode == "structured":
            items = await self.skw_client.request_structured_knowledge(
                meeting_id=request.meeting_id,
                object_type=request.object_type,
                source_module=request.source_module,
                min_confidence=request.min_confidence,
                version=request.version,
                lifecycle_state=request.lifecycle_state,
                limit=request.limit,
                auth_context=request.auth_context,
                correlation_id=request.correlation_id,
            )
        elif search_mode == "semantic":
            items = await self.skw_client.request_semantic_knowledge(
                query=request.query or "*",
                meeting_id=request.meeting_id,
                object_type=request.object_type,
                source_module=request.source_module,
                min_confidence=request.min_confidence,
                version=request.version,
                lifecycle_state=request.lifecycle_state,
                limit=request.limit,
                auth_context=request.auth_context,
                correlation_id=request.correlation_id,
            )
        else:
            # Default to hybrid
            items = await self.skw_client.request_hybrid_knowledge(
                query=request.query or "*",
                meeting_id=request.meeting_id,
                object_type=request.object_type,
                source_module=request.source_module,
                min_confidence=request.min_confidence,
                version=request.version,
                lifecycle_state=request.lifecycle_state,
                limit=request.limit,
                auth_context=request.auth_context,
                correlation_id=request.correlation_id,
            )

        prov = ProvenanceMetadataSchema(
            producing_module="knowledge_memory",
            model_name="knowledge_memory_v1",
            model_version="1.0.0",
            source_segments=[],
            source_intervals=[],
            lineage={"search_mode": search_mode, "meeting_id": str(request.meeting_id) if request.meeting_id else None},
            processing_metadata={"correlation_id": request.correlation_id},
        )

        return KnowledgeMemoryQueryResult(
            meeting_id=request.meeting_id,
            query_mode=search_mode,
            results_count=len(items),
            items=items,
            correlation_id=request.correlation_id,
            provenance=prov,
        )
