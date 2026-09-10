"""
Participant Repository
PostgreSQL async implementation for Participant entity operations.
"""

from typing import Optional, Sequence
import uuid
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.participant import Participant
from app.repositories.base import BaseRepository


class ParticipantRepository(BaseRepository[Participant]):
    """Repository handling database operations for Participant entities."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(Participant, session)

    async def list_by_meeting(
        self,
        meeting_id: uuid.UUID,
        skip: int = 0,
        limit: int = 100,
    ) -> Sequence[Participant]:
        """List all participants registered in a given meeting."""
        query = (
            select(Participant)
            .where(Participant.meeting_id == meeting_id)
            .order_by(Participant.created_at.asc())
            .offset(skip)
            .limit(limit)
        )
        result = await self.session.execute(query)
        return result.scalars().all()

    async def get_by_speaker_label(
        self,
        meeting_id: uuid.UUID,
        speaker_label: str,
    ) -> Optional[Participant]:
        """Find a participant in a meeting by assigned diarization speaker label."""
        query = select(Participant).where(
            Participant.meeting_id == meeting_id,
            Participant.speaker_label == speaker_label,
        )
        result = await self.session.execute(query)
        return result.scalars().first()

    async def get_by_user_id(
        self,
        meeting_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> Optional[Participant]:
        """Find participant record associated with a specific User ID."""
        query = select(Participant).where(
            Participant.meeting_id == meeting_id,
            Participant.user_id == user_id,
        )
        result = await self.session.execute(query)
        return result.scalars().first()
