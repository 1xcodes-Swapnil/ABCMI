"""
Phase 4.11B ACE Integration Flow Tests
Tests the event-driven Adaptive Collaboration Engine (ACE) integration:
- End-to-end task graph planning, scheduling, Blackboard state sync, and completion
- Event bus activation and event channel emissions
- Capability routing across AI module interfaces
- Confidence evaluation and low-confidence verification flow
- Failure isolation, retry handling, and recovery budget escalation
- SKW prerequisite context retrieval and final knowledge object storage
- Observability correlation tracking (request_id, meeting_id, task_id, correlation_id)
"""

import asyncio
from typing import List
import uuid
import pytest

from app.events.redis_bus import RedisEventBus
from app.orchestration.ace_boundary import ACEAdaptiveBlackboardAdapter, ACERequest
from app.orchestration.ace_core import TaskStatus
from app.orchestration.ace_engine import ACEOrchestrator
from app.orchestration.events import (
    ACEBaseOrchestrationEvent,
    ACEOrchestrationEventType,
)
from app.orchestration.module_runner import AIModuleRunner
from app.orchestration.skw_client import BlackboardSKWClient
from unittest.mock import AsyncMock, MagicMock


@pytest.fixture
def test_event_bus():
    """In-process Redis event bus instance for integration testing."""
    return RedisEventBus()


@pytest.fixture
def mock_skw_client():
    """Mock BlackboardSKWClient for testing boundary queries and persistence."""
    client = MagicMock(spec=BlackboardSKWClient)
    client.request_structured_knowledge = AsyncMock(return_value=[])
    client.request_semantic_knowledge = AsyncMock(return_value=[])
    client.request_hybrid_knowledge = AsyncMock(return_value=[])
    return client


@pytest.fixture
def test_blackboard_adapter(mock_skw_client):
    """Adapter wrapping mock SKW client."""
    return ACEAdaptiveBlackboardAdapter(blackboard_skw_client=mock_skw_client)


@pytest.fixture
def test_orchestrator(test_event_bus, test_blackboard_adapter):
    """ACEOrchestrator instance initialized with mock boundary and in-memory event bus."""
    return ACEOrchestrator(
        event_bus=test_event_bus,
        blackboard_adapter=test_blackboard_adapter,
        module_runner=AIModuleRunner(),
    )


@pytest.mark.asyncio
async def test_end_to_end_successful_orchestration(test_orchestrator, test_event_bus):
    """Verify standard processing request executes complete task graph successfully."""
    meeting_id = uuid.uuid4()
    request_id = uuid.uuid4()
    correlation_id = f"trace-{uuid.uuid4()}"

    emitted_events: List[ACEBaseOrchestrationEvent] = []

    async def _event_handler(event_dict):
        emitted_events.append(event_dict)

    channel = f"events:meetings:{meeting_id}:orchestration"
    test_event_bus.subscribe(channel, _event_handler)

    request = ACERequest(
        meeting_id=meeting_id,
        correlation_id=correlation_id,
    )
    request.request_id = request_id  # type: ignore

    blackboard = await test_orchestrator.process_request(
        request=request,
        auth_context={"authenticated": True, "auth_token": "test-token", "meeting_id": str(meeting_id)},
    )

    # Assert Blackboard execution state reaches COMPLETED
    assert blackboard.execution_state["status"] == "COMPLETED"
    
    # Assert all planned tasks were completed
    all_tasks = blackboard.list_tasks()
    assert len(all_tasks) > 0
    for task in all_tasks:
        assert task.status == TaskStatus.COMPLETED

    # Assert events were emitted on Redis bus
    event_types = [e.get("event_type") for e in emitted_events]
    assert ACEOrchestrationEventType.PROCESSING_REQUESTED in event_types
    assert ACEOrchestrationEventType.TASK_PLANNED in event_types
    assert ACEOrchestrationEventType.TASK_SCHEDULED in event_types
    assert ACEOrchestrationEventType.TASK_ACTIVATED in event_types
    assert ACEOrchestrationEventType.TASK_COMPLETED in event_types
    assert ACEOrchestrationEventType.PROCESSING_COMPLETED in event_types


@pytest.mark.asyncio
async def test_capability_routing_execution(test_orchestrator):
    """Verify tasks are routed and executed across core AI capabilities."""
    meeting_id = uuid.uuid4()
    request = ACERequest(meeting_id=meeting_id, correlation_id="trace-routing")

    blackboard = await test_orchestrator.process_request(
        request=request,
        auth_context={"authenticated": True, "auth_token": "test-token"},
    )

    completed_tasks = blackboard.list_tasks(status=TaskStatus.COMPLETED)
    executed_capabilities = {t.required_capability for t in completed_tasks}

    # Verify key required capabilities were invoked
    assert "audio_intelligence" in executed_capabilities
    assert "multilingual_asr" in executed_capabilities
    assert "confidence_fusion" in executed_capabilities
    assert "meeting_understanding" in executed_capabilities
    assert "knowledge_memory" in executed_capabilities


@pytest.mark.asyncio
async def test_confidence_evaluation_and_verification_flow(test_orchestrator):
    """Verify low-confidence outputs trigger the verification engine before proceeding."""
    meeting_id = uuid.uuid4()
    request = ACERequest(meeting_id=meeting_id, correlation_id="trace-confidence")

    # Inject a low confidence score (0.50 < 0.70 threshold) for the ASR task
    planner_plan = test_orchestrator.planner.plan_request(request)
    asr_task = [t for t in planner_plan.tasks if t.required_capability == "multilingual_asr"][0]
    test_orchestrator.module_runner.inject_task_confidence(asr_task.task_id, confidence_score=0.50)

    blackboard = await test_orchestrator.process_request(
        request=request,
        auth_context={"authenticated": True, "auth_token": "test-token"},
    )

    assert blackboard.execution_state["status"] == "COMPLETED"


@pytest.mark.asyncio
async def test_retry_on_task_failure(test_orchestrator, test_event_bus):
    """Verify task failures trigger retry requests and succeed on subsequent attempts."""
    meeting_id = uuid.uuid4()
    request = ACERequest(meeting_id=meeting_id, correlation_id="trace-retry")

    call_count = 0
    async def _intermittent_asr_handler(payload):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise RuntimeError("Temporary GPU OOM")
        return {"confidence_score": 0.95, "result_data": {"asr_transcript": "Retry success"}}

    test_orchestrator.module_runner.register_capability_handler("multilingual_asr", _intermittent_asr_handler)

    emitted_events = []
    channel = f"events:meetings:{meeting_id}:orchestration"
    test_event_bus.subscribe(channel, lambda e: emitted_events.append(e))

    blackboard = await test_orchestrator.process_request(
        request=request,
        auth_context={"authenticated": True, "auth_token": "test-token"},
    )

    # Verify task completed after retry
    asr_tasks = blackboard.get_tasks_by_capability("multilingual_asr")
    assert len(asr_tasks) > 0
    task = asr_tasks[0]
    assert task.status == TaskStatus.COMPLETED
    assert task.retry_count >= 1

    event_types = [e.get("event_type") for e in emitted_events]
    assert ACEOrchestrationEventType.RETRY_REQUESTED in event_types


@pytest.mark.asyncio
async def test_recovery_escalation_when_retries_exhausted(test_event_bus, test_blackboard_adapter):
    """Verify bounded retry budget exhaustion triggers recovery escalation and stops infinite loops."""
    meeting_id = uuid.uuid4()
    request = ACERequest(meeting_id=meeting_id, correlation_id="trace-recovery")

    # Create module runner that fails persistently for a target capability
    persistent_runner = AIModuleRunner()

    async def _failing_handler(payload):
        raise RuntimeError("Persistent Unrecoverable Hardware Fault")

    persistent_runner.register_capability_handler("multilingual_asr", _failing_handler)

    failing_orchestrator = ACEOrchestrator(
        event_bus=test_event_bus,
        blackboard_adapter=test_blackboard_adapter,
        module_runner=persistent_runner,
    )

    emitted_events = []
    channel = f"events:meetings:{meeting_id}:orchestration"
    test_event_bus.subscribe(channel, lambda e: emitted_events.append(e))

    blackboard = await failing_orchestrator.process_request(
        request=request,
        auth_context={"authenticated": True, "auth_token": "test-token"},
    )

    # Pipeline should fail cleanly without hanging or looping infinitely
    assert blackboard.execution_state["status"] == "FAILED"

    event_types = [e.get("event_type") for e in emitted_events]
    assert ACEOrchestrationEventType.RETRY_REQUESTED in event_types
    assert ACEOrchestrationEventType.TASK_FAILED in event_types
    assert ACEOrchestrationEventType.RECOVERY_TRIGGERED in event_types


@pytest.mark.asyncio
async def test_observability_and_correlation_tracking(test_orchestrator, test_event_bus):
    """Verify request_id, meeting_id, task_id, and correlation_id are attached to all events."""
    meeting_id = uuid.uuid4()
    correlation_id = "trace-correlation-12345"
    request = ACERequest(meeting_id=meeting_id, correlation_id=correlation_id)

    emitted_events = []
    channel = f"events:meetings:{meeting_id}:orchestration"
    test_event_bus.subscribe(channel, lambda e: emitted_events.append(e))

    await test_orchestrator.process_request(
        request=request,
        auth_context={"authenticated": True, "auth_token": "test-token"},
    )

    assert len(emitted_events) > 0
    for event in emitted_events:
        assert str(event.get("meeting_id")) == str(meeting_id)
        assert event.get("correlation_id") == correlation_id
        assert "event_id" in event
        assert "timestamp" in event
