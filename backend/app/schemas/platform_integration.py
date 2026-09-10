"""
Pydantic Schemas for Platform Integrations & External Meeting Synchronization
Includes Live Google Meet & Microsoft Teams Real-time Ingestion DTOs
"""

from datetime import datetime
from typing import Any, Dict, List, Optional
import uuid
from pydantic import Field

from app.schemas.base import CoreBaseModel


class PlatformConnectRequest(CoreBaseModel):
    """Payload to connect or authorize an external platform provider."""
    auth_code: Optional[str] = Field(default=None, description="OAuth authorization code or mock token")
    credentials_metadata: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Provider specific configuration")
    correlation_id: Optional[str] = Field(default=None, description="Correlation identifier")


class ExternalMeetingPayload(CoreBaseModel):
    """Normalized external meeting payload from a platform provider."""
    external_meeting_id: str = Field(..., description="External platform meeting ID")
    external_event_id: Optional[str] = Field(default=None, description="Calendar event ID if applicable")
    title: str = Field(..., description="Meeting title")
    description: Optional[str] = Field(default=None, description="Meeting description")
    scheduled_start: datetime = Field(..., description="Timezone-aware start time")
    duration_minutes: Optional[int] = Field(default=60, description="Duration in minutes")
    timezone: Optional[str] = Field(default="UTC", description="Timezone identifier")
    external_metadata: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Raw provider metadata")


class ExternalMeetingReferenceResponse(CoreBaseModel):
    """Frontend-safe DTO for external meeting mapping reference."""
    id: uuid.UUID
    connection_id: uuid.UUID
    meeting_id: uuid.UUID
    external_meeting_id: str
    external_event_id: Optional[str] = None
    sync_status: str
    external_metadata: Optional[Dict[str, Any]] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class PlatformConnectionResponse(CoreBaseModel):
    """Frontend-safe DTO for platform connection (excludes sensitive tokens)."""
    id: uuid.UUID
    user_id: uuid.UUID
    provider: str
    status: str
    token_expires_at: Optional[datetime] = None
    connection_metadata: Optional[Dict[str, Any]] = Field(default_factory=dict)
    correlation_id: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class PlatformWebhookEventPayload(CoreBaseModel):
    """Normalized inbound webhook/event payload from external platform."""
    provider: str = Field(..., description="Platform provider name e.g. zoom, teams, google_meet")
    event_type: str = Field(..., description="Event type e.g. meeting.scheduled, meeting.updated, meeting.cancelled")
    external_meeting_id: str = Field(..., description="External meeting ID")
    external_event_id: Optional[str] = Field(default=None, description="External event ID")
    timestamp: datetime = Field(..., description="Event timestamp")
    payload: Dict[str, Any] = Field(default_factory=dict, description="Event payload data")
    correlation_id: Optional[str] = Field(default=None, description="Correlation identifier")


# -----------------------------------------------------------------------------
# Live Meeting Streaming & Observation DTOs (Google Meet / Microsoft Teams)
# -----------------------------------------------------------------------------

class LiveMeetingJoinRequest(CoreBaseModel):
    """Request payload to join or observe an active live meeting on Google Meet or MS Teams."""
    external_meeting_id: Optional[str] = Field(default=None, description="External meeting code or ID (e.g. abc-defg-hij)")
    meeting_url: Optional[str] = Field(default=None, description="Direct URL to meeting space or call (e.g. https://meet.google.com/abc-defg-hij)")
    stream_mode: str = Field(default="hybrid", description="Ingestion mode: 'audio_stream', 'live_captions', or 'hybrid'")
    language: str = Field(default="en", description="Expected primary spoken language (e.g. 'en', 'hi')")
    auto_record: bool = Field(default=True, description="Whether to capture raw audio chunks into storage")
    observer_name: Optional[str] = Field(default="ABCI-MI Observer", description="Display name for bot or add-on observer")
    correlation_id: Optional[str] = Field(default=None, description="Correlation tracking identifier")


class LiveMeetingJoinByUrlRequest(CoreBaseModel):
    """Convenience payload for initiating live ingestion directly from a real meeting URL."""
    meeting_url: str = Field(..., description="Direct Google Meet or Teams meeting URL")
    stream_mode: str = Field(default="hybrid", description="Ingestion mode: 'audio_stream', 'live_captions', or 'hybrid'")
    language: str = Field(default="en", description="Expected spoken language")
    auto_record: bool = Field(default=True, description="Whether to capture raw audio")
    observer_name: Optional[str] = Field(default="ABCI-MI Observer", description="Observer display name")
    correlation_id: Optional[str] = Field(default=None, description="Correlation tracking identifier")


class LiveTranscriptIngestRequest(CoreBaseModel):
    """Standardized payload for ingesting real-time transcript utterances from live provider."""
    segment_id: Optional[str] = Field(default=None, description="Unique segment UUID if provided by provider")
    external_meeting_id: str = Field(..., description="Provider meeting ID or conference code")
    session_id: Optional[str] = Field(default=None, description="Active live session ID")
    speaker_id: Optional[str] = Field(default=None, description="Provider participant identifier")
    speaker_name: Optional[str] = Field(default=None, description="Participant display name from provider")
    speaker_email: Optional[str] = Field(default=None, description="Participant email from provider")
    text: str = Field(..., description="Utterance transcript text")
    language: str = Field(default="en", description="Spoken language code (e.g. en, hi, fr)")
    start_time_ms: int = Field(..., ge=0, description="Start offset timestamp in milliseconds")
    end_time_ms: int = Field(..., ge=0, description="End offset timestamp in milliseconds")
    confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0, description="Real provider confidence score (None if not provided)")
    sequence: int = Field(default=0, description="Monotonic sequence number")
    is_final: bool = Field(default=True, description="Whether the transcript segment is finalized")
    source: str = Field(default="provider_transcript", description="Source: 'provider_transcript', 'live_captions', 'live_asr'")
    event_id: Optional[str] = Field(default=None, description="Stable provider event ID for idempotency")
    provenance: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Metadata and provider telemetry")
    correlation_id: Optional[str] = Field(default=None, description="Correlation identifier")


class LiveMeetingLeaveRequest(CoreBaseModel):
    """Request payload to disconnect live meeting ingestion."""
    external_meeting_id: str = Field(..., description="External meeting code or ID")
    session_id: Optional[str] = Field(default=None, description="Active session ID if known")
    finalize_transcription: bool = Field(default=True, description="Trigger ACE pipeline and SKW object synthesis upon leaving")
    correlation_id: Optional[str] = Field(default=None, description="Correlation identifier")


class LiveMeetingCapabilityResponse(CoreBaseModel):
    """Response containing live media streaming capabilities for a provider/account."""
    provider: str
    raw_audio_stream_supported: bool
    live_captions_supported: bool
    participant_identity_tracking: bool
    transcript_artifacts_supported: bool = True
    ingestion_modes: List[str] = Field(default_factory=list)
    workspace_tier: Optional[str] = None
    azure_ad_tenant_isolated: Optional[bool] = None
    max_concurrent_streams: Optional[int] = 16
    reason: Optional[str] = None
    requires_configuration: bool = False


class LiveMeetingParticipantDTO(CoreBaseModel):
    """Participant presence and identity representation from live provider stream."""
    participant_id: str
    display_name: str
    email: Optional[str] = None
    role: Optional[str] = "participant"
    is_speaking: bool = False


class LiveMeetingSessionResponse(CoreBaseModel):
    """Response DTO for live session state and observer status."""
    session_id: str
    meeting_id: Optional[uuid.UUID] = None
    external_meeting_id: str
    provider: str
    status: str
    stream_mode: str
    joined_at: datetime
    meeting_url: Optional[str] = None
    participants: List[LiveMeetingParticipantDTO] = Field(default_factory=list)
    chunks_received: int = 0
    diarization_active: bool = True
    correlation_id: Optional[str] = None
