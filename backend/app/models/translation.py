"""
Derived Translation SQLAlchemy ORM Model
Stores translated and derived representations of transcripts and knowledge objects
while preserving canonical authoritative source content, timestamps, speaker labels,
confidence scores, and provenance lineage.
"""

from typing import TYPE_CHECKING, Optional
import uuid
from sqlalchemy import (
    BigInteger,
    Boolean,
    Float,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel

if TYPE_CHECKING:
    from app.models.knowledge_object import KnowledgeObject
    from app.models.meeting import Meeting
    from app.models.transcript import TranscriptSegment


class DerivedTranslation(BaseModel):
    """
    Represents a translated or derived representation of an authoritative knowledge object
    or transcript utterance. Never mutates or overwrites source canonical records.
    """

    __tablename__ = "derived_translations"

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
    source_object_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid,
        ForeignKey("knowledge_objects.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    source_segment_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid,
        ForeignKey("transcript_segments.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    representation_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
    )
    source_language: Mapped[str] = mapped_column(
        String(10),
        nullable=False,
    )
    target_language: Mapped[str] = mapped_column(
        String(10),
        nullable=False,
        index=True,
    )
    original_text: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    translated_text: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    confidence: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        default=1.0,
    )
    is_low_confidence: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
    )
    requires_verification: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
    )
    status: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="active",
        index=True,
    )
    source_version: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1,
    )
    version: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1,
    )
    speaker_label: Mapped[Optional[str]] = mapped_column(
        String(50),
        nullable=True,
    )
    start_time_ms: Mapped[Optional[int]] = mapped_column(
        BigInteger,
        nullable=True,
    )
    end_time_ms: Mapped[Optional[int]] = mapped_column(
        BigInteger,
        nullable=True,
    )
    provenance: Mapped[Optional[dict]] = mapped_column(
        JSON,
        nullable=True,
        default=dict,
    )
    correlation_id: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
    )

    # Relationships
    meeting: Mapped["Meeting"] = relationship(
        "Meeting",
        backref="derived_translations",
        foreign_keys=[meeting_id],
    )
    source_object: Mapped[Optional["KnowledgeObject"]] = relationship(
        "KnowledgeObject",
        backref="derived_translations",
        foreign_keys=[source_object_id],
    )
    source_segment: Mapped[Optional["TranscriptSegment"]] = relationship(
        "TranscriptSegment",
        backref="derived_translations",
        foreign_keys=[source_segment_id],
    )

    __table_args__ = (
        Index(
            "ix_derived_translations_meeting_target_type",
            "meeting_id",
            "target_language",
            "representation_type",
        ),
        Index(
            "ix_derived_translations_idempotency_lookup",
            "meeting_id",
            "source_object_id",
            "source_segment_id",
            "source_language",
            "target_language",
            "representation_type",
            "source_version",
        ),
    )
