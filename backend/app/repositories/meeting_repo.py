"""
Meeting Repository
PostgreSQL async implementation for Meeting entity operations.
"""

from typing import Optional, Sequence
import uuid
from sqlalchemy import select, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.meeting import Meeting
from app.repositories.base import BaseRepository


class MeetingRepository(BaseRepository[Meeting]):
    """Repository handling database operations for Meeting entities."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(Meeting, session)

    @staticmethod
    def visible_to(user_id):
        from app.models.participant import Participant
        return or_(Meeting.host_id == user_id, Meeting.host_id.is_(None),
                   Meeting.participants.any(Participant.user_id == user_id))

    async def list(self, skip=0, limit=100, viewer_id=None, **filters):
        query = select(Meeting).options(selectinload(Meeting.participants),
                                       selectinload(Meeting.audio_recordings))
        for key, value in filters.items():
            query = query.where(getattr(Meeting, key) == value)
        if viewer_id is not None:
            query = query.where(self.visible_to(viewer_id))
        result = await self.session.execute(query.order_by(Meeting.created_at.desc()).offset(skip).limit(limit))
        return result.scalars().all()

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
