"""
Audio SQLAlchemy ORM Model
Represents raw, recorded, and processed audio artifacts for meeting sessions.
"""

from typing import TYPE_CHECKING, Optional
import uuid
from sqlalchemy import BigInteger, Float, ForeignKey, Integer, JSON, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel

if TYPE_CHECKING:
    from app.models.meeting import Meeting


class Audio(BaseModel):
    """Audio entity storing meeting audio recording metadata and storage references."""

    __tablename__ = "audio_recordings"

    meeting_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("meetings.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    file_path: Mapped[str] = mapped_column(
        String(512),
        nullable=False,
    )
    file_name: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
    )
    file_size_bytes: Mapped[Optional[int]] = mapped_column(
        BigInteger,
        nullable=True,
    )
    duration_seconds: Mapped[Optional[float]] = mapped_column(
        Float,
        nullable=True,
    )
    format: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="wav",
    )
    sample_rate: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=16000,
    )
    channels: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1,
    )
    status: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="uploaded",
        index=True,
    )
    meta_data: Mapped[Optional[dict]] = mapped_column(
        JSON,
        nullable=True,
        default=dict,
    )

    # Relationships
    meeting: Mapped["Meeting"] = relationship(
        "Meeting",
        back_populates="audio_recordings",
    )

    def __repr__(self) -> str:
        return f"<Audio id={self.id} meeting_id={self.meeting_id} format='{self.format}' status='{self.status}'>"
