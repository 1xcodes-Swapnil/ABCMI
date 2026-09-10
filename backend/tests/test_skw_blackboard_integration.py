"""
SKW ↔ Adaptive Blackboard Integration Boundary Tests (Phase 4.9)
Verifies:
1. Blackboard event consumer receiving all 9 SKW lifecycle events.
2. Blackboard event deduplication / idempotency via event_id.
3. Blackboard context management without DB/Qdrant coupling.
4. Authorized Knowledge Requests (Structured, Semantic, Hybrid) via BlackboardSKWClient.
5. Security, RBAC, and Meeting scope validation on Knowledge Requests.
6. Audit logging of Knowledge Requests and unauthorized attempts.
7. Explicit distinction between DISTRIBUTED and LOCAL_FALLBACK delivery status.
8. Isolation: Blackboard failure does not corrupt SKW persistence or indexing.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional
import uuid
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.core.exceptions import ForbiddenException, UnauthorizedException
from app.events.redis_bus import EventDeliveryStatus, RedisEventBus
from app.models.knowledge_object import KnowledgeObject as DBKnowledgeObject
from app.orchestration.blackboard_context import BlackboardContext, BlackboardKnowledgeItem
from app.orchestration.blackboard_event_consumer import BlackboardEventConsumer
from app.orchestration.skw_client import BlackboardSKWClient
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
    SKWEventType,
)
from app.skw.models.knowledge_object import CanonicalKnowledgeObject, SKWLifecycleState
from app.skw.services.knowledge_query_engine import KnowledgeQueryEngine


@pytest.fixture
def sample_meeting_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def sample_knowledge_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def mock_event_bus() -> RedisEventBus:
    bus = RedisEventBus()
    return bus


# -----------------------------------------------------------------------------
# 1. Event Consumption Tests
# -----------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_blackboard_consumes_knowledge_published(sample_meeting_id, sample_knowledge_id):
    consumer = BlackboardEventConsumer()
    event_id = uuid.uuid4()

    event_payload = {
        "event_id": str(event_id),
        "event_type": SKWEventType.KNOWLEDGE_PUBLISHED.value,
        "meeting_id": str(sample_meeting_id),
        "knowledge_id": str(sample_knowledge_id),
        "object_type": "decision",
        "source_module": "decision_agent",
        "title": "Migrate to Microservices",
        "content": "The team agreed to migrate the authentication service to Go.",
        "confidence_score": 0.95,
        "version": 1,
        "correlation_id": "corr-pub-123",
        "metadata": {"tags": ["architecture", "go"]},
    }

    success = await consumer.handle_event(event_payload)
    assert success is True

    context = consumer.get_context(sample_meeting_id)
    assert context is not None
    assert context.is_event_seen(event_id) is True

    item = context.get_item(sample_knowledge_id)
    assert item is not None
    assert item.title == "Migrate to Microservices"
    assert item.content == "The team agreed to migrate the authentication service to Go."
    assert item.object_type == "decision"
    assert item.confidence_score == 0.95
    assert item.lifecycle_state == "published"
    assert item.correlation_id == "corr-pub-123"
    assert item.metadata.get("tags") == ["architecture", "go"]


@pytest.mark.asyncio
async def test_blackboard_consumes_knowledge_created(sample_meeting_id, sample_knowledge_id):
    consumer = BlackboardEventConsumer()
    event_id = uuid.uuid4()

    event_payload = {
        "event_id": str(event_id),
        "event_type": SKWEventType.KNOWLEDGE_CREATED.value,
        "meeting_id": str(sample_meeting_id),
        "knowledge_id": str(sample_knowledge_id),
        "object_type": "action_item",
        "source_module": "action_extractor",
        "title": "Draft PRD",
        "content": "Draft the Phase 5 PRD by Friday.",
        "confidence_score": 0.88,
        "version": 1,
        "correlation_id": "corr-created-456",
    }

    success = await consumer.handle_event(event_payload)
    assert success is True

    context = consumer.get_context(sample_meeting_id)
    assert context is not None
    item = context.get_item(sample_knowledge_id)
    assert item is not None
    assert item.lifecycle_state == "created"
    assert item.title == "Draft PRD"


@pytest.mark.asyncio
async def test_blackboard_consumes_knowledge_validated_and_indexed(sample_meeting_id, sample_knowledge_id):
    consumer = BlackboardEventConsumer()
    # First create
    await consumer.handle_event({
        "event_id": str(uuid.uuid4()),
        "event_type": SKWEventType.KNOWLEDGE_CREATED.value,
        "meeting_id": str(sample_meeting_id),
        "knowledge_id": str(sample_knowledge_id),
        "object_type": "summary",
        "source_module": "summarizer",
        "content": "Initial summary content",
    })

    # Validate
    await consumer.handle_event({
        "event_id": str(uuid.uuid4()),
        "event_type": SKWEventType.KNOWLEDGE_VALIDATED.value,
        "meeting_id": str(sample_meeting_id),
        "knowledge_id": str(sample_knowledge_id),
    })

    context = consumer.get_context(sample_meeting_id)
    item = context.get_item(sample_knowledge_id)
    assert item.lifecycle_state == "validated"

    # Index
    await consumer.handle_event({
        "event_id": str(uuid.uuid4()),
        "event_type": SKWEventType.KNOWLEDGE_INDEXED.value,
        "meeting_id": str(sample_meeting_id),
        "knowledge_id": str(sample_knowledge_id),
    })
    assert item.lifecycle_state == "indexed"


@pytest.mark.asyncio
async def test_blackboard_consumes_knowledge_updated(sample_meeting_id, sample_knowledge_id):
    consumer = BlackboardEventConsumer()
    # Initial published
    await consumer.handle_event({
        "event_id": str(uuid.uuid4()),
        "event_type": SKWEventType.KNOWLEDGE_PUBLISHED.value,
        "meeting_id": str(sample_meeting_id),
        "knowledge_id": str(sample_knowledge_id),
        "object_type": "decision",
        "source_module": "decision_agent",
        "title": "Initial Title",
        "content": "Original Content",
        "version": 1,
    })

    # Update event
    update_event_id = uuid.uuid4()
    await consumer.handle_event({
        "event_id": str(update_event_id),
        "event_type": SKWEventType.KNOWLEDGE_UPDATED.value,
        "meeting_id": str(sample_meeting_id),
        "knowledge_id": str(sample_knowledge_id),
        "version": 2,
        "content": "Updated Content with revisions",
        "correlation_id": "corr-upd-789",
    })

    context = consumer.get_context(sample_meeting_id)
    item = context.get_item(sample_knowledge_id)
    assert item is not None
    assert item.version == 2
    assert item.content == "Updated Content with revisions"
    assert item.lifecycle_state == "updated"
    assert item.correlation_id == "corr-upd-789"


@pytest.mark.asyncio
async def test_blackboard_consumes_knowledge_versioned(sample_meeting_id, sample_knowledge_id):
    consumer = BlackboardEventConsumer()
    # Initial published
    await consumer.handle_event({
        "event_id": str(uuid.uuid4()),
        "event_type": SKWEventType.KNOWLEDGE_PUBLISHED.value,
        "meeting_id": str(sample_meeting_id),
        "knowledge_id": str(sample_knowledge_id),
        "object_type": "summary",
        "source_module": "summarizer",
        "content": "Base Summary",
        "version": 1,
    })

    # Versioned event
    await consumer.handle_event({
        "event_id": str(uuid.uuid4()),
        "event_type": SKWEventType.KNOWLEDGE_VERSIONED.value,
        "meeting_id": str(sample_meeting_id),
        "knowledge_id": str(sample_knowledge_id),
        "previous_version": 1,
        "new_version": 2,
    })

    context = consumer.get_context(sample_meeting_id)
    item = context.get_item(sample_knowledge_id)
    assert item.version == 2
    assert item.lifecycle_state == "versioned"


@pytest.mark.asyncio
async def test_blackboard_consumes_knowledge_archived(sample_meeting_id, sample_knowledge_id):
    consumer = BlackboardEventConsumer()
    # Initial published
    await consumer.handle_event({
        "event_id": str(uuid.uuid4()),
        "event_type": SKWEventType.KNOWLEDGE_PUBLISHED.value,
        "meeting_id": str(sample_meeting_id),
        "knowledge_id": str(sample_knowledge_id),
        "object_type": "decision",
        "source_module": "decision_agent",
        "content": "Decision to archive",
    })

    # Archive
    await consumer.handle_event({
        "event_id": str(uuid.uuid4()),
        "event_type": SKWEventType.KNOWLEDGE_ARCHIVED.value,
        "meeting_id": str(sample_meeting_id),
        "knowledge_id": str(sample_knowledge_id),
        "reason": "Superseded by new roadmap",
    })

    context = consumer.get_context(sample_meeting_id)
    item = context.get_item(sample_knowledge_id)
    assert item.lifecycle_state == "archived"
    assert item.metadata.get("archive_reason") == "Superseded by new roadmap"


@pytest.mark.asyncio
async def test_blackboard_consumes_knowledge_validation_and_processing_failed(sample_meeting_id):
    consumer = BlackboardEventConsumer()
    invalid_kid = uuid.uuid4()

    # Validation failed event
    await consumer.handle_event({
        "event_id": str(uuid.uuid4()),
        "event_type": SKWEventType.KNOWLEDGE_VALIDATION_FAILED.value,
        "meeting_id": str(sample_meeting_id),
        "knowledge_id": str(invalid_kid),
        "error_code": "EMPTY_CONTENT",
        "error_message": "Knowledge content cannot be empty",
    })

    context = consumer.get_context(sample_meeting_id)
    # MUST NOT promote to active knowledge items
    assert context.get_item(invalid_kid) is None
    # Must record failure diagnostic
    assert len(context.failed_events) == 1
    assert context.failed_events[0]["error_code"] == "EMPTY_CONTENT"

    # Processing failed event
    await consumer.handle_event({
        "event_id": str(uuid.uuid4()),
        "event_type": SKWEventType.KNOWLEDGE_PROCESSING_FAILED.value,
        "meeting_id": str(sample_meeting_id),
        "knowledge_id": str(uuid.uuid4()),
        "error_code": "LLM_TIMEOUT",
        "error_message": "Enrichment timed out",
    })

    assert len(context.failed_events) == 2
    assert context.failed_events[1]["error_code"] == "LLM_TIMEOUT"


# -----------------------------------------------------------------------------
# 2. Idempotency & Deduplication
# -----------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_blackboard_event_deduplication_idempotency(sample_meeting_id, sample_knowledge_id):
    consumer = BlackboardEventConsumer()
    duplicate_event_id = uuid.uuid4()

    event = {
        "event_id": str(duplicate_event_id),
        "event_type": SKWEventType.KNOWLEDGE_PUBLISHED.value,
        "meeting_id": str(sample_meeting_id),
        "knowledge_id": str(sample_knowledge_id),
        "object_type": "decision",
        "source_module": "decision_agent",
        "title": "Idempotent Item",
        "content": "Content 1",
    }

    # First dispatch
    res1 = await consumer.handle_event(event)
    assert res1 is True

    # Mutate event payload with same event_id
    mutated_event = dict(event)
    mutated_event["title"] = "Hacked Title"

    # Second dispatch with identical event_id
    res2 = await consumer.handle_event(mutated_event)
    assert res2 is True

    context = consumer.get_context(sample_meeting_id)
    item = context.get_item(sample_knowledge_id)
    # Title must remain untouched due to idempotency skipping
    assert item.title == "Idempotent Item"


# -----------------------------------------------------------------------------
# 3. Knowledge Request (Query Engine Boundary) Tests
# -----------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_blackboard_requests_structured_knowledge(sample_meeting_id):
    mock_query_engine = AsyncMock(spec=KnowledgeQueryEngine)
    db_obj = DBKnowledgeObject(
        id=uuid.uuid4(),
        meeting_id=sample_meeting_id,
        object_type="decision",
        source_module="decision_agent",
        title="Microservice Transition",
        content="Migrate auth service to Go",
        confidence=0.92,
        version=1,
        status="published",
        payload={"metadata": {"priority": "high"}},
        provenance={"producer": "decision_agent"},
    )
    mock_query_engine.structured_query.return_value = [db_obj]

    mock_audit = AsyncMock()
    client = BlackboardSKWClient(query_engine=mock_query_engine, audit_repo=mock_audit)

    auth_context = {"authenticated": True, "user_id": str(uuid.uuid4())}
    results = await client.request_structured_knowledge(
        meeting_id=sample_meeting_id,
        object_type="decision",
        min_confidence=0.8,
        auth_context=auth_context,
        correlation_id="corr-query-1",
    )

    assert len(results) == 1
    assert results[0]["title"] == "Microservice Transition"
    assert results[0]["retrieval_source"] == "skw_structured"
    assert results[0]["correlation_id"] == "corr-query-1"
    assert results[0]["confidence_score"] == 0.92

    # Verify audit log was recorded
    assert mock_audit.create.called


@pytest.mark.asyncio
async def test_blackboard_requests_semantic_knowledge(sample_meeting_id):
    mock_query_engine = AsyncMock(spec=KnowledgeQueryEngine)
    mock_query_engine.semantic_query.return_value = [{
        "knowledge_id": str(uuid.uuid4()),
        "meeting_id": str(sample_meeting_id),
        "object_type": "summary",
        "source_module": "summarizer",
        "title": "Q3 Strategy Summary",
        "content": "Focus on cloud-native capabilities.",
        "confidence": 0.89,
        "score": 0.94,
        "version": 1,
        "lifecycle_state": "published",
        "payload": {},
    }]

    client = BlackboardSKWClient(query_engine=mock_query_engine)
    auth_context = {"auth_token": "test-token"}

    results = await client.request_semantic_knowledge(
        query="cloud-native capabilities",
        meeting_id=sample_meeting_id,
        auth_context=auth_context,
        correlation_id="corr-sem-2",
    )

    assert len(results) == 1
    assert results[0]["title"] == "Q3 Strategy Summary"
    assert results[0]["relevance_score"] == 0.94
    assert results[0]["retrieval_source"] == "skw_semantic"
    assert results[0]["correlation_id"] == "corr-sem-2"


@pytest.mark.asyncio
async def test_blackboard_requests_hybrid_knowledge(sample_meeting_id):
    mock_query_engine = AsyncMock(spec=KnowledgeQueryEngine)
    mock_query_engine.hybrid_query.return_value = [{
        "knowledge_id": str(uuid.uuid4()),
        "meeting_id": str(sample_meeting_id),
        "object_type": "decision",
        "source_module": "decision_agent",
        "title": "Cloud Architecture Decision",
        "content": "Deploy with Kubernetes",
        "confidence_score": 0.95,
        "relevance_score": 0.91,
        "version": 1,
        "lifecycle_state": "published",
        "retrieval_source": "hybrid_semantic",
    }]

    client = BlackboardSKWClient(query_engine=mock_query_engine)
    auth_context = {"api_key": "skw-secret-api-key"}

    results = await client.request_hybrid_knowledge(
        query="Kubernetes deployment",
        meeting_id=sample_meeting_id,
        auth_context=auth_context,
        correlation_id="corr-hyb-3",
    )

    assert len(results) == 1
    assert results[0]["title"] == "Cloud Architecture Decision"
    assert results[0]["correlation_id"] == "corr-hyb-3"


# -----------------------------------------------------------------------------
# 4. Security, Scope, and Authorization Tests
# -----------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_blackboard_knowledge_request_unauthorized():
    mock_query_engine = AsyncMock(spec=KnowledgeQueryEngine)
    mock_audit = AsyncMock()
    client = BlackboardSKWClient(query_engine=mock_query_engine, audit_repo=mock_audit)

    # Missing auth context
    with pytest.raises(UnauthorizedException) as exc:
        await client.request_structured_knowledge(auth_context=None)
    assert exc.value.code == "UNAUTHORIZED"
    assert mock_audit.create.called

    # Invalid token
    with pytest.raises(UnauthorizedException) as exc2:
        await client.request_semantic_knowledge(
            query="test",
            auth_context={"auth_token": "bogus-invalid-token"},
        )
    assert exc2.value.code == "INVALID_CREDENTIALS"


@pytest.mark.asyncio
async def test_blackboard_knowledge_request_forbidden_meeting_scope(sample_meeting_id):
    mock_query_engine = AsyncMock(spec=KnowledgeQueryEngine)
    client = BlackboardSKWClient(query_engine=mock_query_engine)

    authorized_meeting_id = uuid.uuid4()
    other_meeting_id = uuid.uuid4()

    auth_context = {
        "authenticated": True,
        "meeting_id": str(authorized_meeting_id),
    }

    # Attempt to query a different meeting
    with pytest.raises(ForbiddenException) as exc:
        await client.request_structured_knowledge(
            meeting_id=other_meeting_id,
            auth_context=auth_context,
        )
    assert exc.value.code == "FORBIDDEN"


# -----------------------------------------------------------------------------
# 5. Redis Delivery Status & Reliability Caveat Tests
# -----------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_redis_delivery_status_distinction(sample_meeting_id, sample_knowledge_id):
    bus = RedisEventBus()

    # 1. When Redis client is None / offline, publishing should report LOCAL_FALLBACK
    with patch.object(bus, "_get_client", new_callable=AsyncMock, return_value=None):
        status = await bus.publish_with_status(
            "events:knowledge",
            {"event_id": str(uuid.uuid4()), "content": "test"},
        )
        assert status == EventDeliveryStatus.LOCAL_FALLBACK

    # 2. When Redis client is connected and succeeds, publishing should report DISTRIBUTED
    mock_client = AsyncMock()
    mock_client.publish = AsyncMock(return_value=1)
    with patch.object(bus, "_get_client", new_callable=AsyncMock, return_value=mock_client):
        status = await bus.publish_with_status(
            "events:knowledge",
            {"event_id": str(uuid.uuid4()), "content": "test"},
        )
        assert status == EventDeliveryStatus.DISTRIBUTED


@pytest.mark.asyncio
async def test_blackboard_failure_isolation(sample_meeting_id, sample_knowledge_id):
    """
    Simulates a failure inside Blackboard event handler; ensures no exceptions escape
    to corrupt or crash the event publisher.
    """
    bus = RedisEventBus()
    consumer = BlackboardEventConsumer(event_bus=bus)

    # Malformed payload missing required meeting_id
    malformed_event = {
        "event_id": str(uuid.uuid4()),
        "event_type": SKWEventType.KNOWLEDGE_PUBLISHED.value,
        # missing meeting_id
    }

    handled = await consumer.handle_event(malformed_event)
    assert handled is False  # Safely discarded without crash
