"""
Project & Cross-Meeting Intelligence REST API Endpoints (Phase 4.22)
Provides endpoints for workspace projects, meeting associations, cross-meeting aggregation,
recurring topics, timelines, and related meetings.
"""

from typing import Any, Dict, Optional
import uuid
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import verify_authentication
from app.infrastructure.database import get_async_db
from app.schemas.project import (
    CrossMeetingActionItemsSummary,
    CrossMeetingDecisionsResponse,
    CrossMeetingInsightsResponse,
    ProjectCreate,
    ProjectHistoricalContextResponse,
    ProjectListResponse,
    ProjectMeetingAssociationRequest,
    ProjectMeetingListResponse,
    ProjectMeetingResponse,
    ProjectResponse,
    ProjectSummaryResponse,
    ProjectUpdate,
    RecurringTopicsResponse,
    RelatedMeetingsResponse,
)
from app.services.project_intelligence_service import ProjectIntelligenceService

router = APIRouter(tags=["Projects & Cross-Meeting Intelligence"])


# -----------------------------------------------------------------------------
# Project Workspaces
# -----------------------------------------------------------------------------


@router.post(
    "/projects",
    response_model=ProjectResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create Project Workspace",
    description="Creates a new project or workspace grouping for meetings.",
)
async def create_project(
    payload: ProjectCreate,
    db: AsyncSession = Depends(get_async_db),
    auth: Dict[str, Any] = Depends(verify_authentication),
) -> ProjectResponse:
    """Creates a new project workspace."""
    service = ProjectIntelligenceService(db)
    return await service.create_project(payload=payload, auth_context=auth)


@router.get(
    "/projects",
    response_model=ProjectListResponse,
    status_code=status.HTTP_200_OK,
    summary="List Projects",
    description="Lists all projects accessible to the authenticated tenant.",
)
async def list_projects(
    status: Optional[str] = Query(default=None, description="Filter by status (active, archived, completed)"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_async_db),
    auth: Dict[str, Any] = Depends(verify_authentication),
) -> ProjectListResponse:
    """Lists projects with pagination and status filter."""
    service = ProjectIntelligenceService(db)
    items, total = await service.list_projects(
        status=status,
        limit=limit,
        offset=offset,
        auth_context=auth,
    )
    return ProjectListResponse(items=items, total=total, limit=limit, offset=offset)


@router.get(
    "/projects/{project_id}",
    response_model=ProjectResponse,
    status_code=status.HTTP_200_OK,
    summary="Get Project Details",
    description="Retrieves details of a project workspace by its unique ID.",
)
async def get_project(
    project_id: uuid.UUID,
    db: AsyncSession = Depends(get_async_db),
    auth: Dict[str, Any] = Depends(verify_authentication),
) -> ProjectResponse:
    """Retrieves a project by ID."""
    service = ProjectIntelligenceService(db)
    return await service.get_project(project_id=project_id, auth_context=auth)


@router.patch(
    "/projects/{project_id}",
    response_model=ProjectResponse,
    status_code=status.HTTP_200_OK,
    summary="Update Project",
    description="Updates project metadata, status, or settings.",
)
async def update_project(
    project_id: uuid.UUID,
    payload: ProjectUpdate,
    db: AsyncSession = Depends(get_async_db),
    auth: Dict[str, Any] = Depends(verify_authentication),
) -> ProjectResponse:
    """Updates a project workspace."""
    service = ProjectIntelligenceService(db)
    return await service.update_project(project_id=project_id, payload=payload, auth_context=auth)


@router.delete(
    "/projects/{project_id}",
    status_code=status.HTTP_200_OK,
    summary="Delete Project",
    description="Deletes a project workspace and its meeting associations.",
)
async def delete_project(
    project_id: uuid.UUID,
    db: AsyncSession = Depends(get_async_db),
    auth: Dict[str, Any] = Depends(verify_authentication),
) -> Dict[str, Any]:
    """Deletes a project workspace."""
    service = ProjectIntelligenceService(db)
    await service.delete_project(project_id=project_id, auth_context=auth)
    return {"status": "success", "message": f"Project '{project_id}' deleted"}


# -----------------------------------------------------------------------------
# Meeting-to-Project Associations
# -----------------------------------------------------------------------------


@router.post(
    "/projects/{project_id}/meetings",
    response_model=ProjectMeetingResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Associate Meeting with Project",
    description="Associates a meeting with a project workspace idempotently.",
)
async def associate_meeting(
    project_id: uuid.UUID,
    payload: ProjectMeetingAssociationRequest,
    db: AsyncSession = Depends(get_async_db),
    auth: Dict[str, Any] = Depends(verify_authentication),
) -> ProjectMeetingResponse:
    """Associates a meeting with a project."""
    service = ProjectIntelligenceService(db)
    return await service.associate_meeting(
        project_id=project_id,
        meeting_id=payload.meeting_id,
        notes=payload.notes,
        auth_context=auth,
    )


@router.delete(
    "/projects/{project_id}/meetings/{meeting_id}",
    status_code=status.HTTP_200_OK,
    summary="Remove Meeting from Project",
    description="Removes a meeting association from a project workspace.",
)
async def remove_meeting_from_project(
    project_id: uuid.UUID,
    meeting_id: uuid.UUID,
    db: AsyncSession = Depends(get_async_db),
    auth: Dict[str, Any] = Depends(verify_authentication),
) -> Dict[str, Any]:
    """Removes a meeting from a project."""
    service = ProjectIntelligenceService(db)
    await service.remove_meeting_from_project(
        project_id=project_id,
        meeting_id=meeting_id,
        auth_context=auth,
    )
    return {"status": "success", "message": f"Meeting '{meeting_id}' removed from project '{project_id}'"}


@router.get(
    "/projects/{project_id}/meetings",
    response_model=ProjectMeetingListResponse,
    status_code=status.HTTP_200_OK,
    summary="List Project Meetings",
    description="Lists all meetings associated with a project.",
)
async def list_project_meetings(
    project_id: uuid.UUID,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_async_db),
    auth: Dict[str, Any] = Depends(verify_authentication),
) -> ProjectMeetingListResponse:
    """Lists meetings in a project."""
    service = ProjectIntelligenceService(db)
    items, total = await service.list_project_meetings(
        project_id=project_id,
        limit=limit,
        offset=offset,
        auth_context=auth,
    )
    return ProjectMeetingListResponse(items=items, total=total, limit=limit, offset=offset)


# -----------------------------------------------------------------------------
# Cross-Meeting Intelligence
# -----------------------------------------------------------------------------


@router.get(
    "/projects/{project_id}/action-items",
    response_model=CrossMeetingActionItemsSummary,
    status_code=status.HTTP_200_OK,
    summary="Get Cross-Meeting Action Items",
    description="Aggregates and filters action items across all meetings in a project.",
)
async def get_cross_meeting_action_items(
    project_id: uuid.UUID,
    status: Optional[str] = Query(default=None, description="Filter by status (open, in_progress, completed, cancelled)"),
    priority: Optional[str] = Query(default=None, description="Filter by priority (low, medium, high, critical)"),
    assignee: Optional[str] = Query(default=None, description="Filter by assignee substring"),
    min_confidence: Optional[float] = Query(default=None, ge=0.0, le=1.0, description="Minimum confidence threshold"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_async_db),
    auth: Dict[str, Any] = Depends(verify_authentication),
) -> CrossMeetingActionItemsSummary:
    """Aggregates action items for a project."""
    service = ProjectIntelligenceService(db)
    return await service.get_cross_meeting_action_items(
        project_id=project_id,
        status=status,
        priority=priority,
        assignee=assignee,
        min_confidence=min_confidence,
        limit=limit,
        offset=offset,
        auth_context=auth,
    )


@router.get(
    "/projects/{project_id}/decisions",
    response_model=CrossMeetingDecisionsResponse,
    status_code=status.HTTP_200_OK,
    summary="Get Cross-Meeting Decisions",
    description="Aggregates decisions recorded across all meetings in a project.",
)
async def get_cross_meeting_decisions(
    project_id: uuid.UUID,
    min_confidence: Optional[float] = Query(default=None, ge=0.0, le=1.0, description="Minimum confidence threshold"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_async_db),
    auth: Dict[str, Any] = Depends(verify_authentication),
) -> CrossMeetingDecisionsResponse:
    """Aggregates decisions across project meetings."""
    service = ProjectIntelligenceService(db)
    return await service.get_cross_meeting_decisions(
        project_id=project_id,
        min_confidence=min_confidence,
        limit=limit,
        offset=offset,
        auth_context=auth,
    )


@router.get(
    "/projects/{project_id}/topics/recurring",
    response_model=RecurringTopicsResponse,
    status_code=status.HTTP_200_OK,
    summary="Get Recurring Topics",
    description="Detects and clusters recurring discussion topics across project meetings.",
)
async def get_recurring_topics(
    project_id: uuid.UUID,
    db: AsyncSession = Depends(get_async_db),
    auth: Dict[str, Any] = Depends(verify_authentication),
) -> RecurringTopicsResponse:
    """Detects recurring topics across project meetings."""
    service = ProjectIntelligenceService(db)
    return await service.get_recurring_topics(
        project_id=project_id,
        auth_context=auth,
    )


@router.get(
    "/projects/{project_id}/insights",
    response_model=CrossMeetingInsightsResponse,
    status_code=status.HTTP_200_OK,
    summary="Get Cross-Meeting Insights",
    description="Aggregates insights and sentiment breakdown across project meetings.",
)
async def get_cross_meeting_insights(
    project_id: uuid.UUID,
    min_confidence: Optional[float] = Query(default=None, ge=0.0, le=1.0, description="Minimum confidence threshold"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_async_db),
    auth: Dict[str, Any] = Depends(verify_authentication),
) -> CrossMeetingInsightsResponse:
    """Aggregates insights across project meetings."""
    service = ProjectIntelligenceService(db)
    return await service.get_cross_meeting_insights(
        project_id=project_id,
        min_confidence=min_confidence,
        limit=limit,
        offset=offset,
        auth_context=auth,
    )


@router.get(
    "/projects/{project_id}/historical-context",
    response_model=ProjectHistoricalContextResponse,
    status_code=status.HTTP_200_OK,
    summary="Get Project Historical Context",
    description="Retrieves chronological timeline progression and recurring themes across project meetings.",
)
async def get_project_historical_context(
    project_id: uuid.UUID,
    db: AsyncSession = Depends(get_async_db),
    auth: Dict[str, Any] = Depends(verify_authentication),
) -> ProjectHistoricalContextResponse:
    """Retrieves project timeline and historical context."""
    service = ProjectIntelligenceService(db)
    return await service.get_project_historical_context(
        project_id=project_id,
        auth_context=auth,
    )


@router.get(
    "/projects/{project_id}/summary",
    response_model=ProjectSummaryResponse,
    status_code=status.HTTP_200_OK,
    summary="Get Project Executive Summary",
    description="Constructs an authoritative executive summary roll-up for the entire project workspace.",
)
async def get_project_summary(
    project_id: uuid.UUID,
    db: AsyncSession = Depends(get_async_db),
    auth: Dict[str, Any] = Depends(verify_authentication),
) -> ProjectSummaryResponse:
    """Retrieves project-level summary roll-up."""
    service = ProjectIntelligenceService(db)
    return await service.get_project_summary(
        project_id=project_id,
        auth_context=auth,
    )


@router.get(
    "/meetings/{meeting_id}/related",
    response_model=RelatedMeetingsResponse,
    status_code=status.HTTP_200_OK,
    summary="Get Related Meetings",
    description="Discovers related meetings sharing overlapping topics or keywords with similarity scoring.",
)
async def get_related_meetings(
    meeting_id: uuid.UUID,
    db: AsyncSession = Depends(get_async_db),
    auth: Dict[str, Any] = Depends(verify_authentication),
) -> RelatedMeetingsResponse:
    """Discovers related meetings."""
    service = ProjectIntelligenceService(db)
    return await service.get_related_meetings(
        meeting_id=meeting_id,
        auth_context=auth,
    )
