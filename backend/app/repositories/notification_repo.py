"""
Notification Repository (Phase 4.24)
Provides asynchronous database access, multi-parameter filtering, unread counts,
idempotency lookups, and batch state transitions for notifications.
"""

from datetime import datetime, timezone
from typing import Any, List, Optional, Tuple
import uuid
from sqlalchemy import and_, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.notification import Notification
from app.repositories.base import BaseRepository


class NotificationRepository(BaseRepository[Notification]):
    """Repository handling persistence, querying, and bulk updates for notifications."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(Notification, session)

    async def get_by_event_id(self, tenant_id: str, event_id: str) -> Optional[Notification]:
        """Finds an existing notification by tenant and source event_id for idempotency."""
        if not event_id:
            return None
        stmt = select(Notification).where(
            and_(
                Notification.tenant_id == tenant_id,
                Notification.event_id == event_id,
            )
        )
        result = await self.session.execute(stmt)
        return result.scalars().first()

    async def list_notifications(
        self,
        tenant_id: str,
        user_id: Optional[uuid.UUID] = None,
        category: Optional[str] = None,
        severity: Optional[str] = None,
        is_read: Optional[bool] = None,
        meeting_id: Optional[uuid.UUID] = None,
        project_id: Optional[uuid.UUID] = None,
        date_from: Optional[datetime] = None,
        date_to: Optional[datetime] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Tuple[List[Notification], int]:
        """
        Lists notifications with multi-parameter filtering, pagination, and total count.
        Scoped to tenant, and either broadcast (user_id IS NULL) or specific user.
        """
        conditions = [Notification.tenant_id == tenant_id]

        if user_id is not None:
            # User sees notifications addressed to them OR broadcast notifications (user_id IS NULL)
            conditions.append(
                or_(
                    Notification.user_id == user_id,
                    Notification.user_id.is_(None),
                )
            )

        if category is not None:
            conditions.append(Notification.category == category)

        if severity is not None:
            conditions.append(Notification.severity == severity)

        if is_read is not None:
            conditions.append(Notification.is_read == is_read)

        if meeting_id is not None:
            conditions.append(Notification.meeting_id == meeting_id)

        if project_id is not None:
            conditions.append(Notification.project_id == project_id)

        if date_from is not None:
            conditions.append(Notification.created_at >= date_from)

        if date_to is not None:
            conditions.append(Notification.created_at <= date_to)

        where_clause = and_(*conditions)

        # Count total matching
        count_stmt = select(func.count(Notification.id)).where(where_clause)
        count_res = await self.session.execute(count_stmt)
        total = count_res.scalar() or 0

        # Query paginated rows
        stmt = (
            select(Notification)
            .where(where_clause)
            .order_by(Notification.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        res = await self.session.execute(stmt)
        items = list(res.scalars().all())

        return items, total

    async def count_unread(
        self,
        tenant_id: str,
        user_id: Optional[uuid.UUID] = None,
    ) -> int:
        """Returns the total unread notification count for a tenant/user scope."""
        conditions = [
            Notification.tenant_id == tenant_id,
            Notification.is_read.is_(False),
        ]
        if user_id is not None:
            conditions.append(
                or_(
                    Notification.user_id == user_id,
                    Notification.user_id.is_(None),
                )
            )
        stmt = select(func.count(Notification.id)).where(and_(*conditions))
        res = await self.session.execute(stmt)
        return res.scalar() or 0

    async def mark_as_read(
        self,
        notification_id: uuid.UUID,
        read_timestamp: Optional[datetime] = None,
    ) -> Optional[Notification]:
        """Marks an individual notification as read."""
        notification = await self.get_by_id(notification_id)
        if not notification:
            return None
        if not notification.is_read:
            notification.is_read = True
            notification.read_at = read_timestamp or datetime.now(timezone.utc)
            await self.session.flush()
            await self.session.refresh(notification)
        return notification

    async def mark_all_as_read(
        self,
        tenant_id: str,
        user_id: Optional[uuid.UUID] = None,
        category: Optional[str] = None,
        meeting_id: Optional[uuid.UUID] = None,
        project_id: Optional[uuid.UUID] = None,
        read_timestamp: Optional[datetime] = None,
    ) -> int:
        """Marks all matching unread notifications as read in bulk."""
        ts = read_timestamp or datetime.now(timezone.utc)
        conditions = [
            Notification.tenant_id == tenant_id,
            Notification.is_read.is_(False),
        ]
        if user_id is not None:
            conditions.append(
                or_(
                    Notification.user_id == user_id,
                    Notification.user_id.is_(None),
                )
            )
        if category is not None:
            conditions.append(Notification.category == category)
        if meeting_id is not None:
            conditions.append(Notification.meeting_id == meeting_id)
        if project_id is not None:
            conditions.append(Notification.project_id == project_id)

        stmt = (
            update(Notification)
            .where(and_(*conditions))
            .values(is_read=True, read_at=ts)
        )
        res = await self.session.execute(stmt)
        await self.session.flush()
        return res.rowcount

    async def cleanup_expired(
        self,
        tenant_id: Optional[str] = None,
        retention_days: int = 30,
        security_retention_days: int = 365,
        include_unread: bool = False,
    ) -> int:
        """
        Deletes notifications older than the retention threshold.
        - Standard notifications: retention_days (default 30 days)
        - Security notifications: security_retention_days (default 365 days)
        - Preserves unread notifications unless include_unread=True.
        - Idempotent and scoped to tenant if provided.
        """
        from datetime import timedelta
        from sqlalchemy import delete

        now = datetime.now(timezone.utc)
        cutoff_standard = now - timedelta(days=retention_days)
        cutoff_security = now - timedelta(days=security_retention_days)

        # Standard notification expiration clause
        standard_conditions = [
            Notification.category != "security",
            Notification.severity != "security",
            Notification.created_at < cutoff_standard,
        ]

        # Security notification expiration clause
        security_conditions = [
            or_(
                Notification.category == "security",
                Notification.severity == "security",
            ),
            Notification.created_at < cutoff_security,
        ]

        if not include_unread:
            standard_conditions.append(Notification.is_read.is_(True))
            security_conditions.append(Notification.is_read.is_(True))

        if tenant_id is not None:
            standard_conditions.append(Notification.tenant_id == tenant_id)
            security_conditions.append(Notification.tenant_id == tenant_id)

        # Combine standard and security branch
        delete_clause = or_(
            and_(*standard_conditions),
            and_(*security_conditions),
        )

        stmt = delete(Notification).where(delete_clause)
        res = await self.session.execute(stmt)
        await self.session.flush()
        return res.rowcount

