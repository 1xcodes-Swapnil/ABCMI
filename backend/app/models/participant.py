"""
Participant SQLAlchemy ORM Model
Represents meeting attendees, speakers, and assigned voiceprints.
"""

from datetime import datetime
from typing import TYPE_CHECKING, List, Optional
import uuid
from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel

if TYPE_CHECKING:
    from app.models.meeting import Meeting
    from app.models.user import User
    from app.models.transcript import TranscriptSegment


class Participant(BaseModel):
    """Participant entity representing an attendee or speaker in a meeting session."""

    __tablename__ = "participants"

    meeting_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("meetings.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    display_name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    email: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
    )
    role: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="attendee",
    )
    speaker_label: Mapped[Optional[str]] = mapped_column(
        String(50),
        nullable=True,
    )
    voiceprint_id: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
    )
    speaking_duration: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        default=0.0,
    )
    joined_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    left_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
    )

    # Relationships
    meeting: Mapped["Meeting"] = relationship(
        "Meeting",
        back_populates="participants",
    )
    user: Mapped[Optional["User"]] = relationship(
        "User",
        back_populates="participations",
    )
    transcript_segments: Mapped[List["TranscriptSegment"]] = relationship(
        "TranscriptSegment",
        back_populates="participant",
    )

    __table_args__ = (
        Index("ix_participants_meeting_speaker", "meeting_id", "speaker_label"),
        Index("ix_participants_meeting_user", "meeting_id", "user_id"),
    )

    def __repr__(self) -> str:
        return f"<Participant id={self.id} name='{self.display_name}' role='{self.role}' speaker='{self.speaker_label}'>"
