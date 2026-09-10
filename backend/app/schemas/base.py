"""
ABCI-MI Base Pydantic Schemas
Provides base models with common configuration, serialization patterns, and API response envelopes.
"""

from datetime import datetime
from typing import Any, Generic, Optional, TypeVar
from pydantic import BaseModel, ConfigDict, Field

T = TypeVar("T")


class CoreBaseModel(BaseModel):
    """Base Pydantic schema for all request/response models."""

    model_config = ConfigDict(
        from_attributes=True,
        populate_by_name=True,
        use_enum_values=True,
        validate_assignment=True,
    )


class TimestampSchema(CoreBaseModel):
    """Schema mixin for entities with created_at and updated_at timestamps."""

    created_at: datetime = Field(default_factory=datetime.utcnow, description="Record creation timestamp")
    updated_at: Optional[datetime] = Field(default=None, description="Record last modification timestamp")


class StandardResponse(CoreBaseModel, Generic[T]):
    """Standard API envelope for successful responses."""

    success: bool = Field(default=True, description="Indicates if the operation succeeded")
    data: Optional[T] = Field(default=None, description="Payload data")
    message: Optional[str] = Field(default=None, description="Optional informational message")


class ErrorDetail(CoreBaseModel):
    """Standard error description."""

    code: str = Field(..., description="Unique machine-readable error code")
    message: str = Field(..., description="Human-readable error explanation")
    details: Optional[Any] = Field(default=None, description="Detailed diagnostic or validation errors")


class ErrorResponse(CoreBaseModel):
    """Standard API envelope for error responses."""

    success: bool = Field(default=False, description="Always false for error responses")
    error: ErrorDetail = Field(..., description="Detailed error object")
