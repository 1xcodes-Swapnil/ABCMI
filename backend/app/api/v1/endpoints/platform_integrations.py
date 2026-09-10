"""
Platform Integration API Router
Implements backend endpoints for provider connections, status checks, meeting mapping,
and Live Google Meet & Microsoft Teams meeting ingestion and observation.
"""

from typing import Any, Dict, List, Optional
import uuid
from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_async_db, verify_authentication
from app.core.logging import get_logger
from app.schemas.platform_integration import (
    ExternalMeetingPayload,
    ExternalMeetingReferenceResponse,
    LiveMeetingCapabilityResponse,
    LiveMeetingJoinByUrlRequest,
    LiveMeetingJoinRequest,
    LiveMeetingLeaveRequest,
    LiveMeetingSessionResponse,
    LiveTranscriptIngestRequest,
    PlatformConnectRequest,
    PlatformConnectionResponse,
    PlatformWebhookEventPayload,
)
from app.services.platform_integration_service import PlatformIntegrationService
from app.services.platform_provider import provider_registry

logger = get_logger(__name__)

router = APIRouter(prefix="/integrations", tags=["Platform Integrations"])


@router.get("/platforms", response_model=List[str], status_code=status.HTTP_200_OK)
async def list_supported_platforms(
    auth_context: Dict[str, Any] = Depends(verify_authentication),
) -> List[str]:
    """List all supported external platform integration providers."""
    return provider_registry.list_providers()


@router.get("/connections", response_model=List[PlatformConnectionResponse], status_code=status.HTTP_200_OK)
async def list_user_connections(
    auth_context: Dict[str, Any] = Depends(verify_authentication),
    db: AsyncSession = Depends(get_async_db),
) -> List[PlatformConnectionResponse]:
    """List all platform connections for the authenticated user."""
    service = PlatformIntegrationService(db)
    connections = await service.list_connections(auth_context)
    return connections  # type: ignore


@router.post("/{provider}/connect", response_model=PlatformConnectionResponse, status_code=status.HTTP_200_OK)
async def connect_platform(
    provider: str,
    payload: Optional[PlatformConnectRequest] = None,
    auth_context: Dict[str, Any] = Depends(verify_authentication),
    db: AsyncSession = Depends(get_async_db),
) -> PlatformConnectionResponse:
    """Authorize and establish connection with a platform provider."""
    service = PlatformIntegrationService(db)
    code = payload.auth_code if payload else None
    meta = payload.credentials_metadata if payload else {}
    connection = await service.connect_provider(provider, code, meta, auth_context)
    return connection  # type: ignore


@router.post("/{provider}/disconnect", response_model=PlatformConnectionResponse, status_code=status.HTTP_200_OK)
async def disconnect_platform(
    provider: str,
    auth_context: Dict[str, Any] = Depends(verify_authentication),
    db: AsyncSession = Depends(get_async_db),
) -> PlatformConnectionResponse:
    """Disconnect and revoke connection with a platform provider."""
    service = PlatformIntegrationService(db)
    connection = await service.disconnect_provider(provider, auth_context)
    return connection  # type: ignore


@router.get("/{provider}/status", response_model=PlatformConnectionResponse, status_code=status.HTTP_200_OK)
async def get_platform_connection_status(
    provider: str,
    auth_context: Dict[str, Any] = Depends(verify_authentication),
    db: AsyncSession = Depends(get_async_db),
) -> PlatformConnectionResponse:
    """Retrieve connection status and metadata for a provider."""
    service = PlatformIntegrationService(db)
    connection = await service.get_connection_status(provider, auth_context)
    return connection  # type: ignore


@router.get("/{provider}/live/capabilities", response_model=LiveMeetingCapabilityResponse, status_code=status.HTTP_200_OK)
async def get_live_capabilities(
    provider: str,
    auth_context: Dict[str, Any] = Depends(verify_authentication),
    db: AsyncSession = Depends(get_async_db),
) -> LiveMeetingCapabilityResponse:
    """Check live streaming, audio capture, and caption capabilities for a platform provider."""
    service = PlatformIntegrationService(db)
    capabilities = await service.get_live_capability(provider, auth_context)
    return capabilities  # type: ignore


@router.post("/live/join-url", response_model=LiveMeetingSessionResponse, status_code=status.HTTP_200_OK)
async def join_live_meeting_by_url_endpoint(
    payload: LiveMeetingJoinByUrlRequest,
    auth_context: Dict[str, Any] = Depends(verify_authentication),
    db: AsyncSession = Depends(get_async_db),
) -> LiveMeetingSessionResponse:
    """Connect ABCI-MI live observer directly via Google Meet or Microsoft Teams meeting URL."""
    service = PlatformIntegrationService(db)
    session = await service.join_live_meeting_by_url(
        meeting_url=payload.meeting_url,
        stream_mode=payload.stream_mode,
        language=payload.language,
        auto_record=payload.auto_record,
        observer_name=payload.observer_name,
        auth_context=auth_context,
    )
    return session  # type: ignore


@router.post("/live/transcript", status_code=status.HTTP_200_OK)
async def ingest_live_transcript_endpoint(
    payload: LiveTranscriptIngestRequest,
    auth_context: Dict[str, Any] = Depends(verify_authentication),
    db: AsyncSession = Depends(get_async_db),
) -> Dict[str, Any]:
    """Ingest a real-time transcript segment utterance from active Google Meet or Microsoft Teams live stream."""
    service = PlatformIntegrationService(db)
    result = await service.ingest_live_transcript(payload, auth_context)
    return result


@router.post("/{provider}/live/join", response_model=LiveMeetingSessionResponse, status_code=status.HTTP_200_OK)
async def join_live_platform_meeting_endpoint(
    provider: str,
    payload: LiveMeetingJoinRequest,
    auth_context: Dict[str, Any] = Depends(verify_authentication),
    db: AsyncSession = Depends(get_async_db),
) -> LiveMeetingSessionResponse:
    """Connect ABCI-MI live observer into an active Google Meet or Microsoft Teams meeting."""
    service = PlatformIntegrationService(db)
    session = await service.join_live_meeting(
        provider_name=provider,
        external_meeting_id=payload.external_meeting_id,
        meeting_url=payload.meeting_url,
        stream_mode=payload.stream_mode,
        language=payload.language,
        auto_record=payload.auto_record,
        observer_name=payload.observer_name,
        auth_context=auth_context,
    )
    return session  # type: ignore


@router.post("/{provider}/live/transcript", status_code=status.HTTP_200_OK)
async def ingest_provider_live_transcript_endpoint(
    provider: str,
    payload: LiveTranscriptIngestRequest,
    auth_context: Dict[str, Any] = Depends(verify_authentication),
    db: AsyncSession = Depends(get_async_db),
) -> Dict[str, Any]:
    """Ingest a real-time transcript segment utterance for a specific provider."""
    service = PlatformIntegrationService(db)
    result = await service.ingest_live_transcript(payload, auth_context)
    return result


@router.post("/{provider}/live/leave", status_code=status.HTTP_200_OK)
async def leave_live_platform_meeting_endpoint(
    provider: str,
    payload: LiveMeetingLeaveRequest,
    auth_context: Dict[str, Any] = Depends(verify_authentication),
    db: AsyncSession = Depends(get_async_db),
) -> Dict[str, Any]:
    """Disconnect ABCI-MI observer from active Google Meet or Microsoft Teams meeting."""
    service = PlatformIntegrationService(db)
    result = await service.leave_live_meeting(
        provider_name=provider,
        external_meeting_id=payload.external_meeting_id,
        session_id=payload.session_id,
        finalize_transcription=payload.finalize_transcription,
        auth_context=auth_context,
    )
    return result


@router.post("/{provider}/meetings/map", response_model=ExternalMeetingReferenceResponse, status_code=status.HTTP_201_CREATED)
async def map_external_meeting_endpoint(
    provider: str,
    payload: ExternalMeetingPayload,
    auth_context: Dict[str, Any] = Depends(verify_authentication),
    db: AsyncSession = Depends(get_async_db),
) -> ExternalMeetingReferenceResponse:
    """Map an external platform meeting to an internal ABCI-MI meeting."""
    service = PlatformIntegrationService(db)
    _, _, ref = await service.map_external_meeting(
        provider_name=provider,
        external_meeting_id=payload.external_meeting_id,
        external_event_id=payload.external_event_id,
        title=payload.title,
        scheduled_start=payload.scheduled_start,
        duration_minutes=payload.duration_minutes or 60,
        timezone_str=payload.timezone or "UTC",
        external_metadata=payload.external_metadata,
        auth_context=auth_context,
    )
    return ref  # type: ignore


@router.post("/webhooks/{provider}", status_code=status.HTTP_200_OK)
async def handle_platform_webhook(
    provider: str,
    payload: PlatformWebhookEventPayload,
    db: AsyncSession = Depends(get_async_db),
) -> Dict[str, Any]:
    """Normalized webhook receiver endpoint for external platform providers."""
    service = PlatformIntegrationService(db)
    result = await service.handle_webhook_event(
        provider_name=provider,
        event_type=payload.event_type,
        external_meeting_id=payload.external_meeting_id,
        external_event_id=payload.external_event_id,
        timestamp=payload.timestamp,
        payload=payload.payload,
        correlation_id=payload.correlation_id,
    )
    return result
