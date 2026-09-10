"""
Admin Service (Phase 4.25)
Provides administrative functionality including user management, role definitions,
and aggregated system operational status.
"""

import asyncio
from datetime import datetime, timezone
import time
from typing import Any, Dict, List, Optional, Sequence, Tuple
import uuid
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.exceptions import ForbiddenException, NotFoundException
from app.core.logging import get_logger
from app.events.redis_bus import RedisEventBus, get_event_bus
from app.infrastructure.database import check_database_health
from app.infrastructure.qdrant import check_qdrant_health
from app.infrastructure.redis import check_redis_health
from app.infrastructure.storage import get_storage_manager
from app.models.meeting import Meeting
from app.models.user import User
from app.repositories.user_repo import UserRepository
from app.schemas.admin_audit import (
    AdminSystemStatusResponse,
    AdminUserListResponse,
    AdminUserResponse,
    EventBusStatus,
    RoleDefinitionResponse,
    RoleListResponse,
    ServiceComponentStatus,
)

logger = get_logger("services.admin_service")

# Global startup baseline for uptime calculations
_SYSTEM_START_TIME = time.time()


class AdminService:
    """
    Service managing administrative operations:
    - User directory query & management
    - Application RBAC role declarations
    - Unified system health and operational status
    """

    ADMIN_ROLES = {"admin"}
    SECURITY_ROLES = {"admin", "security_officer", "security_auditor"}

    # Authoritative ABCI-MI RBAC Catalog
    APPLICATION_ROLES: List[Dict[str, Any]] = [
        {
            "role": "admin",
            "name": "System Administrator",
            "description": "Full administrative control over tenant settings, user directory, system health, audit logs, and security controls.",
            "permissions": [
                "admin:users:read",
                "admin:users:write",
                "admin:system:read",
                "audit:read",
                "security:read",
                "meetings:all",
                "knowledge:all",
                "projects:all",
                "notifications:all",
            ],
            "is_administrative": True,
        },
        {
            "role": "security_officer",
            "name": "Security Officer",
            "description": "Administrative authority for security event monitoring, incident investigation, access denials, and compliance audit log inspection.",
            "permissions": [
                "audit:read",
                "security:read",
                "security:alerts:read",
                "notifications:security:read",
                "admin:system:read",
            ],
            "is_administrative": True,
        },
        {
            "role": "security_auditor",
            "name": "Compliance & Security Auditor",
            "description": "Read-only access to immutable audit trails, access denials, security logs, and compliance telemetry.",
            "permissions": [
                "audit:read",
                "security:read",
                "notifications:security:read",
            ],
            "is_administrative": True,
        },
        {
            "role": "host",
            "name": "Meeting Host",
            "description": "User capable of initiating live meetings, scheduling calls, uploading recordings, and generating intelligence reports.",
            "permissions": [
                "meetings:create",
                "meetings:read",
                "meetings:update",
                "meetings:delete",
                "knowledge:read",
                "knowledge:create",
                "reports:generate",
                "projects:participate",
            ],
            "is_administrative": False,
        },
        {
            "role": "member",
            "name": "Workspace Member",
            "description": "Standard participant capable of viewing assigned meetings, action items, derived translations, and intelligence reports.",
            "permissions": [
                "meetings:read",
                "knowledge:read",
                "reports:read",
                "translations:read",
                "projects:read",
            ],
            "is_administrative": False,
        },
    ]

    def __init__(
        self,
        db: AsyncSession,
        event_bus: Optional[RedisEventBus] = None,
    ) -> None:
        self.db = db
        self.user_repo = UserRepository(db)
        self.event_bus = event_bus or get_event_bus()

    def _extract_admin_context(self, auth_context: Dict[str, Any]) -> Tuple[str, Optional[uuid.UUID], str]:
        """Validates that caller possesses administrative credentials."""
        if not auth_context or not auth_context.get("authenticated", False):
            raise ForbiddenException(message="Authentication credentials required", code="UNAUTHORIZED")

        tenant_id = auth_context.get("tenant_id") or auth_context.get("user_id") or "tenant-default"
        tenant_id = str(tenant_id)

        user_id_raw = auth_context.get("user_id")
        user_id: Optional[uuid.UUID] = None
        if user_id_raw:
            try:
                user_id = uuid.UUID(str(user_id_raw))
            except ValueError:
                user_id = None

        role = str(auth_context.get("role", "user")).lower()
        if role not in self.ADMIN_ROLES:
            raise ForbiddenException("Administrative privileges required for this operation.", code="INSUFFICIENT_ROLE")

        return tenant_id, user_id, role

    async def list_users(
        self,
        auth_context: Dict[str, Any],
        role: Optional[str] = None,
        status: Optional[str] = None,
        search: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> AdminUserListResponse:
        """
        Lists tenant users with pagination, role, and search filters.
        Enforces Admin RBAC.
        """
        self._extract_admin_context(auth_context)

        users, total = await self.user_repo.list_users_filtered(
            role=role,
            status=status,
            search=search,
            skip=offset,
            limit=limit,
        )

        user_dtos: List[AdminUserResponse] = []
        for user in users:
            # Query count of meetings hosted by this user
            count_query = select(func.count(Meeting.id)).where(Meeting.host_id == user.id)
            count_result = await self.db.execute(count_query)
            hosted_count = count_result.scalar() or 0

            user_dtos.append(
                AdminUserResponse(
                    id=user.id,
                    email=user.email,
                    full_name=user.full_name,
                    role=user.role,
                    status=user.status,
                    is_active=user.is_active,
                    preferences=user.preferences or {},
                    hosted_meetings_count=hosted_count,
                    created_at=user.created_at,
                    updated_at=user.updated_at,
                )
            )

        return AdminUserListResponse(
            items=user_dtos,
            total=total,
            limit=limit,
            offset=offset,
        )

    async def get_user_by_id(
        self,
        user_id: uuid.UUID,
        auth_context: Dict[str, Any],
    ) -> AdminUserResponse:
        """
        Fetches an individual user profile for administrative inspection.
        Enforces 404 for missing resources.
        """
        self._extract_admin_context(auth_context)

        user = await self.user_repo.get_by_id(user_id)
        if not user:
            raise NotFoundException(f"User '{user_id}' not found.", code="USER_NOT_FOUND")

        # Query hosted meetings count
        count_query = select(func.count(Meeting.id)).where(Meeting.host_id == user.id)
        count_result = await self.db.execute(count_query)
        hosted_count = count_result.scalar() or 0

        return AdminUserResponse(
            id=user.id,
            email=user.email,
            full_name=user.full_name,
            role=user.role,
            status=user.status,
            is_active=user.is_active,
            preferences=user.preferences or {},
            hosted_meetings_count=hosted_count,
            created_at=user.created_at,
            updated_at=user.updated_at,
        )

    async def list_roles(
        self,
        auth_context: Dict[str, Any],
    ) -> RoleListResponse:
        """
        Returns all supported application roles and their associated capabilities.
        Accessible by admin and security roles.
        """
        if not auth_context or not auth_context.get("authenticated", False):
            raise ForbiddenException(message="Authentication credentials required", code="UNAUTHORIZED")

        role = str(auth_context.get("role", "user")).lower()
        if role not in self.SECURITY_ROLES:
            raise ForbiddenException("Administrative or security credentials required.", code="INSUFFICIENT_ROLE")

        role_dtos = [RoleDefinitionResponse(**r) for r in self.APPLICATION_ROLES]
        return RoleListResponse(
            roles=role_dtos,
            total=len(role_dtos),
        )

    async def get_system_status(
        self,
        auth_context: Dict[str, Any],
    ) -> AdminSystemStatusResponse:
        """
        Aggregates operational status across PostgreSQL, Redis, Qdrant, Local Storage,
        and the RedisEventBus. Enforces RBAC and strictly masks infrastructure credentials/URIs.
        """
        if not auth_context or not auth_context.get("authenticated", False):
            raise ForbiddenException(message="Authentication credentials required", code="UNAUTHORIZED")

        role = str(auth_context.get("role", "user")).lower()
        if role not in self.SECURITY_ROLES:
            raise ForbiddenException("Administrative or security privileges required.", code="INSUFFICIENT_ROLE")

        settings = get_settings()
        uptime = round(time.time() - _SYSTEM_START_TIME, 2)

        # Run health checks concurrently
        db_task = asyncio.create_task(check_database_health())
        redis_task = asyncio.create_task(check_redis_health())
        qdrant_task = asyncio.create_task(check_qdrant_health())
        event_bus_prod_task = asyncio.create_task(self.event_bus.verify_production_readiness())

        storage_mgr = get_storage_manager()
        storage_health = storage_mgr.check_health()

        results = await asyncio.gather(db_task, redis_task, qdrant_task, event_bus_prod_task, return_exceptions=True)

        db_res = results[0] if not isinstance(results[0], Exception) else {"status": "unhealthy", "error": "Database check exception"}
        redis_res = results[1] if not isinstance(results[1], Exception) else {"status": "unhealthy", "error": "Redis check exception"}
        qdrant_res = results[2] if not isinstance(results[2], Exception) else {"status": "unhealthy", "error": "Qdrant check exception"}
        
        eb_prod_res = results[3] if not isinstance(results[3], Exception) else (False, "Event bus check exception")
        eb_is_prod_ready, eb_err = eb_prod_res if isinstance(eb_prod_res, tuple) else (False, str(eb_prod_res))

        event_bus_status = self.event_bus.get_status()

        db_status = ServiceComponentStatus(
            status=db_res.get("status", "unhealthy"),
            latency_ms=db_res.get("latency_ms"),
            error=str(db_res.get("error")) if db_res.get("error") else None,
        )
        redis_status = ServiceComponentStatus(
            status=redis_res.get("status", "unhealthy"),
            latency_ms=redis_res.get("latency_ms"),
            error=str(redis_res.get("error")) if redis_res.get("error") else None,
        )
        qdrant_status = ServiceComponentStatus(
            status=qdrant_res.get("status", "unhealthy"),
            latency_ms=qdrant_res.get("latency_ms"),
            error=str(qdrant_res.get("error")) if qdrant_res.get("error") else None,
        )
        storage_status = ServiceComponentStatus(
            status=storage_health.get("status", "unhealthy"),
            error=str(storage_health.get("error")) if storage_health.get("error") else None,
        )

        eb_dto = EventBusStatus(
            mode=event_bus_status.get("mode", "local_fallback"),
            is_distributed=event_bus_status.get("is_distributed", False),
            production_ready=eb_is_prod_ready,
            total_handlers=event_bus_status.get("total_handlers", 0),
        )

        # Aggregate overall status
        statuses = [db_status.status, redis_status.status, qdrant_status.status, storage_status.status]
        if all(s == "healthy" for s in statuses):
            overall_status = "healthy"
        elif any(s == "unhealthy" for s in statuses):
            overall_status = "degraded" if any(s == "healthy" for s in statuses) else "unhealthy"
        else:
            overall_status = "degraded"

        return AdminSystemStatusResponse(
            status=overall_status,
            environment=settings.ENVIRONMENT,
            version=settings.VERSION,
            uptime_seconds=uptime,
            timestamp=datetime.now(timezone.utc),
            database=db_status,
            redis=redis_status,
            qdrant=qdrant_status,
            storage=storage_status,
            event_bus=eb_dto,
        )
