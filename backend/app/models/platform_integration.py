"""
Platform Integration Domain Models for External Platform Connections & Meeting Mappings
"""

from datetime import datetime
from typing import TYPE_CHECKING, List, Optional
import uuid
from sqlalchemy import DateTime, ForeignKey, Index, JSON, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel

if TYPE_CHECKING:
    from app.models.meeting import Meeting
    from app.models.user import User


class PlatformConnection(BaseModel):
    """Represents a connection/integration between a user/tenant and an external platform provider."""

    __tablename__ = "platform_connections"

    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    provider: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
    )
    status: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="connected",
        index=True,
    )
    # Stored encrypted or masked in DB; never returned in plaintext API responses
    encrypted_access_token: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
    )
    encrypted_refresh_token: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
    )
    token_expires_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    connection_metadata: Mapped[Optional[dict]] = mapped_column(
        JSON,
        nullable=True,
        default=dict,
    )
    correlation_id: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
    )

    # Relationships
    user: Mapped["User"] = relationship(
        "User",
        backref="platform_connections",
        foreign_keys=[user_id],
    )
    meeting_mappings: Mapped[List["ExternalMeetingReference"]] = relationship(
        "ExternalMeetingReference",
        back_populates="connection",
        cascade="all, delete-orphan",
        lazy="selectin",
    )


class ExternalMeetingReference(BaseModel):
    """Maps an external platform meeting/event to an internal ABCI-MI meeting."""

    __tablename__ = "external_meeting_references"

    connection_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("platform_connections.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    meeting_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("meetings.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    external_meeting_id: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        index=True,
    )
    external_event_id: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
        index=True,
    )
    external_metadata: Mapped[Optional[dict]] = mapped_column(
        JSON,
        nullable=True,
        default=dict,
    )
    sync_status: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="synced",
    )
    correlation_id: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
    )

    # Relationships
    connection: Mapped["PlatformConnection"] = relationship(
        "PlatformConnection",
        back_populates="meeting_mappings",
        foreign_keys=[connection_id],
    )
    meeting: Mapped["Meeting"] = relationship(
        "Meeting",
        backref="external_references",
        foreign_keys=[meeting_id],
    )
