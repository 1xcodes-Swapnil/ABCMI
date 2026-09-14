"""
Audit Log SQLAlchemy ORM Model
Represents immutable security, administrative, and system event records in ABCI-MI.
"""

from typing import TYPE_CHECKING, Optional
import uuid
from sqlalchemy import ForeignKey, Index, JSON, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel

if TYPE_CHECKING:
    from app.models.user import User
    from app.models.meeting import Meeting
    from app.models.project import Project


class AuditLog(BaseModel):
    """
    Immutable AuditLog entity for compliance, operational auditing, and security trails.
    Tenant-scoped, append-only, and fully indexed.
    """

    __tablename__ = "audit_logs"

    tenant_id: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        default="tenant-default",
        index=True,
    )
    user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    event_type: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        default="audit.event",
        index=True,
    )
    category: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="system",
        index=True,  # admin, security, meeting, system, data_access, auth
    )
    severity: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="info",
        index=True,  # info, warning, error, critical, security
    )
    action: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        index=True,
    )
    outcome: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="success",
        index=True,  # success, failure, denied, error
    )
    resource_type: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        default="system",
        index=True,
    )
    resource_id: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
        index=True,
    )
    meeting_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid,
        ForeignKey("meetings.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    project_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid,
        ForeignKey("projects.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
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
    event_id: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
        index=True,
    )
    ip_address: Mapped[Optional[str]] = mapped_column(
        String(45),
        nullable=True,
    )
    user_agent: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
    )
    details: Mapped[Optional[dict]] = mapped_column(
        JSON,
        nullable=True,
        default=dict,
    )
    metadata_json: Mapped[Optional[dict]] = mapped_column(
        JSON,
        nullable=True,
        default=dict,
    )

    # Relationships
    user: Mapped[Optional["User"]] = relationship(
        "User",
        back_populates="audit_logs",
        lazy="selectin",
    )
    meeting: Mapped[Optional["Meeting"]] = relationship(
        "Meeting",
        back_populates="audit_logs",
        lazy="selectin",
    )
    project: Mapped[Optional["Project"]] = relationship(
        "Project",
        lazy="selectin",
    )

    __table_args__ = (
        Index("ix_audit_logs_tenant_created", "tenant_id", "created_at"),
        Index("ix_audit_logs_tenant_event_created", "tenant_id", "event_type", "created_at"),
        Index("ix_audit_logs_tenant_user_created", "tenant_id", "user_id", "created_at"),
        Index("ix_audit_logs_tenant_resource_created", "tenant_id", "resource_id", "created_at"),
        Index("ix_audit_logs_tenant_severity_created", "tenant_id", "severity", "created_at"),
        Index("ix_audit_logs_tenant_category_created", "tenant_id", "category", "created_at"),
        Index("ix_audit_logs_tenant_event_id", "tenant_id", "event_id"),
        Index("ix_audit_logs_action_created", "action", "created_at"),
        Index("ix_audit_logs_meeting_created", "meeting_id", "created_at"),
    )

    def __repr__(self) -> str:
        return f"<AuditLog id={self.id} tenant='{self.tenant_id}' action='{self.action}' outcome='{self.outcome}' resource='{self.resource_type}:{self.resource_id}'>"
