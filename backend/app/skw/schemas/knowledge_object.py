"""
SKW Pydantic Schemas
Provides robust validation for Knowledge Object creation, updates, provenance, metadata, and responses.
"""

from __future__ import annotations
from datetime import datetime

from typing import Any, Dict, List, Optional, Union
import uuid
from pydantic import Field, field_validator

from app.schemas.base import CoreBaseModel, TimestampSchema
from app.skw.models.knowledge_object import SKWLifecycleState, SKWKnowledgeType


class KnowledgeProvenance(CoreBaseModel):
    """Provenance metadata tracking source extraction, models, intervals, and lineage."""
    producing_module: str = Field(
        ...,
        min_length=1,
        description="Source producer module or agent (e.g. ASRModule, DialogClassifier)",
    )
    model_name: Optional[str] = Field(default=None, description="AI model name used")
    model_version: Optional[str] = Field(default=None, description="AI model version")
    source_segments: Optional[List[Union[str, int, uuid.UUID]]] = Field(default_factory=list)
    source_intervals: Optional[List[Dict[str, Any]]] = Field(default_factory=list)
    lineage: Optional[Dict[str, Any]] = Field(default_factory=dict)
    processing_metadata: Optional[Dict[str, Any]] = Field(default_factory=dict)


class KnowledgeMetadata(CoreBaseModel):
    """Contextual and semantic metadata attached to Knowledge Objects."""
    tags: Optional[List[str]] = Field(default_factory=list)
    importance_score: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    language: Optional[str] = Field(default="en", max_length=10)
    custom_attributes: Optional[Dict[str, Any]] = Field(default_factory=dict)


class KnowledgeObjectCreate(CoreBaseModel):
    """Validation schema for creating a new Knowledge Object in SKW."""
    meeting_id: uuid.UUID = Field(..., description="UUID of the meeting")
    object_type: str = Field(
        ...,
        min_length=1,
        max_length=50,
        description="Knowledge classification (e.g. decision, action_item, topic)",
    )
    source_module: str = Field(
        ...,
        min_length=1,
        max_length=100,
        description="Module producing the knowledge object",
    )
    content: str = Field(..., min_length=1, description="Primary textual content")
    title: Optional[str] = Field(default=None, max_length=255)
    confidence_score: Optional[float] = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Confidence score between 0.0 and 1.0",
    )
    version: int = Field(default=1, ge=1, description="Version number >= 1")
    lifecycle_state: SKWLifecycleState = Field(
        default=SKWLifecycleState.CREATED,
        description="SKW lifecycle state",
    )
    provenance: Optional[KnowledgeProvenance] = Field(default=None)
    metadata: Optional[KnowledgeMetadata] = Field(default=None)
    payload: Optional[Dict[str, Any]] = Field(default_factory=dict)

    @field_validator("object_type", mode="before")
    def case_insensitive_object_type(cls, v):
        if not v or not str(v).strip():
            raise ValueError("object_type cannot be empty")
        return str(v).strip().lower()

    @field_validator("source_module", mode="before")
    def validate_source_module(cls, v):
        if not v or not str(v).strip():
            raise ValueError("source_module cannot be empty")
        return str(v).strip()


class KnowledgeObjectUpdate(CoreBaseModel):
    """Validation schema for updating a Knowledge Object."""
    title: Optional[str] = Field(default=None, max_length=255)
    content: Optional[str] = Field(default=None)
    confidence_score: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    lifecycle_state: Optional[SKWLifecycleState] = Field(default=None)
    provenance: Optional[KnowledgeProvenance] = Field(default=None)
    metadata: Optional[KnowledgeMetadata] = Field(default=None)
    payload: Optional[Dict[str, Any]] = Field(default=None)


class KnowledgeObjectResponse(TimestampSchema):
    """API response schema for a Knowledge Object."""
    knowledge_id: uuid.UUID
    meeting_id: uuid.UUID
    object_type: str
    source_module: str
    content: str
    title: Optional[str] = None
    confidence_score: Optional[float] = None
    version: int
    lifecycle_state: str
    provenance: Optional[Dict[str, Any]] = None
    metadata: Optional[Dict[str, Any]] = None
    payload: Optional[Dict[str, Any]] = None
