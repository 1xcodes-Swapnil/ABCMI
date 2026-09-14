"""
Meeting Analytics SQLAlchemy ORM Model
Represents quantitative meeting intelligence, speaking time distribution, sentiment, and engagement metrics.
"""

from typing import TYPE_CHECKING, Optional
import uuid
from sqlalchemy import Float, ForeignKey, JSON, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel

if TYPE_CHECKING:
    from app.models.meeting import Meeting


class MeetingAnalytics(BaseModel):
    """MeetingAnalytics entity storing aggregated interaction metrics for a meeting session."""

    __tablename__ = "meeting_analytics"

    meeting_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("meetings.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    speaking_time_distribution: Mapped[dict] = mapped_column(
        JSON,
        nullable=False,
        default=dict,
    )
    collaboration_score: Mapped[Optional[float]] = mapped_column(
        Float,
        nullable=True,
    )
    participation_index: Mapped[Optional[float]] = mapped_column(
        Float,
        nullable=True,
    )
    sentiment_score: Mapped[Optional[float]] = mapped_column(
        Float,
        nullable=True,
    )
    productivity_score: Mapped[Optional[float]] = mapped_column(
        Float,
        nullable=True,
    )
    sentiment_distribution: Mapped[Optional[dict]] = mapped_column(
        JSON,
        nullable=True,
        default=dict,
    )
    engagement_score: Mapped[Optional[float]] = mapped_column(
        Float,
        nullable=True,
    )
    pace_wpm: Mapped[Optional[float]] = mapped_column(
        Float,
        nullable=True,
    )
    turn_taking_metrics: Mapped[Optional[dict]] = mapped_column(
        JSON,
        nullable=True,
        default=dict,
    )
    topic_keywords: Mapped[Optional[list]] = mapped_column(
        JSON,
        nullable=True,
        default=list,
    )
    summary_metrics: Mapped[Optional[dict]] = mapped_column(
        JSON,
        nullable=True,
        default=dict,
    )

    # Relationships
    meeting: Mapped["Meeting"] = relationship(
        "Meeting",
        back_populates="analytics",
    )

    def __repr__(self) -> str:
        return f"<MeetingAnalytics id={self.id} meeting_id={self.meeting_id} engagement={self.engagement_score}>"
