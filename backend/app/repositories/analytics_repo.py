"""
Analytics Repository
PostgreSQL async implementation for MeetingAnalytics entity operations.
"""

from typing import Any, Optional
import uuid
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.analytics import MeetingAnalytics
from app.repositories.base import BaseRepository


class AnalyticsRepository(BaseRepository[MeetingAnalytics]):
    """Repository handling database operations for MeetingAnalytics entities."""

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(MeetingAnalytics, session)

    async def get_by_meeting_id(self, meeting_id: uuid.UUID) -> Optional[MeetingAnalytics]:
        """Fetch analytics metrics for a specific meeting."""
        query = select(MeetingAnalytics).where(MeetingAnalytics.meeting_id == meeting_id)
        result = await self.session.execute(query)
        return result.scalars().first()

    async def upsert_for_meeting(
        self,
        meeting_id: uuid.UUID,
        speaking_time_distribution: dict,
        collaboration_score: Optional[float] = None,
        participation_index: Optional[float] = None,
        sentiment_score: Optional[float] = None,
        productivity_score: Optional[float] = None,
        sentiment_distribution: Optional[dict] = None,
        engagement_score: Optional[float] = None,
        pace_wpm: Optional[float] = None,
        turn_taking_metrics: Optional[dict] = None,
        topic_keywords: Optional[list] = None,
        summary_metrics: Optional[dict] = None,
    ) -> MeetingAnalytics:
        """Create or update meeting analytics data atomically."""
        existing = await self.get_by_meeting_id(meeting_id)
        if existing is not None:
            existing.speaking_time_distribution = speaking_time_distribution
            if collaboration_score is not None:
                existing.collaboration_score = collaboration_score
            if participation_index is not None:
                existing.participation_index = participation_index
            if sentiment_score is not None:
                existing.sentiment_score = sentiment_score
            if productivity_score is not None:
                existing.productivity_score = productivity_score
            if sentiment_distribution is not None:
                existing.sentiment_distribution = sentiment_distribution
            if engagement_score is not None:
                existing.engagement_score = engagement_score
            if pace_wpm is not None:
                existing.pace_wpm = pace_wpm
            if turn_taking_metrics is not None:
                existing.turn_taking_metrics = turn_taking_metrics
            if topic_keywords is not None:
                existing.topic_keywords = topic_keywords
            if summary_metrics is not None:
                existing.summary_metrics = summary_metrics
            await self.session.flush()
            await self.session.refresh(existing)
            return existing

        new_analytics = MeetingAnalytics(
            meeting_id=meeting_id,
            speaking_time_distribution=speaking_time_distribution,
            collaboration_score=collaboration_score,
            participation_index=participation_index,
            sentiment_score=sentiment_score,
            productivity_score=productivity_score,
            sentiment_distribution=sentiment_distribution or {},
            engagement_score=engagement_score,
            pace_wpm=pace_wpm,
            turn_taking_metrics=turn_taking_metrics or {},
            topic_keywords=topic_keywords or [],
            summary_metrics=summary_metrics or {},
        )
        return await self.create(new_analytics)
