"""
Live Session and Streaming Audio Chunk ORM Models
"""

from datetime import datetime
from typing import TYPE_CHECKING, List, Optional
import uuid
from sqlalchemy import DateTime, ForeignKey, Integer, JSON, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel

if TYPE_CHECKING:
    from app.models.meeting import Meeting


class LiveSession(BaseModel):
    """Represents an active or recorded live streaming session for a meeting."""

    __tablename__ = "live_sessions"

    meeting_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("meetings.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
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
    received_chunks_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )
    accepted_chunks_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )
    rejected_chunks_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )
    latest_sequence_number: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=-1,
    )
    started_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    paused_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    resumed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    stopped_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    last_activity_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    correlation_id: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
    )
    request_id: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
    )
    session_metadata: Mapped[Optional[dict]] = mapped_column(
        JSON,
        nullable=True,
        default=dict,
    )

    # Relationship
    meeting: Mapped["Meeting"] = relationship(
        "Meeting",
        backref="live_sessions",
        foreign_keys=[meeting_id],
    )
    chunks: Mapped[List["LiveAudioChunk"]] = relationship(
        "LiveAudioChunk",
        back_populates="session",
        cascade="all, delete-orphan",
        lazy="selectin",
    )


class LiveAudioChunk(BaseModel):
    """Represents an ingested audio chunk within a live session."""

    __tablename__ = "live_audio_chunks"

    session_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("live_sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    sequence_number: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        index=True,
    )
    timestamp_start_ms: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )
    timestamp_end_ms: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )
    file_path: Mapped[str] = mapped_column(
        String(512),
        nullable=False,
    )
    file_size: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )
    checksum: Mapped[Optional[str]] = mapped_column(
        String(128),
        nullable=True,
    )
    status: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="accepted",
    )

    # Relationship
    session: Mapped["LiveSession"] = relationship(
        "LiveSession",
        back_populates="chunks",
        foreign_keys=[session_id],
    )
