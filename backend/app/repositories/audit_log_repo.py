"""
Audit Log Repository
PostgreSQL async implementation for AuditLog entity operations.
"""

from typing import Optional, Sequence
import uuid
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_log import AuditLog
from app.repositories.base import BaseRepository


class AuditLogRepository(BaseRepository[AuditLog]):
    """Repository handling database operations for AuditLog entities."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(AuditLog, session)

    async def list_by_meeting(
        self,
        meeting_id: uuid.UUID,
        skip: int = 0,
        limit: int = 100,
    ) -> Sequence[AuditLog]:
        """List all audit events associated with a meeting session."""
        query = (
            select(AuditLog)
            .where(AuditLog.meeting_id == meeting_id)
            .order_by(AuditLog.created_at.desc())
            .offset(skip)
            .limit(limit)
        )
        result = await self.session.execute(query)
        return result.scalars().all()

    async def list_by_user(
        self,
        user_id: uuid.UUID,
        skip: int = 0,
        limit: int = 100,
    ) -> Sequence[AuditLog]:
        """List all audit events triggered by a specific user."""
        query = (
            select(AuditLog)
            .where(AuditLog.user_id == user_id)
            .order_by(AuditLog.created_at.desc())
            .offset(skip)
            .limit(limit)
        )
        result = await self.session.execute(query)
        return result.scalars().all()

    async def list_by_action(
        self,
        action: str,
        skip: int = 0,
        limit: int = 100,
    ) -> Sequence[AuditLog]:
        """List audit events matching a specific action code."""
        query = (
            select(AuditLog)
            .where(AuditLog.action == action)
            .order_by(AuditLog.created_at.desc())
            .offset(skip)
            .limit(limit)
        )
        result = await self.session.execute(query)
        return result.scalars().all()
