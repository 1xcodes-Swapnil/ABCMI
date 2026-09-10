"""
SKW Event Publisher Service
Integrates Semantic Knowledge Workspace lifecycle milestones with the distributed Redis Event Bus.
Implements KnowledgePublisher protocol and provides typed event emission for all lifecycle transitions.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional, Union
import uuid

from app.core.logging import get_logger
from app.events.redis_bus import EventDeliveryStatus, RedisEventBus, get_event_bus
from app.skw.events.contracts import (
    KnowledgeArchivedEvent,
    KnowledgeCreatedEvent,
    KnowledgeIndexedEvent,
    KnowledgeProcessingFailedEvent,
    KnowledgePublishedEvent,
    KnowledgeUpdatedEvent,
    KnowledgeValidatedEvent,
    KnowledgeValidationFailedEvent,
    KnowledgeVersionedEvent,
    SKWBaseEvent,
    SKWEvent,
    SKWEventType,
)
from app.skw.models.knowledge_object import CanonicalKnowledgeObject, SKWLifecycleState

logger = get_logger("skw.events.publisher")


class SKWEventPublisher:
    """
    Publisher service managing the translation of SKW Knowledge Object lifecycle transitions
    into strongly typed domain events published to Redis Pub/Sub channels.
    Conforms to the KnowledgePublisher protocol.
    """

    DEFAULT_CHANNEL = "events:knowledge"

    def __init__(self, event_bus: Optional[RedisEventBus] = None) -> None:
        self.event_bus = event_bus or get_event_bus()

    def get_meeting_channel(self, meeting_id: Union[str, uuid.UUID]) -> str:
        """Construct meeting-specific event channel."""
        return f"events:meetings:{str(meeting_id)}:knowledge"

    async def publish_event(
        self,
        event: SKWEvent,
        channel: Optional[str] = None,
    ) -> bool:
        """
        Publish a typed SKW event to Redis Pub/Sub.
        Dispatches to both the global SKW channel and the meeting-scoped channel.
        Safe against infrastructure blips without raising exceptions.
        """
        status = await self.publish_event_with_status(event, channel)
        return status == EventDeliveryStatus.DISTRIBUTED

    async def publish_event_with_status(
        self,
        event: SKWEvent,
        channel: Optional[str] = None,
    ) -> EventDeliveryStatus:
        """
        Publish a typed SKW event and return explicit delivery status.
        Explicitly distinguishes between DISTRIBUTED, LOCAL_FALLBACK, and FAILED.
        """
        target_channel = channel or self.DEFAULT_CHANNEL
        meeting_channel = self.get_meeting_channel(event.meeting_id)

        try:
            status1 = await self.event_bus.publish_with_status(target_channel, event)
            if target_channel != meeting_channel:
                await self.event_bus.publish_with_status(meeting_channel, event)
            return status1
        except Exception as e:
            logger.warning(f"Error publishing SKW event '{event.event_type}': {e}")
            return EventDeliveryStatus.FAILED

    async def publish_knowledge_event(
        self,
        event_type: str,
        obj: CanonicalKnowledgeObject,
        correlation_id: Optional[str] = None,
        extra_data: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """
        Protocol implementation for KnowledgePublisher protocol in component_interfaces.py.
        Maps canonical object and string event type to strongly typed event contract.
        """
        extra = extra_data or {}
        event_type_str = str(event_type).lower().strip()

        if event_type_str in {"knowledge.created", "created"}:
            event = KnowledgeCreatedEvent(
                knowledge_id=obj.knowledge_id,
                meeting_id=obj.meeting_id,
                object_type=obj.object_type,
                source_module=obj.source_module,
                version=obj.version,
                lifecycle_state=obj.lifecycle_state.value if hasattr(obj.lifecycle_state, "value") else str(obj.lifecycle_state),
                content=obj.content,
                title=obj.title,
                confidence_score=obj.confidence_score,
                metadata=obj.metadata if isinstance(obj.metadata, dict) else {},
                provenance=obj.provenance if isinstance(obj.provenance, dict) else {},
                payload=obj.payload if isinstance(obj.payload, dict) else {},
                correlation_id=correlation_id,
            )
        elif event_type_str in {"knowledge.validated", "validated", "accepted"}:
            event = KnowledgeValidatedEvent(
                knowledge_id=obj.knowledge_id,
                meeting_id=obj.meeting_id,
                object_type=obj.object_type,
                source_module=obj.source_module,
                version=obj.version,
                lifecycle_state=obj.lifecycle_state.value if hasattr(obj.lifecycle_state, "value") else str(obj.lifecycle_state),
                is_valid=True,
                validation_rules_applied=extra.get("validation_rules_applied", ["schema_validation", "confidence_bounds"]),
                correlation_id=correlation_id,
            )
        elif event_type_str in {"knowledge.indexed", "indexed"}:
            event = KnowledgeIndexedEvent(
                knowledge_id=obj.knowledge_id,
                meeting_id=obj.meeting_id,
                object_type=obj.object_type,
                source_module=obj.source_module,
                version=obj.version,
                lifecycle_state=obj.lifecycle_state.value if hasattr(obj.lifecycle_state, "value") else str(obj.lifecycle_state),
                qdrant_point_id=extra.get("qdrant_point_id", str(obj.knowledge_id)),
                vector_size=extra.get("vector_size", 384),
                collection_name=extra.get("collection_name", "abci_knowledge_objects"),
                correlation_id=correlation_id,
            )
        elif event_type_str in {"knowledge.published", "published"}:
            event = KnowledgePublishedEvent(
                knowledge_id=obj.knowledge_id,
                meeting_id=obj.meeting_id,
                object_type=obj.object_type,
                source_module=obj.source_module,
                version=obj.version,
                lifecycle_state=obj.lifecycle_state.value if hasattr(obj.lifecycle_state, "value") else str(obj.lifecycle_state),
                publisher=extra.get("publisher", "system"),
                channels=extra.get("channels", [self.DEFAULT_CHANNEL]),
                correlation_id=correlation_id,
            )
        elif event_type_str in {"knowledge.updated", "updated"}:
            event = KnowledgeUpdatedEvent(
                knowledge_id=obj.knowledge_id,
                meeting_id=obj.meeting_id,
                object_type=obj.object_type,
                source_module=obj.source_module,
                version=obj.version,
                lifecycle_state=obj.lifecycle_state.value if hasattr(obj.lifecycle_state, "value") else str(obj.lifecycle_state),
                previous_version=extra.get("previous_version", max(1, obj.version - 1)),
                updated_fields=extra.get("updated_fields", ["content", "metadata"]),
                changes_summary=extra.get("changes_summary"),
                correlation_id=correlation_id,
            )
        elif event_type_str in {"knowledge.versioned", "versioned"}:
            event = KnowledgeVersionedEvent(
                knowledge_id=obj.knowledge_id,
                meeting_id=obj.meeting_id,
                object_type=obj.object_type,
                source_module=obj.source_module,
                version=obj.version,
                lifecycle_state=obj.lifecycle_state.value if hasattr(obj.lifecycle_state, "value") else str(obj.lifecycle_state),
                previous_version=extra.get("previous_version", max(1, obj.version - 1)),
                new_version=obj.version,
                parent_id=extra.get("parent_id"),
                correlation_id=correlation_id,
            )
        elif event_type_str in {"knowledge.archived", "archived", "expired"}:
            event = KnowledgeArchivedEvent(
                knowledge_id=obj.knowledge_id,
                meeting_id=obj.meeting_id,
                object_type=obj.object_type,
                source_module=obj.source_module,
                version=obj.version,
                lifecycle_state=obj.lifecycle_state.value if hasattr(obj.lifecycle_state, "value") else str(obj.lifecycle_state),
                reason=extra.get("reason", "expired"),
                correlation_id=correlation_id,
            )
        else:
            # Fallback generic event mapping
            event = KnowledgeCreatedEvent(
                knowledge_id=obj.knowledge_id,
                meeting_id=obj.meeting_id,
                object_type=obj.object_type,
                source_module=obj.source_module,
                version=obj.version,
                lifecycle_state=obj.lifecycle_state.value if hasattr(obj.lifecycle_state, "value") else str(obj.lifecycle_state),
                content=obj.content,
                title=obj.title,
                confidence_score=obj.confidence_score,
                metadata=obj.metadata if isinstance(obj.metadata, dict) else {},
                provenance=obj.provenance if isinstance(obj.provenance, dict) else {},
                payload=obj.payload if isinstance(obj.payload, dict) else {},
                correlation_id=correlation_id,
            )

        return await self.publish_event(event)

    async def publish_created(
        self,
        obj: CanonicalKnowledgeObject,
        correlation_id: Optional[str] = None,
    ) -> bool:
        """Publish KnowledgeCreated event."""
        return await self.publish_knowledge_event("knowledge.created", obj, correlation_id=correlation_id)

    async def publish_validated(
        self,
        obj: CanonicalKnowledgeObject,
        validation_rules: Optional[List[str]] = None,
        correlation_id: Optional[str] = None,
    ) -> bool:
        """Publish KnowledgeValidated event."""
        return await self.publish_knowledge_event(
            "knowledge.validated",
            obj,
            correlation_id=correlation_id,
            extra_data={"validation_rules_applied": validation_rules or ["schema_validation", "confidence_bounds"]},
        )

    async def publish_indexed(
        self,
        obj: CanonicalKnowledgeObject,
        qdrant_point_id: str,
        vector_size: int = 384,
        collection_name: str = "abci_knowledge_objects",
        correlation_id: Optional[str] = None,
    ) -> bool:
        """Publish KnowledgeIndexed event."""
        return await self.publish_knowledge_event(
            "knowledge.indexed",
            obj,
            correlation_id=correlation_id,
            extra_data={
                "qdrant_point_id": qdrant_point_id,
                "vector_size": vector_size,
                "collection_name": collection_name,
            },
        )

    async def publish_published(
        self,
        obj: CanonicalKnowledgeObject,
        publisher: str = "system",
        channels: Optional[List[str]] = None,
        correlation_id: Optional[str] = None,
    ) -> bool:
        """Publish KnowledgePublished event."""
        return await self.publish_knowledge_event(
            "knowledge.published",
            obj,
            correlation_id=correlation_id,
            extra_data={"publisher": publisher, "channels": channels or [self.DEFAULT_CHANNEL]},
        )

    async def publish_updated(
        self,
        obj: CanonicalKnowledgeObject,
        previous_version: int,
        updated_fields: Optional[List[str]] = None,
        changes_summary: Optional[Dict[str, Any]] = None,
        correlation_id: Optional[str] = None,
    ) -> bool:
        """Publish KnowledgeUpdated event."""
        return await self.publish_knowledge_event(
            "knowledge.updated",
            obj,
            correlation_id=correlation_id,
            extra_data={
                "previous_version": previous_version,
                "updated_fields": updated_fields or [],
                "changes_summary": changes_summary,
            },
        )

    async def publish_versioned(
        self,
        obj: CanonicalKnowledgeObject,
        previous_version: int,
        new_version: int,
        parent_id: Optional[uuid.UUID] = None,
        correlation_id: Optional[str] = None,
    ) -> bool:
        """Publish KnowledgeVersioned event."""
        return await self.publish_knowledge_event(
            "knowledge.versioned",
            obj,
            correlation_id=correlation_id,
            extra_data={
                "previous_version": previous_version,
                "new_version": new_version,
                "parent_id": parent_id,
            },
        )

    async def publish_archived(
        self,
        obj: CanonicalKnowledgeObject,
        reason: Optional[str] = None,
        correlation_id: Optional[str] = None,
    ) -> bool:
        """Publish KnowledgeArchived event."""
        return await self.publish_knowledge_event(
            "knowledge.archived",
            obj,
            correlation_id=correlation_id,
            extra_data={"reason": reason or "archived"},
        )

    async def publish_validation_failed(
        self,
        meeting_id: uuid.UUID,
        object_type: str,
        source_module: str,
        error_message: str,
        errors: Optional[List[str]] = None,
        knowledge_id: Optional[uuid.UUID] = None,
        correlation_id: Optional[str] = None,
    ) -> bool:
        """Publish KnowledgeValidationFailed event."""
        event = KnowledgeValidationFailedEvent(
            knowledge_id=knowledge_id or uuid.uuid4(),
            meeting_id=meeting_id,
            object_type=object_type,
            source_module=source_module,
            version=1,
            lifecycle_state=SKWLifecycleState.REJECTED.value,
            error_code="VALIDATION_FAILED",
            error_message=error_message,
            errors=errors or [error_message],
            correlation_id=correlation_id,
        )
        return await self.publish_event(event)

    async def publish_processing_failed(
        self,
        knowledge_id: uuid.UUID,
        meeting_id: uuid.UUID,
        object_type: str,
        source_module: str,
        pipeline_stage: str,
        error_message: str,
        error_code: str = "PROCESSING_FAILED",
        version: int = 1,
        lifecycle_state: str = "invalid",
        details: Optional[Dict[str, Any]] = None,
        correlation_id: Optional[str] = None,
    ) -> bool:
        """Publish KnowledgeProcessingFailed event."""
        event = KnowledgeProcessingFailedEvent(
            knowledge_id=knowledge_id,
            meeting_id=meeting_id,
            object_type=object_type,
            source_module=source_module,
            version=version,
            lifecycle_state=lifecycle_state,
            pipeline_stage=pipeline_stage,
            error_code=error_code,
            error_message=error_message,
            details=details,
            correlation_id=correlation_id,
        )
        return await self.publish_event(event)
