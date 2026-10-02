"""
Meeting Domain Service & Intake Lifecycle Manager
Handles business logic for meeting creation, audio artifact upload, authorization scope verification,
lifecycle state transitions, idempotency checks, and ACE orchestration integration.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional, Set
import uuid
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import BadRequestException, ForbiddenException, NotFoundException
from app.core.logging import get_logger
from app.events.redis_bus import RedisEventBus
from app.infrastructure.storage import get_storage_manager
from app.models.audio import Audio
from app.models.meeting import Meeting
from app.models.user import User
from app.models.participant import Participant
from app.orchestration.ace_boundary import ACERequest
from app.repositories.audio_repo import AudioRepository
from app.repositories.meeting_repo import MeetingRepository
from app.repositories.participant_repo import ParticipantRepository
from app.schemas.meeting import MeetingCreate, MeetingProcessingRequest, MeetingProcessingResponse

logger = get_logger("services.meeting_service")

# State Machine Transition Rules for Meeting Lifecycle
VALID_TRANSITIONS: Dict[str, Set[str]] = {
    "created": {"scheduled", "starting", "active", "processing_requested", "failed", "cancelled"},
    "scheduled": {"starting", "active", "rescheduled", "cancelled", "processing_requested", "failed"},
    "starting": {"active", "failed", "cancelled"},
    "active": {"processing_requested", "running", "completed", "failed", "cancelled"},
    "processing_requested": {"running", "completed", "failed", "cancelled"},
    "running": {"completed", "failed", "cancelled"},
    "completed": {"processing_requested"},  # Allowed only if force_repress=True
    "failed": {"processing_requested", "scheduled"},
    "cancelled": set(),  # terminal state
}

SUPPORTED_AUDIO_FORMATS: Set[str] = {"wav", "mp3", "m4a", "flac", "ogg", "webm"}


class MeetingService:
    """Domain service managing meeting lifecycle, scope authorization, storage, and ACE orchestration."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.meeting_repo = MeetingRepository(db)
        self.audio_repo = AudioRepository(db)
        self.participant_repo = ParticipantRepository(db)

    def validate_transition(self, current_status: str, target_status: str, force_reprocess: bool = False) -> None:
        """
        Validate state machine transition for meeting processing lifecycle.
        Raises BadRequestException on invalid transitions.
        """
        if current_status == target_status:
            return

        allowed = VALID_TRANSITIONS.get(current_status, set())
        if target_status not in allowed:
            if not force_reprocess:
                raise BadRequestException(
                    message=f"Invalid meeting lifecycle transition from '{current_status}' to '{target_status}'.",
                    code="INVALID_STATE_TRANSITION",
                )

    def verify_scope(self, meeting: Meeting, auth_context: Optional[Dict[str, Any]]) -> None:
        """
        Enforce tenant and user security boundary for meeting access.
        Raises ForbiddenException if user lacks authorization for meeting scope.
        """
        if not auth_context:
            return

        role = auth_context.get("role")
        if role == "admin":
            return

        user_id_str = auth_context.get("user_id")
        if not user_id_str:
            return

        # Host check
        if meeting.host_id and str(meeting.host_id) == str(user_id_str):
            return

        # Participant check
        if meeting.participants:
            for p in meeting.participants:
                if p.user_id and str(p.user_id) == str(user_id_str):
                    return

        # If meeting has an explicit host_id set and user is neither host nor participant nor admin
        if meeting.host_id is not None:
            raise ForbiddenException(
                message=f"Forbidden: Access to meeting scope {meeting.id} is denied.",
                code="MEETING_SCOPE_FORBIDDEN",
            )

    async def create_meeting(self, payload: MeetingCreate, auth_context: Optional[Dict[str, Any]] = None) -> Meeting:
        """Create and persist a new meeting entity with initial participants and metadata."""
        host_id = payload.host_id
        if not host_id and auth_context and auth_context.get("user_id"):
            try:
                host_id = uuid.UUID(auth_context["user_id"])
                if await self.db.get(User, host_id) is None:
                    host_id = None
            except ValueError:
                host_id = None

        settings_dict = payload.settings or {}
        if payload.correlation_id:
            settings_dict["correlation_id"] = payload.correlation_id

        tenant_id = (auth_context.get("tenant_id") if auth_context else None) or "default"

        meeting = Meeting(
            title=payload.title,
            description=payload.description,
            language=payload.language or "en",
            secondary_languages=payload.secondary_languages or [],
            host_id=host_id,
            scheduled_start=payload.scheduled_start,
            duration_minutes=payload.duration_minutes or 60,
            timezone=payload.timezone or "UTC",
            settings=settings_dict,
            tenant_id=tenant_id,
            status="scheduled" if payload.scheduled_start else "created",
        )

        meeting = await self.meeting_repo.create(meeting)

        if payload.scheduled_start:
            event_bus = RedisEventBus()
            await event_bus.publish(
                f"events:meetings:{meeting.id}",
                {
                    "event_type": "MeetingScheduled",
                    "meeting_id": str(meeting.id),
                    "scheduled_start": payload.scheduled_start.isoformat(),
                    "status": meeting.status,
                },
            )

        # Create initial participants if provided
        if payload.participants:
            for p in payload.participants:
                participant = Participant(
                    meeting_id=meeting.id,
                    display_name=p.display_name,
                    email=p.email,
                    role=p.role or "attendee",
                    speaker_label=p.speaker_label,
                    voiceprint_id=p.voiceprint_id,
                )
                await self.participant_repo.create(participant)

        # Fetch full meeting with relationships
        full_meeting = await self.meeting_repo.get_with_relations(meeting.id)
        return full_meeting or meeting

    async def get_meeting(self, meeting_id: uuid.UUID, auth_context: Optional[Dict[str, Any]] = None) -> Meeting:
        """Retrieve meeting by UUID while enforcing security scope boundaries."""
        meeting = await self.meeting_repo.get_with_relations(meeting_id)
        if not meeting:
            raise NotFoundException(
                message=f"Meeting {meeting_id} not found",
                code="MEETING_NOT_FOUND",
            )

        self.verify_scope(meeting, auth_context)
        return meeting

    async def list_meetings(
        self,
        skip: int = 0,
        limit: int = 50,
        status: Optional[str] = None,
        auth_context: Optional[Dict[str, Any]] = None,
    ) -> List[Meeting]:
        """List meetings with optional filtering."""
        filters: Dict[str, Any] = {}
        if status:
            filters["status"] = status

        if auth_context and auth_context.get("role") != "admin" and auth_context.get("user_id"):
            try:
                filters["host_id"] = uuid.UUID(auth_context["user_id"])
            except ValueError:
                pass

        return await self.meeting_repo.list(skip=skip, limit=limit, **filters)

    async def upload_audio(
        self,
        meeting_id: uuid.UUID,
        file_name: str,
        content: bytes,
        format: str = "wav",
        sample_rate: int = 16000,
        channels: int = 1,
        auth_context: Optional[Dict[str, Any]] = None,
    ) -> Audio:
        """Upload and store audio payload for a meeting session."""
        meeting = await self.get_meeting(meeting_id, auth_context)

        # File payload validation
        if not content or len(content) == 0:
            raise BadRequestException(
                message="Audio upload payload cannot be empty (0 bytes).",
                code="EMPTY_AUDIO_PAYLOAD",
            )

        clean_format = format.lower().strip(".")
        if clean_format not in SUPPORTED_AUDIO_FORMATS:
            raise BadRequestException(
                message=f"Unsupported audio format '{format}'. Supported formats: {sorted(list(SUPPORTED_AUDIO_FORMATS))}",
                code="UNSUPPORTED_AUDIO_FORMAT",
            )

        storage_mgr = get_storage_manager()
        saved_path = storage_mgr.save_audio_file(meeting.id, file_name, content)

        audio = Audio(
            meeting_id=meeting.id,
            file_path=str(saved_path),
            file_name=file_name,
            file_size_bytes=len(content),
            format=clean_format,
            sample_rate=sample_rate,
            channels=channels,
            status="uploaded",
        )

        return await self.audio_repo.create(audio)

    async def process_meeting(
        self,
        meeting_id: uuid.UUID,
        req: MeetingProcessingRequest,
        auth_context: Dict[str, Any],
        ace_orchestrator: Any,
    ) -> MeetingProcessingResponse:
        """
        Initiate meeting intake processing through the ACE orchestrator lifecycle.
        Enforces state transitions, scope checks, idempotency, and error handling.
        """
        meeting = await self.get_meeting(meeting_id, auth_context)

        # Idempotency check: if already processing or running and not force_reprocess
        if meeting.status in ["processing_requested", "running"] and not req.force_reprocess:
            logger.info(f"Meeting {meeting_id} is already in '{meeting.status}' state. Returning idempotent response.")
            return MeetingProcessingResponse(
                request_id=req.request_id,
                meeting_id=meeting.id,
                correlation_id=req.correlation_id or (meeting.settings or {}).get("correlation_id"),
                status=meeting.status,
                message=f"Meeting processing is already active with status '{meeting.status}'.",
            )

        # Validate transition to processing_requested
        self.validate_transition(meeting.status, "processing_requested", force_reprocess=req.force_reprocess)

        # Update status to processing_requested
        meeting.status = "processing_requested"
        await self.meeting_repo.update(meeting)
        # Keep the genuine intake/audio records available after a worker failure,
        # so the existing CLI --meeting-id path can resume this same meeting.
        await self.db.commit()

        ace_req = ACERequest(
            request_id=req.request_id,
            meeting_id=meeting.id,
            correlation_id=req.correlation_id or str(uuid.uuid4()),
            enable_analytics=req.enable_analytics,
            enable_memory=req.enable_memory,
        )

        try:
            # Mark running during execution
            meeting.status = "running"
            await self.meeting_repo.update(meeting)

            blackboard = await ace_orchestrator.process_request(ace_req, auth_context=auth_context)

            exec_status = blackboard.execution_state.get("status", "COMPLETED").upper()
            final_status = "completed" if exec_status == "COMPLETED" else "failed"
            from app.core.config import get_settings
            if final_status == "completed" and get_settings().EXECUTION_MODE.upper() == "REAL":
                await self._persist_real_transcript(meeting, blackboard, ace_req.correlation_id)

            meeting.status = final_status
            await self.meeting_repo.update(meeting)
            await self.db.commit()

            return MeetingProcessingResponse(
                request_id=req.request_id,
                meeting_id=meeting.id,
                correlation_id=ace_req.correlation_id,
                status=final_status,
                message=f"ACE processing completed with status '{final_status}'.",
            )
        except Exception as ex:
            await self.db.rollback()
            await self.db.refresh(meeting)
            meeting.status = "failed"
            await self.meeting_repo.update(meeting)
            await self.db.commit()
            logger.error(f"ACE processing failed for meeting {meeting_id}: {ex}")
            return MeetingProcessingResponse(
                request_id=req.request_id,
                meeting_id=meeting.id,
                correlation_id=req.correlation_id,
                status="failed",
                message=f"Meeting processing failed: {str(ex)}",
            )

    async def _persist_real_transcript(self, meeting, blackboard, correlation_id):
        """Persist actual completed provider output and verify it in a fresh session."""
        from sqlalchemy.ext.asyncio import async_sessionmaker
        from app.ai.multilingual_asr import ASRSegment
        from app.ai.long_audio_processor import LongAudioProcessor
        from app.ai.speaker_diarization import SpeakerDiarizationEngine
        from app.models.transcript import Transcript, TranscriptSegment
        from app.repositories.transcript_repo import TranscriptRepository, TranscriptSegmentRepository
        outputs = {task.required_capability: task.metadata for task in blackboard.list_tasks()
                   if getattr(task.status, "value", task.status) == "COMPLETED"}
        asr = outputs.get("multilingual_asr", {})
        if asr.get("metadata", {}).get("is_fixture") is not False:
            raise RuntimeError("REAL persistence requires actual non-fixture ASR provenance")
        segments = [ASRSegment.model_validate(s) for s in asr.get("segments", [])]
        duration = outputs.get("audio_intelligence", {}).get("duration_seconds", 0)
        if not segments or duration <= 0:
            raise RuntimeError("REAL persistence requires non-empty observed transcript and audio duration")
        comparison = SpeakerDiarizationEngine().verify_moss_with_pyannote(segments,
            outputs.get("speaker_representation", {}).get("speaker_turns", []))
        comparison["agreement_ratio"] = comparison.pop("accuracy", None)
        processor = LongAudioProcessor()
        chunk_count = asr.get("metadata", {}).get("chunk_count", 1)
        mapping, removed = {}, 0
        if chunk_count > 1:
            mapping = asr.get("metadata", {}).get("speaker_mapping", {})
            removed = asr.get("metadata", {}).get("deduplicated_segments_count", 0)
        if chunk_count == 1:
            chunks = processor.plan_chunks(duration)
            if len(chunks) != 1:
                raise RuntimeError("Single-pass ASR output disagrees with chunk planning")
            global_segments = processor.offset_segments_to_global_time(segments, chunks[0].start_time)
            reconciled, mapping = processor.reconcile_speakers_across_chunks([(chunks[0], global_segments)])
            segments, removed = processor.merge_and_deduplicate_chunks(chunks, reconciled)
        if not segments or any(not (0 <= s.start_time < s.end_time <= duration) for s in segments):
            raise RuntimeError("REAL final transcript contains invalid or empty segments")
        segments.sort(key=lambda s: (s.start_time, s.end_time))
        expected = [(round(s.start_time*1000), round(s.end_time*1000), s.transcript, s.speaker_id) for s in segments]
        repository = TranscriptSegmentRepository(self.db)
        existing = await repository.list_by_meeting(meeting.id)
        if existing:
            signature = [(s.start_time_ms, s.end_time_ms, s.original_text, s.speaker_label) for s in existing]
            if signature != expected:
                raise RuntimeError("Existing transcript differs; replacement requires an explicit data action")
        else:
            await repository.bulk_create_segments([TranscriptSegment(id=s.segment_id, meeting_id=meeting.id,
                start_time_ms=round(s.start_time*1000), end_time_ms=round(s.end_time*1000),
                original_text=s.transcript, speaker_label=s.speaker_id, sequence_number=index+1,
                language=s.detected_language or "und", confidence=s.confidence, words_payload=[], is_final=True)
                for index, s in enumerate(segments)])
        full_text = " ".join(s.transcript for s in segments)
        transcripts = TranscriptRepository(self.db)
        canonical = await transcripts.get_latest_version(meeting.id)
        if canonical is None:
            canonical = await transcripts.create(Transcript(meeting_id=meeting.id, full_text=full_text,
                language="und", confidence_score=None, word_count=len(full_text.split()), is_final=True,
                provenance={"execution_mode": "REAL", "correlation_id": correlation_id,
                    "model": asr.get("metadata", {}), "speaker_comparison": comparison,
                    "speaker_mapping": mapping, "deduplicated_segments": removed}))
        meeting.settings = {**(meeting.settings or {}), "audio_duration_seconds": duration}
        await self.db.commit()
        # A separate identity map/transaction proves committed storage, not the
        # in-memory entities that were just added to this session.
        async with async_sessionmaker(self.db.bind, expire_on_commit=False)() as reader:
            read_segments = await TranscriptSegmentRepository(reader).list_by_meeting(meeting.id)
            read_transcript = await TranscriptRepository(reader).get_latest_version(meeting.id)
            signature = [(s.start_time_ms, s.end_time_ms, s.original_text, s.speaker_label) for s in read_segments]
            if signature != expected or not read_transcript or read_transcript.full_text != full_text:
                raise RuntimeError("REAL committed transcript read-back differs from the final result")
        blackboard.execution_state["transcript_persistence"] = {"segments_written": len(expected),
            "commit": "passed", "read_back": "passed", "canonical_transcript_id": str(canonical.id),
            "chunk_count": chunk_count, "deduplicated_segments": removed, "speaker_comparison": comparison}

    async def schedule_meeting(
        self,
        meeting_id: uuid.UUID,
        scheduled_start: datetime,
        duration_minutes: Optional[int],
        timezone: Optional[str],
        auth_context: Dict[str, Any],
    ) -> Meeting:
        meeting = await self.get_meeting(meeting_id, auth_context)
        role = auth_context.get("role")
        user_id_str = auth_context.get("user_id")
        if role != "admin" and meeting.host_id and user_id_str and str(meeting.host_id) != str(user_id_str):
            raise ForbiddenException(message="Only meeting host or admin can schedule meetings", code="FORBIDDEN")

        self.validate_transition(meeting.status, "scheduled")

        meeting.scheduled_start = scheduled_start
        if duration_minutes is not None:
            meeting.duration_minutes = duration_minutes
        if timezone is not None:
            meeting.timezone = timezone
        meeting.status = "scheduled"

        await self.meeting_repo.update(meeting)

        event_bus = RedisEventBus()
        await event_bus.publish(
            f"events:meetings:{meeting.id}",
            {
                "event_type": "MeetingScheduled",
                "meeting_id": str(meeting.id),
                "scheduled_start": scheduled_start.isoformat() if scheduled_start else None,
                "status": meeting.status,
            },
        )
        return await self.get_meeting(meeting.id, auth_context)

    async def reschedule_meeting(
        self,
        meeting_id: uuid.UUID,
        new_scheduled_start: datetime,
        duration_minutes: Optional[int],
        timezone: Optional[str],
        auth_context: Dict[str, Any],
    ) -> Meeting:
        meeting = await self.get_meeting(meeting_id, auth_context)
        role = auth_context.get("role")
        user_id_str = auth_context.get("user_id")
        if role != "admin" and meeting.host_id and user_id_str and str(meeting.host_id) != str(user_id_str):
            raise ForbiddenException(message="Only meeting host or admin can reschedule meetings", code="FORBIDDEN")

        if meeting.status == "cancelled":
            raise BadRequestException(message="Cannot reschedule a cancelled meeting", code="INVALID_LIFECYCLE_STATE")

        old_start = meeting.scheduled_start
        meeting.scheduled_start = new_scheduled_start
        if duration_minutes is not None:
            meeting.duration_minutes = duration_minutes
        if timezone is not None:
            meeting.timezone = timezone
        meeting.status = "scheduled"

        await self.meeting_repo.update(meeting)

        event_bus = RedisEventBus()
        await event_bus.publish(
            f"events:meetings:{meeting.id}",
            {
                "event_type": "MeetingRescheduled",
                "meeting_id": str(meeting.id),
                "old_scheduled_start": old_start.isoformat() if old_start else None,
                "new_scheduled_start": new_scheduled_start.isoformat() if new_scheduled_start else None,
                "status": meeting.status,
            },
        )
        return await self.get_meeting(meeting.id, auth_context)

    async def cancel_meeting(
        self,
        meeting_id: uuid.UUID,
        reason: Optional[str],
        auth_context: Dict[str, Any],
    ) -> Meeting:
        meeting = await self.get_meeting(meeting_id, auth_context)
        role = auth_context.get("role")
        user_id_str = auth_context.get("user_id")
        if role != "admin" and meeting.host_id and user_id_str and str(meeting.host_id) != str(user_id_str):
            raise ForbiddenException(message="Only meeting host or admin can cancel meetings", code="FORBIDDEN")

        self.validate_transition(meeting.status, "cancelled")
        meeting.status = "cancelled"
        await self.meeting_repo.update(meeting)

        event_bus = RedisEventBus()
        await event_bus.publish(
            f"events:meetings:{meeting.id}",
            {
                "event_type": "MeetingCancelled",
                "meeting_id": str(meeting.id),
                "reason": reason,
                "status": meeting.status,
            },
        )
        return await self.get_meeting(meeting.id, auth_context)

    async def start_meeting(
        self,
        meeting_id: uuid.UUID,
        auth_context: Dict[str, Any],
    ) -> Meeting:
        meeting = await self.get_meeting(meeting_id, auth_context)
        role = auth_context.get("role")
        user_id_str = auth_context.get("user_id")
        if role != "admin" and meeting.host_id and user_id_str and str(meeting.host_id) != str(user_id_str):
            raise ForbiddenException(message="Only meeting host or admin can start meetings", code="FORBIDDEN")

        if meeting.status not in {"created", "scheduled", "starting"}:
            raise BadRequestException(message=f"Cannot start meeting from state '{meeting.status}'", code="INVALID_LIFECYCLE_STATE")

        meeting.status = "active"
        if not meeting.actual_start:
            meeting.actual_start = datetime.utcnow()

        await self.meeting_repo.update(meeting)

        event_bus = RedisEventBus()
        await event_bus.publish(
            f"events:meetings:{meeting.id}",
            {
                "event_type": "MeetingStarted",
                "meeting_id": str(meeting.id),
                "actual_start": meeting.actual_start.isoformat() if meeting.actual_start else None,
                "status": meeting.status,
            },
        )
        return await self.get_meeting(meeting.id, auth_context)
