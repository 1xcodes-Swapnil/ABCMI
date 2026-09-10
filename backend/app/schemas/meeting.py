"""
Meeting Intake & Processing Lifecycle Schemas
Defines request and response schemas for meeting creation, audio upload, processing lifecycle,
participant management, and status tracking.
"""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
import uuid
from pydantic import Field

from app.schemas.base import CoreBaseModel


class MeetingStatus(str, Enum):
    """Authoritative meeting processing lifecycle states."""

    CREATED = "created"
    PROCESSING_REQUESTED = "processing_requested"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class ParticipantCreate(CoreBaseModel):
    """Participant creation schema for meeting intake."""

    display_name: str = Field(..., description="Full display name of the participant")
    email: Optional[str] = Field(default=None, description="Optional email address")
    role: str = Field(default="attendee", description="Meeting role (e.g., host, speaker, attendee)")
    speaker_label: Optional[str] = Field(default=None, description="Assigned speaker label (e.g. Speaker_1)")
    voiceprint_id: Optional[str] = Field(default=None, description="Voiceprint identifier")


class ParticipantResponse(CoreBaseModel):
    """Participant details response schema."""

    id: uuid.UUID
    meeting_id: uuid.UUID
    user_id: Optional[uuid.UUID] = None
    display_name: str
    email: Optional[str] = None
    role: str
    speaker_label: Optional[str] = None
    voiceprint_id: Optional[str] = None
    speaking_duration: float = 0.0
    created_at: Optional[datetime] = None


class AudioResponse(CoreBaseModel):
    """Audio artifact metadata response schema."""

    id: uuid.UUID
    meeting_id: uuid.UUID
    file_path: str
    file_name: Optional[str] = None
    file_size_bytes: Optional[int] = None
    duration_seconds: Optional[float] = None
    format: str = "wav"
    sample_rate: int = 16000
    channels: int = 1
    status: str = "uploaded"
    created_at: Optional[datetime] = None


class MeetingCreate(CoreBaseModel):
    """Meeting creation payload schema."""

    title: str = Field(..., min_length=1, max_length=255, description="Meeting title")
    description: Optional[str] = Field(default=None, description="Optional meeting description")
    language: str = Field(default="en", description="Primary meeting language code")
    secondary_languages: Optional[List[str]] = Field(default_factory=list, description="Secondary spoken language codes")
    host_id: Optional[uuid.UUID] = Field(default=None, description="Host user UUID")
    scheduled_start: Optional[datetime] = Field(default=None, description="Scheduled start timestamp")
    duration_minutes: Optional[int] = Field(default=60, description="Scheduled meeting duration in minutes")
    timezone: Optional[str] = Field(default="UTC", description="Timezone identifier e.g. UTC, America/New_York")
    settings: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Meeting and tenant-scoped settings")
    participants: Optional[List[ParticipantCreate]] = Field(default_factory=list, description="Initial participants list")
    correlation_id: Optional[str] = Field(default=None, description="Distributed tracing correlation ID")


class MeetingScheduleRequest(CoreBaseModel):
    """Meeting scheduling payload."""
    scheduled_start: datetime = Field(..., description="Timezone-aware scheduled start timestamp")
    duration_minutes: Optional[int] = Field(default=60, description="Duration in minutes")
    timezone: Optional[str] = Field(default="UTC", description="Timezone identifier")


class MeetingRescheduleRequest(CoreBaseModel):
    """Meeting rescheduling payload."""
    scheduled_start: datetime = Field(..., description="New timezone-aware scheduled start timestamp")
    duration_minutes: Optional[int] = Field(default=None, description="Updated duration in minutes")
    timezone: Optional[str] = Field(default=None, description="Updated timezone identifier")


class MeetingCancelRequest(CoreBaseModel):
    """Meeting cancellation payload."""
    reason: Optional[str] = Field(default=None, description="Optional cancellation reason")


class MeetingProcessingRequest(CoreBaseModel):
    """Payload to trigger ACE processing for a meeting intake session."""

    meeting_id: Optional[uuid.UUID] = Field(default=None, description="Meeting UUID if passed in body")
    request_id: uuid.UUID = Field(default_factory=uuid.uuid4, description="Unique processing request UUID")
    correlation_id: Optional[str] = Field(default=None, description="Distributed correlation ID")
    enable_analytics: bool = Field(default=True, description="Enable meeting analytics generation")
    enable_memory: bool = Field(default=True, description="Enable canonical memory indexing in SKW")
    force_reprocess: bool = Field(default=False, description="Force re-processing if completed or failed")


class MeetingResponse(CoreBaseModel):
    """Comprehensive meeting response schema."""

    id: uuid.UUID
    title: str
    description: Optional[str] = None
    status: str = "created"
    language: str = "en"
    secondary_languages: Optional[List[str]] = Field(default_factory=list)
    host_id: Optional[uuid.UUID] = None
    scheduled_start: Optional[datetime] = None
    actual_start: Optional[datetime] = None
    actual_end: Optional[datetime] = None
    duration_minutes: Optional[int] = 60
    timezone: Optional[str] = "UTC"
    settings: Optional[Dict[str, Any]] = Field(default_factory=dict)
    audio_recordings: List[AudioResponse] = Field(default_factory=list)
    participants: List[ParticipantResponse] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class MeetingProcessingResponse(CoreBaseModel):
    """Response returned upon initiating meeting processing lifecycle."""

    request_id: uuid.UUID
    meeting_id: uuid.UUID
    correlation_id: Optional[str] = None
    status: str
    message: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)
