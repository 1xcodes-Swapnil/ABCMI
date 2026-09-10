"""
Knowledge Object Pydantic Schemas
Defines request, response, provenance, and filter schemas for Knowledge Objects.
"""

from enum import Enum
from typing import Any, Dict, List, Optional, Union
import uuid
from pydantic import Field

from app.models.knowledge_object import KnowledgeObjectStatus
from app.schemas.base import CoreBaseModel, TimestampSchema


class ProvenanceMetadataSchema(CoreBaseModel):
    """
    Structured provenance tracking according to SDD specifications.
    Preserves producing module, model metadata, source intervals, lineage, and processing context.
    """

    producing_module: str = Field(
        ...,
        description="Module or agent that extracted or synthesized this knowledge object",
    )
    model_name: Optional[str] = Field(
        default=None,
        description="Underlying AI/ASR model name (e.g., gemini-1.5-pro, whisper-large-v3)",
    )
    model_version: Optional[str] = Field(
        default=None,
        description="Model checkpoint or API version",
    )
    source_segments: Optional[List[Union[str, int, uuid.UUID]]] = Field(
        default_factory=list,
        description="Transcript segment IDs or indices grounding this extraction",
    )
    source_intervals: Optional[List[Dict[str, Any]]] = Field(
        default_factory=list,
        description="Temporal grounding intervals [start_ms, end_ms] in meeting audio",
    )
    lineage: Optional[Dict[str, Any]] = Field(
        default_factory=dict,
        description="Lineage metadata tracing parent objects, root derivation, and transformation reasons",
    )
    processing_metadata: Optional[Dict[str, Any]] = Field(
        default_factory=dict,
        description="Execution telemetry, latency, token metrics, or prompt tracking",
    )


class KnowledgeObjectCreate(CoreBaseModel):
    """Schema for creating a new Knowledge Object."""

    meeting_id: uuid.UUID = Field(
        ...,
        description="UUID of the associated meeting context",
    )
    object_type: str = Field(
        ...,
        max_length=50,
        description="Knowledge classification (e.g., decision, action_item, topic, summary, fact)",
    )
    title: Optional[str] = Field(
        default=None,
        max_length=255,
        description="Concise label or summary heading",
    )
    content: str = Field(
        ...,
        description="Detailed text content or structured statement",
    )
    confidence: Optional[float] = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Probabilistic confidence score bounded between 0.0 and 1.0",
    )
    status: KnowledgeObjectStatus = Field(
        default=KnowledgeObjectStatus.ACTIVE,
        description="Authoritative lifecycle status",
    )
    version: int = Field(
        default=1,
        ge=1,
        description="Version number (minimum 1)",
    )
    parent_id: Optional[uuid.UUID] = Field(
        default=None,
        description="Optional ancestor or superseded revision UUID",
    )
    provenance: Optional[Union[ProvenanceMetadataSchema, Dict[str, Any]]] = Field(
        default_factory=dict,
        description="Audit provenance metadata",
    )
    payload: Optional[Dict[str, Any]] = Field(
        default_factory=dict,
        description="Type-specific structured payload (assignee, priority, alternatives, etc.)",
    )
    qdrant_point_id: Optional[str] = Field(
        default=None,
        max_length=255,
        description="Deterministic Qdrant vector point ID reference",
    )


class KnowledgeObjectUpdate(CoreBaseModel):
    """Schema for updating fields of a Knowledge Object or staging a new version."""

    title: Optional[str] = Field(
        default=None,
        max_length=255,
    )
    content: Optional[str] = Field(
        default=None,
    )
    confidence: Optional[float] = Field(
        default=None,
        ge=0.0,
        le=1.0,
    )
    status: Optional[KnowledgeObjectStatus] = Field(
        default=None,
    )
    provenance: Optional[Union[ProvenanceMetadataSchema, Dict[str, Any]]] = Field(
        default=None,
    )
    payload: Optional[Dict[str, Any]] = Field(
        default=None,
    )
    qdrant_point_id: Optional[str] = Field(
        default=None,
        max_length=255,
    )


class KnowledgeObjectResponse(TimestampSchema):
    """Authoritative API response schema for a Knowledge Object."""

    id: uuid.UUID
    meeting_id: uuid.UUID
    object_type: str
    title: Optional[str] = None
    content: str
    confidence: Optional[float] = None
    status: str
    version: int
    parent_id: Optional[uuid.UUID] = None
    provenance: Optional[Dict[str, Any]] = None
    payload: Optional[Dict[str, Any]] = None
    qdrant_point_id: Optional[str] = None


class KnowledgeObjectFilter(CoreBaseModel):
    """Criteria filter for querying Knowledge Objects."""

    meeting_id: Optional[uuid.UUID] = None
    object_type: Optional[str] = None
    status: Optional[KnowledgeObjectStatus] = None
    parent_id: Optional[uuid.UUID] = None
    min_confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    max_confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    skip: int = Field(default=0, ge=0)
    limit: int = Field(default=100, ge=1, le=1000)
