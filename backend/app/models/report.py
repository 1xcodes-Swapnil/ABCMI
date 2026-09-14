"""
Meeting Report SQLAlchemy ORM Model
Stores metadata, storage paths, checksums, versions, and provenance for generated meeting reports.
"""

from typing import TYPE_CHECKING, Optional
import uuid
from sqlalchemy import ForeignKey, Integer, JSON, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel

if TYPE_CHECKING:
    from app.models.meeting import Meeting
    from app.models.user import User


class MeetingReport(BaseModel):
    """Represents a generated meeting report entity."""

    __tablename__ = "meeting_reports"

    meeting_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("meetings.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    tenant_id: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
        index=True,
    )
    report_type: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        default="comprehensive",
    )
    status: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="generated",
        index=True,
    )
    format: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="json",
    )
    storage_path: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
    )
    file_size: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )
    checksum: Mapped[Optional[str]] = mapped_column(
        String(64),
        nullable=True,
    )
    generated_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    correlation_id: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
    )
    version: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1,
    )
    provenance: Mapped[Optional[dict]] = mapped_column(
        JSON,
        nullable=True,
        default=dict,
    )

    # Relationships
    meeting: Mapped["Meeting"] = relationship(
        "Meeting",
        backref="reports",
        foreign_keys=[meeting_id],
    )
    generator: Mapped[Optional["User"]] = relationship(
        "User",
        foreign_keys=[generated_by],
    )
