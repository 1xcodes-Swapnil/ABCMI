"""
QueryRecord SQLAlchemy ORM Model (Phase 4.23)
Stores immutable metadata and results for natural-language Ask ABCI-MI queries.
Provides tenant-scoped auditability, meeting query history, and request idempotency.
"""

from datetime import datetime
from typing import TYPE_CHECKING, Any, Dict, List, Optional
import uuid
from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, JSON, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel

if TYPE_CHECKING:
    from app.models.user import User
    from app.models.meeting import Meeting
    from app.models.project import Project


class QueryRecord(BaseModel):
    """
    QueryRecord entity storing executed natural-language queries,
    synthesized answers, confidence metrics, and source attributions.
    """

    __tablename__ = "query_records"

    tenant_id: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        index=True,
    )
    user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    query: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    scope: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="meeting",
        index=True,  # meeting, project, cross_meeting
    )
    meeting_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid,
        ForeignKey("meetings.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    project_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid,
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    answer: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    status: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="answered",
        index=True,  # answered, insufficient_context, requires_verification, failed
    )
    confidence: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        default=0.8,
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
    search_mode: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="hybrid",
    )
    sources: Mapped[List[Dict[str, Any]]] = mapped_column(
        JSON,
        nullable=False,
        default=list,
    )
    source_meetings: Mapped[List[Dict[str, Any]]] = mapped_column(
        JSON,
        nullable=False,
        default=list,
    )
    source_projects: Mapped[List[Dict[str, Any]]] = mapped_column(
        JSON,
        nullable=False,
        default=list,
    )
    provenance: Mapped[Dict[str, Any]] = mapped_column(
        JSON,
        nullable=False,
        default=dict,
    )
    correlation_id: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
        index=True,
    )
    request_id: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
        index=True,
    )

    # Relationships
    user: Mapped[Optional["User"]] = relationship(
        "User",
        lazy="selectin",
    )
    meeting: Mapped[Optional["Meeting"]] = relationship(
        "Meeting",
        lazy="selectin",
    )
    project: Mapped[Optional["Project"]] = relationship(
        "Project",
        lazy="selectin",
    )

    __table_args__ = (
        Index("ix_query_records_tenant_created", "tenant_id", "created_at"),
        Index("ix_query_records_meeting_created", "meeting_id", "created_at"),
        Index("ix_query_records_project_created", "project_id", "created_at"),
        Index("ix_query_records_user_created", "user_id", "created_at"),
        Index("ix_query_records_tenant_correlation", "tenant_id", "correlation_id"),
    )
