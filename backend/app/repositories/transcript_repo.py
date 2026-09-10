"""
Transcript & Transcript Segment Repositories
PostgreSQL async implementations for TranscriptSegment and canonical Transcript entity operations.
"""

from typing import List, Optional, Sequence
import uuid
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.transcript import Transcript, TranscriptSegment
from app.repositories.base import BaseRepository


class TranscriptSegmentRepository(BaseRepository[TranscriptSegment]):
    """Repository handling database operations for TranscriptSegment entities."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(TranscriptSegment, session)

    async def list_by_meeting(
        self,
        meeting_id: uuid.UUID,
        skip: int = 0,
        limit: int = 1000,
    ) -> Sequence[TranscriptSegment]:
        """List all transcript segments for a meeting in sequential order."""
        query = (
            select(TranscriptSegment)
            .where(TranscriptSegment.meeting_id == meeting_id)
            .order_by(TranscriptSegment.sequence_number.asc())
            .offset(skip)
            .limit(limit)
        )
        result = await self.session.execute(query)
        return result.scalars().all()

    async def get_latest_sequence(self, meeting_id: uuid.UUID) -> int:
        """Get the highest sequence number among transcript segments for a meeting."""
        query = select(func.max(TranscriptSegment.sequence_number)).where(
            TranscriptSegment.meeting_id == meeting_id
        )
        result = await self.session.execute(query)
        max_seq = result.scalar()
        return max_seq if max_seq is not None else 0

    async def bulk_create_segments(
        self,
        segments: List[TranscriptSegment],
    ) -> Sequence[TranscriptSegment]:
        """Persist a batch of transcript segments efficiently."""
        self.session.add_all(segments)
        await self.session.flush()
        return segments

    async def list_in_timerange(
        self,
        meeting_id: uuid.UUID,
        start_ms: int,
        end_ms: int,
    ) -> Sequence[TranscriptSegment]:
        """Fetch transcript segments overlapping with a specific time window."""
        query = (
            select(TranscriptSegment)
            .where(
                TranscriptSegment.meeting_id == meeting_id,
                TranscriptSegment.start_time_ms <= end_ms,
                TranscriptSegment.end_time_ms >= start_ms,
            )
            .order_by(TranscriptSegment.sequence_number.asc())
        )
        result = await self.session.execute(query)
        return result.scalars().all()


class TranscriptRepository(BaseRepository[Transcript]):
    """Repository handling database operations for canonical / versioned Transcript entities."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(Transcript, session)

    async def list_by_meeting(
        self,
        meeting_id: uuid.UUID,
        skip: int = 0,
        limit: int = 100,
    ) -> Sequence[Transcript]:
        """List all transcripts (versions) for a given meeting."""
        query = (
            select(Transcript)
            .where(Transcript.meeting_id == meeting_id)
            .order_by(Transcript.version.desc())
            .offset(skip)
            .limit(limit)
        )
        result = await self.session.execute(query)
        return result.scalars().all()

    async def get_latest_version(self, meeting_id: uuid.UUID) -> Optional[Transcript]:
        """Get the latest version of the canonical transcript for a meeting."""
        query = (
            select(Transcript)
            .where(Transcript.meeting_id == meeting_id)
            .order_by(Transcript.version.desc())
            .limit(1)
        )
        result = await self.session.execute(query)
        return result.scalars().first()
