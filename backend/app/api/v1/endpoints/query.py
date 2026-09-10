"""
Ask ABCI-MI Natural Language Query REST API Endpoints (Phase 4.23)
Provides natural-language question answering across meetings, projects, and workspaces,
query inspection by ID, meeting-scoped query history, and regeneration.
"""

from datetime import datetime
from typing import Any, Dict, Optional
import uuid
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import verify_authentication
from app.infrastructure.database import get_async_db
from app.schemas.query import QueryHistoryListResponse, QueryRequest, QueryResponse
from app.services.query_interface_service import QueryInterfaceService

router = APIRouter(tags=["Ask ABCI-MI Query Interface"])


@router.post(
    "/queries",
    response_model=QueryResponse,
    status_code=status.HTTP_200_OK,
    summary="Ask ABCI-MI Question",
    description="Natural-language question answering over meetings, projects, decisions, action items, and historical workspace knowledge.",
)
@router.post(
    "/query",
    response_model=QueryResponse,
    status_code=status.HTTP_200_OK,
    include_in_schema=False,
)
async def ask_query(
    payload: QueryRequest,
    db: AsyncSession = Depends(get_async_db),
    auth: Dict[str, Any] = Depends(verify_authentication),
) -> QueryResponse:
    """
    Executes a natural language query with multi-mode retrieval, grounded answer synthesis,
    source attribution, confidence tracking, and request persistence.
    """
    service = QueryInterfaceService(db)
    return await service.execute_query(request=payload, auth_context=auth)


@router.get(
    "/queries",
    response_model=QueryHistoryListResponse,
    status_code=status.HTTP_200_OK,
    summary="List Query History",
    description="Retrieves a paginated list of historical queries with optional meeting, project, and date-range filters.",
)
async def list_queries(
    meeting_id: Optional[uuid.UUID] = Query(default=None, description="Optional meeting filter"),
    project_id: Optional[uuid.UUID] = Query(default=None, description="Optional project filter"),
    start_time: Optional[datetime] = Query(default=None, description="Filter queries created on or after this timestamp"),
    end_time: Optional[datetime] = Query(default=None, description="Filter queries created on or before this timestamp"),
    date_from: Optional[datetime] = Query(default=None, description="Alias for start_time"),
    date_to: Optional[datetime] = Query(default=None, description="Alias for end_time"),
    limit: int = Query(default=50, ge=1, le=100, description="Max number of queries to return"),
    offset: int = Query(default=0, ge=0, description="Pagination offset"),
    db: AsyncSession = Depends(get_async_db),
    auth: Dict[str, Any] = Depends(verify_authentication),
) -> QueryHistoryListResponse:
    """Retrieves historical queries across workspace/tenant scope with date-range and entity filters."""
    service = QueryInterfaceService(db)
    effective_start = start_time or date_from
    effective_end = end_time or date_to
    return await service.list_queries(
        auth_context=auth,
        meeting_id=meeting_id,
        project_id=project_id,
        start_time=effective_start,
        end_time=effective_end,
        skip=offset,
        limit=limit,
    )


@router.get(
    "/queries/{query_id}",
    response_model=QueryResponse,
    status_code=status.HTTP_200_OK,
    summary="Get Query by ID",
    description="Retrieves an executed natural-language query record and its synthesized answer by ID.",
)
async def get_query_by_id(
    query_id: uuid.UUID,
    db: AsyncSession = Depends(get_async_db),
    auth: Dict[str, Any] = Depends(verify_authentication),
) -> QueryResponse:
    """Retrieves a historical query result by its unique UUID."""
    service = QueryInterfaceService(db)
    return await service.get_query_by_id(query_id=query_id, auth_context=auth)


@router.post(
    "/queries/{query_id}/regenerate",
    response_model=QueryResponse,
    status_code=status.HTTP_200_OK,
    summary="Regenerate Query Answer",
    description="Re-runs knowledge retrieval and answer synthesis for an existing query.",
)
async def regenerate_query(
    query_id: uuid.UUID,
    db: AsyncSession = Depends(get_async_db),
    auth: Dict[str, Any] = Depends(verify_authentication),
) -> QueryResponse:
    """Regenerates answer for a previously executed query."""
    service = QueryInterfaceService(db)
    return await service.regenerate_query(query_id=query_id, auth_context=auth)


@router.get(
    "/meetings/{meeting_id}/queries",
    response_model=QueryHistoryListResponse,
    status_code=status.HTTP_200_OK,
    summary="Get Meeting Query History",
    description="Retrieves a paginated list of historical queries executed within the scope of a specific meeting.",
)
async def get_meeting_queries(
    meeting_id: uuid.UUID,
    start_time: Optional[datetime] = Query(default=None, description="Filter queries created on or after this timestamp"),
    end_time: Optional[datetime] = Query(default=None, description="Filter queries created on or before this timestamp"),
    date_from: Optional[datetime] = Query(default=None, description="Alias for start_time"),
    date_to: Optional[datetime] = Query(default=None, description="Alias for end_time"),
    limit: int = Query(default=50, ge=1, le=100, description="Max number of queries to return"),
    offset: int = Query(default=0, ge=0, description="Pagination offset"),
    db: AsyncSession = Depends(get_async_db),
    auth: Dict[str, Any] = Depends(verify_authentication),
) -> QueryHistoryListResponse:
    """Retrieves historical queries scoped to a meeting in reverse chronological order with optional date-range filtering."""
    service = QueryInterfaceService(db)
    effective_start = start_time or date_from
    effective_end = end_time or date_to
    return await service.list_meeting_queries(
        meeting_id=meeting_id,
        auth_context=auth,
        start_time=effective_start,
        end_time=effective_end,
        skip=offset,
        limit=limit,
    )
