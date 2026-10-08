"""
Streaming Audio Ingestion & Live Session Management Service
Handles live meeting lifecycle states, sequential audio chunk ingestion,
Redis event publishing, and incremental processing adapter boundaries.
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set, Tuple
import uuid
import hashlib
import io
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppException, BadRequestException, ForbiddenException, NotFoundException
from app.core.config import get_settings
from app.core.logging import get_logger
from app.events.redis_bus import RedisEventBus
from app.infrastructure.storage import get_storage_manager
from app.models.live_session import LiveSession, LiveAudioChunk
from app.models.inference_job import InferenceJob
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


class LiveSessionService:
    """Service handling live session lifecycle and streaming audio chunk ingestion."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.meeting_repo = MeetingRepository(db)
        self.event_bus = RedisEventBus()
        self.storage = get_storage_manager()

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
        if not user_id_str or not auth_context.get("tenant_id") or str(meeting.tenant_id) != str(auth_context["tenant_id"]):
            raise ForbiddenException(message="Live session tenant does not match authenticated identity")
        if role != "admin" and (not meeting.host_id or str(meeting.host_id) != str(user_id_str)):
            raise ForbiddenException(message="Only meeting host or admin can manage live sessions", code="FORBIDDEN")
        return meeting

    async def get_or_create_session(self, meeting_id: uuid.UUID, auth_context: Dict[str, Any], language: str = "en", session_metadata: Optional[dict] = None) -> LiveSession:
        meeting = await self._verify_meeting_access(meeting_id, auth_context)
        # Serialize session creation and ingestion for this meeting.
        await self.db.execute(select(Meeting.id).where(Meeting.id == meeting_id).with_for_update())
        
        stmt = select(LiveSession).where(LiveSession.meeting_id == meeting_id)
        result = await self.db.execute(stmt)
        session = result.scalars().first()

        if not session:
            session = LiveSession(
                meeting_id=meeting_id,
                tenant_id=meeting.tenant_id,
                status="created",
                language=language,
                session_metadata={**(session_metadata or {}), "authorized_actor": {
                    "user_id": auth_context["user_id"], "tenant_id": auth_context["tenant_id"],
                    "role": auth_context.get("role", "member")}},
                correlation_id=auth_context.get("correlation_id") or str(uuid.uuid4()),
                request_id=auth_context.get("request_id") or str(uuid.uuid4()),
            )
            self.db.add(session)
            await self.db.commit()
            await self.db.refresh(session)
        return session

    async def start_session(self, meeting_id: uuid.UUID, auth_context: Dict[str, Any], language: str = "en", session_metadata: Optional[dict] = None) -> LiveSession:
        settings = get_settings()
        if settings.EXECUTION_MODE.upper() != "REAL":
            raise BadRequestException(message="Live ingestion requires EXECUTION_MODE=REAL")
        if not 0 < settings.LIVE_OVERLAP_SECONDS < settings.LIVE_CHUNK_SECONDS:
            raise BadRequestException(message="Live overlap must be positive and smaller than the chunk duration")
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
        if session.status in {"completed", "stopping"}:
            return session
        self.validate_transition(session.status, "stopping")

        session.status = "stopping"
        session.stopped_at = datetime.now(timezone.utc)
        session.last_activity_at = datetime.now(timezone.utc)
        self.db.add(InferenceJob(job_key=f"finalize:{session.id}", kind="finalize",
            meeting_id=meeting_id, session_id=session.id, status="queued"))
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
        await self.db.refresh(session, with_for_update=True)
        settings = get_settings()
        if settings.EXECUTION_MODE.upper() != "REAL":
            raise BadRequestException(message="Live ingestion requires EXECUTION_MODE=REAL")
        digest = hashlib.sha256(file_bytes).hexdigest()
        previous = (await self.db.execute(select(LiveAudioChunk).where(
            LiveAudioChunk.session_id == session.id,
            LiveAudioChunk.sequence_number == sequence_number))).scalar_one_or_none()
        if previous:
            if (previous.checksum == digest and previous.timestamp_start_ms == timestamp_start_ms
                    and previous.timestamp_end_ms == timestamp_end_ms):
                return previous, previous.status
            raise BadRequestException(message="Sequence already exists with different audio or timestamps")
        if session.status != "live":
            raise BadRequestException(
                message=f"Cannot ingest audio chunk while live session status is '{session.status}'",
                code="SESSION_NOT_LIVE",
            )

        session.received_chunks_count += 1
        session.last_activity_at = datetime.now(timezone.utc)

        if not file_bytes or len(file_bytes) > settings.LIVE_MAX_CHUNK_BYTES:
            raise BadRequestException(message="Live chunk is empty or exceeds the configured byte limit")
        if checksum and checksum.lower() != digest:
            raise BadRequestException(message="Live chunk SHA-256 mismatch")
        try:
            import soundfile as sf
            info = sf.info(io.BytesIO(file_bytes))
        except Exception as exc:
            raise BadRequestException(message="Live chunks must contain decodable PCM WAV audio") from exc
        if info.format != "WAV" or info.channels != 1 or info.frames <= 0:
            raise BadRequestException(message="Live chunks require non-empty mono WAV audio")
        if timestamp_start_ms < 0 or timestamp_end_ms <= timestamp_start_ms:
            raise BadRequestException(message="Invalid live chunk time interval")
        if abs(info.duration * 1000 - (timestamp_end_ms - timestamp_start_ms)) > 2:
            raise BadRequestException(message="Audio duration does not match chunk timestamps")
        if info.duration > settings.LIVE_CHUNK_SECONDS + .002:
            raise BadRequestException(message="Live chunk exceeds the configured inference window")
        last = (await self.db.execute(select(LiveAudioChunk).where(
            LiveAudioChunk.session_id == session.id).order_by(LiveAudioChunk.sequence_number.desc()).limit(1))).scalar_one_or_none()
        if last:
            expected = last.timestamp_end_ms - round(settings.LIVE_OVERLAP_SECONDS * 1000)
            if abs(timestamp_start_ms - expected) > 2 or timestamp_end_ms <= last.timestamp_end_ms:
                raise BadRequestException(message="Chunk coverage/overlap is inconsistent with the preceding chunk")
        elif timestamp_start_ms != 0:
            raise BadRequestException(message="First live chunk must start at zero")
        pending = await self.db.scalar(select(func.count()).select_from(InferenceJob).where(
            InferenceJob.session_id == session.id, InferenceJob.kind == "chunk",
            InferenceJob.status.in_(["queued", "running"])))
        if pending >= settings.LIVE_MAX_PENDING_CHUNKS:
            raise AppException(message="Inference backlog is full; retain and retry this chunk", code="LIVE_BACKPRESSURE", status_code=429)

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
        if sequence_number != session.latest_sequence_number + 1:
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
            checksum=digest,
            status="queued",
        )
        self.db.add(chunk)
        await self.db.flush()
        self.db.add(InferenceJob(job_key=f"chunk:{chunk.id}", kind="chunk",
            meeting_id=meeting_id, session_id=session.id, chunk_id=chunk.id, status="queued"))

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

        return chunk, "queued"

    async def get_session_status(self, meeting_id: uuid.UUID, auth_context: Dict[str, Any]) -> Dict[str, Any]:
        session = await self.get_or_create_session(meeting_id, auth_context)
        recent_chunks = (await self.db.execute(select(LiveAudioChunk).where(
            LiveAudioChunk.session_id == session.id).order_by(LiveAudioChunk.sequence_number.desc()).limit(20))).scalars().all()
        jobs = list(reversed((await self.db.execute(select(InferenceJob).where(InferenceJob.session_id == session.id)
            .order_by(InferenceJob.created_at.desc()).limit(50))).scalars().all()))
        counts = dict((await self.db.execute(select(InferenceJob.status, func.count()).where(
            InferenceJob.session_id == session.id).group_by(InferenceJob.status))).all())
        pending = counts.get("queued", 0) + counts.get("running", 0)
        failed = counts.get("failed", 0)
        return {
            "session": session,
            "recent_chunks": recent_chunks,
            "processing_state": "failed" if failed else "processing" if pending else session.status,
            "pending_jobs": pending,
            "failed_jobs": failed,
            "jobs": [{"id": str(job.id), "chunk_id": str(job.chunk_id) if job.chunk_id else None,
                "kind": job.kind, "status": job.status,
                "result": {k: v for k, v in (job.result or {}).items() if k in {
                    "segments", "elapsed_seconds", "rtf", "speaker_scope", "canonical_transcript_id", "final_segments"}},
                "error": job.error,
                "created_at": job.created_at, "started_at": job.started_at, "finished_at": job.finished_at} for job in jobs],
            "chunk_seconds": get_settings().LIVE_CHUNK_SECONDS,
            "overlap_seconds": get_settings().LIVE_OVERLAP_SECONDS,
        }
