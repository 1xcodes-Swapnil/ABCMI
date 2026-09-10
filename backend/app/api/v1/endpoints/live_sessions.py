"""
Live Meeting & Streaming Ingestion API Router
Implements backend endpoints for live session lifecycle management, chunk ingestion, and status monitoring.
"""

from typing import Any, Dict, Optional
import uuid
from fastapi import APIRouter, Depends, File, Form, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_async_db, verify_authentication
from app.core.logging import get_logger
from app.schemas.live_session import (
    AudioChunkResponse,
    LiveSessionResponse,
    LiveSessionStartRequest,
    LiveSessionStatusResponse,
)
from app.services.live_session_service import LiveSessionService

logger = get_logger(__name__)

router = APIRouter(prefix="/meetings/{meeting_id}/live", tags=["Live Meeting Streaming"])


@router.post("/start", response_model=LiveSessionResponse, status_code=status.HTTP_201_CREATED)
async def start_live_session(
    meeting_id: uuid.UUID,
    payload: Optional[LiveSessionStartRequest] = None,
    auth_context: Dict[str, Any] = Depends(verify_authentication),
    db: AsyncSession = Depends(get_async_db),
) -> LiveSessionResponse:
    """Start or create a live streaming session for a meeting."""
    service = LiveSessionService(db)
    lang = payload.language if payload else "en"
    meta = payload.session_metadata if payload else {}
    session = await service.start_session(meeting_id, auth_context, language=lang, session_metadata=meta)
    return session  # type: ignore


@router.post("/pause", response_model=LiveSessionResponse, status_code=status.HTTP_200_OK)
async def pause_live_session(
    meeting_id: uuid.UUID,
    auth_context: Dict[str, Any] = Depends(verify_authentication),
    db: AsyncSession = Depends(get_async_db),
) -> LiveSessionResponse:
    """Pause an active live streaming session."""
    service = LiveSessionService(db)
    session = await service.pause_session(meeting_id, auth_context)
    return session  # type: ignore


@router.post("/resume", response_model=LiveSessionResponse, status_code=status.HTTP_200_OK)
async def resume_live_session(
    meeting_id: uuid.UUID,
    auth_context: Dict[str, Any] = Depends(verify_authentication),
    db: AsyncSession = Depends(get_async_db),
) -> LiveSessionResponse:
    """Resume a paused live streaming session."""
    service = LiveSessionService(db)
    session = await service.resume_session(meeting_id, auth_context)
    return session  # type: ignore


@router.post("/stop", response_model=LiveSessionResponse, status_code=status.HTTP_200_OK)
async def stop_live_session(
    meeting_id: uuid.UUID,
    auth_context: Dict[str, Any] = Depends(verify_authentication),
    db: AsyncSession = Depends(get_async_db),
) -> LiveSessionResponse:
    """Stop and finalize a live streaming session."""
    service = LiveSessionService(db)
    session = await service.stop_session(meeting_id, auth_context)
    return session  # type: ignore


@router.post("/chunks", response_model=AudioChunkResponse, status_code=status.HTTP_201_CREATED)
async def ingest_audio_chunk(
    meeting_id: uuid.UUID,
    sequence_number: int = Form(...),
    timestamp_start_ms: int = Form(0),
    timestamp_end_ms: int = Form(0),
    checksum: Optional[str] = Form(None),
    file: UploadFile = File(...),
    auth_context: Dict[str, Any] = Depends(verify_authentication),
    db: AsyncSession = Depends(get_async_db),
) -> AudioChunkResponse:
    """Ingest a sequential audio chunk for the active live session."""
    service = LiveSessionService(db)
    file_bytes = await file.read()
    chunk, _ = await service.ingest_chunk(
        meeting_id=meeting_id,
        sequence_number=sequence_number,
        timestamp_start_ms=timestamp_start_ms,
        timestamp_end_ms=timestamp_end_ms,
        file_bytes=file_bytes,
        filename=file.filename or "chunk.wav",
        auth_context=auth_context,
        checksum=checksum,
    )
    return chunk  # type: ignore


@router.get("/status", response_model=LiveSessionStatusResponse, status_code=status.HTTP_200_OK)
async def get_live_session_status(
    meeting_id: uuid.UUID,
    auth_context: Dict[str, Any] = Depends(verify_authentication),
    db: AsyncSession = Depends(get_async_db),
) -> LiveSessionStatusResponse:
    """Retrieve live session status, chunk metrics, and recent activity."""
    service = LiveSessionService(db)
    status_data = await service.get_session_status(meeting_id, auth_context)
    return status_data  # type: ignore
