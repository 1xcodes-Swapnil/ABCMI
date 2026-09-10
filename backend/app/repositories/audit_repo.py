"""
Audit Log Repository (Phase 4.25)
PostgreSQL async implementation for immutable AuditLog entities.
Supports tenant isolation, comprehensive multi-attribute filtering, date windows,
and security telemetry aggregation.
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence, Tuple
import uuid
from sqlalchemy import distinct, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_log import AuditLog
from app.repositories.base import BaseRepository


class AuditLogRepository(BaseRepository[AuditLog]):
    """
    Asynchronous repository for immutable AuditLog persistence and multi-tenant querying.
    Strictly append-only; update/delete operations are intentionally not exposed.
    """

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(AuditLog, session)

    async def get_by_event_id(self, tenant_id: str, event_id: str) -> Optional[AuditLog]:
        """Fetch audit record by stable event idempotency identifier within a tenant."""
        if not event_id:
            return None
        query = (
            select(AuditLog)
            .where(
                AuditLog.tenant_id == tenant_id,
                AuditLog.event_id == event_id,
            )
            .limit(1)
        )
        result = await self.session.execute(query)
        return result.scalars().first()

    async def get_by_id_and_tenant(self, audit_id: uuid.UUID, tenant_id: str) -> Optional[AuditLog]:
        """Fetch a single audit log record strictly scoped to a tenant."""
        query = (
            select(AuditLog)
            .where(
                AuditLog.id == audit_id,
                AuditLog.tenant_id == tenant_id,
            )
            .limit(1)
        )
        result = await self.session.execute(query)
        return result.scalars().first()

    async def list_audit_logs(
        self,
        tenant_id: str,
        user_id: Optional[uuid.UUID] = None,
        event_type: Optional[str] = None,
        category: Optional[str] = None,
        severity: Optional[str] = None,
        outcome: Optional[str] = None,
        resource_type: Optional[str] = None,
        resource_id: Optional[str] = None,
        meeting_id: Optional[uuid.UUID] = None,
        project_id: Optional[uuid.UUID] = None,
        correlation_id: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Tuple[Sequence[AuditLog], int]:
        """
        Queries paginated audit logs with multi-column filtering and tenant isolation.
        Returns a tuple of (items, total_count).
        """
        base_filters = [AuditLog.tenant_id == tenant_id]

        if user_id is not None:
            base_filters.append(AuditLog.user_id == user_id)
        if event_type:
            base_filters.append(AuditLog.event_type == event_type)
        if category:
            base_filters.append(AuditLog.category == category)
        if severity:
            base_filters.append(AuditLog.severity == severity)
        if outcome:
            base_filters.append(AuditLog.outcome == outcome)
        if resource_type:
            base_filters.append(AuditLog.resource_type == resource_type)
        if resource_id:
            base_filters.append(AuditLog.resource_id == str(resource_id).strip())
        if meeting_id is not None:
            base_filters.append(AuditLog.meeting_id == meeting_id)
        if project_id is not None:
            base_filters.append(AuditLog.project_id == project_id)
        if correlation_id:
            base_filters.append(AuditLog.correlation_id == correlation_id)
        if start_date:
            base_filters.append(AuditLog.created_at >= start_date)
        if end_date:
            base_filters.append(AuditLog.created_at <= end_date)

        # Count total matching records
        count_query = select(func.count(AuditLog.id)).where(*base_filters)
        count_result = await self.session.execute(count_query)
        total = count_result.scalar() or 0

        # Query paginated items
        items_query = (
            select(AuditLog)
            .where(*base_filters)
            .order_by(AuditLog.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        items_result = await self.session.execute(items_query)
        items = items_result.scalars().all()

        return items, total

    async def list_security_events(
        self,
        tenant_id: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Tuple[Sequence[AuditLog], int]:
        """Queries security-relevant audit logs (security category, critical/security severity, or denied outcomes)."""
        base_filters = [
            AuditLog.tenant_id == tenant_id,
            (
                (AuditLog.category == "security")
                | (AuditLog.category == "access_control")
                | (AuditLog.category == "auth")
                | (AuditLog.severity == "security")
                | (AuditLog.severity == "critical")
                | (AuditLog.outcome == "denied")
            ),
        ]

        if start_date:
            base_filters.append(AuditLog.created_at >= start_date)
        if end_date:
            base_filters.append(AuditLog.created_at <= end_date)

        count_query = select(func.count(AuditLog.id)).where(*base_filters)
        count_result = await self.session.execute(count_query)
        total = count_result.scalar() or 0

        items_query = (
            select(AuditLog)
            .where(*base_filters)
            .order_by(AuditLog.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        items_result = await self.session.execute(items_query)
        items = items_result.scalars().all()

        return items, total

    async def list_resource_history(
        self,
        tenant_id: str,
        resource_id: str,
        resource_type: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Tuple[Sequence[AuditLog], int]:
        """Queries chronological audit trail for a specific resource identifier."""
        base_filters = [
            AuditLog.tenant_id == tenant_id,
            AuditLog.resource_id == str(resource_id).strip(),
        ]
        if resource_type:
            base_filters.append(AuditLog.resource_type == resource_type)

        count_query = select(func.count(AuditLog.id)).where(*base_filters)
        count_result = await self.session.execute(count_query)
        total = count_result.scalar() or 0

        items_query = (
            select(AuditLog)
            .where(*base_filters)
            .order_by(AuditLog.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        items_result = await self.session.execute(items_query)
        items = items_result.scalars().all()

        return items, total

    async def list_access_denials(
        self,
        tenant_id: str,
        user_id: Optional[uuid.UUID] = None,
        resource_type: Optional[str] = None,
        resource_id: Optional[str] = None,
        meeting_id: Optional[uuid.UUID] = None,
        project_id: Optional[uuid.UUID] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Tuple[Sequence[AuditLog], int]:
        """Queries authorization failures and access denial records."""
        base_filters = [
            AuditLog.tenant_id == tenant_id,
            AuditLog.outcome == "denied",
        ]
        if user_id is not None:
            base_filters.append(AuditLog.user_id == user_id)
        if resource_type:
            base_filters.append(AuditLog.resource_type == resource_type)
        if resource_id:
            base_filters.append(AuditLog.resource_id == str(resource_id).strip())
        if meeting_id is not None:
            base_filters.append(AuditLog.meeting_id == meeting_id)
        if project_id is not None:
            base_filters.append(AuditLog.project_id == project_id)
        if start_date:
            base_filters.append(AuditLog.created_at >= start_date)
        if end_date:
            base_filters.append(AuditLog.created_at <= end_date)

        count_query = select(func.count(AuditLog.id)).where(*base_filters)
        count_result = await self.session.execute(count_query)
        total = count_result.scalar() or 0

        items_query = (
            select(AuditLog)
            .where(*base_filters)
            .order_by(AuditLog.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        items_result = await self.session.execute(items_query)
        items = items_result.scalars().all()

        return items, total

    async def get_security_summary(
        self,
        tenant_id: str,
        start_date: datetime,
        end_date: datetime,
    ) -> Dict[str, Any]:
        """Aggregates security metrics across an evaluation window."""
        # 1. Authentication Failures
        auth_failures_q = select(func.count(AuditLog.id)).where(
            AuditLog.tenant_id == tenant_id,
            AuditLog.category == "auth",
            AuditLog.outcome.in_(["failure", "denied"]),
            AuditLog.created_at >= start_date,
            AuditLog.created_at <= end_date,
        )
        auth_failures = (await self.session.execute(auth_failures_q)).scalar() or 0

        # 2. Authorization Failures / Access Denials
        authz_failures_q = select(func.count(AuditLog.id)).where(
            AuditLog.tenant_id == tenant_id,
            AuditLog.outcome == "denied",
            AuditLog.created_at >= start_date,
            AuditLog.created_at <= end_date,
        )
        authz_failures = (await self.session.execute(authz_failures_q)).scalar() or 0

        # 3. Security Alerts
        alerts_q = select(func.count(AuditLog.id)).where(
            AuditLog.tenant_id == tenant_id,
            (AuditLog.severity.in_(["critical", "security"]) | (AuditLog.category == "security")),
            AuditLog.created_at >= start_date,
            AuditLog.created_at <= end_date,
        )
        alerts = (await self.session.execute(alerts_q)).scalar() or 0

        # 4. Distinct affected users
        affected_users_q = select(func.count(distinct(AuditLog.user_id))).where(
            AuditLog.tenant_id == tenant_id,
            (AuditLog.outcome == "denied") | (AuditLog.severity.in_(["critical", "security"])),
            AuditLog.user_id.isnot(None),
            AuditLog.created_at >= start_date,
            AuditLog.created_at <= end_date,
        )
        affected_users = (await self.session.execute(affected_users_q)).scalar() or 0

        # 5. Distinct affected resources
        affected_res_q = select(func.count(distinct(AuditLog.resource_id))).where(
            AuditLog.tenant_id == tenant_id,
            (AuditLog.outcome == "denied") | (AuditLog.severity.in_(["critical", "security"])),
            AuditLog.resource_id.isnot(None),
            AuditLog.created_at >= start_date,
            AuditLog.created_at <= end_date,
        )
        affected_res = (await self.session.execute(affected_res_q)).scalar() or 0

        return {
            "authentication_failures": auth_failures,
            "authorization_failures": authz_failures,
            "access_denials": authz_failures,
            "security_alerts": alerts,
            "affected_users": affected_users,
            "affected_resources": affected_res,
        }
