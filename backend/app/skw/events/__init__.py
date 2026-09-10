"""
SKW Events Package
Exports strongly typed event contracts and SKWEventPublisher for event bus integration.
"""

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
from app.skw.events.publisher import SKWEventPublisher

__all__ = [
    "SKWEventType",
    "SKWBaseEvent",
    "KnowledgeCreatedEvent",
    "KnowledgeValidatedEvent",
    "KnowledgeIndexedEvent",
    "KnowledgePublishedEvent",
    "KnowledgeUpdatedEvent",
    "KnowledgeVersionedEvent",
    "KnowledgeArchivedEvent",
    "KnowledgeValidationFailedEvent",
    "KnowledgeProcessingFailedEvent",
    "SKWEvent",
    "SKWEventPublisher",
]
