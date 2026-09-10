"""
Comprehensive Unit & Integration Tests for Phase 4.8:
SKW Event Integration Boundary & Strongly Typed Event Bus Contracts.
Verifies all 9 lifecycle event contracts, payload schemas, Redis Pub/Sub event bus,
lifecycle enforcement, idempotency, traceability, and failure isolation.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock, patch
import uuid
import pytest
import pytest_asyncio
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.events.redis_bus import RedisEventBus, get_event_bus
from app.models.meeting import Meeting
from app.repositories.meeting_repo import MeetingRepository
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
    SKWEventType,
)
from app.skw.events.publisher import SKWEventPublisher
from app.skw.interfaces.component_interfaces import KnowledgePublisher as KnowledgePublisherProtocol
from app.skw.models.knowledge_object import CanonicalKnowledgeObject, SKWLifecycleState
from app.skw.services.knowledge_publisher import KnowledgePublisher
from app.skw.services.version_manager import DefaultVersionManager


# ============================================================================
# 1. STRONGLY TYPED EVENT CONTRACTS & SCHEMA VALIDATION TESTS
# ============================================================================


def test_knowledge_created_event_schema() -> None:
    """Verify KnowledgeCreatedEvent payload structure, default values, and schema constraints."""
    knowledge_id = uuid.uuid4()
    meeting_id = uuid.uuid4()

    event = KnowledgeCreatedEvent(
        knowledge_id=knowledge_id,
        meeting_id=meeting_id,
        object_type="decision",
        source_module="decision_agent",
        version=1,
        lifecycle_state=SKWLifecycleState.CREATED.value,
        content="Migrate database to PostgreSQL async driver",
        title="DB Migration Decision",
        confidence_score=0.95,
        metadata={"priority": "high"},
        provenance={"producing_module": "decision_agent"},
        payload={"approved_by": "architect"},
        correlation_id="corr-12345",
    )

    assert event.event_type == SKWEventType.KNOWLEDGE_CREATED
    assert isinstance(event.event_id, uuid.UUID)
    assert isinstance(event.timestamp, datetime)
    assert event.knowledge_id == knowledge_id
    assert event.meeting_id == meeting_id
    assert event.object_type == "decision"
    assert event.version == 1
    assert event.confidence_score == 0.95
    assert event.correlation_id == "corr-12345"

    # Verify JSON serialization
    serialized = event.model_dump_json()
    assert "Migrate database to PostgreSQL async driver" in serialized
    assert "corr-12345" in serialized


def test_knowledge_validated_event_schema() -> None:
    """Verify KnowledgeValidatedEvent schema and attributes."""
    knowledge_id = uuid.uuid4()
    meeting_id = uuid.uuid4()

    event = KnowledgeValidatedEvent(
        knowledge_id=knowledge_id,
        meeting_id=meeting_id,
        object_type="action_item",
        source_module="action_agent",
        version=1,
        lifecycle_state=SKWLifecycleState.ACCEPTED.value,
        is_valid=True,
        validation_rules_applied=["schema_validation", "confidence_bounds", "module_attribution"],
    )

    assert event.event_type == SKWEventType.KNOWLEDGE_VALIDATED
    assert event.is_valid is True
    assert len(event.validation_rules_applied) == 3


def test_knowledge_indexed_event_schema() -> None:
    """Verify KnowledgeIndexedEvent schema and attributes."""
    knowledge_id = uuid.uuid4()
    meeting_id = uuid.uuid4()

    event = KnowledgeIndexedEvent(
        knowledge_id=knowledge_id,
        meeting_id=meeting_id,
        object_type="topic",
        source_module="topic_agent",
        version=1,
        lifecycle_state=SKWLifecycleState.INDEXED.value,
        qdrant_point_id=str(knowledge_id),
        vector_size=384,
        collection_name="abci_knowledge_objects",
    )

    assert event.event_type == SKWEventType.KNOWLEDGE_INDEXED
    assert event.qdrant_point_id == str(knowledge_id)
    assert event.vector_size == 384


def test_knowledge_published_event_schema() -> None:
    """Verify KnowledgePublishedEvent schema and attributes."""
    knowledge_id = uuid.uuid4()
    meeting_id = uuid.uuid4()

    event = KnowledgePublishedEvent(
        knowledge_id=knowledge_id,
        meeting_id=meeting_id,
        object_type="decision",
        source_module="system",
        version=1,
        lifecycle_state=SKWLifecycleState.PUBLISHED.value,
        publisher="system",
        channels=["events:knowledge", f"events:meetings:{meeting_id}:knowledge"],
    )

    assert event.event_type == SKWEventType.KNOWLEDGE_PUBLISHED
    assert len(event.channels) == 2


def test_knowledge_updated_and_versioned_event_schemas() -> None:
    """Verify KnowledgeUpdatedEvent and KnowledgeVersionedEvent schemas."""
    knowledge_id = uuid.uuid4()
    meeting_id = uuid.uuid4()
    parent_id = uuid.uuid4()

    # Updated event
    upd_event = KnowledgeUpdatedEvent(
        knowledge_id=knowledge_id,
        meeting_id=meeting_id,
        object_type="summary",
        source_module="summary_agent",
        version=2,
        lifecycle_state=SKWLifecycleState.UPDATED.value,
        previous_version=1,
        updated_fields=["content", "metadata"],
        changes_summary={"diff": "Added conclusion section"},
    )
    assert upd_event.event_type == SKWEventType.KNOWLEDGE_UPDATED
    assert upd_event.previous_version == 1

    # Versioned event
    ver_event = KnowledgeVersionedEvent(
        knowledge_id=knowledge_id,
        meeting_id=meeting_id,
        object_type="summary",
        source_module="summary_agent",
        version=2,
        lifecycle_state=SKWLifecycleState.VERSIONED.value,
        previous_version=1,
        new_version=2,
        parent_id=parent_id,
    )
    assert ver_event.event_type == SKWEventType.KNOWLEDGE_VERSIONED
    assert ver_event.new_version == 2
    assert ver_event.parent_id == parent_id


def test_knowledge_archived_and_failed_event_schemas() -> None:
    """Verify KnowledgeArchivedEvent, ValidationFailed, and ProcessingFailed schemas."""
    knowledge_id = uuid.uuid4()
    meeting_id = uuid.uuid4()

    # Archived event
    arch_event = KnowledgeArchivedEvent(
        knowledge_id=knowledge_id,
        meeting_id=meeting_id,
        object_type="decision",
        source_module="system",
        version=1,
        lifecycle_state=SKWLifecycleState.ARCHIVED.value,
        reason="Meeting retention period expired",
    )
    assert arch_event.event_type == SKWEventType.KNOWLEDGE_ARCHIVED
    assert arch_event.reason == "Meeting retention period expired"

    # Validation failed event
    val_fail = KnowledgeValidationFailedEvent(
        knowledge_id=knowledge_id,
        meeting_id=meeting_id,
        object_type="decision",
        source_module="system",
        version=1,
        lifecycle_state=SKWLifecycleState.REJECTED.value,
        error_code="VALIDATION_FAILED",
        error_message="Missing required field: content",
        errors=["Missing required field: content", "Invalid confidence score"],
    )
    assert val_fail.event_type == SKWEventType.KNOWLEDGE_VALIDATION_FAILED
    assert len(val_fail.errors) == 2

    # Processing failed event
    proc_fail = KnowledgeProcessingFailedEvent(
        knowledge_id=knowledge_id,
        meeting_id=meeting_id,
        object_type="decision",
        source_module="system",
        version=1,
        lifecycle_state="invalid",
        pipeline_stage="semantic_indexing",
        error_code="QDRANT_UNAVAILABLE",
        error_message="Vector index connection timeout",
        details={"attempt": 3, "timeout_sec": 5.0},
    )
    assert proc_fail.event_type == SKWEventType.KNOWLEDGE_PROCESSING_FAILED
    assert proc_fail.pipeline_stage == "semantic_indexing"


def test_event_schema_boundary_and_type_enforcement() -> None:
    """Verify validation errors when required fields or bounds are violated in event contracts."""
    knowledge_id = uuid.uuid4()
    meeting_id = uuid.uuid4()

    # Out of bounds confidence score
    with pytest.raises(ValidationError):
        KnowledgeCreatedEvent(
            knowledge_id=knowledge_id,
            meeting_id=meeting_id,
            object_type="decision",
            source_module="agent",
            lifecycle_state="created",
            content="Valid content",
            confidence_score=1.5,  # Invalid: > 1.0
        )

    # Invalid version (< 1)
    with pytest.raises(ValidationError):
        KnowledgeCreatedEvent(
            knowledge_id=knowledge_id,
            meeting_id=meeting_id,
            object_type="decision",
            source_module="agent",
            lifecycle_state="created",
            content="Valid content",
            version=0,  # Invalid: < 1
        )


# ============================================================================
# 2. REDIS EVENT BUS & SUBSCRIPTION DISPATCHING TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_redis_event_bus_in_memory_subscription_and_dispatch() -> None:
    """Verify that RedisEventBus correctly dispatches events to registered local subscribers."""
    mock_redis = AsyncMock()
    mock_redis.publish.return_value = 1

    bus = RedisEventBus(redis_client=mock_redis)

    received_events: List[Dict[str, Any]] = []

    async def sample_handler(event_data: Dict[str, Any]) -> None:
        received_events.append(event_data)

    channel = "events:knowledge"
    bus.subscribe(channel, sample_handler)

    test_event = KnowledgeCreatedEvent(
        knowledge_id=uuid.uuid4(),
        meeting_id=uuid.uuid4(),
        object_type="decision",
        source_module="test_agent",
        lifecycle_state="created",
        content="Test event dispatch",
    )

    success = await bus.publish(channel, test_event)
    assert success is True
    mock_redis.publish.assert_called_once()

    # Check local in-memory subscriber received the event
    assert len(received_events) == 1
    assert received_events[0]["content"] == "Test event dispatch"
    assert received_events[0]["event_type"] == SKWEventType.KNOWLEDGE_CREATED.value

    # Test unsubscribe
    bus.unsubscribe(channel, sample_handler)
    await bus.publish(channel, test_event)
    assert len(received_events) == 1  # No additional call


@pytest.mark.asyncio
async def test_redis_event_bus_resilience_when_redis_offline() -> None:
    """Verify that RedisEventBus handles Redis connection failures gracefully without raising exceptions."""
    # Simulate Redis client raising an exception
    failing_redis = AsyncMock()
    failing_redis.publish.side_effect = ConnectionError("Redis connection refused")

    bus = RedisEventBus(redis_client=failing_redis)

    received_events: List[Dict[str, Any]] = []

    async def fallback_handler(event_data: Dict[str, Any]) -> None:
        received_events.append(event_data)

    channel = "events:knowledge"
    bus.subscribe(channel, fallback_handler)

    test_event = KnowledgeValidatedEvent(
        knowledge_id=uuid.uuid4(),
        meeting_id=uuid.uuid4(),
        object_type="action_item",
        source_module="test_agent",
        lifecycle_state="accepted",
        is_valid=True,
    )

    # Should not raise exception; should return False and still dispatch locally
    success = await bus.publish(channel, test_event)
    assert success is False
    assert len(received_events) == 1
    assert received_events[0]["event_type"] == SKWEventType.KNOWLEDGE_VALIDATED.value


# ============================================================================
# 3. SKW EVENT PUBLISHER & LIFECYCLE EVENT EMISSION TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_skw_event_publisher_typed_emission_and_multi_channel_routing() -> None:
    """Verify that SKWEventPublisher routes events to both global and meeting-scoped channels."""
    mock_redis = AsyncMock()
    mock_redis.publish.return_value = 1
    bus = RedisEventBus(redis_client=mock_redis)

    publisher = SKWEventPublisher(event_bus=bus)

    meeting_id = uuid.uuid4()
    knowledge_id = uuid.uuid4()

    canonical_ko = CanonicalKnowledgeObject(
        knowledge_id=knowledge_id,
        meeting_id=meeting_id,
        object_type="decision",
        source_module="decision_agent",
        content="Decide architecture approach",
        confidence_score=0.92,
        version=1,
        lifecycle_state=SKWLifecycleState.CREATED,
    )

    # 1. Publish Created
    res_created = await publisher.publish_created(canonical_ko, correlation_id="req-1")
    assert res_created is True

    # 2. Publish Validated
    res_val = await publisher.publish_validated(canonical_ko, validation_rules=["schema_ok"])
    assert res_val is True

    # 3. Publish Indexed
    res_idx = await publisher.publish_indexed(canonical_ko, qdrant_point_id=str(knowledge_id))
    assert res_idx is True

    # 4. Publish Published
    res_pub = await publisher.publish_published(canonical_ko, publisher="agent_x")
    assert res_pub is True

    # 5. Publish Updated
    res_upd = await publisher.publish_updated(canonical_ko, previous_version=1, updated_fields=["content"])
    assert res_upd is True

    # 6. Publish Versioned
    res_ver = await publisher.publish_versioned(canonical_ko, previous_version=1, new_version=2)
    assert res_ver is True

    # 7. Publish Archived
    res_arch = await publisher.publish_archived(canonical_ko, reason="superseded")
    assert res_arch is True

    # 8. Publish Validation Failed
    res_val_fail = await publisher.publish_validation_failed(
        meeting_id=meeting_id,
        object_type="decision",
        source_module="agent",
        error_message="Invalid confidence",
    )
    assert res_val_fail is True

    # 9. Publish Processing Failed
    res_proc_fail = await publisher.publish_processing_failed(
        knowledge_id=knowledge_id,
        meeting_id=meeting_id,
        object_type="decision",
        source_module="agent",
        pipeline_stage="embedding",
        error_message="Timeout embedding",
    )
    assert res_proc_fail is True

    # Verify publish was called for multiple channels across the 9 invocations
    assert mock_redis.publish.call_count >= 9


@pytest.mark.asyncio
async def test_skw_event_publisher_protocol_conformance() -> None:
    """Verify that SKWEventPublisher satisfies the KnowledgePublisher protocol."""
    publisher = SKWEventPublisher()
    assert isinstance(publisher, KnowledgePublisherProtocol)


# ============================================================================
# 4. END-TO-END PUBLISHING SERVICE & EVENT INTEGRATION TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_knowledge_publisher_service_emits_published_event(db_session: AsyncSession) -> None:
    """Verify that KnowledgePublisher emits KnowledgePublishedEvent upon publication transition."""
    meeting_repo = MeetingRepository(db_session)
    meeting = await meeting_repo.create(Meeting(title="Event Test Meeting"))

    vm = DefaultVersionManager(db_session)
    ko = await vm.create_version(
        meeting_id=meeting.id,
        object_type="decision",
        source_module="Agent1",
        content="Deploy microservices to staging",
        confidence_score=0.88,
    )

    # Transition to ACCEPTED state
    await vm.transition_lifecycle(ko.id, SKWLifecycleState.ACCEPTED)

    mock_redis = AsyncMock()
    mock_redis.publish.return_value = 1
    event_bus = RedisEventBus(redis_client=mock_redis)
    event_publisher = SKWEventPublisher(event_bus=event_bus)

    publisher_service = KnowledgePublisher(
        session=db_session,
        version_manager=vm,
        event_publisher=event_publisher,
    )

    # Publish knowledge object
    published_ko = await publisher_service.publish_knowledge_object(ko.id, correlation_id="trace-abc")
    assert published_ko.status == SKWLifecycleState.PUBLISHED.value

    # Verify publish was invoked on Redis Pub/Sub
    assert mock_redis.publish.call_count >= 1
    call_args_list = mock_redis.publish.call_args_list
    # Find published payload
    published_payload_str = str(call_args_list[-1])
    assert "knowledge.published" in published_payload_str or "events:knowledge" in published_payload_str


@pytest.mark.asyncio
async def test_knowledge_publisher_service_emits_processing_failed_on_prerequisite_violation(
    db_session: AsyncSession,
) -> None:
    """Verify that attempting to publish in CREATED or REJECTED state emits a failure event."""
    meeting_repo = MeetingRepository(db_session)
    meeting = await meeting_repo.create(Meeting(title="Failure Event Meeting"))

    vm = DefaultVersionManager(db_session)
    ko = await vm.create_version(
        meeting_id=meeting.id,
        object_type="action_item",
        source_module="Agent1",
        content="Unvalidated action item",
    )
    assert ko.status == SKWLifecycleState.CREATED.value

    mock_redis = AsyncMock()
    mock_redis.publish.return_value = 1
    event_bus = RedisEventBus(redis_client=mock_redis)
    event_publisher = SKWEventPublisher(event_bus=event_bus)

    publisher_service = KnowledgePublisher(
        session=db_session,
        version_manager=vm,
        event_publisher=event_publisher,
    )

    with pytest.raises(Exception):
        await publisher_service.publish_knowledge_object(ko.id)

    # Verify failure event was dispatched
    assert mock_redis.publish.call_count >= 1
    call_args_str = str(mock_redis.publish.call_args_list)
    assert "knowledge.processing_failed" in call_args_str or "prerequisite_validation" in call_args_str
