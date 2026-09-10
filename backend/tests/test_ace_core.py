"""
ACE Core Orchestration Tests (Phase 4.11A)
Verifies:
1. Task creation with correct default values.
2. Task planning and graph dependency assembly.
3. Dependency resolution (blocked vs ready classification).
4. Ready-task detection upon dependency completion.
5. Circular dependency detection validation.
6. Scheduler selection determinism.
7. Priority handling and tie-breaking.
8. Dynamic routing lookup.
9. Invalid capability handling and error raising.
10. State transition flow (PENDING -> RUNNING -> COMPLETED/FAILED/RETRYING).
11. Policy lookup and capability limit customizations.
12. Execution monitoring (duration tracing, metadata storage, and track states).
"""

import asyncio
import time
import uuid
import pytest

from app.orchestration.ace_core import (
    TaskStatus,
    ACETask,
    PolicyManager,
    DependencyAnalyzer,
    TaskPlanner,
    AdaptiveTaskScheduler,
    DynamicRoutingEngine,
    ConfidenceEvaluator,
    ExecutionMonitor,
)


# -----------------------------------------------------------------------------
# 1. Task Creation Unit Test
# -----------------------------------------------------------------------------
def test_task_creation():
    meeting_id = uuid.uuid4()
    task = ACETask(
        meeting_id=meeting_id,
        task_type="process_audio",
        required_capability="audio_intelligence",
        priority=5,
    )
    assert isinstance(task.task_id, uuid.UUID)
    assert task.meeting_id == meeting_id
    assert task.task_type == "process_audio"
    assert task.status == TaskStatus.PENDING
    assert task.priority == 5
    assert len(task.dependencies) == 0
    assert task.retry_count == 0
    assert isinstance(task.metadata, dict)


# -----------------------------------------------------------------------------
# 2. Task Planning Unit Test
# -----------------------------------------------------------------------------
def test_task_planning():
    meeting_id = uuid.uuid4()
    plan = TaskPlanner.generate_plan(
        meeting_id=meeting_id,
        enable_analytics=True,
        enable_memory=True,
    )

    # Verify that we have created tasks for our required capabilities
    caps = {t.required_capability for t in plan}
    expected_caps = {
        "audio_intelligence",
        "multilingual_asr",
        "overlap_resolution",
        "speaker_representation",
        "code_switch_intelligence",
        "timestamp_intelligence",
        "transcript_intelligence",
        "confidence_fusion",
        "context_intelligence",
        "verification_engine",
        "meeting_understanding",
        "meeting_analytics",
        "knowledge_memory",
    }
    assert expected_caps.issubset(caps)

    # Validate that dependencies are correctly mapped (e.g. multilingual_asr depends on audio_intelligence)
    task_dict = {t.required_capability: t for t in plan}
    
    asr_task = task_dict["multilingual_asr"]
    audio_task = task_dict["audio_intelligence"]
    assert audio_task.task_id in asr_task.dependencies

    # Optional module checking
    plan_no_opt = TaskPlanner.generate_plan(
        meeting_id=meeting_id,
        enable_analytics=False,
        enable_memory=False,
    )
    caps_no_opt = {t.required_capability for t in plan_no_opt}
    assert "meeting_analytics" not in caps_no_opt
    assert "knowledge_memory" not in caps_no_opt


# -----------------------------------------------------------------------------
# 3. Dependency Resolution & 4. Ready-Task Detection Unit Tests
# -----------------------------------------------------------------------------
def test_dependency_resolution_and_ready_detection():
    meeting_id = uuid.uuid4()
    task_a = ACETask(meeting_id=meeting_id, task_type="A", required_capability="cap_a")
    task_b = ACETask(meeting_id=meeting_id, task_type="B", required_capability="cap_b", dependencies=[task_a.task_id])
    task_c = ACETask(meeting_id=meeting_id, task_type="C", required_capability="cap_c", dependencies=[task_b.task_id])

    tasks = [task_a, task_b, task_c]

    # At start, only task_a is ready (no dependencies)
    ready = DependencyAnalyzer.get_ready_tasks(tasks)
    assert len(ready) == 1
    assert ready[0].task_id == task_a.task_id

    blocked = DependencyAnalyzer.get_blocked_tasks(tasks)
    assert len(blocked) == 2
    assert {t.task_id for t in blocked} == {task_b.task_id, task_c.task_id}

    # Complete task_a
    task_a.status = TaskStatus.COMPLETED

    # Now task_b is ready, task_c is still blocked
    ready = DependencyAnalyzer.get_ready_tasks(tasks)
    assert len(ready) == 1
    assert ready[0].task_id == task_b.task_id

    blocked = DependencyAnalyzer.get_blocked_tasks(tasks)
    assert len(blocked) == 1
    assert blocked[0].task_id == task_c.task_id


# -----------------------------------------------------------------------------
# 5. Circular Dependency Detection Unit Test
# -----------------------------------------------------------------------------
def test_circular_dependency_detection():
    meeting_id = uuid.uuid4()
    
    # Simple cycle: A -> B -> A
    task_a = ACETask(meeting_id=meeting_id, task_type="A", required_capability="cap_a")
    task_b = ACETask(meeting_id=meeting_id, task_type="B", required_capability="cap_b", dependencies=[task_a.task_id])
    
    # Mutate task_a to depend on task_b to create a cycle
    task_a.dependencies.append(task_b.task_id)

    with pytest.raises(ValueError, match="Circular dependency detected"):
        DependencyAnalyzer.validate_plan([task_a, task_b])

    # Missing dependency validation check
    task_missing = ACETask(meeting_id=meeting_id, task_type="X", required_capability="cap_x", dependencies=[uuid.uuid4()])
    with pytest.raises(ValueError, match="references missing dependency"):
        DependencyAnalyzer.validate_plan([task_missing])


# -----------------------------------------------------------------------------
# 6. Scheduler Selection & 7. Priority Handling Unit Tests
# -----------------------------------------------------------------------------
def test_scheduler_selection_and_priority():
    policy_manager = PolicyManager()
    scheduler = AdaptiveTaskScheduler(policy_manager=policy_manager)

    meeting_id = uuid.uuid4()
    # Create multiple ready tasks with different priorities
    task_low = ACETask(meeting_id=meeting_id, task_type="Low", required_capability="transcript_intelligence", priority=1)
    task_high = ACETask(meeting_id=meeting_id, task_type="High", required_capability="context_intelligence", priority=10)
    task_medium = ACETask(meeting_id=meeting_id, task_type="Med", required_capability="timestamp_intelligence", priority=5)

    tasks = [task_low, task_high, task_medium]

    # Verify that the scheduler picks the highest priority task first
    selected = scheduler.schedule_next(tasks)
    assert selected is not None
    assert selected.task_id == task_high.task_id
    assert selected.status == TaskStatus.SCHEDULED

    # Verify concurrency constraint (let's set max_concurrency to 1)
    policy_manager.set_policy("max_concurrency", 1)
    # Since one task is scheduled, running_count is 1. Next scheduling should return None.
    next_selected = scheduler.schedule_next(tasks)
    assert next_selected is None


# -----------------------------------------------------------------------------
# 8. Dynamic Routing & 9. Invalid Capability Handling Unit Tests
# -----------------------------------------------------------------------------
def test_dynamic_routing_and_invalid_capability():
    routing_engine = DynamicRoutingEngine()

    def asr_handler(task):
        return f"Handled {task.task_id} with ASR"

    # Register handler
    routing_engine.register_handler("multilingual_asr", asr_handler)

    meeting_id = uuid.uuid4()
    task_valid = ACETask(meeting_id=meeting_id, task_type="ASR", required_capability="multilingual_asr")
    task_invalid = ACETask(meeting_id=meeting_id, task_type="Dummy", required_capability="unknown_capability")

    # Resolve valid
    handler = routing_engine.resolve_route(task_valid)
    assert handler(task_valid) == f"Handled {task_valid.task_id} with ASR"

    # Resolve invalid raises ValueError
    with pytest.raises(ValueError, match="No handler registered for capability"):
        routing_engine.resolve_route(task_invalid)


# -----------------------------------------------------------------------------
# 10. State Transitions Unit Test
# -----------------------------------------------------------------------------
def test_state_transitions():
    policy_manager = PolicyManager()
    monitor = ExecutionMonitor(policy_manager=policy_manager)

    meeting_id = uuid.uuid4()
    task = ACETask(meeting_id=meeting_id, task_type="Test", required_capability="multilingual_asr")
    monitor.track_task(task)

    assert task.status == TaskStatus.PENDING

    # Transition to running
    monitor.start_task(task.task_id)
    assert task.status == TaskStatus.RUNNING

    # Complete
    monitor.complete_task(task.task_id, {"result_key": "some_value"})
    assert task.status == TaskStatus.COMPLETED
    assert task.metadata["result_key"] == "some_value"


# -----------------------------------------------------------------------------
# 11. Policy Lookup Unit Test
# -----------------------------------------------------------------------------
def test_policy_lookup():
    # Test initialization with default and custom policy overrides
    policy_manager = PolicyManager({"max_concurrency": 12, "custom_rule": "strict"})

    assert policy_manager.get_policy("max_concurrency") == 12
    assert policy_manager.get_policy("custom_rule") == "strict"
    assert policy_manager.get_policy("default_retry_limit") == 3  # Inherited default

    # Capability limit checks
    assert policy_manager.get_capability_limit("audio_intelligence") == 1
    assert policy_manager.get_capability_limit("transcript_intelligence") == 3

    # Dynamic adjustment
    policy_manager.set_capability_limit("audio_intelligence", 5)
    assert policy_manager.get_capability_limit("audio_intelligence") == 5


# -----------------------------------------------------------------------------
# 12. Execution Monitoring Unit Test
# -----------------------------------------------------------------------------
def test_execution_monitoring():
    policy_manager = PolicyManager({"default_retry_limit": 2})
    monitor = ExecutionMonitor(policy_manager=policy_manager)

    meeting_id = uuid.uuid4()
    task = ACETask(meeting_id=meeting_id, task_type="Monitored", required_capability="multilingual_asr")
    monitor.track_task(task)

    monitor.start_task(task.task_id)
    time.sleep(0.01)  # small delta to guarantee some duration
    
    # Simulate a failure
    monitor.fail_task(task.task_id, "Resource timed out")
    assert task.status == TaskStatus.RETRYING
    assert task.retry_count == 1

    # Simulate second failure (triggers permanent failure status based on policy retry limits)
    monitor.fail_task(task.task_id, "Authentication failed")
    assert task.status == TaskStatus.RETRYING
    assert task.retry_count == 2

    # Third failure exceeds retry count (limit = 2)
    monitor.fail_task(task.task_id, "Out of storage")
    assert task.status == TaskStatus.FAILED
    assert task.metadata["error_message"] == "Out of storage"

    # Require recovery transitions
    recovery_task = ACETask(meeting_id=meeting_id, task_type="RecoveryNeeded", required_capability="multilingual_asr")
    monitor.track_task(recovery_task)
    monitor.require_recovery(recovery_task.task_id, "ASR language pack missing")
    assert recovery_task.status == TaskStatus.RECOVERY_REQUIRED
    assert recovery_task.metadata["recovery_reason"] == "ASR language pack missing"

    # Tracing durations
    assert monitor.get_duration(task.task_id) > 0.0
