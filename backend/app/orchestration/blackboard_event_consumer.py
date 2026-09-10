"""
Adaptive Blackboard Event Consumer
Subscribes to distributed Redis Event Bus channels, enforces event idempotency (by event_id),
and updates meeting Blackboard context across all 9 SKW lifecycle events.
"""

from typing import Any, Dict, Optional
import uuid

from app.core.logging import get_logger
from app.events.redis_bus import RedisEventBus, get_event_bus
from app.orchestration.blackboard_context import BlackboardContext, BlackboardKnowledgeItem
from app.skw.events.contracts import SKWEventType

logger = get_logger("orchestration.blackboard_consumer")


class BlackboardEventConsumer:
    """
    Event consumer for the Adaptive Blackboard.
    Consumes SKW domain events from the Redis Event Bus, enforces idempotency,
    and updates the meeting's Blackboard context accordingly.
    """

    def __init__(
        self,
        event_bus: Optional[RedisEventBus] = None,
    ) -> None:
        self.event_bus = event_bus or get_event_bus()
        self._contexts: Dict[uuid.UUID, BlackboardContext] = {}

    def get_or_create_context(self, meeting_id: uuid.UUID) -> BlackboardContext:
        """Retrieve existing Blackboard context for meeting or initialize a new one."""
        if meeting_id not in self._contexts:
            self._contexts[meeting_id] = BlackboardContext(meeting_id=meeting_id)
        return self._contexts[meeting_id]

    def get_context(self, meeting_id: uuid.UUID) -> Optional[BlackboardContext]:
        """Retrieve Blackboard context if present."""
        return self._contexts.get(meeting_id)

    async def handle_event(self, event_dict: Dict[str, Any]) -> bool:
        """
        Process an incoming SKW event dictionary.
        Enforces idempotency via event_id deduplication.
        Returns True if processed or acknowledged, False if ignored or invalid.
        """
        event_id_raw = event_dict.get("event_id")
        if not event_id_raw:
            logger.warning("Received event without event_id; discarding")
            return False

        try:
            event_id = uuid.UUID(str(event_id_raw))
        except (ValueError, TypeError):
            logger.warning(f"Malformed event_id '{event_id_raw}'; discarding")
            return False

        meeting_id_raw = event_dict.get("meeting_id")
        if not meeting_id_raw:
            logger.warning("Received event without meeting_id; discarding")
            return False

        try:
            meeting_id = uuid.UUID(str(meeting_id_raw))
        except (ValueError, TypeError):
            logger.warning(f"Malformed meeting_id '{meeting_id_raw}'; discarding")
            return False

        context = self.get_or_create_context(meeting_id)

        # Idempotency check
        if context.is_event_seen(event_id):
            logger.info(f"Duplicate event {event_id} received for meeting {meeting_id}; skipping duplicate processing")
            return True

        # Mark event as seen
        context.mark_event_seen(event_id)

        event_type = event_dict.get("event_type")
        knowledge_id_raw = event_dict.get("knowledge_id")
        knowledge_id = uuid.UUID(str(knowledge_id_raw)) if knowledge_id_raw else None
        correlation_id = event_dict.get("correlation_id")

        logger.debug(f"Processing event '{event_type}' (id={event_id}) for meeting {meeting_id}")

        if event_type == SKWEventType.KNOWLEDGE_PUBLISHED.value:
            # Full published event - update or insert active item
            if knowledge_id:
                # If content is present in payload or event dict
                content = event_dict.get("content")
                if not content and context.get_item(knowledge_id):
                    content = context.get_item(knowledge_id).content  # type: ignore[union-attr]
                content = content or "[Published Knowledge Object]"

                item = BlackboardKnowledgeItem(
                    knowledge_id=knowledge_id,
                    meeting_id=meeting_id,
                    object_type=event_dict.get("object_type", "knowledge"),
                    source_module=event_dict.get("source_module", "skw"),
                    title=event_dict.get("title"),
                    content=content,
                    confidence_score=event_dict.get("confidence_score"),
                    version=event_dict.get("version", 1),
                    lifecycle_state="published",
                    correlation_id=correlation_id,
                    metadata=event_dict.get("metadata", {}),
                    provenance=event_dict.get("provenance", {}),
                    payload=event_dict.get("payload", {}),
                )
                context.upsert_item(item)

        elif event_type == SKWEventType.KNOWLEDGE_CREATED.value:
            # Preliminary creation event
            if knowledge_id:
                item = BlackboardKnowledgeItem(
                    knowledge_id=knowledge_id,
                    meeting_id=meeting_id,
                    object_type=event_dict.get("object_type", "knowledge"),
                    source_module=event_dict.get("source_module", "skw"),
                    title=event_dict.get("title"),
                    content=event_dict.get("content", ""),
                    confidence_score=event_dict.get("confidence_score"),
                    version=event_dict.get("version", 1),
                    lifecycle_state="created",
                    correlation_id=correlation_id,
                    metadata=event_dict.get("metadata", {}),
                    provenance=event_dict.get("provenance", {}),
                    payload=event_dict.get("payload", {}),
                )
                context.upsert_item(item)

        elif event_type in {SKWEventType.KNOWLEDGE_VALIDATED.value, SKWEventType.KNOWLEDGE_INDEXED.value}:
            # Update state of existing item in Blackboard context
            if knowledge_id:
                existing = context.get_item(knowledge_id)
                if existing:
                    existing.lifecycle_state = "validated" if "validated" in event_type else "indexed"
                    if correlation_id:
                        existing.correlation_id = correlation_id

        elif event_type == SKWEventType.KNOWLEDGE_UPDATED.value:
            # Update existing item in Blackboard context
            if knowledge_id:
                existing = context.get_item(knowledge_id)
                if existing:
                    existing.version = event_dict.get("version", existing.version + 1)
                    existing.lifecycle_state = "updated"
                    if "content" in event_dict and event_dict["content"]:
                        existing.content = event_dict["content"]
                    if correlation_id:
                        existing.correlation_id = correlation_id
                else:
                    # Knowledge updated without prior created event in memory
                    item = BlackboardKnowledgeItem(
                        knowledge_id=knowledge_id,
                        meeting_id=meeting_id,
                        object_type=event_dict.get("object_type", "knowledge"),
                        source_module=event_dict.get("source_module", "skw"),
                        title=event_dict.get("title"),
                        content=event_dict.get("content", "[Updated Knowledge]"),
                        version=event_dict.get("version", 2),
                        lifecycle_state="updated",
                        correlation_id=correlation_id,
                    )
                    context.upsert_item(item)

        elif event_type == SKWEventType.KNOWLEDGE_VERSIONED.value:
            # New version revision
            if knowledge_id:
                existing = context.get_item(knowledge_id)
                if existing:
                    existing.version = event_dict.get("new_version", existing.version + 1)
                    existing.lifecycle_state = "versioned"
                    if correlation_id:
                        existing.correlation_id = correlation_id

        elif event_type == SKWEventType.KNOWLEDGE_ARCHIVED.value:
            # Archival event
            if knowledge_id:
                context.archive_item(knowledge_id, reason=event_dict.get("reason"))

        elif event_type in {SKWEventType.KNOWLEDGE_VALIDATION_FAILED.value, SKWEventType.KNOWLEDGE_PROCESSING_FAILED.value}:
            # Failed / rejected knowledge - record failure diagnostic without promoting to active knowledge
            context.record_failure({
                "event_id": str(event_id),
                "event_type": event_type,
                "knowledge_id": str(knowledge_id) if knowledge_id else None,
                "error_code": event_dict.get("error_code", "ERROR"),
                "error_message": event_dict.get("error_message", "Unknown error"),
                "correlation_id": correlation_id,
            })
            logger.info(f"Recorded failure diagnostic for {event_type} in meeting {meeting_id}")

        return True

    def register_subscriptions(self, meeting_id: Optional[uuid.UUID] = None) -> None:
        """Register consumer listener on the Redis Event Bus."""
        global_channel = "events:knowledge"
        self.event_bus.subscribe(global_channel, self.handle_event)

        if meeting_id:
            meeting_channel = f"events:meetings:{str(meeting_id)}:knowledge"
            self.event_bus.subscribe(meeting_channel, self.handle_event)

    def unregister_subscriptions(self, meeting_id: Optional[uuid.UUID] = None) -> None:
        """Unregister consumer listener."""
        global_channel = "events:knowledge"
        self.event_bus.unsubscribe(global_channel, self.handle_event)

        if meeting_id:
            meeting_channel = f"events:meetings:{str(meeting_id)}:knowledge"
            self.event_bus.unsubscribe(meeting_channel, self.handle_event)
