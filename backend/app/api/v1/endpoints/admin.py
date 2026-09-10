"""
Admin, Audit, and Security Endpoints (Phase 4.25)
Exposes administrative user management, application roles, system status,
immutable audit logs, and security telemetry query endpoints.
"""

from datetime import datetime
from typing import Any, Dict, Optional
import uuid
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import verify_authentication
from app.infrastructure.database import get_async_db
from app.schemas.admin_audit import (
    AccessDenialListResponse,
    AdminSystemStatusResponse,
    AdminUserListResponse,
    AdminUserResponse,
    AuditLogListResponse,
    AuditLogResponse,
    RoleListResponse,
    SecuritySummaryResponse,
)
from app.services.admin_service import AdminService
from app.services.audit_service import AuditService

router = APIRouter(prefix="/admin", tags=["Administration, Audit & Security"])


# =============================================================================
# 1. Admin Endpoints
# =============================================================================

@router.get(
    "/users",
    response_model=AdminUserListResponse,
    status_code=status.HTTP_200_OK,
    summary="List Users (Admin)",
    description="Retrieves a paginated list of registered users with optional role, status, and search filters.",
)
async def list_users(
    role: Optional[str] = Query(default=None, description="Filter by user role (admin, host, member)"),
    status_param: Optional[str] = Query(default=None, alias="status", description="Filter by account status"),
    search: Optional[str] = Query(default=None, description="Search term for user email or full name"),
    limit: int = Query(default=50, ge=1, le=100, description="Items per page"),
    offset: int = Query(default=0, ge=0, description="Pagination offset"),
    db: AsyncSession = Depends(get_async_db),
    auth: Dict[str, Any] = Depends(verify_authentication),
) -> AdminUserListResponse:
    """Lists users for administrative management."""
    service = AdminService(db)
    return await service.list_users(
        auth_context=auth,
        role=role,
        status=status_param,
        search=search,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/users/{user_id}",
    response_model=AdminUserResponse,
    status_code=status.HTTP_200_OK,
    summary="Get User Details (Admin)",
    description="Retrieves a detailed safe administrative profile for a specific user.",
)
async def get_user(
    user_id: uuid.UUID,
    db: AsyncSession = Depends(get_async_db),
    auth: Dict[str, Any] = Depends(verify_authentication),
) -> AdminUserResponse:
    """Fetches user details by user ID."""
    service = AdminService(db)
    return await service.get_user_by_id(user_id=user_id, auth_context=auth)


@router.get(
    "/roles",
    response_model=RoleListResponse,
    status_code=status.HTTP_200_OK,
    summary="List Application Roles",
    description="Returns supported RBAC application roles and their associated permission capabilities.",
)
async def list_roles(
    db: AsyncSession = Depends(get_async_db),
    auth: Dict[str, Any] = Depends(verify_authentication),
) -> RoleListResponse:
    """Lists application roles and permission matrices."""
    service = AdminService(db)
    return await service.list_roles(auth_context=auth)


@router.get(
    "/system/status",
    response_model=AdminSystemStatusResponse,
    status_code=status.HTTP_200_OK,
    summary="System Operational Status",
    description="Aggregates infrastructure connectivity, operational health, and event bus readiness without secret leaks.",
)
async def get_system_status(
    db: AsyncSession = Depends(get_async_db),
    auth: Dict[str, Any] = Depends(verify_authentication),
) -> AdminSystemStatusResponse:
    """Retrieves aggregated infrastructure operational status."""
    service = AdminService(db)
    return await service.get_system_status(auth_context=auth)


# =============================================================================
# 2. Audit Log Endpoints
# =============================================================================

@router.get(
    "/audit",
    response_model=AuditLogListResponse,
    status_code=status.HTTP_200_OK,
    summary="Query Audit Logs",
    description="Retrieves a paginated list of immutable audit logs with multi-column filtering.",
)
async def query_audit_logs(
    user_id: Optional[uuid.UUID] = Query(default=None, description="Filter by actor user ID"),
    event_type: Optional[str] = Query(default=None, description="Filter by event type"),
    category: Optional[str] = Query(default=None, description="Filter by category (admin, security, auth, meeting)"),
    severity: Optional[str] = Query(default=None, description="Filter by severity (info, warning, error, security)"),
    outcome: Optional[str] = Query(default=None, description="Filter by outcome (success, failure, denied)"),
    resource_type: Optional[str] = Query(default=None, description="Filter by resource type"),
    resource_id: Optional[str] = Query(default=None, description="Filter by resource ID"),
    meeting_id: Optional[uuid.UUID] = Query(default=None, description="Filter by meeting ID"),
    project_id: Optional[uuid.UUID] = Query(default=None, description="Filter by project ID"),
    correlation_id: Optional[str] = Query(default=None, description="Filter by correlation ID"),
    start_date: Optional[datetime] = Query(default=None, description="Start time window (ISO 8601)"),
    end_date: Optional[datetime] = Query(default=None, description="End time window (ISO 8601)"),
    limit: int = Query(default=50, ge=1, le=100, description="Items per page"),
    offset: int = Query(default=0, ge=0, description="Pagination offset"),
    db: AsyncSession = Depends(get_async_db),
    auth: Dict[str, Any] = Depends(verify_authentication),
) -> AuditLogListResponse:
    """Queries audit log entries."""
    service = AuditService(db)
    return await service.list_audit_logs(
        auth_context=auth,
        user_id=user_id,
        event_type=event_type,
        category=category,
        severity=severity,
        outcome=outcome,
        resource_type=resource_type,
        resource_id=resource_id,
        meeting_id=meeting_id,
        project_id=project_id,
        correlation_id=correlation_id,
        start_date=start_date,
        end_date=end_date,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/audit/security",
    response_model=AuditLogListResponse,
    status_code=status.HTTP_200_OK,
    summary="Query Security Audit Events",
    description="Retrieves security-specific audit logs and critical security alerts.",
)
async def query_security_audit_events(
    start_date: Optional[datetime] = Query(default=None, description="Start time window (ISO 8601)"),
    end_date: Optional[datetime] = Query(default=None, description="End time window (ISO 8601)"),
    limit: int = Query(default=50, ge=1, le=100, description="Items per page"),
    offset: int = Query(default=0, ge=0, description="Pagination offset"),
    db: AsyncSession = Depends(get_async_db),
    auth: Dict[str, Any] = Depends(verify_authentication),
) -> AuditLogListResponse:
    """Queries security-specific audit log records."""
    service = AuditService(db)
    return await service.list_security_events(
        auth_context=auth,
        start_date=start_date,
        end_date=end_date,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/audit/resource/{resource_id}",
    response_model=AuditLogListResponse,
    status_code=status.HTTP_200_OK,
    summary="Query Resource Audit History",
    description="Retrieves chronological audit history for a specific resource ID (UUID or external string).",
)
async def query_resource_audit_history(
    resource_id: str,
    resource_type: Optional[str] = Query(default=None, description="Optional resource type filter"),
    limit: int = Query(default=50, ge=1, le=100, description="Items per page"),
    offset: int = Query(default=0, ge=0, description="Pagination offset"),
    db: AsyncSession = Depends(get_async_db),
    auth: Dict[str, Any] = Depends(verify_authentication),
) -> AuditLogListResponse:
    """Queries audit history for a single resource identifier."""
    service = AuditService(db)
    return await service.list_resource_history(
        resource_id=resource_id,
        auth_context=auth,
        resource_type=resource_type,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/audit/{audit_id}",
    response_model=AuditLogResponse,
    status_code=status.HTTP_200_OK,
    summary="Get Audit Log by ID",
    description="Retrieves a single immutable audit log record.",
)
async def get_audit_log(
    audit_id: uuid.UUID,
    db: AsyncSession = Depends(get_async_db),
    auth: Dict[str, Any] = Depends(verify_authentication),
) -> AuditLogResponse:
    """Retrieves an individual audit log by UUID."""
    service = AuditService(db)
    return await service.get_audit_log(audit_id=audit_id, auth_context=auth)


# =============================================================================
# 3. Security Telemetry Endpoints
# =============================================================================

@router.get(
    "/security/events",
    response_model=AuditLogListResponse,
    status_code=status.HTTP_200_OK,
    summary="Security Events Stream",
    description="Retrieves security events (auth failures, access denials, security warnings).",
)
async def get_security_events(
    start_date: Optional[datetime] = Query(default=None, description="Start time window (ISO 8601)"),
    end_date: Optional[datetime] = Query(default=None, description="End time window (ISO 8601)"),
    limit: int = Query(default=50, ge=1, le=100, description="Items per page"),
    offset: int = Query(default=0, ge=0, description="Pagination offset"),
    db: AsyncSession = Depends(get_async_db),
    auth: Dict[str, Any] = Depends(verify_authentication),
) -> AuditLogListResponse:
    """Retrieves security events stream."""
    service = AuditService(db)
    return await service.list_security_events(
        auth_context=auth,
        start_date=start_date,
        end_date=end_date,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/security/summary",
    response_model=SecuritySummaryResponse,
    status_code=status.HTTP_200_OK,
    summary="Security Summary Metrics",
    description="Aggregates security metrics (auth failures, access denials, alerts, affected resources) over a time window.",
)
async def get_security_summary(
    days: int = Query(default=7, ge=1, le=365, description="Lookback window in days"),
    db: AsyncSession = Depends(get_async_db),
    auth: Dict[str, Any] = Depends(verify_authentication),
) -> SecuritySummaryResponse:
    """Aggregates security metrics."""
    service = AuditService(db)
    return await service.get_security_summary(auth_context=auth, days=days)


@router.get(
    "/security/access-denials",
    response_model=AccessDenialListResponse,
    status_code=status.HTTP_200_OK,
    summary="Access Denials History",
    description="Retrieves paginated authorization failures and access denial records.",
)
async def get_access_denials(
    user_id: Optional[uuid.UUID] = Query(default=None, description="Filter by user ID"),
    resource_type: Optional[str] = Query(default=None, description="Filter by resource type"),
    resource_id: Optional[str] = Query(default=None, description="Filter by resource ID"),
    meeting_id: Optional[uuid.UUID] = Query(default=None, description="Filter by meeting ID"),
    project_id: Optional[uuid.UUID] = Query(default=None, description="Filter by project ID"),
    start_date: Optional[datetime] = Query(default=None, description="Start date (ISO 8601)"),
    end_date: Optional[datetime] = Query(default=None, description="End date (ISO 8601)"),
    limit: int = Query(default=50, ge=1, le=100, description="Items per page"),
    offset: int = Query(default=0, ge=0, description="Pagination offset"),
    db: AsyncSession = Depends(get_async_db),
    auth: Dict[str, Any] = Depends(verify_authentication),
) -> AccessDenialListResponse:
    """Queries access denial events."""
    service = AuditService(db)
    return await service.list_access_denials(
        auth_context=auth,
        user_id=user_id,
        resource_type=resource_type,
        resource_id=resource_id,
        meeting_id=meeting_id,
        project_id=project_id,
        start_date=start_date,
        end_date=end_date,
        limit=limit,
        offset=offset,
    )
