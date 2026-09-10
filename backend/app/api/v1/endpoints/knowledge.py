"""
ABCI-MI Knowledge API Endpoints
Implements REST endpoints for knowledge object creation, retrieval, search, hybrid queries,
version history, and publishing, fully integrated with authentication, RBAC, and error handling.
"""

from typing import Any, Dict, List, Optional
import uuid
from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.database import get_async_db
from app.core.exceptions import BadRequestException, NotFoundException, UnauthorizedException, ForbiddenException
from app.api.dependencies import verify_authentication
from app.skw.schemas.knowledge_object import (
    KnowledgeObjectCreate,
    KnowledgeObjectResponse,
    KnowledgeObjectUpdate,
)
from app.skw.models.knowledge_object import CanonicalKnowledgeObject
from app.skw.services.ingestion_service import DefaultKnowledgeValidator, DefaultKnowledgeIngestionService
from app.skw.services.version_manager import DefaultVersionManager
from app.skw.services.knowledge_publisher import KnowledgePublisher
from app.skw.services.knowledge_query_engine import KnowledgeQueryEngine
from app.repositories.knowledge_object_repo import KnowledgeObjectRepository


router = APIRouter(prefix="/knowledge", tags=["Knowledge Management (SKW)"])


def _to_response(obj: Any) -> KnowledgeObjectResponse:
    """Map DB knowledge object or dict to KnowledgeObjectResponse schema."""
    if isinstance(obj, dict):
        meta = obj.get("metadata")
        if not isinstance(meta, dict):
            meta = {}
        prov = obj.get("provenance")
        if not isinstance(prov, dict):
            prov = {}
        pay = obj.get("payload")
        if not isinstance(pay, dict):
            pay = {}

        return KnowledgeObjectResponse(
            knowledge_id=uuid.UUID(str(obj.get("knowledge_id") or obj.get("id"))),
            meeting_id=uuid.UUID(str(obj.get("meeting_id"))),
            object_type=obj.get("object_type"),
            source_module=obj.get("source_module"),
            content=obj.get("content"),
            title=obj.get("title"),
            confidence_score=obj.get("confidence_score") or obj.get("confidence"),
            version=obj.get("version", 1),
            lifecycle_state=obj.get("lifecycle_state") or obj.get("status", "created"),
            provenance=prov,
            metadata=meta,
            payload=pay,
            created_at=obj.get("created_at") or obj.get("timestamp"),
            updated_at=obj.get("updated_at"),
        )
    else:
        meta = obj.metadata if (hasattr(obj, "metadata") and isinstance(obj.metadata, dict)) else {}
        prov = obj.provenance if (hasattr(obj, "provenance") and isinstance(obj.provenance, dict)) else {}
        pay = obj.payload if (hasattr(obj, "payload") and isinstance(obj.payload, dict)) else {}

        return KnowledgeObjectResponse(
            knowledge_id=obj.id,
            meeting_id=obj.meeting_id,
            object_type=obj.object_type,
            source_module=obj.source_module,
            content=obj.content,
            title=obj.title,
            confidence_score=obj.confidence,
            version=obj.version,
            lifecycle_state=obj.status,
            provenance=prov,
            metadata=meta,
            payload=pay,
            created_at=obj.created_at,
            updated_at=obj.updated_at,
        )


@router.post(
    "",
    response_model=KnowledgeObjectResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create / Ingest Knowledge Object",
    description="Ingests and validates a new Knowledge Object into SKW.",
)
async def create_knowledge(
    payload: KnowledgeObjectCreate,
    db: AsyncSession = Depends(get_async_db),
    auth: Dict[str, Any] = Depends(verify_authentication),
) -> KnowledgeObjectResponse:
    """Create a new knowledge object via validator and version manager."""
    validator = DefaultKnowledgeValidator()
    await validator.validate_object(payload)

    vm = DefaultVersionManager(db)
    db_obj = await vm.create_version(
        meeting_id=payload.meeting_id,
        object_type=payload.object_type,
        source_module=payload.source_module,
        content=payload.content,
        title=payload.title,
        confidence_score=payload.confidence_score,
        provenance=payload.provenance.model_dump() if payload.provenance else {},
        metadata=payload.metadata.model_dump() if payload.metadata else {},
        payload=payload.payload or {},
    )
    return _to_response(db_obj)


@router.get(
    "/{knowledge_id}",
    response_model=KnowledgeObjectResponse,
    summary="Get Knowledge Object by ID",
    description="Retrieves a specific Knowledge Object by its UUID.",
)
async def get_knowledge(
    knowledge_id: uuid.UUID,
    db: AsyncSession = Depends(get_async_db),
    auth: Dict[str, Any] = Depends(verify_authentication),
) -> KnowledgeObjectResponse:
    """Retrieve knowledge object by UUID."""
    repo = KnowledgeObjectRepository(db)
    obj = await repo.get(knowledge_id)
    if not obj:
        raise NotFoundException(
            message=f"Knowledge object {knowledge_id} not found",
            code="OBJECT_NOT_FOUND",
        )
    return _to_response(obj)


@router.get(
    "/meeting/{meeting_id}",
    response_model=List[KnowledgeObjectResponse],
    summary="Get Knowledge Objects by Meeting ID",
    description="Retrieves all Knowledge Objects associated with a specific meeting.",
)
async def get_knowledge_by_meeting(
    meeting_id: uuid.UUID,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_async_db),
    auth: Dict[str, Any] = Depends(verify_authentication),
) -> List[KnowledgeObjectResponse]:
    """Retrieve knowledge objects by meeting ID."""
    query_engine = KnowledgeQueryEngine(db)
    objs = await query_engine.structured_query(meeting_id=meeting_id, limit=limit, offset=offset)
    return [_to_response(o) for o in objs]


@router.get(
    "/type/{object_type}",
    response_model=List[KnowledgeObjectResponse],
    summary="Get Knowledge Objects by Type",
    description="Retrieves all Knowledge Objects matching a specific object type (e.g. decision, action_item).",
)
async def get_knowledge_by_type(
    object_type: str,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_async_db),
    auth: Dict[str, Any] = Depends(verify_authentication),
) -> List[KnowledgeObjectResponse]:
    """Retrieve knowledge objects by object type."""
    query_engine = KnowledgeQueryEngine(db)
    objs = await query_engine.structured_query(object_type=object_type, limit=limit, offset=offset)
    return [_to_response(o) for o in objs]


@router.post(
    "/search",
    response_model=List[Dict[str, Any]],
    summary="Semantic Search Knowledge Objects",
    description="Performs semantic similarity vector search across Knowledge Objects.",
)
async def search_knowledge(
    body: Dict[str, Any],
    db: AsyncSession = Depends(get_async_db),
    auth: Dict[str, Any] = Depends(verify_authentication),
) -> List[Dict[str, Any]]:
    """Execute semantic vector search."""
    query_text = body.get("query")
    if not query_text:
        raise BadRequestException(message="Query text is required for semantic search", code="INVALID_QUERY")

    meeting_id = uuid.UUID(body["meeting_id"]) if body.get("meeting_id") else None
    object_type = body.get("object_type")
    source_module = body.get("source_module")
    min_confidence = body.get("min_confidence")
    version = body.get("version")
    lifecycle_state = body.get("lifecycle_state")
    limit = body.get("limit", 10)

    query_engine = KnowledgeQueryEngine(db)
    results = await query_engine.semantic_query(
        query=query_text,
        meeting_id=meeting_id,
        object_type=object_type,
        source_module=source_module,
        min_confidence=min_confidence,
        version=version,
        lifecycle_state=lifecycle_state,
        limit=limit,
    )
    return results


@router.post(
    "/query",
    response_model=List[Dict[str, Any]],
    summary="Hybrid Knowledge Query Engine",
    description="Executes hybrid retrieval combining structured constraints and semantic similarity search with result fusion.",
)
async def query_knowledge(
    body: Dict[str, Any],
    db: AsyncSession = Depends(get_async_db),
    auth: Dict[str, Any] = Depends(verify_authentication),
) -> List[Dict[str, Any]]:
    """Execute hybrid query and result fusion."""
    query_text = body.get("query", "")
    meeting_id = uuid.UUID(body["meeting_id"]) if body.get("meeting_id") else None
    object_type = body.get("object_type")
    source_module = body.get("source_module")
    min_confidence = body.get("min_confidence")
    version = body.get("version")
    lifecycle_state = body.get("lifecycle_state")
    limit = body.get("limit", 10)

    query_engine = KnowledgeQueryEngine(db)
    results = await query_engine.hybrid_query(
        query=query_text,
        meeting_id=meeting_id,
        object_type=object_type,
        source_module=source_module,
        min_confidence=min_confidence,
        version=version,
        lifecycle_state=lifecycle_state,
        limit=limit,
    )
    return results


@router.get(
    "/{knowledge_id}/versions",
    response_model=List[KnowledgeObjectResponse],
    summary="Get Knowledge Object Version History",
    description="Retrieves the full version history chain for a Knowledge Object.",
)
async def get_knowledge_versions(
    knowledge_id: uuid.UUID,
    db: AsyncSession = Depends(get_async_db),
    auth: Dict[str, Any] = Depends(verify_authentication),
) -> List[KnowledgeObjectResponse]:
    """Retrieve version history chain."""
    vm = DefaultVersionManager(db)
    history = await vm.get_version_history(knowledge_id)
    if not history:
        raise NotFoundException(message=f"Knowledge object {knowledge_id} not found", code="OBJECT_NOT_FOUND")
    return [_to_response(h) for h in history]


@router.post(
    "/{knowledge_id}/publish",
    response_model=KnowledgeObjectResponse,
    summary="Publish Knowledge Object",
    description="Validates prerequisites and publishes a Knowledge Object.",
)
async def publish_knowledge(
    knowledge_id: uuid.UUID,
    db: AsyncSession = Depends(get_async_db),
    auth: Dict[str, Any] = Depends(verify_authentication),
) -> KnowledgeObjectResponse:
    """Publish knowledge object."""
    publisher = KnowledgePublisher(db)
    published_obj = await publisher.publish_knowledge_object(knowledge_id)
    return _to_response(published_obj)
