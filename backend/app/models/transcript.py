"""
Transcript & Transcript Segment SQLAlchemy ORM Models
Represents streaming timed speech segments (TranscriptSegment) and canonical compiled transcripts (Transcript).
"""

from typing import TYPE_CHECKING, Optional
import uuid
from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Float,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship, synonym

from app.models.base import BaseModel

if TYPE_CHECKING:
    from app.models.meeting import Meeting
    from app.models.participant import Participant


class TranscriptSegment(BaseModel):
    """TranscriptSegment entity representing an individual timed utterance in a meeting."""

    __tablename__ = "transcript_segments"

    meeting_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("meetings.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    participant_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid,
        ForeignKey("participants.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    speaker_label: Mapped[Optional[str]] = mapped_column(
        String(50),
        nullable=True,
    )
    start_time_ms: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
    )
    end_time_ms: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
    )
    language: Mapped[str] = mapped_column(
        String(10),
        nullable=False,
        default="en",
    )
    original_text: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    text = synonym("original_text")
    translated_text: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
    )
    confidence: Mapped[Optional[float]] = mapped_column(
        Float,
        nullable=True,
    )
    is_final: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
    )
    sequence_number: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        index=True,
    )
    words_payload: Mapped[Optional[list]] = mapped_column(
        JSON,
        nullable=True,
        default=list,
    )

    # Relationships
    meeting: Mapped["Meeting"] = relationship(
        "Meeting",
        back_populates="transcript_segments",
    )
    participant: Mapped[Optional["Participant"]] = relationship(
        "Participant",
        back_populates="transcript_segments",
    )

    __table_args__ = (
        CheckConstraint("end_time_ms >= start_time_ms", name="ck_transcript_segments_time_range"),
        Index("ix_transcript_segments_meeting_seq", "meeting_id", "sequence_number"),
        Index("ix_transcript_segments_meeting_time", "meeting_id", "start_time_ms"),
    )

    def __repr__(self) -> str:
        return (
            f"<TranscriptSegment id={self.id} meeting_id={self.meeting_id} "
            f"seq={self.sequence_number} speaker='{self.speaker_label}'>"
        )


class Transcript(BaseModel):
    """Canonical/versioned full transcript entity for meeting sessions."""

    __tablename__ = "transcripts"

    meeting_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("meetings.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    version: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1,
    )
    language: Mapped[str] = mapped_column(
        String(10),
        nullable=False,
        default="en",
    )
    detected_language = synonym("language")
    full_text: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    is_final: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
    )
    confidence_score: Mapped[Optional[float]] = mapped_column(
        Float,
        nullable=True,
    )
    word_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )
    provenance: Mapped[Optional[dict]] = mapped_column(
        JSON,
        nullable=True,
        default=dict,
    )

    # Relationships
    meeting: Mapped["Meeting"] = relationship(
        "Meeting",
        back_populates="transcripts",
    )

    __table_args__ = (
        Index("ix_transcripts_meeting_version", "meeting_id", "version"),
    )

    def __repr__(self) -> str:
        return f"<Transcript id={self.id} meeting_id={self.meeting_id} v={self.version} is_final={self.is_final}>"
