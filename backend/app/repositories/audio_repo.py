"""
Audio Repository
PostgreSQL async implementation for Audio entity operations.
"""

from typing import Optional, Sequence
import uuid
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audio import Audio
from app.repositories.base import BaseRepository


class AudioRepository(BaseRepository[Audio]):
    """Repository handling database operations for Audio entities."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(Audio, session)

    async def list_by_meeting(
        self,
        meeting_id: uuid.UUID,
        skip: int = 0,
        limit: int = 100,
    ) -> Sequence[Audio]:
        """List all audio recordings associated with a meeting session."""
        query = (
            select(Audio)
            .where(Audio.meeting_id == meeting_id)
            .order_by(Audio.created_at.desc())
            .offset(skip)
            .limit(limit)
        )
        result = await self.session.execute(query)
        return result.scalars().all()

    async def get_latest_by_meeting(self, meeting_id: uuid.UUID) -> Optional[Audio]:
        """Get the most recent audio recording for a meeting."""
        query = (
            select(Audio)
            .where(Audio.meeting_id == meeting_id)
            .order_by(Audio.created_at.desc())
            .limit(1)
        )
        result = await self.session.execute(query)
        return result.scalars().first()
