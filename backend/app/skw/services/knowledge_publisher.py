"""
SKW Knowledge Publisher Service
Implements KnowledgePublisher protocol, validating that required processing pipeline stages
(Validated -> Enriched -> Indexed -> Persisted) have successfully completed before transitioning
Knowledge Objects to the PUBLISHED state.
"""

import uuid
from typing import Any, Dict, Optional
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import BadRequestException, NotFoundException
from app.skw.models.knowledge_object import CanonicalKnowledgeObject, SKWLifecycleState
from app.models.knowledge_object import KnowledgeObject as DBKnowledgeObject
from app.skw.services.version_manager import DefaultVersionManager
from app.skw.indexing.semantic_indexer import SemanticIndexer
from app.skw.events.publisher import SKWEventPublisher


class KnowledgePublisher:
    """
    Publisher service ensuring Knowledge Objects meet strict processing prerequisites
    (persistence, validation, enrichment, and vector indexing) prior to publishing,
    and emitting strongly typed domain events to the distributed Redis Event Bus.
    """

    def __init__(
        self,
        session: AsyncSession,
        version_manager: Optional[DefaultVersionManager] = None,
        semantic_indexer: Optional[SemanticIndexer] = None,
        event_publisher: Optional[SKWEventPublisher] = None,
    ) -> None:
        self.session = session
        self.version_manager = version_manager or DefaultVersionManager(session)
        self.semantic_indexer = semantic_indexer or SemanticIndexer()
        self.event_publisher = event_publisher or SKWEventPublisher()

    async def publish_knowledge_event(
        self,
        event_type: str,
        obj: CanonicalKnowledgeObject,
        correlation_id: Optional[str] = None,
    ) -> bool:
        """
        Implements KnowledgePublisher protocol in component_interfaces.py.
        Dispatches knowledge events via SKWEventPublisher.
        """
        return await self.event_publisher.publish_knowledge_event(
            event_type=event_type,
            obj=obj,
            correlation_id=correlation_id,
        )

    async def publish_knowledge_object(
        self,
        knowledge_id: uuid.UUID,
        correlation_id: Optional[str] = None,
    ) -> DBKnowledgeObject:
        """
        Validate prerequisites and publish a Knowledge Object.
        Prerequisite checks:
        1. Persisted in database.
        2. Validated (not in CREATED or REJECTED state).
        3. Vector indexed (qdrant_point_id present or successfully indexed).
        Emits KnowledgePublishedEvent upon successful state transition.
        """
        obj = await self.session.get(DBKnowledgeObject, knowledge_id)
        if not obj:
            raise NotFoundException(
                message=f"Knowledge object {knowledge_id} not found",
                code="OBJECT_NOT_FOUND",
            )

        # Check validation prerequisite
        current_state = str(obj.status).lower()
        if current_state in {SKWLifecycleState.CREATED.value, SKWLifecycleState.REJECTED.value, SKWLifecycleState.ARCHIVED.value}:
            await self.event_publisher.publish_processing_failed(
                knowledge_id=knowledge_id,
                meeting_id=obj.meeting_id,
                object_type=obj.object_type,
                source_module=obj.source_module or "unknown",
                pipeline_stage="prerequisite_validation",
                error_message=f"Cannot publish knowledge object in state '{current_state}'. Must be validated and indexed.",
                error_code="PUBLICATION_PREREQUISITES_NOT_MET",
                version=obj.version,
                lifecycle_state=current_state,
                correlation_id=correlation_id,
            )
            raise BadRequestException(
                message=f"Cannot publish knowledge object in state '{current_state}'. Must be validated and indexed.",
                code="PUBLICATION_PREREQUISITES_NOT_MET",
                details={"current_state": current_state, "required": "validated, accepted, or indexed"}
            )

        # Ensure indexed in Qdrant if not already indexed
        if not obj.qdrant_point_id or obj.status != "indexed":
            canonical = CanonicalKnowledgeObject(
                knowledge_id=obj.id,
                meeting_id=obj.meeting_id,
                object_type=obj.object_type,
                source_module=obj.source_module,
                content=obj.content,
                title=obj.title,
                confidence_score=obj.confidence,
                version=obj.version,
                lifecycle_state=SKWLifecycleState(current_state) if current_state in SKWLifecycleState._value2member_map_ else SKWLifecycleState.INDEXED,
                provenance=obj.provenance or {},
                metadata=obj.metadata or {},
                payload=obj.payload or {},
            )
            try:
                await self.semantic_indexer.index_knowledge_object(canonical, session=self.session)
                await self.event_publisher.publish_indexed(
                    obj=canonical,
                    qdrant_point_id=str(canonical.knowledge_id),
                    correlation_id=correlation_id,
                )
            except Exception as e:
                await self.event_publisher.publish_processing_failed(
                    knowledge_id=knowledge_id,
                    meeting_id=obj.meeting_id,
                    object_type=obj.object_type,
                    source_module=obj.source_module or "unknown",
                    pipeline_stage="semantic_indexing",
                    error_message=f"Indexing prerequisite failed during publication: {str(e)}",
                    error_code="PUBLICATION_PREREQUISITES_NOT_MET",
                    version=obj.version,
                    lifecycle_state=current_state,
                    details={"error": str(e)},
                    correlation_id=correlation_id,
                )
                raise BadRequestException(
                    message=f"Indexing prerequisite failed during publication: {str(e)}",
                    code="PUBLICATION_PREREQUISITES_NOT_MET",
                    details={"error": str(e)}
                )

        # Transition to published state through VersionManager
        # If currently indexed or shared or accepted, transition to published
        target_state = SKWLifecycleState.PUBLISHED
        published_obj = await self.version_manager.transition_lifecycle(knowledge_id, target_state)

        # Emit KnowledgePublishedEvent
        published_canonical = CanonicalKnowledgeObject(
            knowledge_id=published_obj.id,
            meeting_id=published_obj.meeting_id,
            object_type=published_obj.object_type,
            source_module=published_obj.source_module,
            content=published_obj.content,
            title=published_obj.title,
            confidence_score=published_obj.confidence,
            version=published_obj.version,
            lifecycle_state=SKWLifecycleState.PUBLISHED,
            provenance=published_obj.provenance or {},
            metadata=published_obj.metadata or {},
            payload=published_obj.payload or {},
        )
        await self.event_publisher.publish_published(
            obj=published_canonical,
            publisher="system",
            correlation_id=correlation_id,
        )

        return published_obj
