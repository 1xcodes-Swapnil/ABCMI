"""
Notifications & Real-Time Events REST API Endpoints (Phase 4.24)
Provides endpoints for retrieving user/tenant notifications, unread counts,
marking notifications as read, and deleting notifications with multi-parameter filtering.
"""

from datetime import datetime
from typing import Any, Dict, Optional
import uuid
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import verify_authentication
from app.infrastructure.database import get_async_db
from app.schemas.notification import (
    NotificationBatchReadResponse,
    NotificationCategory,
    NotificationCleanupRequest,
    NotificationCleanupResponse,
    NotificationListResponse,
    NotificationResponse,
    NotificationSeverity,
    NotificationUnreadCountResponse,
)
from app.services.notification_service import NotificationService

router = APIRouter(tags=["Notifications & Real-Time Events"])


@router.get(
    "/notifications",
    response_model=NotificationListResponse,
    status_code=status.HTTP_200_OK,
    summary="List Notifications",
    description="Retrieves a paginated list of notifications for the authenticated user and tenant with filtering.",
)
async def list_notifications(
    category: Optional[NotificationCategory] = Query(default=None, description="Filter by category"),
    severity: Optional[NotificationSeverity] = Query(default=None, description="Filter by severity level"),
    is_read: Optional[bool] = Query(default=None, description="Filter by read/unread status"),
    meeting_id: Optional[uuid.UUID] = Query(default=None, description="Filter by meeting ID"),
    project_id: Optional[uuid.UUID] = Query(default=None, description="Filter by project workspace ID"),
    date_from: Optional[datetime] = Query(default=None, description="Start date filter (UTC)"),
    date_to: Optional[datetime] = Query(default=None, description="End date filter (UTC)"),
    limit: int = Query(default=50, ge=1, le=100, description="Items per page"),
    offset: int = Query(default=0, ge=0, description="Page offset"),
    db: AsyncSession = Depends(get_async_db),
    auth: Dict[str, Any] = Depends(verify_authentication),
) -> NotificationListResponse:
    """Fetches paginated notifications matching criteria."""
    service = NotificationService(db)
    return await service.list_notifications(
        auth_context=auth,
        category=category,
        severity=severity,
        is_read=is_read,
        meeting_id=meeting_id,
        project_id=project_id,
        date_from=date_from,
        date_to=date_to,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/notifications/unread-count",
    response_model=NotificationUnreadCountResponse,
    status_code=status.HTTP_200_OK,
    summary="Get Unread Notification Count",
    description="Returns the total number of unread notifications for the caller's scope.",
)
async def get_unread_count(
    db: AsyncSession = Depends(get_async_db),
    auth: Dict[str, Any] = Depends(verify_authentication),
) -> NotificationUnreadCountResponse:
    """Returns total unread notifications count."""
    service = NotificationService(db)
    return await service.get_unread_count(auth_context=auth)


@router.get(
    "/notifications/{notification_id}",
    response_model=NotificationResponse,
    status_code=status.HTTP_200_OK,
    summary="Get Notification Details",
    description="Retrieves a single notification by its unique ID.",
)
async def get_notification(
    notification_id: uuid.UUID,
    db: AsyncSession = Depends(get_async_db),
    auth: Dict[str, Any] = Depends(verify_authentication),
) -> NotificationResponse:
    """Fetches single notification with ownership validation."""
    service = NotificationService(db)
    return await service.get_notification(notification_id=notification_id, auth_context=auth)


@router.post(
    "/notifications/{notification_id}/read",
    response_model=NotificationResponse,
    status_code=status.HTTP_200_OK,
    summary="Mark Notification as Read",
    description="Marks a specific notification as read (idempotent operation).",
)
async def mark_notification_as_read(
    notification_id: uuid.UUID,
    db: AsyncSession = Depends(get_async_db),
    auth: Dict[str, Any] = Depends(verify_authentication),
) -> NotificationResponse:
    """Marks single notification as read."""
    service = NotificationService(db)
    return await service.mark_as_read(notification_id=notification_id, auth_context=auth)


@router.post(
    "/notifications/read-all",
    response_model=NotificationBatchReadResponse,
    status_code=status.HTTP_200_OK,
    summary="Mark All Notifications as Read",
    description="Marks all unread notifications matching optional scope filters as read.",
)
async def mark_all_notifications_as_read(
    category: Optional[NotificationCategory] = Query(default=None, description="Optional category filter"),
    meeting_id: Optional[uuid.UUID] = Query(default=None, description="Optional meeting filter"),
    project_id: Optional[uuid.UUID] = Query(default=None, description="Optional project filter"),
    db: AsyncSession = Depends(get_async_db),
    auth: Dict[str, Any] = Depends(verify_authentication),
) -> NotificationBatchReadResponse:
    """Marks all unread notifications in scope as read."""
    service = NotificationService(db)
    return await service.mark_all_as_read(
        auth_context=auth,
        category=category,
        meeting_id=meeting_id,
        project_id=project_id,
    )


@router.delete(
    "/notifications/{notification_id}",
    status_code=status.HTTP_200_OK,
    summary="Delete Notification",
    description="Deletes a notification by its ID.",
)
async def delete_notification(
    notification_id: uuid.UUID,
    db: AsyncSession = Depends(get_async_db),
    auth: Dict[str, Any] = Depends(verify_authentication),
) -> Dict[str, Any]:
    """Deletes notification after validating tenant ownership."""
    service = NotificationService(db)
    deleted = await service.delete_notification(notification_id=notification_id, auth_context=auth)
    return {"status": "deleted", "id": str(notification_id), "success": deleted}


@router.post(
    "/notifications/cleanup",
    response_model=NotificationCleanupResponse,
    status_code=status.HTTP_200_OK,
    summary="Cleanup Expired Notifications",
    description="Executes retention policy cleanup of expired notifications (Admin/Security only).",
)
async def cleanup_notifications(
    body: NotificationCleanupRequest = NotificationCleanupRequest(),
    db: AsyncSession = Depends(get_async_db),
    auth: Dict[str, Any] = Depends(verify_authentication),
) -> NotificationCleanupResponse:
    """Deletes notifications exceeding retention thresholds."""
    service = NotificationService(db)
    return await service.cleanup_notifications(
        auth_context=auth,
        retention_days=body.retention_days,
        security_retention_days=body.security_retention_days,
        include_unread=body.include_unread,
    )
