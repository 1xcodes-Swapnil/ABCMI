"""
Pydantic Schemas for Multilingual Translation & Derived Representations
Defines request, response, filter, and regeneration schemas for translation operations.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional, Set
import uuid
from pydantic import Field, field_validator

from app.schemas.base import CoreBaseModel

SUPPORTED_LANGUAGES: Set[str] = {
    "en", "hi", "ta", "te", "kn", "ml", "bn", "mr", "gu", "pa",
    "zh", "ja", "fr", "es", "de", "ru", "ar",
}

SUPPORTED_REPRESENTATION_TYPES: Set[str] = {
    "transcript", "summary", "topic", "decision", "action_item",
    "fact", "hypothesis", "transcript_insight",
}


class TranslationRequest(CoreBaseModel):
    """Payload to trigger multilingual translation / derived representation generation."""

    target_language: str = Field(
        ...,
        description="Target ISO 639-1 language code (e.g., 'hi', 'ta', 'es', 'zh')",
    )
    source_language: Optional[str] = Field(
        default=None,
        description="Optional source language code. If omitted, uses meeting language or auto-detection.",
    )
    representation_types: Optional[List[str]] = Field(
        default=None,
        description="Optional subset of representation types to translate (e.g. ['transcript', 'decision', 'action_item'])",
    )
    source_object_ids: Optional[List[uuid.UUID]] = Field(
        default=None,
        description="Optional specific Knowledge Object or Segment UUIDs to translate",
    )
    confidence_threshold: Optional[float] = Field(
        default=0.75,
        ge=0.0,
        le=1.0,
        description="Threshold below which translations are flagged as low confidence",
    )
    correlation_id: Optional[str] = Field(
        default=None,
        description="Correlation ID for provenance and telemetry tracking",
    )

    @field_validator("target_language")
    @classmethod
    def validate_target_language(cls, v: str) -> str:
        lang = v.strip().lower()
        if lang not in SUPPORTED_LANGUAGES:
            raise ValueError(
                f"Unsupported target language '{v}'. Supported languages: {sorted(list(SUPPORTED_LANGUAGES))}"
            )
        return lang

    @field_validator("source_language")
    @classmethod
    def validate_source_language(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        lang = v.strip().lower()
        if lang not in SUPPORTED_LANGUAGES:
            raise ValueError(
                f"Unsupported source language '{v}'. Supported languages: {sorted(list(SUPPORTED_LANGUAGES))}"
            )
        return lang

    @field_validator("representation_types")
    @classmethod
    def validate_representation_types(cls, v: Optional[List[str]]) -> Optional[List[str]]:
        if v is None:
            return None
        valid_types = []
        for t in v:
            norm_t = t.strip().lower()
            if norm_t not in SUPPORTED_REPRESENTATION_TYPES:
                raise ValueError(
                    f"Unsupported representation type '{t}'. Supported types: {sorted(list(SUPPORTED_REPRESENTATION_TYPES))}"
                )
            valid_types.append(norm_t)
        return valid_types


class DerivedTranslationResponse(CoreBaseModel):
    """Frontend-safe DTO for a translated/derived representation."""

    id: uuid.UUID
    meeting_id: uuid.UUID
    tenant_id: Optional[str] = None
    source_object_id: Optional[uuid.UUID] = None
    source_segment_id: Optional[uuid.UUID] = None
    representation_type: str
    source_language: str
    target_language: str
    original_text: str
    translated_text: str
    confidence: float
    is_low_confidence: bool
    requires_verification: bool
    status: str
    source_version: int
    version: int
    speaker_label: Optional[str] = None
    start_time_ms: Optional[int] = None
    end_time_ms: Optional[int] = None
    provenance: Optional[Dict[str, Any]] = Field(default_factory=dict)
    correlation_id: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class TranslationListResponse(CoreBaseModel):
    """Paginated list response for derived translations."""

    items: List[DerivedTranslationResponse] = Field(default_factory=list)
    total: int
    limit: int
    offset: int


class TranslationRegenerateRequest(CoreBaseModel):
    """Payload to request deterministic re-translation or regeneration."""

    target_language: Optional[str] = Field(
        default=None,
        description="Optional updated target language code",
    )
    confidence_override: Optional[float] = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Optional confidence score override for verification simulation",
    )
    correlation_id: Optional[str] = Field(
        default=None,
        description="Correlation identifier",
    )

    @field_validator("target_language")
    @classmethod
    def validate_target_language(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        lang = v.strip().lower()
        if lang not in SUPPORTED_LANGUAGES:
            raise ValueError(
                f"Unsupported target language '{v}'. Supported languages: {sorted(list(SUPPORTED_LANGUAGES))}"
            )
        return lang
