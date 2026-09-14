"""
User SQLAlchemy ORM Model
Represents registered users, hosts, and team members in ABCI-MI.
"""

from typing import TYPE_CHECKING, List, Optional
from sqlalchemy import JSON, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel

if TYPE_CHECKING:
    from app.models.meeting import Meeting
    from app.models.participant import Participant
    from app.models.audit_log import AuditLog


class User(BaseModel):
    """User entity representing authenticated account holders and meeting hosts."""

    __tablename__ = "users"

    email: Mapped[str] = mapped_column(
        String(255),
        unique=True,
        nullable=False,
        index=True,
    )
    full_name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    role: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="member",
    )
    status: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="active",
        index=True,
    )
    preferences: Mapped[Optional[dict]] = mapped_column(
        JSON,
        nullable=True,
        default=dict,
    )

    @property
    def is_active(self) -> bool:
        """Determines active state from authoritative status field."""
        return self.status == "active"

    # Relationships
    hosted_meetings: Mapped[List["Meeting"]] = relationship(
        "Meeting",
        back_populates="host",
        foreign_keys="Meeting.host_id",
    )
    participations: Mapped[List["Participant"]] = relationship(
        "Participant",
        back_populates="user",
    )
    audit_logs: Mapped[List["AuditLog"]] = relationship(
        "AuditLog",
        back_populates="user",
    )

    def __repr__(self) -> str:
        return f"<User id={self.id} email='{self.email}' role='{self.role}' status='{self.status}'>"
