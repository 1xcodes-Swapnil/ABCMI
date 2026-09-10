"""
Meeting Repository
PostgreSQL async implementation for Meeting entity operations.
"""

from typing import Optional, Sequence
import uuid
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.meeting import Meeting
from app.repositories.base import BaseRepository


class MeetingRepository(BaseRepository[Meeting]):
    """Repository handling database operations for Meeting entities."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(Meeting, session)

    async def get_with_relations(self, meeting_id: uuid.UUID) -> Optional[Meeting]:
        """Fetch meeting with eagerly loaded participants, audio, transcripts, analytics, and knowledge objects."""
        query = (
            select(Meeting)
            .where(Meeting.id == meeting_id)
            .options(
                selectinload(Meeting.host),
                selectinload(Meeting.participants),
                selectinload(Meeting.audio_recordings),
                selectinload(Meeting.transcript_segments),
                selectinload(Meeting.transcripts),
                selectinload(Meeting.analytics),
                selectinload(Meeting.knowledge_objects),
            )
            .execution_options(populate_existing=True)
        )
        result = await self.session.execute(query)
        return result.scalars().first()

    async def list_by_status(
        self,
        status: str,
        skip: int = 0,
        limit: int = 100,
    ) -> Sequence[Meeting]:
        """List meetings filtered by operational status."""
        query = (
            select(Meeting)
            .where(Meeting.status == status)
            .order_by(Meeting.created_at.desc())
            .offset(skip)
            .limit(limit)
        )
        result = await self.session.execute(query)
        return result.scalars().all()

    async def list_by_host(
        self,
        host_id: uuid.UUID,
        skip: int = 0,
        limit: int = 100,
    ) -> Sequence[Meeting]:
        """List meetings hosted by a specific user."""
        query = (
            select(Meeting)
            .where(Meeting.host_id == host_id)
            .order_by(Meeting.created_at.desc())
            .offset(skip)
            .limit(limit)
        )
        result = await self.session.execute(query)
        return result.scalars().all()
