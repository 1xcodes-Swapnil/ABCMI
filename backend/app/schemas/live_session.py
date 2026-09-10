"""
Pydantic Schemas for Live Meeting & Streaming Ingestion
"""

from datetime import datetime
from typing import Any, Dict, List, Optional
import uuid
from pydantic import Field

from app.schemas.base import CoreBaseModel


class LiveSessionStartRequest(CoreBaseModel):
    """Payload to start a live meeting streaming session."""
    language: Optional[str] = Field(default="en", description="Primary spoken language code")
    session_metadata: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Session configuration metadata")
    correlation_id: Optional[str] = Field(default=None, description="Distributed correlation ID")


class AudioChunkIngestRequest(CoreBaseModel):
    """Payload metadata for an ingested audio chunk (binary file sent via multipart)."""
    sequence_number: int = Field(..., description="Monotonically increasing sequence number")
    timestamp_start_ms: int = Field(default=0, description="Chunk start timestamp in milliseconds")
    timestamp_end_ms: int = Field(default=0, description="Chunk end timestamp in milliseconds")
    checksum: Optional[str] = Field(default=None, description="Optional SHA256 or MD5 checksum")


class AudioChunkResponse(CoreBaseModel):
    """Response DTO for an ingested audio chunk."""
    id: uuid.UUID
    session_id: uuid.UUID
    sequence_number: int
    timestamp_start_ms: int
    timestamp_end_ms: int
    file_size: int
    status: str
    created_at: datetime

    class Config:
        from_attributes = True


class LiveSessionResponse(CoreBaseModel):
    """Response DTO for live session details."""
    id: uuid.UUID
    meeting_id: uuid.UUID
    status: str
    language: str
    received_chunks_count: int
    accepted_chunks_count: int
    rejected_chunks_count: int
    latest_sequence_number: int
    started_at: Optional[datetime] = None
    paused_at: Optional[datetime] = None
    resumed_at: Optional[datetime] = None
    stopped_at: Optional[datetime] = None
    last_activity_at: Optional[datetime] = None
    correlation_id: Optional[str] = None
    request_id: Optional[str] = None
    session_metadata: Optional[Dict[str, Any]] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class LiveSessionStatusResponse(CoreBaseModel):
    """Status summary response for live session monitoring."""
    session: LiveSessionResponse
    recent_chunks: List[AudioChunkResponse] = Field(default_factory=list)
    processing_state: str = Field(default="idle", description="Incremental processing provider state")
