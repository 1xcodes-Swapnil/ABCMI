"""
Notification Application Service & Real-Time Event Dispatcher (Phase 4.24)
Orchestrates event-to-notification mapping, idempotency deduplication, security sanitization,
persistent storage, unread tracking, retention management, and provider-neutral real-time delivery.
"""

from datetime import datetime, timezone
import json
import re
from typing import Any, Callable, Coroutine, Dict, List, Optional, Set, Tuple, Union
import uuid
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import BadRequestException, ForbiddenException, NotFoundException
from app.core.logging import get_logger
from app.events.redis_bus import EventHandler, RedisEventBus, get_event_bus
from app.models.notification import Notification
from app.repositories.notification_repo import NotificationRepository
from app.schemas.base import CoreBaseModel
from app.schemas.notification import (
    NotificationBatchReadResponse,
    NotificationCategory,
    NotificationCleanupResponse,
    NotificationCreate,
    NotificationListResponse,
    NotificationResponse,
    NotificationSeverity,
    NotificationUnreadCountResponse,
    RealtimeNotificationPayload,
)

logger = get_logger("services.notification")


# -----------------------------------------------------------------------------
# Real-Time Event Adapter Interface & Default Implementation
# -----------------------------------------------------------------------------


class RealtimeDeliveryAdapter:
    """
    Provider-neutral interface for dispatching real-time notification events
    to connected clients or transport brokers (e.g., Redis Pub/Sub, SSE, WebSockets).
    Guarantees that raw ORM entities and un-sanitized internal details are never broadcast.
    """

    def __init__(self, event_bus: Optional[RedisEventBus] = None) -> None:
        self.event_bus = event_bus or get_event_bus()

    def build_payload(
        self,
        notification: Notification,
        event_type: str = "NotificationCreated",
    ) -> RealtimeNotificationPayload:
        """Constructs a strongly-typed, frontend-safe real-time delivery payload."""
        return RealtimeNotificationPayload(
            event_type=event_type,
            id=notification.id,
            tenant_id=notification.tenant_id,
            user_id=notification.user_id,
            category=NotificationCategory(notification.category),
            severity=NotificationSeverity(notification.severity),
            title=notification.title,
            description=notification.description,
            is_read=notification.is_read,
            meeting_id=notification.meeting_id,
            project_id=notification.project_id,
            resource_id=notification.resource_id,
            correlation_id=notification.correlation_id,
            event_id=notification.event_id,
            created_at=notification.created_at or datetime.now(timezone.utc),
            read_at=notification.read_at,
            metadata=notification.metadata_json or {},
        )

    async def broadcast_notification(
        self,
        notification: Notification,
        event_type: str = "NotificationCreated",
    ) -> bool:
        """
        Broadcasts frontend-safe notification payload across Redis channels:
        1. Tenant channel: abci.notifications.{tenant_id}
        2. User channel (if user-specific): abci.notifications.{tenant_id}.{user_id}
        """
        payload = self.build_payload(notification, event_type=event_type)
        payload_dict = payload.model_dump()

        # Publish to tenant-wide notification channel
        tenant_channel = f"abci.notifications.{notification.tenant_id}"
        delivered = await self.event_bus.publish(tenant_channel, payload_dict)

        # If targeted to a specific user, also publish to user-scoped channel
        if notification.user_id:
            user_channel = f"abci.notifications.{notification.tenant_id}.{notification.user_id}"
            await self.event_bus.publish(user_channel, payload_dict)

        return delivered


# -----------------------------------------------------------------------------
# Core Notification Service
# -----------------------------------------------------------------------------


class NotificationService:
    """
    Application Service orchestrating the notification lifecycle:
    - Event ingestion and mapping to user-safe notifications
    - Idempotency guarantees to prevent duplicate notifications
    - Recursive security sanitization of text and structured metadata
    - Secure multi-tenant querying and role-based access control
    - Retention management and lifecycle cleanup
    - Provider-neutral real-time event broadcasting
    """

    # Secret-bearing dictionary keys that must be redacted case-insensitively
    SECRET_KEYS: Set[str] = {
        "password",
        "pass",
        "secret",
        "secret_key",
        "client_secret",
        "token",
        "access_token",
        "refresh_token",
        "id_token",
        "api_key",
        "apikey",
        "x-api-key",
        "authorization",
        "auth",
        "cookie",
        "jwt",
        "private_key",
        "priv_key",
        "session_id",
        "credentials",
        "connection_string",
        "database_url",
        "db_url",
        "redis_password",
    }

    # Roles permitted to view security alerts and execute retention cleanup
    SECURITY_ROLES: Set[str] = {"admin", "security_officer", "security_auditor"}

    def __init__(
        self,
        db: AsyncSession,
        event_bus: Optional[RedisEventBus] = None,
        realtime_adapter: Optional[RealtimeDeliveryAdapter] = None,
    ) -> None:
        self.db = db
        self.repo = NotificationRepository(db)
        self.event_bus = event_bus or get_event_bus()
        self.realtime_adapter = realtime_adapter or RealtimeDeliveryAdapter(self.event_bus)

    # -------------------------------------------------------------------------
    # Authentication & Scope Helpers
    # -------------------------------------------------------------------------

    def _extract_auth_context(self, auth_context: Dict[str, Any]) -> Tuple[str, Optional[uuid.UUID], str]:
        """Extracts tenant_id, user_id, and role from auth context safely."""
        if not auth_context or not auth_context.get("authenticated", False):
            raise ForbiddenException(message="Authentication credentials required", code="UNAUTHORIZED")

        tenant_id = auth_context.get("tenant_id")
        if not tenant_id:
            tenant_id = auth_context.get("user_id") or "tenant-default"
        tenant_id = str(tenant_id)

        user_id_raw = auth_context.get("user_id")
        user_id: Optional[uuid.UUID] = None
        if user_id_raw:
            try:
                user_id = uuid.UUID(str(user_id_raw))
            except ValueError:
                user_id = None

        role = str(auth_context.get("role", "user")).lower()
        return tenant_id, user_id, role

    def _sanitize_text(self, text: Optional[str]) -> str:
        """
        Strips potential internal secrets, authorization tokens, database URIs,
        private keys, internal filesystem paths, and exception stack traces.
        """
        if not text:
            return ""

        sanitized = str(text)

        # 1. Mask Authorization / Bearer / Basic tokens
        sanitized = re.sub(r"(Bearer\s+)[A-Za-z0-9\-\._~+/]+=*", r"\1[REDACTED]", sanitized, flags=re.IGNORECASE)
        sanitized = re.sub(r"(Basic\s+)[A-Za-z0-9+/=]+", r"\1[REDACTED]", sanitized, flags=re.IGNORECASE)

        # 2. Mask explicit API keys and token parameters
        sanitized = re.sub(r"((?:x-)?api[_-]?key\s*[:=]\s*)[A-Za-z0-9\-\._~+/]+", r"\1[REDACTED]", sanitized, flags=re.IGNORECASE)
        sanitized = re.sub(r"((?:access_|refresh_|id_)?token\s*[:=]\s*)[^\s,;'\"]+", r"\1[REDACTED]", sanitized, flags=re.IGNORECASE)
        sanitized = re.sub(r"(password\s*[:=]\s*)[^\s,;'\"]+", r"\1[REDACTED]", sanitized, flags=re.IGNORECASE)
        sanitized = re.sub(r"(secret(?:_key)?\s*[:=]\s*)[^\s,;'\"]+", r"\1[REDACTED]", sanitized, flags=re.IGNORECASE)

        # 3. Mask JWT tokens
        sanitized = re.sub(r"eyJ[A-Za-z0-9-_=]+\.eyJ[A-Za-z0-9-_=]+\.[A-Za-z0-9-_.+/=]*", "[JWT_TOKEN_REDACTED]", sanitized)

        # 4. Mask Private Key blocks
        sanitized = re.sub(r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z ]*PRIVATE KEY-----", "[PRIVATE_KEY_REDACTED]", sanitized)

        # 5. Mask Database / Broker connection URIs
        sanitized = re.sub(
            r"(?:postgresql|postgres|redis|mysql|sqlite|mongodb|amqp)(\+[a-z0-9]+)?://[^\s,;'\"]+",
            "[DATABASE_URI_REDACTED]",
            sanitized,
            flags=re.IGNORECASE,
        )

        # 6. Mask internal server file paths
        sanitized = re.sub(r"(?:/(?:backend|app|usr|etc|var)/[^\s:,]+|[A-Za-z]:\\[^\s:,]+)", "[SERVER_PATH]", sanitized)

        # 7. Mask exception stack traces
        sanitized = re.sub(r"Traceback \(most recent call last\):[\s\S]*?(?:Error|Exception):[^\n]*", "[EXCEPTION_STACK_TRACE_REDACTED]", sanitized)

        # Cap length to prevent unbounded payload storage
        return sanitized[:2000].strip()

    def _sanitize_dict(self, data: Any, depth: int = 0) -> Any:
        """
        Recursively sanitizes structured metadata dictionaries and lists.
        Redacts secret-bearing keys case-insensitively and cleans all string values.
        """
        if depth > 10:
            return "[MAX_DEPTH_REACHED]"

        if isinstance(data, dict):
            clean_dict: Dict[str, Any] = {}
            for k, v in data.items():
                key_str = str(k).strip()
                key_lower = key_str.lower()
                # Check exact match or presence in secret key catalog
                if key_lower in self.SECRET_KEYS or any(secret in key_lower for secret in ["secret", "password", "token", "apikey", "api_key"]):
                    clean_dict[key_str] = "[REDACTED]"
                else:
                    clean_dict[key_str] = self._sanitize_dict(v, depth + 1)
            return clean_dict

        if isinstance(data, (list, tuple, set)):
            return [self._sanitize_dict(item, depth + 1) for item in data]

        if isinstance(data, str):
            return self._sanitize_text(data)

        if isinstance(data, (int, float, bool)) or data is None:
            return data

        if isinstance(data, uuid.UUID):
            return str(data)

        if isinstance(data, datetime):
            return data.isoformat()

        # Fallback for arbitrary objects
        return self._sanitize_text(str(data))

    def _map_to_dto(self, model: Notification) -> NotificationResponse:
        """Converts Notification ORM model to frontend-safe DTO."""
        return NotificationResponse(
            id=model.id,
            tenant_id=model.tenant_id,
            user_id=model.user_id,
            event_type=model.event_type,
            category=NotificationCategory(model.category),
            title=model.title,
            description=model.description,
            severity=NotificationSeverity(model.severity),
            is_read=model.is_read,
            meeting_id=model.meeting_id,
            project_id=model.project_id,
            resource_id=model.resource_id,
            correlation_id=model.correlation_id,
            event_id=model.event_id,
            read_at=model.read_at,
            metadata=model.metadata_json or {},
            created_at=model.created_at,
            updated_at=model.updated_at,
        )

    # -------------------------------------------------------------------------
    # Notification Ingestion & Event Mapping
    # -------------------------------------------------------------------------

    async def create_notification(self, payload: NotificationCreate) -> NotificationResponse:
        """
        Creates and persists a notification with idempotency check and real-time broadcast.
        """
        # Idempotency check: if event_id is provided, check if already recorded
        if payload.event_id:
            existing = await self.repo.get_by_event_id(payload.tenant_id, payload.event_id)
            if existing:
                logger.info(f"Duplicate event_id '{payload.event_id}' for tenant '{payload.tenant_id}'. Returning existing.")
                return self._map_to_dto(existing)

        sanitized_desc = self._sanitize_text(payload.description)
        sanitized_title = self._sanitize_text(payload.title)[:255]
        clean_metadata = self._sanitize_dict(payload.metadata or {})

        notification = Notification(
            id=uuid.uuid4(),
            tenant_id=payload.tenant_id,
            user_id=payload.user_id,
            event_type=payload.event_type,
            category=payload.category.value,
            title=sanitized_title,
            description=sanitized_desc,
            severity=payload.severity.value,
            is_read=False,
            meeting_id=payload.meeting_id,
            project_id=payload.project_id,
            resource_id=payload.resource_id.strip() if payload.resource_id else None,
            correlation_id=payload.correlation_id.strip() if payload.correlation_id else None,
            event_id=payload.event_id.strip() if payload.event_id else None,
            metadata_json=clean_metadata,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )

        saved = await self.repo.create(notification)
        await self.db.commit()
        await self.db.refresh(saved)

        # Real-time event delivery broadcast
        try:
            await self.realtime_adapter.broadcast_notification(saved, event_type="NotificationCreated")
        except Exception as e:
            logger.warning(f"Real-time broadcast failed for notification '{saved.id}': {e}")

        return self._map_to_dto(saved)

    async def ingest_event(
        self,
        event_type: str,
        event_data: Dict[str, Any],
    ) -> Optional[NotificationResponse]:
        """
        Maps a system domain event into a persistent user/tenant notification.
        Preserves correlation_id and event_id while sanitizing sensitive details.
        """
        tenant_id = str(event_data.get("tenant_id") or "tenant-default")
        user_id_raw = event_data.get("user_id") or event_data.get("host_id") or event_data.get("created_by")
        user_id: Optional[uuid.UUID] = None
        if user_id_raw:
            try:
                user_id = uuid.UUID(str(user_id_raw))
            except ValueError:
                user_id = None

        meeting_id_raw = event_data.get("meeting_id")
        meeting_id: Optional[uuid.UUID] = None
        if meeting_id_raw:
            try:
                meeting_id = uuid.UUID(str(meeting_id_raw))
            except ValueError:
                meeting_id = None

        project_id_raw = event_data.get("project_id")
        project_id: Optional[uuid.UUID] = None
        if project_id_raw:
            try:
                project_id = uuid.UUID(str(project_id_raw))
            except ValueError:
                project_id = None

        # Extract correlation_id preservation across possible locations
        metadata_dict = event_data.get("metadata") if isinstance(event_data.get("metadata"), dict) else {}
        context_dict = event_data.get("context") if isinstance(event_data.get("context"), dict) else {}
        tracing_dict = event_data.get("tracing") if isinstance(event_data.get("tracing"), dict) else {}

        correlation_id_raw = (
            event_data.get("correlation_id")
            or metadata_dict.get("correlation_id")
            or context_dict.get("correlation_id")
            or tracing_dict.get("correlation_id")
        )
        correlation_id = str(correlation_id_raw).strip() if correlation_id_raw else None

        # Normalized external / resource reference extraction (Zoom, Teams, Meet, Jira, Slack, etc.)
        resource_id_raw = (
            event_data.get("resource_id")
            or event_data.get("knowledge_id")
            or event_data.get("item_id")
            or event_data.get("report_id")
            or event_data.get("query_id")
            or event_data.get("external_id")
            or event_data.get("zoom_id")
            or event_data.get("teams_id")
            or meeting_id
            or project_id
        )
        resource_id = str(resource_id_raw).strip() if resource_id_raw is not None else None

        # Stable idempotency deduplication key extraction
        event_id_raw = (
            event_data.get("event_id")
            or event_data.get("event_uuid")
            or event_data.get("id")
        )
        if event_id_raw:
            event_id = str(event_id_raw).strip()
        elif correlation_id:
            event_id = f"{tenant_id}:{event_type}:{correlation_id}:{resource_id or ''}"
        else:
            event_id = f"{tenant_id}:{event_type}:{resource_id or ''}"

        # Event Mapping Logic
        title: str = f"Event: {event_type}"
        description: str = f"A {event_type} event was processed."
        category = NotificationCategory.SYSTEM
        severity = NotificationSeverity.INFO

        # Normalize event_type if typed contract name or namespaced
        clean_event_type = event_type.replace("abci.", "").replace("events:", "")

        # 1. Meeting Events
        if event_type in {"MeetingScheduled", "abci.meeting.scheduled"} or clean_event_type in {"meeting.scheduled", "meeting_scheduled"}:
            category = NotificationCategory.MEETING
            severity = NotificationSeverity.INFO
            m_title = event_data.get("title") or "Untitled Meeting"
            title = "Meeting Scheduled"
            description = f"Meeting '{m_title}' has been scheduled."

        elif event_type in {"MeetingStarted", "abci.meeting.started"} or clean_event_type in {"meeting.started", "meeting_started"}:
            category = NotificationCategory.MEETING
            severity = NotificationSeverity.INFO
            m_title = event_data.get("title") or "Meeting"
            title = "Meeting Started"
            description = f"Meeting '{m_title}' is now in progress."

        elif event_type in {"MeetingStopped", "abci.meeting.stopped"} or clean_event_type in {"meeting.stopped", "meeting_stopped"}:
            category = NotificationCategory.MEETING
            severity = NotificationSeverity.INFO
            m_title = event_data.get("title") or "Meeting"
            title = "Meeting Stopped"
            description = f"Meeting '{m_title}' has stopped."

        elif event_type in {"MeetingCompleted", "abci.meeting.completed"} or clean_event_type in {"meeting.completed", "meeting_completed"}:
            category = NotificationCategory.MEETING
            severity = NotificationSeverity.SUCCESS
            m_title = event_data.get("title") or "Meeting"
            title = "Meeting Completed"
            description = f"Meeting '{m_title}' completed successfully."

        elif event_type in {"MeetingFailed", "abci.meeting.failed"} or clean_event_type in {"meeting.failed", "meeting_failed"}:
            category = NotificationCategory.MEETING
            severity = NotificationSeverity.ERROR
            m_title = event_data.get("title") or "Meeting"
            err = self._sanitize_text(event_data.get("error") or "Processing error")
            title = "Meeting Processing Failed"
            description = f"Meeting '{m_title}' encountered an error: {err}."

        # 2. Processing Pipeline Events
        elif event_type in {"ProcessingRequested", "abci.processing.requested"} or clean_event_type in {"processing.requested", "processing_requested"}:
            category = NotificationCategory.PROCESSING
            severity = NotificationSeverity.INFO
            title = "Processing Started"
            description = "Meeting intelligence processing has been initiated."

        elif event_type in {"ProcessingCompleted", "abci.processing.completed"} or clean_event_type in {"processing.completed", "processing_completed"}:
            category = NotificationCategory.PROCESSING
            severity = NotificationSeverity.SUCCESS
            title = "Processing Finished"
            description = "Audio transcription and knowledge extraction completed."

        elif event_type in {"ProcessingFailed", "abci.processing.failed"} or clean_event_type in {"processing.failed", "processing_failed"}:
            category = NotificationCategory.PROCESSING
            severity = NotificationSeverity.ERROR
            err = self._sanitize_text(event_data.get("error") or "Pipeline failure")
            title = "Processing Failed"
            description = f"Intelligence pipeline failed: {err}."

        elif event_type in {"AudioChunkReceived", "TranscriptGenerated"}:
            category = NotificationCategory.PROCESSING
            severity = NotificationSeverity.INFO
            title = "Transcript Available"
            description = "New transcript segments were generated for the meeting."

        # 3. Knowledge Events (including SKW typed contracts)
        elif event_type in {"KnowledgeCreatedEvent", "KnowledgeObjectCreated", "abci.knowledge.created"} or clean_event_type in {"knowledge.created", "knowledge_created"}:
            category = NotificationCategory.KNOWLEDGE
            severity = NotificationSeverity.INFO
            otype = event_data.get("object_type", "knowledge")
            k_title = event_data.get("title") or "Item"
            title = f"{otype.replace('_', ' ').title()} Extracted"
            description = f"New {otype} extracted: '{k_title}'."

        elif event_type in {"KnowledgeUpdatedEvent", "KnowledgeObjectUpdated", "abci.knowledge.updated"} or clean_event_type in {"knowledge.updated", "knowledge_updated"}:
            category = NotificationCategory.KNOWLEDGE
            severity = NotificationSeverity.INFO
            otype = event_data.get("object_type", "knowledge")
            k_title = event_data.get("title") or "Item"
            title = f"{otype.replace('_', ' ').title()} Updated"
            description = f"{otype.replace('_', ' ').title()} '{k_title}' was updated."

        elif event_type in {"KnowledgeValidatedEvent", "KnowledgeObjectValidated", "abci.knowledge.validated"} or clean_event_type in {"knowledge.validated", "knowledge_validated"}:
            category = NotificationCategory.KNOWLEDGE
            severity = NotificationSeverity.SUCCESS
            otype = event_data.get("object_type", "knowledge")
            k_title = event_data.get("title") or "Item"
            title = f"{otype.replace('_', ' ').title()} Validated"
            description = f"{otype.replace('_', ' ').title()} '{k_title}' was successfully validated."

        elif event_type in {"KnowledgeValidationFailedEvent", "KnowledgeObjectValidationFailed", "abci.knowledge.validation_failed"} or clean_event_type in {"knowledge.validation_failed"}:
            category = NotificationCategory.KNOWLEDGE
            severity = NotificationSeverity.WARNING
            otype = event_data.get("object_type", "knowledge")
            k_title = event_data.get("title") or "Item"
            title = f"{otype.replace('_', ' ').title()} Validation Failed"
            description = f"{otype.replace('_', ' ').title()} '{k_title}' did not pass validation criteria."

        elif event_type in {"KnowledgePublishedEvent", "KnowledgeObjectPublished", "abci.knowledge.published"} or clean_event_type in {"knowledge.published", "knowledge_published"}:
            category = NotificationCategory.KNOWLEDGE
            severity = NotificationSeverity.SUCCESS
            otype = event_data.get("object_type", "knowledge")
            k_title = event_data.get("title") or "Item"
            title = f"{otype.replace('_', ' ').title()} Published"
            description = f"{otype.replace('_', ' ').title()} '{k_title}' published to knowledge base."

        elif event_type in {"KnowledgeArchivedEvent", "KnowledgeObjectArchived", "abci.knowledge.archived"} or clean_event_type in {"knowledge.archived", "knowledge_archived"}:
            category = NotificationCategory.KNOWLEDGE
            severity = NotificationSeverity.WARNING
            otype = event_data.get("object_type", "knowledge")
            k_title = event_data.get("title") or "Item"
            title = f"{otype.replace('_', ' ').title()} Archived"
            description = f"{otype.replace('_', ' ').title()} '{k_title}' was archived."

        elif event_type in {"KnowledgeIndexedEvent", "KnowledgeObjectIndexed", "abci.knowledge.indexed"} or clean_event_type in {"knowledge.indexed", "knowledge_indexed"}:
            category = NotificationCategory.KNOWLEDGE
            severity = NotificationSeverity.INFO
            otype = event_data.get("object_type", "knowledge")
            k_title = event_data.get("title") or "Item"
            title = f"{otype.replace('_', ' ').title()} Indexed"
            description = f"{otype.replace('_', ' ').title()} '{k_title}' was indexed for semantic search."

        elif event_type in {"KnowledgeProcessingFailedEvent", "KnowledgeObjectFailed", "abci.knowledge.failed"} or clean_event_type in {"knowledge.failed", "knowledge_failed"}:
            category = NotificationCategory.KNOWLEDGE
            severity = NotificationSeverity.ERROR
            otype = event_data.get("object_type", "knowledge")
            k_title = event_data.get("title") or "Item"
            err = self._sanitize_text(event_data.get("error") or "Processing failure")
            title = f"{otype.replace('_', ' ').title()} Processing Failed"
            description = f"Failed to process {otype} '{k_title}': {err}."

        elif event_type in {"KnowledgeVersionedEvent", "KnowledgeObjectVersioned", "abci.knowledge.versioned"} or clean_event_type in {"knowledge.versioned", "knowledge_versioned"}:
            category = NotificationCategory.KNOWLEDGE
            severity = NotificationSeverity.INFO
            otype = event_data.get("object_type", "knowledge")
            k_title = event_data.get("title") or "Item"
            ver = event_data.get("version", "")
            title = f"{otype.replace('_', ' ').title()} Versioned"
            description = f"{otype.replace('_', ' ').title()} '{k_title}' updated to version {ver}."

        elif event_type in {"DecisionExtracted", "DecisionRecorded"}:
            category = NotificationCategory.KNOWLEDGE
            severity = NotificationSeverity.INFO
            d_title = event_data.get("title") or "Decision"
            title = "Decision Recorded"
            description = f"New decision recorded: '{d_title}'."

        elif event_type in {"TopicExtracted", "TopicIdentified"}:
            category = NotificationCategory.KNOWLEDGE
            severity = NotificationSeverity.INFO
            t_title = event_data.get("title") or "Topic"
            title = "Topic Identified"
            description = f"Discussion topic identified: '{t_title}'."

        elif event_type in {"InsightGenerated", "TranscriptInsightCreated"}:
            category = NotificationCategory.KNOWLEDGE
            severity = NotificationSeverity.INFO
            i_title = event_data.get("title") or "Insight"
            title = "Insight Generated"
            description = f"Key meeting insight generated: '{i_title}'."

        # 4. Action Item Events
        elif event_type in {"ActionItemCreated", "abci.action_item.created"}:
            category = NotificationCategory.KNOWLEDGE
            severity = NotificationSeverity.INFO
            ai_title = event_data.get("title") or "Action Item"
            assignee = event_data.get("assignee")
            assign_str = f" (Assigned to: {assignee})" if assignee else ""
            title = "Action Item Created"
            description = f"Action item created: '{ai_title}'{assign_str}."

        elif event_type in {"ActionItemUpdated", "abci.action_item.updated"}:
            category = NotificationCategory.KNOWLEDGE
            severity = NotificationSeverity.INFO
            ai_title = event_data.get("title") or "Action Item"
            title = "Action Item Updated"
            description = f"Action item updated: '{ai_title}'."

        elif event_type in {"ActionItemCompleted", "abci.action_item.completed"}:
            category = NotificationCategory.KNOWLEDGE
            severity = NotificationSeverity.SUCCESS
            ai_title = event_data.get("title") or "Action Item"
            title = "Action Item Completed"
            description = f"Action item marked as completed: '{ai_title}'."

        elif event_type in {"ActionItemCancelled", "abci.action_item.cancelled"}:
            category = NotificationCategory.KNOWLEDGE
            severity = NotificationSeverity.WARNING
            ai_title = event_data.get("title") or "Action Item"
            title = "Action Item Cancelled"
            description = f"Action item was cancelled: '{ai_title}'."

        elif event_type in {"ActionItemVerificationRequired", "ActionItemLowConfidence"}:
            category = NotificationCategory.KNOWLEDGE
            severity = NotificationSeverity.WARNING
            ai_title = event_data.get("title") or "Action Item"
            title = "Action Item Verification Required"
            description = f"Action item '{ai_title}' was flagged with low confidence and requires review."

        # 5. Report Events
        elif event_type in {"ReportGenerated", "abci.report.generated"}:
            category = NotificationCategory.REPORT
            severity = NotificationSeverity.SUCCESS
            r_title = event_data.get("title") or "Executive Summary"
            title = "Report Ready"
            description = f"Meeting report '{r_title}' is ready for review."

        elif event_type in {"ReportExported", "abci.report.exported"}:
            category = NotificationCategory.REPORT
            severity = NotificationSeverity.INFO
            fmt = event_data.get("format", "PDF").upper()
            title = "Report Exported"
            description = f"Meeting report was exported in {fmt} format."

        elif event_type in {"ReportFailed", "abci.report.failed"}:
            category = NotificationCategory.REPORT
            severity = NotificationSeverity.ERROR
            err = self._sanitize_text(event_data.get("error") or "Export failure")
            title = "Report Generation Failed"
            description = f"Failed to generate report: {err}."

        # 6. Translation Events
        elif event_type in {"TranslationGenerated", "abci.translation.generated"}:
            category = NotificationCategory.KNOWLEDGE
            severity = NotificationSeverity.INFO
            lang = event_data.get("target_language", "target language")
            title = "Translation Generated"
            description = f"Transcript translation into {lang} completed."

        elif event_type in {"TranslationVerificationRequired", "abci.translation.verification_required"}:
            category = NotificationCategory.KNOWLEDGE
            severity = NotificationSeverity.WARNING
            title = "Translation Needs Verification"
            description = "Translation confidence is low and requires human verification."

        # 7. Ask ABCI-MI Query Events
        elif event_type in {"QueryRequested", "abci.query.requested"}:
            category = NotificationCategory.SYSTEM
            severity = NotificationSeverity.INFO
            q_text = self._sanitize_text(event_data.get("query", ""))[:60]
            title = "Query Processing"
            description = f"Query received: '{q_text}'."

        elif event_type in {"QueryCompleted", "abci.query.completed"}:
            category = NotificationCategory.SYSTEM
            severity = NotificationSeverity.SUCCESS
            sources_cnt = event_data.get("sources_count", 0)
            title = "Query Answered"
            description = f"Query answered successfully using {sources_cnt} authoritative sources."

        elif event_type in {"QueryInsufficientContext", "abci.query.insufficient_context"}:
            category = NotificationCategory.SYSTEM
            severity = NotificationSeverity.WARNING
            title = "Query Insufficient Context"
            description = "Could not find sufficient authoritative context to answer the question."

        elif event_type in {"QueryVerificationRequired", "abci.query.verification_required"}:
            category = NotificationCategory.SYSTEM
            severity = NotificationSeverity.WARNING
            title = "Query Requires Verification"
            description = "Answer synthesized with low confidence and requires verification."

        elif event_type in {"QueryFailed", "abci.query.failed"}:
            category = NotificationCategory.SYSTEM
            severity = NotificationSeverity.ERROR
            err = self._sanitize_text(event_data.get("error") or "Execution failure")
            title = "Query Failed"
            description = f"Failed to process natural language query: {err}."

        # 8. Platform Integration Events
        elif event_type in {"PlatformConnected", "abci.platform.connected"}:
            category = NotificationCategory.SYSTEM
            severity = NotificationSeverity.SUCCESS
            plat = event_data.get("platform", "External platform").title()
            title = "Platform Connected"
            description = f"{plat} integration connected successfully."

        elif event_type in {"PlatformDisconnected", "abci.platform.disconnected"}:
            category = NotificationCategory.SYSTEM
            severity = NotificationSeverity.WARNING
            plat = event_data.get("platform", "External platform").title()
            title = "Platform Disconnected"
            description = f"{plat} integration was disconnected."

        elif event_type in {"PlatformEventFailed", "abci.platform.failed"}:
            category = NotificationCategory.SYSTEM
            severity = NotificationSeverity.ERROR
            plat = event_data.get("platform", "External platform").title()
            title = "Integration Event Failed"
            description = f"Failed to sync incoming event from {plat}."

        elif event_type in {"ExternalMeetingImported", "abci.platform.imported"}:
            category = NotificationCategory.MEETING
            severity = NotificationSeverity.INFO
            plat = event_data.get("platform", "platform").title()
            title = "External Meeting Imported"
            description = f"Meeting synchronized from {plat}."

        # 9. Project Events
        elif event_type in {"ProjectCreated", "abci.project.created"}:
            category = NotificationCategory.SYSTEM
            severity = NotificationSeverity.INFO
            p_name = event_data.get("name") or "Project"
            title = "Project Created"
            description = f"Project workspace '{p_name}' was created."

        elif event_type in {"ProjectUpdated", "abci.project.updated"}:
            category = NotificationCategory.SYSTEM
            severity = NotificationSeverity.INFO
            p_name = event_data.get("name") or "Project"
            title = "Project Updated"
            description = f"Project workspace '{p_name}' was updated."

        elif event_type in {"ProjectDeleted", "abci.project.deleted"}:
            category = NotificationCategory.SYSTEM
            severity = NotificationSeverity.WARNING
            title = "Project Deleted"
            description = "Project workspace was removed."

        elif event_type in {"MeetingAssociatedWithProject", "abci.project.meeting_associated"}:
            category = NotificationCategory.MEETING
            severity = NotificationSeverity.INFO
            title = "Meeting Added to Project"
            description = "A meeting was added to the project workspace."

        elif event_type in {"MeetingRemovedFromProject", "abci.project.meeting_removed"}:
            category = NotificationCategory.MEETING
            severity = NotificationSeverity.INFO
            title = "Meeting Removed from Project"
            description = "A meeting was unlinked from the project workspace."

        # 10. Security & System Health Events
        elif event_type in {"SecurityAlert", "abci.security.alert"}:
            category = NotificationCategory.SECURITY
            severity = NotificationSeverity.SECURITY
            details = self._sanitize_text(event_data.get("details") or "Suspicious security pattern detected")
            title = "Security Alert"
            description = f"Security event detected: {details}."

        elif event_type in {"AuthenticationFailed", "abci.security.auth_failed"}:
            category = NotificationCategory.SECURITY
            severity = NotificationSeverity.SECURITY
            title = "Authentication Failure"
            description = "Failed login attempt detected for workspace."

        elif event_type in {"AccessDenied", "abci.security.access_denied"}:
            category = NotificationCategory.SECURITY
            severity = NotificationSeverity.SECURITY
            title = "Access Denied"
            description = "Unauthorized attempt to access protected resource blocked."

        elif event_type in {"SystemDegraded", "abci.system.degraded"}:
            category = NotificationCategory.SYSTEM
            severity = NotificationSeverity.WARNING
            svc = event_data.get("service") or "Storage cluster"
            title = "System Degraded"
            description = f"Subsystem '{svc}' is currently degraded."

        elif event_type in {"ServiceHealthChanged", "abci.system.health"}:
            category = NotificationCategory.SYSTEM
            severity = NotificationSeverity.INFO
            svc = event_data.get("service") or "Service"
            st = event_data.get("status") or "updated"
            title = "Service Health Updated"
            description = f"Service '{svc}' status changed to '{st}'."

        create_schema = NotificationCreate(
            tenant_id=tenant_id,
            user_id=user_id,
            event_type=event_type,
            category=category,
            title=title,
            description=description,
            severity=severity,
            meeting_id=meeting_id,
            project_id=project_id,
            resource_id=resource_id,
            correlation_id=correlation_id,
            event_id=event_id,
            metadata=event_data,
        )

        return await self.create_notification(create_schema)

    # -------------------------------------------------------------------------
    # Redis Event Bus Consumer & Subscription Management
    # -------------------------------------------------------------------------

    async def consume_event(
        self,
        event: Union[Dict[str, Any], CoreBaseModel, str],
    ) -> Optional[NotificationResponse]:
        """
        Consumes an event payload from RedisEventBus or direct caller.
        Preserves correlation_id and ensures idempotency deduplication by event_id.
        """
        event_dict: Dict[str, Any] = {}
        event_type = "DomainEvent"

        if isinstance(event, str):
            try:
                event_dict = json.loads(event)
            except Exception as e:
                logger.warning(f"Could not parse event string as JSON: {e}")
                event_dict = {"raw": event}
        elif isinstance(event, CoreBaseModel):
            event_dict = event.model_dump()
            event_type = getattr(event, "event_type", event.__class__.__name__)
        elif isinstance(event, dict):
            event_dict = dict(event)
        else:
            event_dict = {"data": str(event)}

        # Extract explicit event type if present in dictionary
        if "event_type" in event_dict and event_dict["event_type"]:
            event_type = str(event_dict["event_type"])
        elif "type" in event_dict and event_dict["type"]:
            event_type = str(event_dict["type"])
        elif "event" in event_dict and event_dict["event"]:
            event_type = str(event_dict["event"])

        logger.debug(f"NotificationService consuming event '{event_type}'")
        return await self.ingest_event(event_type=event_type, event_data=event_dict)

    def create_event_handler(self) -> EventHandler:
        """
        Returns an asynchronous event handler callback compatible with RedisEventBus.subscribe().
        """
        async def _handler(event_payload: Dict[str, Any]) -> None:
            try:
                await self.consume_event(event_payload)
            except Exception as e:
                logger.error(f"Error in NotificationService event handler: {e}", exc_info=True)

        return _handler

    def subscribe_to_event_bus(
        self,
        channels: Optional[List[str]] = None,
    ) -> List[str]:
        """
        Registers event listeners on the RedisEventBus for the configured channels.
        Returns the list of subscribed channels.
        """
        target_channels = channels or [
            "events:knowledge",
            "events:meeting",
            "events:meetings",
            "events:processing",
            "events:reports",
            "events:translations",
            "events:queries",
            "events:security",
            "events:projects",
            "events:action_items",
            "events:platform",
            "events:system",
            "abci.events",
        ]
        handler = self.create_event_handler()
        for ch in target_channels:
            self.event_bus.subscribe(ch, handler)
            logger.info(f"NotificationService subscribed to RedisEventBus channel '{ch}'")
        return target_channels

    def unsubscribe_from_event_bus(
        self,
        channels: Optional[List[str]] = None,
    ) -> None:
        """
        Unsubscribes handlers from the RedisEventBus.
        """
        target_channels = channels or [
            "events:knowledge",
            "events:meeting",
            "events:meetings",
            "events:processing",
            "events:reports",
            "events:translations",
            "events:queries",
            "events:security",
            "events:projects",
            "events:action_items",
            "events:platform",
            "events:system",
            "abci.events",
        ]
        handler = self.create_event_handler()
        for ch in target_channels:
            self.event_bus.unsubscribe(ch, handler)
            logger.info(f"NotificationService unsubscribed from RedisEventBus channel '{ch}'")

    @classmethod
    async def consume_event_with_session(
        cls,
        session_factory: Any,
        event: Union[Dict[str, Any], CoreBaseModel, str],
        event_bus: Optional[RedisEventBus] = None,
    ) -> Optional[NotificationResponse]:
        """
        Convenience execution helper for background tasks / event loops.
        Acquires an AsyncSession, consumes the event, and persists the notification.
        """
        async with session_factory() as session:
            try:
                service = cls(session, event_bus=event_bus)
                result = await service.consume_event(event)
                await session.commit()
                return result
            except Exception:
                await session.rollback()
                raise

    # -------------------------------------------------------------------------
    # Notification Query & Lifecycle APIs
    # -------------------------------------------------------------------------

    async def list_notifications(
        self,
        auth_context: Dict[str, Any],
        category: Optional[NotificationCategory] = None,
        severity: Optional[NotificationSeverity] = None,
        is_read: Optional[bool] = None,
        meeting_id: Optional[uuid.UUID] = None,
        project_id: Optional[uuid.UUID] = None,
        date_from: Optional[datetime] = None,
        date_to: Optional[datetime] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> NotificationListResponse:
        """
        Fetches a paginated, filtered list of notifications for the authenticated user and tenant.
        Prevents non-security roles from querying security notifications.
        """
        tenant_id, user_id, role = self._extract_auth_context(auth_context)

        # Enforce security role check if querying security category / severity explicitly
        if (category == NotificationCategory.SECURITY or severity == NotificationSeverity.SECURITY) and role not in self.SECURITY_ROLES:
            raise ForbiddenException(
                "Access to security notifications requires administrative or security auditor privileges.",
                code="INSUFFICIENT_ROLE",
            )

        # Non-admin users only see their own user-scoped + broadcast notifications
        query_user_id = user_id if role != "admin" else None

        items, total = await self.repo.list_notifications(
            tenant_id=tenant_id,
            user_id=query_user_id,
            category=category.value if category else None,
            severity=severity.value if severity else None,
            is_read=is_read,
            meeting_id=meeting_id,
            project_id=project_id,
            date_from=date_from,
            date_to=date_to,
            limit=limit,
            offset=offset,
        )

        # If regular user did not specify security category, filter out any security notifications from general list
        if role not in self.SECURITY_ROLES:
            items = [n for n in items if n.category != NotificationCategory.SECURITY.value and n.severity != NotificationSeverity.SECURITY.value]
            total = len(items)

        unread_cnt = await self.repo.count_unread(
            tenant_id=tenant_id,
            user_id=query_user_id,
        )

        return NotificationListResponse(
            items=[self._map_to_dto(n) for n in items],
            total=total,
            unread_count=unread_cnt,
            limit=limit,
            offset=offset,
        )

    async def get_unread_count(
        self,
        auth_context: Dict[str, Any],
    ) -> NotificationUnreadCountResponse:
        """
        Retrieves current total unread notifications count for caller's scope.
        """
        tenant_id, user_id, role = self._extract_auth_context(auth_context)
        query_user_id = user_id if role != "admin" else None
        unread_cnt = await self.repo.count_unread(tenant_id=tenant_id, user_id=query_user_id)

        return NotificationUnreadCountResponse(
            unread_count=unread_cnt,
            tenant_id=tenant_id,
            user_id=user_id,
        )

    async def get_notification(
        self,
        notification_id: uuid.UUID,
        auth_context: Dict[str, Any],
    ) -> NotificationResponse:
        """
        Fetches an individual notification verifying tenant and user ownership.
        """
        tenant_id, user_id, role = self._extract_auth_context(auth_context)

        notification = await self.repo.get_by_id(notification_id)
        if not notification:
            raise NotFoundException(f"Notification '{notification_id}' not found.", code="NOTIFICATION_NOT_FOUND")

        if notification.tenant_id != tenant_id:
            raise ForbiddenException("Access to this notification is forbidden.", code="TENANT_MISMATCH")

        # If user-specific notification and caller is non-admin user
        if role != "admin" and notification.user_id is not None and notification.user_id != user_id:
            raise ForbiddenException("Access to this notification is forbidden.", code="USER_MISMATCH")

        # If security alert and caller is regular user without security role
        if (notification.category == NotificationCategory.SECURITY.value or notification.severity == NotificationSeverity.SECURITY.value) and role not in self.SECURITY_ROLES:
            raise ForbiddenException("Access to security notifications requires administrative or security privileges.", code="INSUFFICIENT_ROLE")

        return self._map_to_dto(notification)

    async def mark_as_read(
        self,
        notification_id: uuid.UUID,
        auth_context: Dict[str, Any],
    ) -> NotificationResponse:
        """
        Marks an individual notification as read (idempotent).
        """
        tenant_id, user_id, role = self._extract_auth_context(auth_context)

        notification = await self.repo.get_by_id(notification_id)
        if not notification:
            raise NotFoundException(f"Notification '{notification_id}' not found.", code="NOTIFICATION_NOT_FOUND")

        if notification.tenant_id != tenant_id:
            raise ForbiddenException("Access to this notification is forbidden.", code="TENANT_MISMATCH")

        if role != "admin" and notification.user_id is not None and notification.user_id != user_id:
            raise ForbiddenException("Access to this notification is forbidden.", code="USER_MISMATCH")

        updated = await self.repo.mark_as_read(notification_id)
        await self.db.commit()
        await self.db.refresh(updated)
        return self._map_to_dto(updated)

    async def mark_all_as_read(
        self,
        auth_context: Dict[str, Any],
        category: Optional[NotificationCategory] = None,
        meeting_id: Optional[uuid.UUID] = None,
        project_id: Optional[uuid.UUID] = None,
    ) -> NotificationBatchReadResponse:
        """
        Marks all matching unread notifications as read for current scope.
        """
        tenant_id, user_id, role = self._extract_auth_context(auth_context)
        query_user_id = user_id if role != "admin" else None
        now = datetime.now(timezone.utc)

        count = await self.repo.mark_all_as_read(
            tenant_id=tenant_id,
            user_id=query_user_id,
            category=category.value if category else None,
            meeting_id=meeting_id,
            project_id=project_id,
            read_timestamp=now,
        )
        await self.db.commit()

        return NotificationBatchReadResponse(
            status="success",
            updated_count=count,
            read_at=now,
        )

    async def delete_notification(
        self,
        notification_id: uuid.UUID,
        auth_context: Dict[str, Any],
    ) -> bool:
        """
        Deletes an individual notification after validating ownership and privileges.
        Regular users may only delete notifications explicitly assigned to their user ID.
        """
        tenant_id, user_id, role = self._extract_auth_context(auth_context)

        notification = await self.repo.get_by_id(notification_id)
        if not notification:
            raise NotFoundException(f"Notification '{notification_id}' not found.", code="NOTIFICATION_NOT_FOUND")

        if notification.tenant_id != tenant_id:
            raise ForbiddenException("Access to this notification is forbidden.", code="TENANT_MISMATCH")

        if role != "admin":
            if notification.user_id is None:
                raise ForbiddenException("Only administrators can delete tenant broadcast notifications.", code="INSUFFICIENT_ROLE")
            if notification.user_id != user_id:
                raise ForbiddenException("Access to this notification is forbidden.", code="USER_MISMATCH")

        deleted = await self.repo.delete(notification_id)
        await self.db.commit()
        return deleted

    async def cleanup_notifications(
        self,
        auth_context: Dict[str, Any],
        retention_days: int = 30,
        security_retention_days: int = 365,
        include_unread: bool = False,
    ) -> NotificationCleanupResponse:
        """
        Executes retention cleanup of expired notifications.
        Enforces administrator or security officer role and tenant boundaries.
        """
        tenant_id, user_id, role = self._extract_auth_context(auth_context)
        if role not in self.SECURITY_ROLES:
            raise ForbiddenException("Notification retention cleanup requires administrative privileges.", code="INSUFFICIENT_ROLE")

        deleted_count = await self.repo.cleanup_expired(
            tenant_id=tenant_id,
            retention_days=retention_days,
            security_retention_days=security_retention_days,
            include_unread=include_unread,
        )
        await self.db.commit()

        return NotificationCleanupResponse(
            status="success",
            deleted_count=deleted_count,
            retention_days_applied=retention_days,
            security_retention_days_applied=security_retention_days,
            include_unread_applied=include_unread,
            executed_at=datetime.now(timezone.utc),
        )
