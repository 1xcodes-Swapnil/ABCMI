"""
Meeting SQLAlchemy ORM Model
Represents collaboration sessions, scheduled calls, and live meeting events.
"""

from datetime import datetime
from typing import TYPE_CHECKING, List, Optional
import uuid
from sqlalchemy import DateTime, ForeignKey, Index, Integer, JSON, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship, synonym

from app.models.base import BaseModel

if TYPE_CHECKING:
    from app.models.user import User
    from app.models.participant import Participant
    from app.models.audio import Audio
    from app.models.transcript import Transcript, TranscriptSegment
    from app.models.analytics import MeetingAnalytics
    from app.models.knowledge_object import KnowledgeObject
    from app.models.audit_log import AuditLog


class Meeting(BaseModel):
    """Meeting entity representing a collaboration session."""

    __tablename__ = "meetings"

    title: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    description: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
    )
    status: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="created",
        index=True,
    )
    language: Mapped[str] = mapped_column(
        String(10),
        nullable=False,
        default="en",
    )
    secondary_languages: Mapped[Optional[list]] = mapped_column(
        JSON,
        nullable=True,
        default=list,
    )
    host_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    scheduled_start: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    start_time = synonym("scheduled_start")
    actual_start: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    actual_end: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    duration_minutes: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
        default=60,
    )
    timezone: Mapped[Optional[str]] = mapped_column(
        String(50),
        nullable=True,
        default="UTC",
    )
    settings: Mapped[Optional[dict]] = mapped_column(
        JSON,
        nullable=True,
        default=dict,
    )
    tenant_id: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
        default="default",
        index=True,
    )

    # Relationships
    host: Mapped[Optional["User"]] = relationship(
        "User",
        back_populates="hosted_meetings",
        foreign_keys=[host_id],
    )
    participants: Mapped[List["Participant"]] = relationship(
        "Participant",
        back_populates="meeting",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    audio_recordings: Mapped[List["Audio"]] = relationship(
        "Audio",
        back_populates="meeting",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    transcript_segments: Mapped[List["TranscriptSegment"]] = relationship(
        "TranscriptSegment",
        back_populates="meeting",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    transcripts: Mapped[List["Transcript"]] = relationship(
        "Transcript",
        back_populates="meeting",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    analytics: Mapped[Optional["MeetingAnalytics"]] = relationship(
        "MeetingAnalytics",
        back_populates="meeting",
        cascade="all, delete-orphan",
        uselist=False,
        lazy="selectin",
    )
    knowledge_objects: Mapped[List["KnowledgeObject"]] = relationship(
        "KnowledgeObject",
        back_populates="meeting",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    audit_logs: Mapped[List["AuditLog"]] = relationship(
        "AuditLog",
        back_populates="meeting",
    )

    __table_args__ = (
        Index("ix_meetings_status_created_at", "status", "created_at"),
        Index("ix_meetings_host_created_at", "host_id", "created_at"),
    )

    def __repr__(self) -> str:
        return f"<Meeting id={self.id} title='{self.title}' status='{self.status}'>"
