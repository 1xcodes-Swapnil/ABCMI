"""
Platform Integration Service
Manages provider connections, external meeting mappings, synchronization,
live Google Meet and Microsoft Teams meeting joining, observation, and webhook events.
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
import uuid
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import BadRequestException, ForbiddenException, NotFoundException
from app.core.logging import get_logger
from app.events.redis_bus import RedisEventBus, get_event_bus
from app.models.live_session import LiveSession
from app.models.meeting import Meeting
from app.models.platform_integration import PlatformConnection, ExternalMeetingReference
from app.repositories.meeting_repo import MeetingRepository
from app.schemas.platform_integration import LiveTranscriptIngestRequest
from app.services.live_meeting_ingestion_service import LiveMeetingIngestionService
from app.services.meeting_url_parser import MeetingURLParser
from app.services.platform_provider import provider_registry, LiveMeetingAdapter

logger = get_logger(__name__)


class PlatformIntegrationService:
    """Service handling platform integrations, connections, and external meeting sync."""

    def __init__(self, db: AsyncSession, event_bus: Optional[RedisEventBus] = None):
        self.db = db
        self.meeting_repo = MeetingRepository(db)
        self.event_bus = event_bus or get_event_bus()
        self.ingestion_service = LiveMeetingIngestionService(db, event_bus=self.event_bus)

    async def connect_provider(
        self,
        provider_name: str,
        auth_code: Optional[str],
        credentials_metadata: Optional[Dict[str, Any]],
        auth_context: Dict[str, Any],
    ) -> PlatformConnection:
        provider = provider_registry.get(provider_name)
        user_id_str = auth_context.get("user_id")
        if not user_id_str:
            raise ForbiddenException(message="User authentication required for platform connection", code="UNAUTHORIZED")
        user_id = uuid.UUID(user_id_str)

        # Authorize provider
        auth_result = await provider.authorize(auth_code, credentials_metadata)

        # Check existing connection
        stmt = select(PlatformConnection).where(
            PlatformConnection.user_id == user_id,
            PlatformConnection.provider == provider.provider_name,
        )
        result = await self.db.execute(stmt)
        connection = result.scalars().first()

        access_token = auth_result.get("access_token")
        refresh_token = auth_result.get("refresh_token")
        expires_at_ts = auth_result.get("expires_at")
        expires_at = datetime.fromtimestamp(expires_at_ts, tz=timezone.utc) if expires_at_ts else None

        if connection:
            connection.status = "connected"
            connection.encrypted_access_token = access_token
            connection.encrypted_refresh_token = refresh_token
            connection.token_expires_at = expires_at
            connection.connection_metadata = credentials_metadata or {}
            connection.correlation_id = auth_context.get("correlation_id") or str(uuid.uuid4())
            await self.db.commit()
            await self.db.refresh(connection)
        else:
            connection = PlatformConnection(
                user_id=user_id,
                provider=provider.provider_name,
                status="connected",
                encrypted_access_token=access_token,
                encrypted_refresh_token=refresh_token,
                token_expires_at=expires_at,
                connection_metadata=credentials_metadata or {},
                correlation_id=auth_context.get("correlation_id") or str(uuid.uuid4()),
            )
            self.db.add(connection)
            await self.db.commit()
            await self.db.refresh(connection)

        await self.event_bus.publish(
            f"events:integrations:{provider.provider_name}",
            {
                "event_type": "PlatformConnected",
                "provider": provider.provider_name,
                "user_id": str(user_id),
                "connection_id": str(connection.id),
                "status": connection.status,
            },
        )
        return connection

    async def disconnect_provider(
        self,
        provider_name: str,
        auth_context: Dict[str, Any],
    ) -> PlatformConnection:
        provider = provider_registry.get(provider_name)
        user_id_str = auth_context.get("user_id")
        if not user_id_str:
            raise ForbiddenException(message="User authentication required", code="UNAUTHORIZED")
        user_id = uuid.UUID(user_id_str)

        stmt = select(PlatformConnection).where(
            PlatformConnection.user_id == user_id,
            PlatformConnection.provider == provider.provider_name,
        )
        result = await self.db.execute(stmt)
        connection = result.scalars().first()
        if not connection:
            raise NotFoundException(message=f"No connection found for provider '{provider_name}'", code="CONNECTION_NOT_FOUND")

        connection.status = "disconnected"
        connection.encrypted_access_token = None
        connection.encrypted_refresh_token = None
        await self.db.commit()
        await self.db.refresh(connection)

        await self.event_bus.publish(
            f"events:integrations:{provider.provider_name}",
            {
                "event_type": "PlatformDisconnected",
                "provider": provider.provider_name,
                "user_id": str(user_id),
                "connection_id": str(connection.id),
            },
        )
        return connection

    async def get_connection_status(
        self,
        provider_name: str,
        auth_context: Dict[str, Any],
    ) -> PlatformConnection:
        provider = provider_registry.get(provider_name)
        user_id_str = auth_context.get("user_id")
        if not user_id_str:
            raise ForbiddenException(message="User authentication required", code="UNAUTHORIZED")
        user_id = uuid.UUID(user_id_str)

        stmt = select(PlatformConnection).where(
            PlatformConnection.user_id == user_id,
            PlatformConnection.provider == provider.provider_name,
        )
        result = await self.db.execute(stmt)
        connection = result.scalars().first()
        if not connection:
            raise NotFoundException(message=f"No connection found for provider '{provider_name}'", code="CONNECTION_NOT_FOUND")
        return connection

    async def list_connections(self, auth_context: Dict[str, Any]) -> List[PlatformConnection]:
        user_id_str = auth_context.get("user_id")
        if not user_id_str:
            raise ForbiddenException(message="User authentication required", code="UNAUTHORIZED")
        user_id = uuid.UUID(user_id_str)

        stmt = select(PlatformConnection).where(PlatformConnection.user_id == user_id)
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def map_external_meeting(
        self,
        provider_name: str,
        external_meeting_id: str,
        external_event_id: Optional[str],
        title: str,
        scheduled_start: datetime,
        duration_minutes: int,
        timezone_str: str,
        external_metadata: Optional[Dict[str, Any]],
        auth_context: Dict[str, Any],
    ) -> Tuple[PlatformConnection, Meeting, ExternalMeetingReference]:
        user_id_str = auth_context.get("user_id")
        if not user_id_str:
            raise ForbiddenException(message="User authentication required", code="UNAUTHORIZED")
        user_id = uuid.UUID(user_id_str)

        provider = provider_registry.get(provider_name)

        # Get or verify connection
        stmt = select(PlatformConnection).where(
            PlatformConnection.user_id == user_id,
            PlatformConnection.provider == provider.provider_name,
        )
        result = await self.db.execute(stmt)
        connection = result.scalars().first()
        if not connection or connection.status != "connected":
            raise BadRequestException(message=f"Active connection to '{provider_name}' is required to map meetings", code="PROVIDER_NOT_CONNECTED")

        # Create internal ABCI-MI meeting
        meeting = Meeting(
            title=title,
            scheduled_start=scheduled_start,
            duration_minutes=duration_minutes,
            timezone=timezone_str,
            host_id=user_id,
            status="scheduled",
            settings=external_metadata or {},
        )
        meeting = await self.meeting_repo.create(meeting)
        await self.db.commit()

        # Create external meeting reference
        ref = ExternalMeetingReference(
            connection_id=connection.id,
            meeting_id=meeting.id,
            external_meeting_id=external_meeting_id,
            external_event_id=external_event_id,
            external_metadata=external_metadata or {},
            sync_status="synced",
            correlation_id=auth_context.get("correlation_id") or str(uuid.uuid4()),
        )
        self.db.add(ref)
        await self.db.commit()
        await self.db.refresh(ref)

        await self.event_bus.publish(
            f"events:integrations:{provider.provider_name}",
            {
                "event_type": "PlatformMeetingLinked",
                "provider": provider.provider_name,
                "meeting_id": str(meeting.id),
                "external_meeting_id": external_meeting_id,
            },
        )
        return connection, meeting, ref

    async def get_live_capability(
        self,
        provider_name: str,
        auth_context: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Queries live media capabilities for a platform provider."""
        provider = provider_registry.get(provider_name)
        if not isinstance(provider, LiveMeetingAdapter):
            raise BadRequestException(
                message=f"Provider '{provider_name}' does not support live meeting streaming",
                code="LIVE_STREAMING_UNSUPPORTED",
            )
        
        # Check if user has credentials metadata or stored connection tokens
        user_id_str = auth_context.get("user_id")
        conn_meta = {}
        credentials = {}
        if user_id_str:
            try:
                user_id = uuid.UUID(user_id_str)
                stmt = select(PlatformConnection).where(
                    PlatformConnection.user_id == user_id,
                    PlatformConnection.provider == provider.provider_name,
                )
                res = await self.db.execute(stmt)
                conn = res.scalars().first()
                if conn:
                    conn_meta = conn.connection_metadata or {}
                    if conn.encrypted_access_token:
                        credentials["access_token"] = conn.encrypted_access_token
            except Exception:
                pass

        capabilities = await provider.check_raw_media_capability(credentials=credentials, connection_metadata=conn_meta)
        return capabilities

    async def join_live_meeting_by_url(
        self,
        meeting_url: str,
        stream_mode: str,
        language: str,
        auto_record: bool,
        observer_name: Optional[str],
        auth_context: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Parses meeting URL, auto-discovers provider, and joins live meeting.
        """
        parsed = MeetingURLParser.parse(meeting_url)
        return await self.join_live_meeting(
            provider_name=parsed.provider,
            external_meeting_id=parsed.external_meeting_id,
            meeting_url=parsed.canonical_url,
            stream_mode=stream_mode,
            language=language,
            auto_record=auto_record,
            observer_name=observer_name,
            auth_context=auth_context,
        )

    async def join_live_meeting(
        self,
        provider_name: str,
        external_meeting_id: Optional[str],
        meeting_url: Optional[str],
        stream_mode: str,
        language: str,
        auto_record: bool,
        observer_name: Optional[str],
        auth_context: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Connects or joins ABCI-MI live observer into a Google Meet or Microsoft Teams meeting.
        """
        provider = provider_registry.get(provider_name)
        if not isinstance(provider, LiveMeetingAdapter):
            raise BadRequestException(
                message=f"Provider '{provider_name}' does not support live meeting streaming",
                code="LIVE_STREAMING_UNSUPPORTED",
            )

        # Parse & validate URL or meeting ID
        raw_input = meeting_url or external_meeting_id or ""
        parsed = MeetingURLParser.parse(raw_input, expected_provider=provider.provider_name)
        resolved_external_id = parsed.external_meeting_id
        canonical_url = parsed.canonical_url

        user_id_str = auth_context.get("user_id")
        user_id = uuid.UUID(user_id_str) if user_id_str else uuid.uuid4()
        tenant_id = auth_context.get("tenant_id", "default")

        # Fetch stored connection tokens if available
        credentials: Dict[str, Any] = {}
        if user_id_str:
            try:
                conn_stmt = select(PlatformConnection).where(
                    PlatformConnection.user_id == user_id,
                    PlatformConnection.provider == provider.provider_name,
                )
                c_res = await self.db.execute(conn_stmt)
                conn = c_res.scalars().first()
                if conn and conn.encrypted_access_token:
                    credentials["access_token"] = conn.encrypted_access_token
            except Exception:
                pass

        # Check or create internal meeting record
        stmt = select(ExternalMeetingReference).where(
            ExternalMeetingReference.external_meeting_id == resolved_external_id
        )
        result = await self.db.execute(stmt)
        ref = result.scalars().first()

        if ref:
            meeting = await self.meeting_repo.get_by_id(ref.meeting_id)
            meeting_id = ref.meeting_id
        else:
            meeting_title = f"{provider.provider_name.replace('_', ' ').title()} Live Meeting ({resolved_external_id})"
            meeting = Meeting(
                title=meeting_title,
                scheduled_start=datetime.now(timezone.utc),
                duration_minutes=60,
                timezone="UTC",
                host_id=user_id,
                status="live",
                settings={"stream_mode": stream_mode, "language": language, "meeting_url": canonical_url},
            )
            meeting = await self.meeting_repo.create(meeting)
            await self.db.commit()
            meeting_id = meeting.id

            # Create reference mapping
            ref = ExternalMeetingReference(
                connection_id=conn.id if 'conn' in locals() and conn else None,
                meeting_id=meeting_id,
                external_meeting_id=resolved_external_id,
                external_metadata={"canonical_url": canonical_url},
                sync_status="live_joined",
                correlation_id=auth_context.get("correlation_id") or str(uuid.uuid4()),
            )
            self.db.add(ref)
            await self.db.commit()

        # Invoke adapter live session join
        join_options = {
            "stream_mode": stream_mode,
            "language": language,
            "auto_record": auto_record,
            "observer_name": observer_name or "ABCI-MI Observer",
            "meeting_url": canonical_url,
        }
        session_info = await provider.join_live_session(resolved_external_id, credentials=credentials, join_options=join_options)
        session_id = session_info.get("session_id", str(uuid.uuid4()))

        # Create or update LiveSession model
        sess_stmt = select(LiveSession).where(LiveSession.meeting_id == meeting_id)
        sess_res = await self.db.execute(sess_stmt)
        live_session = sess_res.scalars().first()

        if not live_session:
            live_session = LiveSession(
                tenant_id=tenant_id,
                meeting_id=meeting_id,
                provider=provider.provider_name,
                external_meeting_id=resolved_external_id,
                meeting_url=canonical_url,
                session_id=session_id,
                status="connected",
                language=language,
                media_mode=stream_mode,
                transcript_source="hybrid",
                connected_at=datetime.now(timezone.utc),
                started_at=datetime.now(timezone.utc),
                participant_count=len(session_info.get("participants", [])),
                correlation_id=auth_context.get("correlation_id") or str(uuid.uuid4()),
            )
            self.db.add(live_session)
        else:
            live_session.status = "connected"
            live_session.provider = provider.provider_name
            live_session.external_meeting_id = resolved_external_id
            live_session.meeting_url = canonical_url
            live_session.session_id = session_id
            live_session.connected_at = datetime.now(timezone.utc)
            live_session.participant_count = len(session_info.get("participants", []))

        await self.db.commit()

        # Publish Redis integration events
        join_event_data = {
            "event_type": "LiveMeetingConnected",
            "provider": provider.provider_name,
            "external_meeting_id": resolved_external_id,
            "meeting_id": str(meeting_id),
            "session_id": session_id,
            "stream_mode": stream_mode,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "correlation_id": auth_context.get("correlation_id"),
        }
        await self.event_bus.publish(f"events:integrations:{provider.provider_name}", join_event_data)
        await self.event_bus.publish(f"events:meetings:{meeting_id}:live", join_event_data)

        start_event_data = {
            "event_type": "LiveMeetingStarted",
            "provider": provider.provider_name,
            "external_meeting_id": resolved_external_id,
            "meeting_id": str(meeting_id),
            "session_id": session_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        await self.event_bus.publish(f"events:meetings:{meeting_id}:live", start_event_data)

        return {
            "session_id": session_id,
            "meeting_id": meeting_id,
            "external_meeting_id": resolved_external_id,
            "provider": provider.provider_name,
            "status": "connected",
            "stream_mode": stream_mode,
            "joined_at": session_info.get("joined_at", datetime.now(timezone.utc).isoformat()),
            "meeting_url": canonical_url,
            "participants": session_info.get("participants", []),
            "chunks_received": 0,
            "diarization_active": True,
            "correlation_id": auth_context.get("correlation_id"),
        }

    async def leave_live_meeting(
        self,
        provider_name: str,
        external_meeting_id: str,
        session_id: Optional[str],
        finalize_transcription: bool,
        auth_context: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Disconnects ABCI-MI live observer from the Google Meet or Microsoft Teams meeting.
        """
        provider = provider_registry.get(provider_name)
        if not isinstance(provider, LiveMeetingAdapter):
            raise BadRequestException(
                message=f"Provider '{provider_name}' does not support live meeting streaming",
                code="LIVE_STREAMING_UNSUPPORTED",
            )

        parsed = MeetingURLParser.parse(external_meeting_id, expected_provider=provider.provider_name)
        resolved_external_id = parsed.external_meeting_id

        success = await provider.leave_live_session(resolved_external_id, credentials={}, session_id=session_id)

        # Update LiveSession model if present
        ref_stmt = select(ExternalMeetingReference).where(
            ExternalMeetingReference.external_meeting_id == resolved_external_id
        )
        ref_res = await self.db.execute(ref_stmt)
        ref = ref_res.scalars().first()
        meeting_id = ref.meeting_id if ref else None

        if meeting_id:
            sess_stmt = select(LiveSession).where(LiveSession.meeting_id == meeting_id)
            sess_res = await self.db.execute(sess_stmt)
            live_sess = sess_res.scalars().first()
            if live_sess:
                live_sess.status = "completed"
                live_sess.disconnected_at = datetime.now(timezone.utc)
                live_sess.stopped_at = datetime.now(timezone.utc)
                await self.db.commit()

        # Publish LiveMeetingDisconnected event
        leave_event = {
            "event_type": "LiveMeetingDisconnected",
            "provider": provider.provider_name,
            "external_meeting_id": resolved_external_id,
            "session_id": session_id,
            "meeting_id": str(meeting_id) if meeting_id else None,
            "finalize_transcription": finalize_transcription,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        await self.event_bus.publish(f"events:integrations:{provider.provider_name}", leave_event)
        if meeting_id:
            await self.event_bus.publish(f"events:meetings:{meeting_id}:live", leave_event)

        return {
            "status": "disconnected",
            "provider": provider.provider_name,
            "external_meeting_id": resolved_external_id,
            "session_id": session_id,
            "finalized": finalize_transcription,
        }

    async def ingest_live_transcript(
        self,
        payload: LiveTranscriptIngestRequest,
        auth_context: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Routes incoming real-time transcript utterances from Google Meet or Teams to the ingestion pipeline.
        """
        # Resolve meeting by external reference
        stmt = select(ExternalMeetingReference).where(
            ExternalMeetingReference.external_meeting_id == payload.external_meeting_id
        )
        res = await self.db.execute(stmt)
        ref = res.scalars().first()
        if not ref:
            raise NotFoundException(
                message=f"No active meeting found mapped to external ID '{payload.external_meeting_id}'",
                code="MEETING_NOT_FOUND",
            )

        return await self.ingestion_service.ingest_transcript_segment(
            meeting_id=ref.meeting_id,
            payload=payload,
            auth_context=auth_context,
        )

    async def handle_webhook_event(
        self,
        provider_name: str,
        event_type: str,
        external_meeting_id: str,
        external_event_id: Optional[str],
        timestamp: datetime,
        payload: Dict[str, Any],
        correlation_id: Optional[str],
    ) -> Dict[str, Any]:
        """Handles incoming webhook events from platform providers idempotently."""
        provider = provider_registry.get(provider_name)

        # Find existing mapping
        stmt = select(ExternalMeetingReference).where(
            ExternalMeetingReference.external_meeting_id == external_meeting_id
        )
        result = await self.db.execute(stmt)
        ref = result.scalars().first()

        await self.event_bus.publish(
            f"events:integrations:{provider.provider_name}",
            {
                "event_type": "PlatformEventReceived",
                "provider": provider.provider_name,
                "event_subtype": event_type,
                "external_meeting_id": external_meeting_id,
                "meeting_id": str(ref.meeting_id) if ref else None,
            },
        )

        if not ref:
            logger.info("Received webhook event for unmapped external meeting %s", external_meeting_id)
            return {"status": "ignored_unmapped", "external_meeting_id": external_meeting_id}

        meeting = await self.meeting_repo.get_by_id(ref.meeting_id)
        if not meeting:
            raise NotFoundException(message=f"Meeting reference points to non-existent meeting {ref.meeting_id}", code="MEETING_NOT_FOUND")

        if event_type in {"meeting.cancelled", "cancelled"}:
            meeting.status = "cancelled"
            ref.sync_status = "cancelled"
            await self.db.commit()
            await self.event_bus.publish(
                f"events:integrations:{provider.provider_name}",
                {
                    "event_type": "PlatformMeetingCancelled",
                    "provider": provider.provider_name,
                    "meeting_id": str(meeting.id),
                    "external_meeting_id": external_meeting_id,
                },
            )
        elif event_type in {"meeting.updated", "updated"}:
            if "title" in payload:
                meeting.title = payload["title"]
            if "duration_minutes" in payload:
                meeting.duration_minutes = payload["duration_minutes"]
            ref.sync_status = "updated"
            await self.db.commit()
            await self.event_bus.publish(
                f"events:integrations:{provider.provider_name}",
                {
                    "event_type": "PlatformMeetingUpdated",
                    "provider": provider.provider_name,
                    "meeting_id": str(meeting.id),
                    "external_meeting_id": external_meeting_id,
                },
            )

        return {"status": "processed", "event_type": event_type, "meeting_id": str(meeting.id)}
