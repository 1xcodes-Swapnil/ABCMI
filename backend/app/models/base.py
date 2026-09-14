"""
ABCI-MI Base SQLAlchemy ORM Models
Provides foundational mixins (UUID, Timestamps, Table naming) for domain models.
"""

from datetime import datetime, timezone
import uuid
from sqlalchemy import DateTime, func, Uuid
from sqlalchemy.orm import Mapped, declared_attr, mapped_column

from app.infrastructure.database import Base


class TableNameMixin:
    """Auto-generates snake_case table name from model class name."""

    @declared_attr.directive
    def __tablename__(cls) -> str:
        name = cls.__name__
        # Convert CamelCase to snake_case
        return "".join(["_" + c.lower() if c.isupper() else c for c in name]).lstrip("_")


class UUIDPrimaryKeyMixin:
    """Provides a UUID v4 primary key column."""

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        default=uuid.uuid4,
        index=True,
    )


class TimestampMixin:
    """Provides created_at and updated_at datetime tracking columns in UTC."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        default=lambda: datetime.now(timezone.utc),
        onupdate=func.now(),
        nullable=False,
    )


class BaseModel(Base, TableNameMixin, UUIDPrimaryKeyMixin, TimestampMixin):
    """
    Abstract base ORM model providing UUID primary key, timestamps, and auto-table naming.
    Concrete domain models will inherit from this class in subsequent phases.
    """

    __abstract__ = True
