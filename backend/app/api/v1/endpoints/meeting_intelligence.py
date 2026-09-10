"""
Meeting Intelligence REST API Endpoints (Phase 4.21)
Exposes SKW-backed decisions, topics, insights, summaries, facts, and hypotheses.
"""

from typing import Any, Dict, Optional
import uuid
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import verify_authentication
from app.infrastructure.database import get_async_db
from app.schemas.meeting_intelligence import (
    DecisionListResponse,
    FactListResponse,
    HypothesisListResponse,
    InsightListResponse,
    SummaryResponse,
    TopicListResponse,
)
from app.services.meeting_intelligence_service import MeetingIntelligenceService

router = APIRouter(tags=["Meeting Intelligence"])


@router.get(
    "/meetings/{meeting_id}/decisions",
    response_model=DecisionListResponse,
    status_code=status.HTTP_200_OK,
    summary="List Meeting Decisions",
    description="Retrieves structured decisions recorded during the meeting.",
)
async def list_meeting_decisions(
    meeting_id: uuid.UUID,
    min_confidence: Optional[float] = Query(default=None, ge=0.0, le=1.0, description="Minimum confidence threshold"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_async_db),
    auth: Dict[str, Any] = Depends(verify_authentication),
) -> DecisionListResponse:
    """Lists decisions for a given meeting."""
    service = MeetingIntelligenceService(db)
    items, total = await service.list_decisions(
        meeting_id=meeting_id,
        min_confidence=min_confidence,
        limit=limit,
        offset=offset,
        auth_context=auth,
    )
    return DecisionListResponse(items=items, total=total, limit=limit, offset=offset)


@router.get(
    "/meetings/{meeting_id}/topics",
    response_model=TopicListResponse,
    status_code=status.HTTP_200_OK,
    summary="List Meeting Topics",
    description="Retrieves structured discussion topics extracted from the meeting transcript.",
)
async def list_meeting_topics(
    meeting_id: uuid.UUID,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_async_db),
    auth: Dict[str, Any] = Depends(verify_authentication),
) -> TopicListResponse:
    """Lists topics for a given meeting."""
    service = MeetingIntelligenceService(db)
    items, total = await service.list_topics(
        meeting_id=meeting_id,
        limit=limit,
        offset=offset,
        auth_context=auth,
    )
    return TopicListResponse(items=items, total=total, limit=limit, offset=offset)


@router.get(
    "/meetings/{meeting_id}/insights",
    response_model=InsightListResponse,
    status_code=status.HTTP_200_OK,
    summary="List Meeting Insights",
    description="Retrieves transcript and sentiment insights derived from the meeting.",
)
async def list_meeting_insights(
    meeting_id: uuid.UUID,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_async_db),
    auth: Dict[str, Any] = Depends(verify_authentication),
) -> InsightListResponse:
    """Lists insights for a given meeting."""
    service = MeetingIntelligenceService(db)
    items, total = await service.list_insights(
        meeting_id=meeting_id,
        limit=limit,
        offset=offset,
        auth_context=auth,
    )
    return InsightListResponse(items=items, total=total, limit=limit, offset=offset)


@router.get(
    "/meetings/{meeting_id}/summary",
    response_model=SummaryResponse,
    status_code=status.HTTP_200_OK,
    summary="Get Meeting Summary",
    description="Retrieves executive and structured meeting summary.",
)
async def get_meeting_summary(
    meeting_id: uuid.UUID,
    db: AsyncSession = Depends(get_async_db),
    auth: Dict[str, Any] = Depends(verify_authentication),
) -> SummaryResponse:
    """Retrieves structured summary for a given meeting."""
    service = MeetingIntelligenceService(db)
    return await service.get_meeting_summary(
        meeting_id=meeting_id,
        auth_context=auth,
    )


@router.get(
    "/meetings/{meeting_id}/facts",
    response_model=FactListResponse,
    status_code=status.HTTP_200_OK,
    summary="List Meeting Facts",
    description="Retrieves extracted or verified facts for the meeting context.",
)
async def list_meeting_facts(
    meeting_id: uuid.UUID,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_async_db),
    auth: Dict[str, Any] = Depends(verify_authentication),
) -> FactListResponse:
    """Lists facts for a given meeting."""
    service = MeetingIntelligenceService(db)
    items, total = await service.list_facts(
        meeting_id=meeting_id,
        limit=limit,
        offset=offset,
        auth_context=auth,
    )
    return FactListResponse(items=items, total=total, limit=limit, offset=offset)


@router.get(
    "/meetings/{meeting_id}/hypotheses",
    response_model=HypothesisListResponse,
    status_code=status.HTTP_200_OK,
    summary="List Meeting Hypotheses",
    description="Retrieves working hypotheses and assumptions proposed during the meeting.",
)
async def list_meeting_hypotheses(
    meeting_id: uuid.UUID,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_async_db),
    auth: Dict[str, Any] = Depends(verify_authentication),
) -> HypothesisListResponse:
    """Lists hypotheses for a given meeting."""
    service = MeetingIntelligenceService(db)
    items, total = await service.list_hypotheses(
        meeting_id=meeting_id,
        limit=limit,
        offset=offset,
        auth_context=auth,
    )
    return HypothesisListResponse(items=items, total=total, limit=limit, offset=offset)
