"""
System Configuration SQLAlchemy ORM Model
Represents dynamic application configurations, LLM/ASR parameters, and system feature flags.
"""

from typing import Optional
from sqlalchemy import Boolean, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import BaseModel


class SystemConfiguration(BaseModel):
    """SystemConfiguration entity representing dynamic system settings and feature toggles."""

    __tablename__ = "system_configurations"

    key: Mapped[str] = mapped_column(
        String(100),
        unique=True,
        nullable=False,
        index=True,
    )
    value: Mapped[dict] = mapped_column(
        JSON,
        nullable=False,
    )
    description: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
    )
    category: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="general",
        index=True,
    )
    is_secret: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
    )

    def __repr__(self) -> str:
        return f"<SystemConfiguration key='{self.key}' category='{self.category}'>"
