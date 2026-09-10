"""
Streaming Audio Ingestion & Live Session Management Service
Handles live meeting lifecycle states, sequential audio chunk ingestion,
Redis event publishing, and incremental processing adapter boundaries.
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set, Tuple
import uuid
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import BadRequestException, ForbiddenException, NotFoundException
from app.core.logging import get_logger
from app.events.redis_bus import RedisEventBus
from app.infrastructure.storage import get_storage_manager
from app.models.live_session import LiveSession, LiveAudioChunk
from app.models.meeting import Meeting
from app.repositories.meeting_repo import MeetingRepository

logger = get_logger(__name__)

LIVE_VALID_TRANSITIONS: Dict[str, Set[str]] = {
    "created": {"live", "cancelled", "failed"},
    "live": {"paused", "stopping", "completed", "failed", "cancelled"},
    "paused": {"live", "stopping", "cancelled", "failed"},
    "stopping": {"completed", "failed"},
    "completed": set(),
    "failed": set(),
    "cancelled": set(),
}


class StreamingProcessingProvider:
    """
    Interface / Adapter for incremental audio processing in live sessions.
    Operates in mock/fixture mode for Phase 4.17 without real GPU/Whisper inference.
    """

    async def process_chunk(self, session: LiveSession, chunk: LiveAudioChunk) -> Dict[str, Any]:
        logger.info(
            "StreamingProcessingProvider processing chunk %d for session %s (meeting %s)",
            chunk.sequence_number,
            session.id,
            session.meeting_id,
        )
        return {
            "status": "processed_fixture",
            "session_id": str(session.id),
            "sequence_number": chunk.sequence_number,
            "transcript_snippet": f"[Fixture live transcript for chunk {chunk.sequence_number}]",
        }


class LiveSessionService:
    """Service handling live session lifecycle and streaming audio chunk ingestion."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.meeting_repo = MeetingRepository(db)
        self.event_bus = RedisEventBus()
        self.storage = get_storage_manager()
        self.processor = StreamingProcessingProvider()

    def validate_transition(self, current_state: str, new_state: str) -> None:
        allowed = LIVE_VALID_TRANSITIONS.get(current_state, set())
        if new_state not in allowed:
            raise BadRequestException(
                message=f"Invalid live session state transition from '{current_state}' to '{new_state}'",
                code="INVALID_LIFECYCLE_TRANSITION",
            )

    async def _verify_meeting_access(self, meeting_id: uuid.UUID, auth_context: Dict[str, Any]) -> Meeting:
        meeting = await self.meeting_repo.get_by_id(meeting_id)
        if not meeting:
            raise NotFoundException(message=f"Meeting {meeting_id} not found", code="MEETING_NOT_FOUND")
        
        role = auth_context.get("role")
        user_id_str = auth_context.get("user_id")
        if role != "admin" and meeting.host_id and user_id_str and str(meeting.host_id) != str(user_id_str):
            raise ForbiddenException(message="Only meeting host or admin can manage live sessions", code="FORBIDDEN")
        return meeting

    async def get_or_create_session(self, meeting_id: uuid.UUID, auth_context: Dict[str, Any], language: str = "en", session_metadata: Optional[dict] = None) -> LiveSession:
        await self._verify_meeting_access(meeting_id, auth_context)
        
        stmt = select(LiveSession).where(LiveSession.meeting_id == meeting_id)
        result = await self.db.execute(stmt)
        session = result.scalars().first()

        if not session:
            session = LiveSession(
                meeting_id=meeting_id,
                status="created",
                language=language,
                session_metadata=session_metadata or {},
                correlation_id=auth_context.get("correlation_id") or str(uuid.uuid4()),
                request_id=auth_context.get("request_id") or str(uuid.uuid4()),
            )
            self.db.add(session)
            await self.db.commit()
            await self.db.refresh(session)
        return session

    async def start_session(self, meeting_id: uuid.UUID, auth_context: Dict[str, Any], language: str = "en", session_metadata: Optional[dict] = None) -> LiveSession:
        session = await self.get_or_create_session(meeting_id, auth_context, language, session_metadata)
        self.validate_transition(session.status, "live")

        session.status = "live"
        session.started_at = datetime.now(timezone.utc)
        session.last_activity_at = datetime.now(timezone.utc)
        await self.db.commit()
        await self.db.refresh(session)

        await self.event_bus.publish(
            f"events:meetings:{meeting_id}:live",
            {
                "event_type": "LiveSessionStarted",
                "meeting_id": str(meeting_id),
                "session_id": str(session.id),
                "status": session.status,
                "timestamp": session.started_at.isoformat(),
                "correlation_id": session.correlation_id,
            },
        )
        return session

    async def pause_session(self, meeting_id: uuid.UUID, auth_context: Dict[str, Any]) -> LiveSession:
        session = await self.get_or_create_session(meeting_id, auth_context)
        self.validate_transition(session.status, "paused")

        session.status = "paused"
        session.paused_at = datetime.now(timezone.utc)
        session.last_activity_at = datetime.now(timezone.utc)
        await self.db.commit()
        await self.db.refresh(session)

        await self.event_bus.publish(
            f"events:meetings:{meeting_id}:live",
            {
                "event_type": "LiveSessionPaused",
                "meeting_id": str(meeting_id),
                "session_id": str(session.id),
                "status": session.status,
                "timestamp": session.paused_at.isoformat(),
            },
        )
        return session

    async def resume_session(self, meeting_id: uuid.UUID, auth_context: Dict[str, Any]) -> LiveSession:
        session = await self.get_or_create_session(meeting_id, auth_context)
        self.validate_transition(session.status, "live")

        session.status = "live"
        session.resumed_at = datetime.now(timezone.utc)
        session.last_activity_at = datetime.now(timezone.utc)
        await self.db.commit()
        await self.db.refresh(session)

        await self.event_bus.publish(
            f"events:meetings:{meeting_id}:live",
            {
                "event_type": "LiveSessionResumed",
                "meeting_id": str(meeting_id),
                "session_id": str(session.id),
                "status": session.status,
                "timestamp": session.resumed_at.isoformat(),
            },
        )
        return session

    async def stop_session(self, meeting_id: uuid.UUID, auth_context: Dict[str, Any]) -> LiveSession:
        session = await self.get_or_create_session(meeting_id, auth_context)
        if session.status in {"completed", "stopped"}:
            return session
        self.validate_transition(session.status, "stopping")

        session.status = "stopping"
        await self.db.commit()

        session.status = "completed"
        session.stopped_at = datetime.now(timezone.utc)
        session.last_activity_at = datetime.now(timezone.utc)
        await self.db.commit()
        await self.db.refresh(session)

        await self.event_bus.publish(
            f"events:meetings:{meeting_id}:live",
            {
                "event_type": "LiveSessionStopped",
                "meeting_id": str(meeting_id),
                "session_id": str(session.id),
                "status": session.status,
                "timestamp": session.stopped_at.isoformat(),
                "accepted_chunks": session.accepted_chunks_count,
            },
        )
        return session

    async def ingest_chunk(
        self,
        meeting_id: uuid.UUID,
        sequence_number: int,
        timestamp_start_ms: int,
        timestamp_end_ms: int,
        file_bytes: bytes,
        filename: str,
        auth_context: Dict[str, Any],
        checksum: Optional[str] = None,
    ) -> Tuple[LiveAudioChunk, str]:
        session = await self.get_or_create_session(meeting_id, auth_context)
        if session.status != "live":
            raise BadRequestException(
                message=f"Cannot ingest audio chunk while live session status is '{session.status}'",
                code="SESSION_NOT_LIVE",
            )

        session.received_chunks_count += 1
        session.last_activity_at = datetime.now(timezone.utc)

        await self.event_bus.publish(
            f"events:meetings:{meeting_id}:live",
            {
                "event_type": "AudioChunkReceived",
                "meeting_id": str(meeting_id),
                "session_id": str(session.id),
                "sequence_number": sequence_number,
            },
        )

        # Validate sequence ordering
        if sequence_number <= session.latest_sequence_number:
            session.rejected_chunks_count += 1
            await self.db.commit()
            await self.event_bus.publish(
                f"events:meetings:{meeting_id}:live",
                {
                    "event_type": "AudioChunkRejected",
                    "meeting_id": str(meeting_id),
                    "session_id": str(session.id),
                    "sequence_number": sequence_number,
                    "reason": "Duplicate or out-of-order sequence number",
                },
            )
            raise BadRequestException(
                message=f"Out-of-order or duplicate chunk sequence {sequence_number} (latest: {session.latest_sequence_number})",
                code="INVALID_CHUNK_SEQUENCE",
            )

        # Save audio chunk using existing local storage manager
        stored_path = await self.storage.save_audio_chunk(
            meeting_id=str(meeting_id),
            session_id=str(session.id),
            sequence_number=sequence_number,
            file_bytes=file_bytes,
        )

        chunk = LiveAudioChunk(
            session_id=session.id,
            sequence_number=sequence_number,
            timestamp_start_ms=timestamp_start_ms,
            timestamp_end_ms=timestamp_end_ms,
            file_path=stored_path,
            file_size=len(file_bytes),
            checksum=checksum,
            status="accepted",
        )
        self.db.add(chunk)

        session.accepted_chunks_count += 1
        session.latest_sequence_number = sequence_number
        await self.db.commit()
        await self.db.refresh(chunk)
        await self.db.refresh(session)

        await self.event_bus.publish(
            f"events:meetings:{meeting_id}:live",
            {
                "event_type": "AudioChunkAccepted",
                "meeting_id": str(meeting_id),
                "session_id": str(session.id),
                "sequence_number": sequence_number,
            },
        )

        # Trigger incremental processing adapter
        processing_result = await self.processor.process_chunk(session, chunk)

        return chunk, processing_result.get("status", "processed")

    async def get_session_status(self, meeting_id: uuid.UUID, auth_context: Dict[str, Any]) -> Dict[str, Any]:
        session = await self.get_or_create_session(meeting_id, auth_context)
        recent_chunks = session.chunks[-20:] if session.chunks else []
        return {
            "session": session,
            "recent_chunks": recent_chunks,
            "processing_state": "active_fixture",
        }
