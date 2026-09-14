"""
Project & Project-Meeting Association SQLAlchemy ORM Models (Phase 4.22)
Represents project / workspace groupings for meetings and cross-meeting intelligence.
"""

from typing import TYPE_CHECKING, List, Optional
import uuid
from sqlalchemy import ForeignKey, Index, JSON, String, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel

if TYPE_CHECKING:
    from app.models.meeting import Meeting


class Project(BaseModel):
    """Project or Workspace entity grouping multiple collaboration sessions."""

    __tablename__ = "projects"

    name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        index=True,
    )
    description: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
    )
    tenant_id: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        index=True,
    )
    status: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="active",
        index=True,
    )
    created_by: Mapped[Optional[str]] = mapped_column(
        String(150),
        nullable=True,
    )
    owner_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    settings: Mapped[Optional[dict]] = mapped_column(
        JSON,
        nullable=True,
        default=dict,
    )

    # Relationships
    project_meetings: Mapped[List["ProjectMeeting"]] = relationship(
        "ProjectMeeting",
        back_populates="project",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    __table_args__ = (
        Index("ix_projects_tenant_status", "tenant_id", "status"),
        Index("ix_projects_tenant_name", "tenant_id", "name"),
    )

    def __repr__(self) -> str:
        return f"<Project id={self.id} name='{self.name}' tenant_id='{self.tenant_id}'>"


class ProjectMeeting(BaseModel):
    """Association linking a meeting to a project/workspace."""

    __tablename__ = "project_meetings"

    project_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    meeting_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("meetings.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    tenant_id: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        default="default",
        index=True,
    )
    added_by: Mapped[Optional[str]] = mapped_column(
        String(150),
        nullable=True,
    )
    notes: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
    )

    # Relationships
    project: Mapped["Project"] = relationship(
        "Project",
        back_populates="project_meetings",
    )
    meeting: Mapped["Meeting"] = relationship(
        "Meeting",
        lazy="selectin",
    )

    __table_args__ = (
        UniqueConstraint("project_id", "meeting_id", name="uq_project_meeting"),
        Index("ix_project_meetings_tenant", "tenant_id", "project_id"),
    )

    def __repr__(self) -> str:
        return f"<ProjectMeeting project_id={self.project_id} meeting_id={self.meeting_id}>"
