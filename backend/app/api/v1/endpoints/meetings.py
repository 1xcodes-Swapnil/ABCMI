"""
Meeting Intake & Processing Lifecycle Endpoints (Phase 4.13A)
Implements meeting intake, audio upload, metadata configuration, security scoping,
ACE orchestration integration, and Redis event emission.
"""

from pydantic import BaseModel, Field
from datetime import datetime
from typing import Any, Dict, List, Optional
import uuid
from fastapi import APIRouter, Body, Depends, File, Form, Header, HTTPException, Query, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import verify_authentication
from app.core.exceptions import BadRequestException, ForbiddenException, NotFoundException, UnauthorizedException
from app.core.logging import get_logger
from app.infrastructure.database import get_async_db
from app.events.redis_bus import RedisEventBus
from app.orchestration.ace_engine import ACEOrchestrator
from app.orchestration.module_runner import AIModuleRunner
from app.orchestration.skw_client import BlackboardSKWClient
from app.orchestration.ace_boundary import ACEAdaptiveBlackboardAdapter, ACERequest
from app.skw.services.knowledge_query_engine import KnowledgeQueryEngine
from app.schemas.meeting import (
    AudioResponse,
    MeetingCancelRequest,
    MeetingCreate,
    MeetingProcessingRequest,
    MeetingProcessingResponse,
    MeetingRescheduleRequest,
    MeetingResponse,
    MeetingScheduleRequest,
    ParticipantCreate,
    ParticipantResponse,
)
from app.services.meeting_service import MeetingService

router = APIRouter(prefix="/meetings", tags=["Meeting Intake & Lifecycle"])
logger = get_logger("api.meetings")

# Shared singleton event bus for API lifecycle event dispatch
_event_bus = RedisEventBus()


def get_ace_orchestrator(db: AsyncSession) -> ACEOrchestrator:
    """Factory function to build ACEOrchestrator bound to request DB session via KnowledgeQueryEngine."""
    query_engine = KnowledgeQueryEngine(db)
    skw_client = BlackboardSKWClient(query_engine=query_engine)
    adapter = ACEAdaptiveBlackboardAdapter(blackboard_skw_client=skw_client)
    return ACEOrchestrator(
        event_bus=_event_bus,
        blackboard_adapter=adapter,
        module_runner=AIModuleRunner(),
    )


def _to_meeting_response(meeting: Any) -> MeetingResponse:
    """Map Meeting ORM model to MeetingResponse schema."""
    audio_list = [
        AudioResponse(
            id=a.id,
            meeting_id=a.meeting_id,
            file_path=a.file_path,
            file_name=a.file_name,
            file_size_bytes=a.file_size_bytes,
            duration_seconds=a.duration_seconds,
            format=a.format,
            sample_rate=a.sample_rate,
            channels=a.channels,
            status=a.status,
            created_at=a.created_at,
        )
        for a in (meeting.audio_recordings or [])
    ]

    participant_list = [
        ParticipantResponse(
            id=p.id,
            meeting_id=p.meeting_id,
            user_id=p.user_id,
            display_name=p.display_name,
            email=p.email,
            role=p.role,
            speaker_label=p.speaker_label,
            voiceprint_id=p.voiceprint_id,
            speaking_duration=p.speaking_duration or 0.0,
            created_at=p.created_at,
        )
        for p in (meeting.participants or [])
    ]

    return MeetingResponse(
        id=meeting.id,
        title=meeting.title,
        description=meeting.description,
        status=meeting.status,
        language=meeting.language,
        secondary_languages=meeting.secondary_languages or [],
        host_id=meeting.host_id,
        scheduled_start=meeting.scheduled_start,
        actual_start=meeting.actual_start,
        actual_end=meeting.actual_end,
        settings=meeting.settings or {},
        audio_recordings=audio_list,
        participants=participant_list,
        created_at=meeting.created_at,
        updated_at=meeting.updated_at,
    )


async def _emit_lifecycle_event(
    meeting_id: uuid.uuid4,
    event_type: str,
    request_id: Optional[uuid.UUID] = None,
    correlation_id: Optional[str] = None,
    payload: Optional[Dict[str, Any]] = None,
) -> None:
    """Emit meeting orchestration lifecycle events via Redis Event Bus."""
    try:
        event_id = uuid.uuid4()
        req_id = request_id or uuid.uuid4()
        corr_id = correlation_id or str(uuid.uuid4())
        timestamp = datetime.utcnow().isoformat()

        event_data = {
            "event_id": str(event_id),
            "event_type": event_type,
            "request_id": str(req_id),
            "meeting_id": str(meeting_id),
            "correlation_id": corr_id,
            "timestamp": timestamp,
            "payload": payload or {},
        }

        channel = f"events:meetings:{str(meeting_id)}:orchestration"
        await _event_bus.publish(channel, event_data)
        await _event_bus.publish("events:meetings:global", event_data)
    except Exception as e:
        logger.warning(f"Failed to emit meeting lifecycle event {event_type}: {e}")


@router.post("", response_model=MeetingResponse, status_code=status.HTTP_201_CREATED)
async def create_meeting(
    payload: MeetingCreate,
    auth_context: Dict[str, Any] = Depends(verify_authentication),
    db: AsyncSession = Depends(get_async_db),
) -> MeetingResponse:
    """
    1. MEETING INTAKE: Create a new meeting session with metadata, language configuration,
    participants, and tenant scoping.
    """
    service = MeetingService(db)
    meeting = await service.create_meeting(payload, auth_context)

    # Emit meeting created / intake event
    await _emit_lifecycle_event(
        meeting_id=meeting.id,
        event_type="meeting_created",
        correlation_id=payload.correlation_id,
        payload={"title": meeting.title, "language": meeting.language, "status": meeting.status},
    )

    return _to_meeting_response(meeting)


@router.get("", response_model=List[MeetingResponse], status_code=status.HTTP_200_OK)
async def list_meetings(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    status: Optional[str] = Query(None),
    auth_context: Dict[str, Any] = Depends(verify_authentication),
    db: AsyncSession = Depends(get_async_db),
) -> List[MeetingResponse]:
    """List meetings with optional filtering and RBAC security scope enforcement."""
    service = MeetingService(db)
    meetings = await service.list_meetings(skip=skip, limit=limit, status=status, auth_context=auth_context)
    return [_to_meeting_response(m) for m in meetings]


@router.get("/{meeting_id}", response_model=MeetingResponse, status_code=status.HTTP_200_OK)
async def get_meeting(
    meeting_id: uuid.UUID,
    auth_context: Dict[str, Any] = Depends(verify_authentication),
    db: AsyncSession = Depends(get_async_db),
) -> MeetingResponse:
    """Retrieve comprehensive meeting details, audio artifacts, and participants with scope check."""
    service = MeetingService(db)
    meeting = await service.get_meeting(meeting_id, auth_context)
    return _to_meeting_response(meeting)


@router.post("/{meeting_id}/audio", response_model=AudioResponse, status_code=status.HTTP_201_CREATED)
async def upload_meeting_audio(
    meeting_id: uuid.UUID,
    file: UploadFile = File(...),
    format: str = Form("wav"),
    sample_rate: int = Form(16000),
    channels: int = Form(1),
    auth_context: Dict[str, Any] = Depends(verify_authentication),
    db: AsyncSession = Depends(get_async_db),
) -> AudioResponse:
    """
    Upload and register audio recording payloads for meeting transcription and AI pipeline ingestion.
    """
    service = MeetingService(db)
    content = await file.read()
    file_name = file.filename or "meeting_audio.wav"

    audio = await service.upload_audio(
        meeting_id=meeting_id,
        file_name=file_name,
        content=content,
        format=format,
        sample_rate=sample_rate,
        channels=channels,
        auth_context=auth_context,
    )

    await _emit_lifecycle_event(
        meeting_id=meeting_id,
        event_type="audio_uploaded",
        payload={"audio_id": str(audio.id), "file_name": file_name, "size_bytes": len(content)},
    )

    return AudioResponse(
        id=audio.id,
        meeting_id=audio.meeting_id,
        file_path=audio.file_path,
        file_name=audio.file_name,
        file_size_bytes=audio.file_size_bytes,
        duration_seconds=audio.duration_seconds,
        format=audio.format,
        sample_rate=audio.sample_rate,
        channels=audio.channels,
        status=audio.status,
        created_at=audio.created_at,
    )


@router.post("/{meeting_id}/process", response_model=MeetingProcessingResponse, status_code=status.HTTP_200_OK)
async def process_meeting(
    meeting_id: uuid.UUID,
    payload: Optional[MeetingProcessingRequest] = Body(default=None),
    auth_context: Dict[str, Any] = Depends(verify_authentication),
    db: AsyncSession = Depends(get_async_db),
) -> MeetingProcessingResponse:
    """
    3. ACE INTEGRATION & PROCESSING LIFECYCLE:
    Initiates meeting processing request, validates lifecycle state transitions,
    invokes ACE via event-driven boundary, tracks status, and emits Redis events.
    """
    req = payload or MeetingProcessingRequest(meeting_id=meeting_id)
    req.meeting_id = meeting_id

    service = MeetingService(db)
    ace_orchestrator = get_ace_orchestrator(db)

    # Emit processing requested event
    await _emit_lifecycle_event(
        meeting_id=meeting_id,
        event_type="processing_requested",
        request_id=req.request_id,
        correlation_id=req.correlation_id,
        payload={"enable_analytics": req.enable_analytics, "enable_memory": req.enable_memory},
    )

    try:
        # Emit processing started event
        await _emit_lifecycle_event(
            meeting_id=meeting_id,
            event_type="processing_started",
            request_id=req.request_id,
            correlation_id=req.correlation_id,
        )

        response = await service.process_meeting(
            meeting_id=meeting_id,
            req=req,
            auth_context=auth_context,
            ace_orchestrator=ace_orchestrator,
        )

        if response.status == "completed":
            await _emit_lifecycle_event(
                meeting_id=meeting_id,
                event_type="processing_completed",
                request_id=req.request_id,
                correlation_id=req.correlation_id,
                payload={"status": "completed"},
            )
        else:
            await _emit_lifecycle_event(
                meeting_id=meeting_id,
                event_type="processing_failed",
                request_id=req.request_id,
                correlation_id=req.correlation_id,
                payload={"reason": response.message},
            )

        return response
    except Exception as ex:
        logger.error(f"Meeting processing endpoint error for meeting {meeting_id}: {ex}")
        await _emit_lifecycle_event(
            meeting_id=meeting_id,
            event_type="processing_failed",
            request_id=req.request_id,
            correlation_id=req.correlation_id,
            payload={"error": str(ex)},
        )
        raise BadRequestException(
            message=f"Meeting processing failed: {str(ex)}",
            code="MEETING_PROCESSING_FAILED",
        )


class MeetingUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    language: Optional[str] = None
    status: Optional[str] = None
    settings: Optional[Dict[str, Any]] = None


@router.put("/{meeting_id}", response_model=MeetingResponse, status_code=status.HTTP_200_OK)
async def update_meeting(
    meeting_id: uuid.UUID,
    payload: MeetingUpdate,
    auth_context: Dict[str, Any] = Depends(verify_authentication),
    db: AsyncSession = Depends(get_async_db),
) -> MeetingResponse:
    """Update meeting metadata and settings with scope enforcement."""
    service = MeetingService(db)
    meeting = await service.get_meeting(meeting_id, auth_context)
    
    update_data = payload.model_dump(exclude_unset=True) if hasattr(payload, "model_dump") else payload
    for k, v in update_data.items():
        if v is not None:
            setattr(meeting, k, v)
    
    await db.commit()
    updated = await service.get_meeting(meeting_id, auth_context)
    return _to_meeting_response(updated)


@router.delete("/{meeting_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_meeting(
    meeting_id: uuid.UUID,
    auth_context: Dict[str, Any] = Depends(verify_authentication),
    db: AsyncSession = Depends(get_async_db),
) -> None:
    """Delete or archive a meeting session with RBAC check."""
    service = MeetingService(db)
    meeting = await service.get_meeting(meeting_id, auth_context)
    
    if auth_context.get("role") != "admin" and str(meeting.host_id or "") != str(auth_context.get("user_id", "")):
        raise ForbiddenException(message="Only meeting host or admin can delete a meeting", code="FORBIDDEN")

    await db.delete(meeting)
    await db.commit()


@router.get("/{meeting_id}/transcript", status_code=status.HTTP_200_OK)
async def get_meeting_transcript(
    meeting_id: uuid.UUID,
    auth_context: Dict[str, Any] = Depends(verify_authentication),
    db: AsyncSession = Depends(get_async_db),
) -> List[Dict[str, Any]]:
    """Retrieve chronologically ordered transcript segments and speaker turns for a meeting."""
    service = MeetingService(db)
    meeting = await service.get_meeting(meeting_id, auth_context)

    segments = sorted(meeting.transcript_segments or [], key=lambda s: s.sequence_number)
    return [
        {
            "segment_id": str(s.id),
            "meeting_id": str(s.meeting_id),
            "speaker_label": s.speaker_label,
            "start_time_ms": s.start_time_ms,
            "end_time_ms": s.end_time_ms,
            "language": s.language,
            "original_text": s.original_text,
            "translated_text": s.translated_text,
            "confidence": s.confidence,
            "sequence_number": s.sequence_number,
        }
        for s in segments
    ]


@router.get("/{meeting_id}/analytics", status_code=status.HTTP_200_OK)
async def get_meeting_analytics(
    meeting_id: uuid.UUID,
    auth_context: Dict[str, Any] = Depends(verify_authentication),
    db: AsyncSession = Depends(get_async_db),
) -> Dict[str, Any]:
    """Retrieve quantitative meeting analytics, speaker participation, and interaction scores."""
    service = MeetingService(db)
    meeting = await service.get_meeting(meeting_id, auth_context)

    analytics = meeting.analytics
    if not analytics:
        return {
            "meeting_id": str(meeting.id),
            "speaking_time_distribution": {},
            "collaboration_score": 0.0,
            "participation_index": 0.0,
            "sentiment_score": 0.0,
            "productivity_score": 0.0,
            "topic_keywords": [],
            "summary_metrics": {},
        }

    return {
        "meeting_id": str(meeting.id),
        "speaking_time_distribution": analytics.speaking_time_distribution or {},
        "collaboration_score": analytics.collaboration_score,
        "participation_index": analytics.participation_index,
        "sentiment_score": analytics.sentiment_score,
        "productivity_score": analytics.productivity_score,
        "sentiment_distribution": analytics.sentiment_distribution or {},
        "engagement_score": analytics.engagement_score,
        "pace_wpm": analytics.pace_wpm,
        "turn_taking_metrics": analytics.turn_taking_metrics or {},
        "topic_keywords": analytics.topic_keywords or [],
        "summary_metrics": analytics.summary_metrics or {},
    }


@router.post("/{meeting_id}/schedule", response_model=MeetingResponse, status_code=status.HTTP_200_OK)
async def schedule_meeting_endpoint(
    meeting_id: uuid.UUID,
    payload: MeetingScheduleRequest,
    auth_context: Dict[str, Any] = Depends(verify_authentication),
    db: AsyncSession = Depends(get_async_db),
) -> MeetingResponse:
    """Schedule a meeting with timezone-aware start time and duration."""
    service = MeetingService(db)
    meeting = await service.schedule_meeting(
        meeting_id=meeting_id,
        scheduled_start=payload.scheduled_start,
        duration_minutes=payload.duration_minutes,
        timezone=payload.timezone,
        auth_context=auth_context,
    )
    return _to_meeting_response(meeting)


@router.post("/{meeting_id}/reschedule", response_model=MeetingResponse, status_code=status.HTTP_200_OK)
async def reschedule_meeting_endpoint(
    meeting_id: uuid.UUID,
    payload: MeetingRescheduleRequest,
    auth_context: Dict[str, Any] = Depends(verify_authentication),
    db: AsyncSession = Depends(get_async_db),
) -> MeetingResponse:
    """Reschedule an existing meeting to a new start time."""
    service = MeetingService(db)
    meeting = await service.reschedule_meeting(
        meeting_id=meeting_id,
        new_scheduled_start=payload.scheduled_start,
        duration_minutes=payload.duration_minutes,
        timezone=payload.timezone,
        auth_context=auth_context,
    )
    return _to_meeting_response(meeting)


@router.post("/{meeting_id}/cancel", response_model=MeetingResponse, status_code=status.HTTP_200_OK)
async def cancel_meeting_endpoint(
    meeting_id: uuid.UUID,
    payload: Optional[MeetingCancelRequest] = None,
    auth_context: Dict[str, Any] = Depends(verify_authentication),
    db: AsyncSession = Depends(get_async_db),
) -> MeetingResponse:
    """Cancel a meeting with optional reason."""
    service = MeetingService(db)
    reason = payload.reason if payload else None
    meeting = await service.cancel_meeting(
        meeting_id=meeting_id,
        reason=reason,
        auth_context=auth_context,
    )
    return _to_meeting_response(meeting)


@router.post("/{meeting_id}/start", response_model=MeetingResponse, status_code=status.HTTP_200_OK)
async def start_meeting_endpoint(
    meeting_id: uuid.UUID,
    auth_context: Dict[str, Any] = Depends(verify_authentication),
    db: AsyncSession = Depends(get_async_db),
) -> MeetingResponse:
    """Transition meeting status from scheduled/created to active (live)."""
    service = MeetingService(db)
    meeting = await service.start_meeting(
        meeting_id=meeting_id,
        auth_context=auth_context,
    )
    return _to_meeting_response(meeting)

