"""
Knowledge Object SQLAlchemy ORM Model
Persistence foundation for Knowledge Objects (Decisions, Action Items, Topics, Facts, Summaries).
Prepares schema for future versioning and provenance tracking without implementing business logic.
"""

from enum import Enum
from typing import TYPE_CHECKING, List, Optional
import uuid
from sqlalchemy import CheckConstraint, Float, ForeignKey, Index, Integer, JSON, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel

if TYPE_CHECKING:
    from app.models.meeting import Meeting


class KnowledgeObjectStatus(str, Enum):
    """Authoritative SDD-defined lifecycle states for Knowledge Objects."""

    DRAFT = "draft"
    ACTIVE = "active"
    VALIDATED = "validated"
    SUPERSEDED = "superseded"
    REJECTED = "rejected"
    DEPRECATED = "deprecated"


class KnowledgeObject(BaseModel):
    """
    KnowledgeObject entity representing structured collaboration insights.
    Stores extracted knowledge artifacts linked to meetings with version/provenance pointers.
    """

    __tablename__ = "knowledge_objects"

    meeting_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("meetings.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    object_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
    )
    source_module: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
        index=True,
    )
    title: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
    )
    content: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    confidence: Mapped[Optional[float]] = mapped_column(
        Float,
        nullable=True,
    )
    status: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default=KnowledgeObjectStatus.ACTIVE.value,
        index=True,
    )
    version: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1,
    )
    parent_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid,
        ForeignKey("knowledge_objects.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    provenance: Mapped[Optional[dict]] = mapped_column(
        JSON,
        nullable=True,
        default=dict,
    )
    payload: Mapped[Optional[dict]] = mapped_column(
        JSON,
        nullable=True,
        default=dict,
    )
    qdrant_point_id: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
    )

    @property
    def knowledge_id(self) -> uuid.UUID:
        return self.id

    @knowledge_id.setter
    def knowledge_id(self, value: uuid.UUID) -> None:
        self.id = value

    @property
    def confidence_score(self) -> Optional[float]:
        return self.confidence

    @confidence_score.setter
    def confidence_score(self, value: Optional[float]) -> None:
        self.confidence = value

    @property
    def lifecycle_state(self) -> str:
        return self.status

    @lifecycle_state.setter
    def lifecycle_state(self, value: str) -> None:
        self.status = value

    # Relationships
    meeting: Mapped["Meeting"] = relationship(
        "Meeting",
        back_populates="knowledge_objects",
    )
    parent: Mapped[Optional["KnowledgeObject"]] = relationship(
        "KnowledgeObject",
        remote_side="KnowledgeObject.id",
        backref="derived_objects",
    )

    __table_args__ = (
        Index("ix_knowledge_objects_meeting_type", "meeting_id", "object_type"),
        Index("ix_knowledge_objects_meeting_status_type", "meeting_id", "status", "object_type"),
        Index("ix_knowledge_objects_qdrant_point_id", "qdrant_point_id"),
        CheckConstraint(
            "confidence IS NULL OR (confidence >= 0.0 AND confidence <= 1.0)",
            name="ck_knowledge_objects_confidence_range",
        ),
        CheckConstraint(
            "version >= 1",
            name="ck_knowledge_objects_version_positive",
        ),
    )

    def __repr__(self) -> str:
        return (
            f"<KnowledgeObject id={self.id} type='{self.object_type}' "
            f"meeting_id={self.meeting_id} v={self.version}>"
        )
