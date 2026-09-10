"""
Query Repository (Phase 4.23)
PostgreSQL async implementation for QueryRecord persistence, history, and correlation lookups.
"""

from datetime import datetime
from typing import Optional, Sequence, Tuple
import uuid
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.query_record import QueryRecord
from app.repositories.base import BaseRepository


class QueryRecordRepository(BaseRepository[QueryRecord]):
    """Repository handling database operations for QueryRecord entities."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(QueryRecord, session)

    async def get_by_correlation_id(
        self,
        tenant_id: str,
        correlation_id: str,
    ) -> Optional[QueryRecord]:
        """Find an existing query record by correlation ID for idempotency."""
        stmt = (
            select(QueryRecord)
            .where(
                QueryRecord.tenant_id == tenant_id,
                QueryRecord.correlation_id == correlation_id,
            )
            .order_by(QueryRecord.created_at.desc())
            .limit(1)
        )
        res = await self.session.execute(stmt)
        return res.scalars().first()

    async def list_by_meeting(
        self,
        tenant_id: str,
        meeting_id: uuid.UUID,
        user_id: Optional[uuid.UUID] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        skip: int = 0,
        limit: int = 50,
    ) -> Tuple[Sequence[QueryRecord], int]:
        """
        List query records for a specific meeting, ordered chronologically with optional date-range filters.
        Returns a tuple of (items, total_count).
        """
        conditions = [
            QueryRecord.tenant_id == tenant_id,
            QueryRecord.meeting_id == meeting_id,
        ]
        if user_id is not None:
            conditions.append(QueryRecord.user_id == user_id)
        if start_time is not None:
            conditions.append(QueryRecord.created_at >= start_time)
        if end_time is not None:
            conditions.append(QueryRecord.created_at <= end_time)

        # Count total
        count_stmt = select(func.count(QueryRecord.id)).where(*conditions)
        count_res = await self.session.execute(count_stmt)
        total = count_res.scalar() or 0

        # Fetch records
        stmt = (
            select(QueryRecord)
            .where(*conditions)
            .order_by(QueryRecord.created_at.desc())
            .offset(skip)
            .limit(limit)
        )
        res = await self.session.execute(stmt)
        return res.scalars().all(), total

    async def list_by_project(
        self,
        tenant_id: str,
        project_id: uuid.UUID,
        user_id: Optional[uuid.UUID] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        skip: int = 0,
        limit: int = 50,
    ) -> Tuple[Sequence[QueryRecord], int]:
        """
        List query records for a specific project with optional date-range filters.
        Returns a tuple of (items, total_count).
        """
        conditions = [
            QueryRecord.tenant_id == tenant_id,
            QueryRecord.project_id == project_id,
        ]
        if user_id is not None:
            conditions.append(QueryRecord.user_id == user_id)
        if start_time is not None:
            conditions.append(QueryRecord.created_at >= start_time)
        if end_time is not None:
            conditions.append(QueryRecord.created_at <= end_time)

        count_stmt = select(func.count(QueryRecord.id)).where(*conditions)
        count_res = await self.session.execute(count_stmt)
        total = count_res.scalar() or 0

        stmt = (
            select(QueryRecord)
            .where(*conditions)
            .order_by(QueryRecord.created_at.desc())
            .offset(skip)
            .limit(limit)
        )
        res = await self.session.execute(stmt)
        return res.scalars().all(), total

    async def list_by_tenant(
        self,
        tenant_id: str,
        user_id: Optional[uuid.UUID] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        skip: int = 0,
        limit: int = 50,
    ) -> Tuple[Sequence[QueryRecord], int]:
        """
        List query records for a tenant with optional date-range filters.
        Returns a tuple of (items, total_count).
        """
        conditions = [QueryRecord.tenant_id == tenant_id]
        if user_id is not None:
            conditions.append(QueryRecord.user_id == user_id)
        if start_time is not None:
            conditions.append(QueryRecord.created_at >= start_time)
        if end_time is not None:
            conditions.append(QueryRecord.created_at <= end_time)

        count_stmt = select(func.count(QueryRecord.id)).where(*conditions)
        count_res = await self.session.execute(count_stmt)
        total = count_res.scalar() or 0

        stmt = (
            select(QueryRecord)
            .where(*conditions)
            .order_by(QueryRecord.created_at.desc())
            .offset(skip)
            .limit(limit)
        )
        res = await self.session.execute(stmt)
        return res.scalars().all(), total

    async def list_queries(
        self,
        tenant_id: str,
        meeting_id: Optional[uuid.UUID] = None,
        project_id: Optional[uuid.UUID] = None,
        user_id: Optional[uuid.UUID] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        skip: int = 0,
        limit: int = 50,
    ) -> Tuple[Sequence[QueryRecord], int]:
        """
        Generalized query history search across tenant with meeting, project, user, and date-range filters.
        Returns a tuple of (items, total_count).
        """
        conditions = [QueryRecord.tenant_id == tenant_id]
        if meeting_id is not None:
            conditions.append(QueryRecord.meeting_id == meeting_id)
        if project_id is not None:
            conditions.append(QueryRecord.project_id == project_id)
        if user_id is not None:
            conditions.append(QueryRecord.user_id == user_id)
        if start_time is not None:
            conditions.append(QueryRecord.created_at >= start_time)
        if end_time is not None:
            conditions.append(QueryRecord.created_at <= end_time)

        count_stmt = select(func.count(QueryRecord.id)).where(*conditions)
        count_res = await self.session.execute(count_stmt)
        total = count_res.scalar() or 0

        stmt = (
            select(QueryRecord)
            .where(*conditions)
            .order_by(QueryRecord.created_at.desc())
            .offset(skip)
            .limit(limit)
        )
        res = await self.session.execute(stmt)
        return res.scalars().all(), total
