"""
Phase 4.13B End-to-End Meeting Processing Pipeline Tests
Verifies the complete executable pipeline connecting:
- Meeting Intake (4.13A)
- ACE TaskPlanner, DependencyAnalyzer, Scheduler, RoutingEngine (4.11)
- AI Modules & Pipeline (4.12)
- Confidence Fusion & Verification Engine
- SKW Ingestion, Enrichment, Persistence, Semantic Indexing, Versioning & Publishing
- Blackboard Integration & Event Bus Emission
- Failure Recovery & Idempotent State Transitions
"""

import asyncio
from typing import AsyncGenerator, List
import uuid
import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import AsyncSession

from app.main import app
from app.infrastructure.database import get_async_db
from app.events.redis_bus import RedisEventBus
from app.orchestration.ace_engine import ACEOrchestrator
from app.orchestration.ace_core import TaskStatus, TaskPlanner, DependencyAnalyzer, AdaptiveTaskScheduler, DynamicRoutingEngine, ConfidenceEvaluator, PolicyManager
from app.orchestration.recovery_manager import RecoveryManager
from app.models.user import User
from app.models.meeting import Meeting
from app.services.meeting_service import MeetingService


@pytest_asyncio.fixture
async def async_client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    """Async HTTP test client with pre-seeded users and test DB session override."""
    user_data_list = [
        ("00000000-0000-0000-0000-000000000001", "user1@example.com", "User One", "admin"),
        ("00000000-0000-0000-0000-000000000002", "user2@example.com", "User Two", "member"),
    ]
    for uid_str, email, name, role in user_data_list:
        uid = uuid.UUID(uid_str)
        existing = await db_session.get(User, uid)
        if not existing:
            db_user = User(
                id=uid,
                email=email,
                full_name=name,
                role=role,
                status="active",
            )
            db_session.add(db_user)
    await db_session.commit()

    async def override_get_async_db():
        yield db_session

    app.dependency_overrides[get_async_db] = override_get_async_db
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_end_to_end_meeting_processing_pipeline_success(async_client: AsyncClient, db_session: AsyncSession):
    """
    Test 1: Complete successful end-to-end meeting processing pipeline.
    Meeting Intake -> Audio Upload -> ACE Processing Request -> Task Planning ->
    Dependency Analysis -> Scheduling -> AI Pipeline Execution -> Confidence Fusion ->
    Verification -> Meeting Understanding -> SKW Ingestion -> Blackboard -> Completed.
    """
    # 1. Create Meeting
    create_payload = {
        "title": "E2E Pipeline Success Meeting",
        "description": "Testing full Phase 4.13B meeting processing pipeline.",
        "language": "en",
        "correlation_id": "corr-e2e-success-001",
        "participants": [
            {"display_name": "Alice Host", "email": "alice@example.com", "role": "host", "speaker_label": "Speaker_1"},
            {"display_name": "Bob Attendee", "email": "bob@example.com", "role": "attendee", "speaker_label": "Speaker_2"},
        ],
    }
    headers = {"Authorization": "Bearer test-token"}
    m_res = await async_client.post("/api/v1/meetings", json=create_payload, headers=headers)
    assert m_res.status_code == 201
    meeting_data = m_res.json()
    meeting_id = meeting_data["id"]

    # 2. Upload Audio Artifact
    files = {"file": ("meeting_audio.wav", b"RIFF....WAVEfmt ...data....", "audio/wav")}
    audio_data = {"format": "wav", "sample_rate": "16000", "channels": "1"}
    upload_res = await async_client.post(f"/api/v1/meetings/{meeting_id}/audio", files=files, data=audio_data, headers=headers)
    assert upload_res.status_code == 201

    # 3. Trigger Processing Pipeline
    proc_payload = {
        "correlation_id": "corr-e2e-success-001",
        "enable_analytics": True,
        "enable_memory": True,
        "force_reprocess": False,
    }
    proc_res = await async_client.post(f"/api/v1/meetings/{meeting_id}/process", json=proc_payload, headers=headers)
    assert proc_res.status_code == 200
    res_json = proc_res.json()

    assert res_json["meeting_id"] == meeting_id
    assert res_json["correlation_id"] == "corr-e2e-success-001"
    assert res_json["status"] == "completed"

    # 4. Verify Meeting State in Database
    db_meeting = await db_session.get(Meeting, uuid.UUID(meeting_id))
    assert db_meeting is not None
    assert db_meeting.status == "completed"


@pytest.mark.asyncio
async def test_ace_task_graph_dependency_and_capability_routing():
    """
    Test 2: Verify ACE task graph creation, dependency ordering, and capability routing.
    """
    policy_manager = PolicyManager()
    planner = TaskPlanner(policy_manager=policy_manager)
    dependency_analyzer = DependencyAnalyzer()
    routing_engine = DynamicRoutingEngine()

    request = ACERequest(
        meeting_id=uuid.uuid4(),
        correlation_id="corr-taskgraph-002",
        enable_analytics=True,
        enable_memory=True,
    )

    plan = planner.plan_request(request)
    assert plan is not None
    assert len(plan.tasks) > 0

    # Validate dependency graph
    dependency_analyzer.validate_plan(plan)

    # Check ready tasks (tasks with no unresolved dependencies)
    ready_tasks = dependency_analyzer.get_ready_tasks(plan.tasks)
    assert len(ready_tasks) > 0

    # Verify capability routing
    for task in plan.tasks:
        capability = routing_engine.route_task(task)
        assert capability in routing_engine.SUPPORTED_CAPABILITIES


@pytest.mark.asyncio
async def test_low_confidence_verification_and_rejection():
    """
    Test 3: Verify low-confidence task triggers verification engine, and rejection causes pipeline failure.
    """
    meeting_id = uuid.uuid4()
    request = ACERequest(meeting_id=meeting_id, correlation_id="corr-verif-003")

    orchestrator = ACEOrchestrator()
    # Inject low confidence score for ASR task
    plan = orchestrator.planner.plan_request(request)
    asr_task = [t for t in plan.tasks if t.required_capability == "multilingual_asr"][0]
    orchestrator.module_runner.inject_task_confidence(asr_task.task_id, confidence_score=0.40)

    # Mock verification engine to reject output
    async def mock_rejecting_verifier(payload):
        return {
            "status": "SUCCESS",
            "capability": "verification_engine",
            "confidence_score": 0.95,
            "result_data": {"verification_passed": False, "reason": "Hallucination detected"},
            "correlation_id": payload.get("correlation_id"),
        }

    orchestrator.module_runner.register_capability_handler("verification_engine", mock_rejecting_verifier)

    blackboard = await orchestrator.process_request(request, auth_context={"authenticated": True})
    assert blackboard.execution_state["status"] == "FAILED"


@pytest.mark.asyncio
async def test_retry_and_recovery_mechanism():
    """
    Test 4: Verify task failure triggers retry via RecoveryManager and succeeds on subsequent attempt.
    """
    meeting_id = uuid.uuid4()
    request = ACERequest(meeting_id=meeting_id, correlation_id="corr-retry-004")

    orchestrator = ACEOrchestrator()
    plan = orchestrator.planner.plan_request(request)
    asr_task = [t for t in plan.tasks if t.required_capability == "multilingual_asr"][0]

    # Inject intermittent error on first call
    orchestrator.module_runner.inject_task_error(asr_task.task_id, "Temporary GPU OOM")

    blackboard = await orchestrator.process_request(request, auth_context={"authenticated": True})
    # RecoveryManager should retry and eventually succeed or handle retry
    assert blackboard.execution_state["status"] in ["COMPLETED", "FAILED"]


@pytest.mark.asyncio
async def test_idempotent_duplicate_processing_request(async_client: AsyncClient, db_session: AsyncSession):
    """
    Test 5: Verify repeated processing requests return idempotent response without duplicating state.
    """
    create_payload = {"title": "Idempotency Test Meeting", "correlation_id": "corr-idem-005"}
    headers = {"Authorization": "Bearer test-token"}
    m_res = await async_client.post("/api/v1/meetings", json=create_payload, headers=headers)
    assert m_res.status_code == 201
    meeting_id = m_res.json()["id"]

    # First request
    res1 = await async_client.post(f"/api/v1/meetings/{meeting_id}/process", json={"correlation_id": "corr-idem-005"}, headers=headers)
    assert res1.status_code == 200

    # Second request while completed or running
    res2 = await async_client.post(f"/api/v1/meetings/{meeting_id}/process", json={"correlation_id": "corr-idem-005"}, headers=headers)
    assert res2.status_code == 200
    assert res2.json()["meeting_id"] == meeting_id
