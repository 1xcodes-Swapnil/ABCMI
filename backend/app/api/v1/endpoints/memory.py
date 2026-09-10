"""
Knowledge Memory API Endpoints (Phase 4.14 / 4.15)
Exposes contextual and historical memory retrieval endpoints for ACE and AI modules
via KnowledgeMemoryEngine and BlackboardSKWClient.
"""

from typing import Any, Dict, List, Optional
import uuid
from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import verify_authentication
from app.ai.knowledge_memory import KnowledgeMemoryEngine, KnowledgeMemoryQueryRequest, KnowledgeMemoryQueryResult
from app.infrastructure.database import get_async_db
from app.orchestration.skw_client import BlackboardSKWClient
from app.skw.services.knowledge_query_engine import KnowledgeQueryEngine

router = APIRouter(prefix="/memory", tags=["Knowledge Memory"])


def get_memory_engine(db: AsyncSession) -> KnowledgeMemoryEngine:
    """Factory for KnowledgeMemoryEngine bound to DB session."""
    query_engine = KnowledgeQueryEngine(db)
    skw_client = BlackboardSKWClient(query_engine=query_engine)
    return KnowledgeMemoryEngine(skw_client=skw_client)


@router.post("/query", response_model=KnowledgeMemoryQueryResult, status_code=status.HTTP_200_OK)
async def query_knowledge_memory(
    payload: KnowledgeMemoryQueryRequest,
    auth_context: Dict[str, Any] = Depends(verify_authentication),
    db: AsyncSession = Depends(get_async_db),
) -> KnowledgeMemoryQueryResult:
    """
    Query long-term Knowledge Memory (structured, semantic, or hybrid retrieval)
    with strict security scoping and correlation tracking.
    """
    payload.auth_context = auth_context
    engine = get_memory_engine(db)
    result = await engine.query_memory(payload)
    return result
