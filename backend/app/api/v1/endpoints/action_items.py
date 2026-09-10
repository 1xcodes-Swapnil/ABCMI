"""
Action Items REST API Endpoints (Phase 4.21)
Provides secure endpoints for listing, retrieving, creating, updating, and completing meeting action items.
"""

from typing import Any, Dict, Optional
import uuid
from fastapi import APIRouter, Depends, Header, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import verify_authentication
from app.infrastructure.database import get_async_db
from app.schemas.action_item import (
    ActionItemCreate,
    ActionItemListResponse,
    ActionItemResponse,
    ActionItemUpdate,
)
from app.services.meeting_intelligence_service import MeetingIntelligenceService

router = APIRouter(tags=["Action Items"])


@router.get(
    "/meetings/{meeting_id}/action-items",
    response_model=ActionItemListResponse,
    status_code=status.HTTP_200_OK,
    summary="List Action Items for Meeting",
    description="Lists all action items extracted or assigned for the specified meeting context.",
)
async def list_meeting_action_items(
    meeting_id: uuid.UUID,
    status: Optional[str] = Query(default=None, description="Filter by status (open, in_progress, completed, cancelled)"),
    priority: Optional[str] = Query(default=None, description="Filter by priority (low, medium, high, critical)"),
    assignee: Optional[str] = Query(default=None, description="Filter by assignee substring"),
    min_confidence: Optional[float] = Query(default=None, ge=0.0, le=1.0, description="Minimum confidence threshold"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_async_db),
    auth: Dict[str, Any] = Depends(verify_authentication),
) -> ActionItemListResponse:
    """Lists action items for a given meeting."""
    service = MeetingIntelligenceService(db)
    items, total = await service.list_action_items(
        meeting_id=meeting_id,
        status=status,
        priority=priority,
        assignee=assignee,
        min_confidence=min_confidence,
        limit=limit,
        offset=offset,
        auth_context=auth,
    )
    return ActionItemListResponse(items=items, total=total, limit=limit, offset=offset)


@router.post(
    "/meetings/{meeting_id}/action-items",
    response_model=ActionItemResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create Action Item",
    description="Creates or records a user-confirmed action item for a meeting.",
)
async def create_action_item(
    meeting_id: uuid.UUID,
    payload: ActionItemCreate,
    db: AsyncSession = Depends(get_async_db),
    auth: Dict[str, Any] = Depends(verify_authentication),
) -> ActionItemResponse:
    """Creates a user-confirmed action item."""
    service = MeetingIntelligenceService(db)
    return await service.create_action_item(
        meeting_id=meeting_id,
        payload=payload,
        auth_context=auth,
    )


@router.get(
    "/action-items/{action_item_id}",
    response_model=ActionItemResponse,
    status_code=status.HTTP_200_OK,
    summary="Get Action Item",
    description="Retrieves a single action item by its unique ID.",
)
async def get_action_item(
    action_item_id: uuid.UUID,
    db: AsyncSession = Depends(get_async_db),
    auth: Dict[str, Any] = Depends(verify_authentication),
) -> ActionItemResponse:
    """Retrieves an action item by ID."""
    service = MeetingIntelligenceService(db)
    return await service.get_action_item(
        action_item_id=action_item_id,
        auth_context=auth,
    )


@router.patch(
    "/action-items/{action_item_id}",
    response_model=ActionItemResponse,
    status_code=status.HTTP_200_OK,
    summary="Update Action Item",
    description="Updates action item details, assignee, due date, status, or priority, preserving provenance.",
)
async def update_action_item(
    action_item_id: uuid.UUID,
    payload: ActionItemUpdate,
    db: AsyncSession = Depends(get_async_db),
    auth: Dict[str, Any] = Depends(verify_authentication),
) -> ActionItemResponse:
    """Updates an action item with version lineage and provenance."""
    service = MeetingIntelligenceService(db)
    return await service.update_action_item(
        action_item_id=action_item_id,
        payload=payload,
        auth_context=auth,
    )


@router.post(
    "/action-items/{action_item_id}/complete",
    response_model=ActionItemResponse,
    status_code=status.HTTP_200_OK,
    summary="Complete Action Item",
    description="Idempotently transitions an action item to completed status.",
)
async def complete_action_item(
    action_item_id: uuid.UUID,
    x_correlation_id: Optional[str] = Header(default=None),
    db: AsyncSession = Depends(get_async_db),
    auth: Dict[str, Any] = Depends(verify_authentication),
) -> ActionItemResponse:
    """Marks an action item as completed."""
    service = MeetingIntelligenceService(db)
    return await service.complete_action_item(
        action_item_id=action_item_id,
        auth_context=auth,
        correlation_id=x_correlation_id,
    )


@router.post(
    "/action-items/{action_item_id}/cancel",
    response_model=ActionItemResponse,
    status_code=status.HTTP_200_OK,
    summary="Cancel Action Item",
    description="Idempotently transitions an action item to cancelled status.",
)
async def cancel_action_item(
    action_item_id: uuid.UUID,
    x_correlation_id: Optional[str] = Header(default=None),
    db: AsyncSession = Depends(get_async_db),
    auth: Dict[str, Any] = Depends(verify_authentication),
) -> ActionItemResponse:
    """Marks an action item as cancelled."""
    service = MeetingIntelligenceService(db)
    return await service.cancel_action_item(
        action_item_id=action_item_id,
        auth_context=auth,
        correlation_id=x_correlation_id,
    )
