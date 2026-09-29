"""
Notification SQLAlchemy ORM Model (Phase 4.24)
"""

from datetime import datetime
from typing import TYPE_CHECKING, Optional
import uuid
from sqlalchemy import Boolean, DateTime, ForeignKey, Index, JSON, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel

if TYPE_CHECKING:
    from app.models.user import User
    from app.models.meeting import Meeting
    from app.models.project import Project


class Notification(BaseModel):
    """Notification entity storing user and tenant notifications."""

    __tablename__ = "notifications"

    tenant_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True
    )
    event_type: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    category: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    severity: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    is_read: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    meeting_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid, ForeignKey("meetings.id", ondelete="SET NULL"), nullable=True, index=True
    )
    project_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid, ForeignKey("projects.id", ondelete="SET NULL"), nullable=True, index=True
    )
    resource_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    correlation_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, index=True)
    event_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, index=True)
    read_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    metadata_json: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True, default=dict)

    user: Mapped[Optional["User"]] = relationship("User", lazy="selectin")
    meeting: Mapped[Optional["Meeting"]] = relationship("Meeting", lazy="selectin")
    project: Mapped[Optional["Project"]] = relationship("Project", lazy="selectin")

    __table_args__ = (
        Index("ix_notifications_tenant_user_read", "tenant_id", "user_id", "is_read"),
        Index("ix_notifications_tenant_category_created", "tenant_id", "category", "created_at"),
        Index("ix_notifications_event_id_unique", "tenant_id", "event_id"),
        Index(
            "ix_notifications_retention_cleanup",
            "tenant_id", "is_read", "category", "created_at",
        ),
    )

    def __repr__(self) -> str:
        return (
            f"<Notification id={self.id} tenant='{self.tenant_id}' "
            f"category='{self.category}' severity='{self.severity}' is_read={self.is_read}>"
        )
