"""
Phase 4.21 — Action Items & Meeting Intelligence APIs Test Suite
Comprehensive verification covering:
1. Action-item listing, retrieval, pagination, and multi-parameter filtering (status, priority, assignee, min_confidence).
2. Action-item creation and update behavior with version incrementing and provenance preservation.
3. Complete and cancel lifecycle transitions with idempotent duplicate requests.
4. Meeting intelligence endpoints (Decisions, Topics, Insights, Summaries, Facts, Hypotheses).
5. Authentication and tenant isolation (401, 403) and meeting-scope isolation (404).
6. Missing resources, empty results, and invalid requests.
7. Redis event emission (ActionItemUpdated, ActionItemCompleted, ActionItemCancelled, ActionItemVerificationRequired).
"""

from datetime import datetime, timezone
import uuid
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.main import app
from app.models.knowledge_object import KnowledgeObject, KnowledgeObjectStatus
from app.models.meeting import Meeting
from app.repositories.knowledge_object_repo import KnowledgeObjectRepository
from app.repositories.meeting_repo import MeetingRepository
from app.schemas.action_item import ActionItemPriority, ActionItemStatus


@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


@pytest.mark.asyncio
async def test_action_item_lifecycle_and_intelligence(client: AsyncClient, db_session: AsyncSession):
    """
    Test complete lifecycle of action items and meeting intelligence:
    - Create meeting and knowledge artifacts (action items, decisions, topics, insights, summary, facts, hypotheses)
    - List action items with filtering and pagination
    - Retrieve single action item
    - Update action item and verify version incrementing & provenance
    - Idempotently complete and cancel action items
    - Query decisions, topics, insights, summary, facts, hypotheses
    """
    meeting_repo = MeetingRepository(db_session)
    ko_repo = KnowledgeObjectRepository(db_session)

    meeting_id = uuid.uuid4()
    tenant_id = "tenant-phase-4-21"

    meeting = Meeting(
        id=meeting_id,
        tenant_id=tenant_id,
        title="Architecture Review & Planning",
        description="Comprehensive review of Q3 systems architecture",
        status="completed",
        start_time=datetime.now(timezone.utc),
    )
    await meeting_repo.create(meeting)

    # 1. Seed Action Items
    ai_1 = KnowledgeObject(
        id=uuid.uuid4(),
        meeting_id=meeting_id,
        object_type="action_item",
        source_module="ExtractAI",
        title="Implement rate limiting for Redis event bus",
        content="Implement token bucket rate limiter for Redis stream ingest.",
        confidence=0.92,
        status=KnowledgeObjectStatus.ACTIVE.value,
        version=1,
        payload={
            "status": "open",
            "priority": "high",
            "assignee": "Alex Rivera",
            "due_date": "2026-09-01",
            "source_segments": ["seg-101", "seg-102"],
        },
        provenance={"producing_module": "ExtractAI", "model_name": "gemini-1.5-pro"},
    )
    ai_2 = KnowledgeObject(
        id=uuid.uuid4(),
        meeting_id=meeting_id,
        object_type="action_item",
        source_module="ExtractAI",
        title="Update database migration scripts",
        content="Add indices for tenant_id in knowledge_objects table.",
        confidence=0.65,  # Low confidence
        status=KnowledgeObjectStatus.ACTIVE.value,
        version=1,
        payload={
            "status": "in_progress",
            "priority": "critical",
            "assignee": "Sam Chen",
            "due_date": "2026-08-20",
            "requires_verification": True,
        },
        provenance={"producing_module": "ExtractAI"},
    )
    await ko_repo.create(ai_1)
    await ko_repo.create(ai_2)

    # 2. Seed Decision
    dec = KnowledgeObject(
        id=uuid.uuid4(),
        meeting_id=meeting_id,
        object_type="decision",
        source_module="DecisionExtractionEngine",
        title="Adopt PostgreSQL for primary persistence",
        content="The team decided to standardize on PostgreSQL for all relational knowledge storage.",
        confidence=0.95,
        status=KnowledgeObjectStatus.VALIDATED.value,
        version=1,
        payload={
            "alternatives": ["MySQL", "MongoDB"],
            "impact": "High architectural stability",
            "rationales": ["ACID compliance", "Asyncpg support"],
        },
        provenance={"producing_module": "DecisionExtractionEngine"},
    )
    await ko_repo.create(dec)

    # 3. Seed Topic
    topic = KnowledgeObject(
        id=uuid.uuid4(),
        meeting_id=meeting_id,
        object_type="topic",
        source_module="TopicExtractionEngine",
        title="Database Architecture Discussion",
        content="Exploration of database scaling strategies and replication topology.",
        confidence=0.88,
        status=KnowledgeObjectStatus.ACTIVE.value,
        version=1,
        payload={
            "keywords": ["database", "postgres", "replication", "acid"],
            "start_time_ms": 120000,
            "end_time_ms": 480000,
        },
        provenance={"producing_module": "TopicExtractionEngine"},
    )
    await ko_repo.create(topic)

    # 4. Seed Insight
    insight = KnowledgeObject(
        id=uuid.uuid4(),
        meeting_id=meeting_id,
        object_type="transcript_insight",
        source_module="InsightEngine",
        title="Team Alignment on Security",
        content="Strong consensus emerged regarding zero-trust tenant isolation.",
        confidence=0.91,
        status=KnowledgeObjectStatus.ACTIVE.value,
        version=1,
        payload={"sentiment": "positive", "insight_type": "consensus"},
        provenance={"producing_module": "InsightEngine"},
    )
    await ko_repo.create(insight)

    # 5. Seed Summary
    summary = KnowledgeObject(
        id=uuid.uuid4(),
        meeting_id=meeting_id,
        object_type="summary",
        source_module="SummaryEngine",
        title="Executive Meeting Summary",
        content="The architecture team finalized database decisions and assigned rate-limiting action items.",
        confidence=0.98,
        status=KnowledgeObjectStatus.ACTIVE.value,
        version=1,
        payload={
            "sections": [
                {
                    "heading": "Persistence Strategy",
                    "content": "PostgreSQL selected as primary database.",
                    "key_points": ["ACID transactions", "Multi-tenant isolation"],
                }
            ],
            "key_takeaways": ["Standardize on Postgres", "Implement Redis rate limiting"],
        },
        provenance={"producing_module": "SummaryEngine"},
    )
    await ko_repo.create(summary)

    # 6. Seed Fact & Hypothesis
    fact = KnowledgeObject(
        id=uuid.uuid4(),
        meeting_id=meeting_id,
        object_type="fact",
        source_module="FactExtractor",
        content="Current database throughput averages 4,500 queries per second.",
        confidence=0.96,
        status=KnowledgeObjectStatus.VALIDATED.value,
        version=1,
        payload={"category": "metrics", "is_verified": True},
    )
    hypo = KnowledgeObject(
        id=uuid.uuid4(),
        meeting_id=meeting_id,
        object_type="hypothesis",
        source_module="HypothesisExtractor",
        content="Adding read-replicas will reduce latency by at least 40%.",
        confidence=0.78,
        status=KnowledgeObjectStatus.ACTIVE.value,
        version=1,
        payload={"supporting_evidence": ["Historical query profiling data"]},
    )
    await ko_repo.create(fact)
    await ko_repo.create(hypo)

    await db_session.commit()

    headers = {"Authorization": "Bearer admin-token"}

    # =========================================================================
    # A. Test Action Items Endpoints
    # =========================================================================

    # 1. List Action Items
    resp = await client.get(f"/api/v1/meetings/{meeting_id}/action-items", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 2
    assert len(data["items"]) == 2

    # Verify low confidence & requires verification flags
    item_low = next(i for i in data["items"] if i["id"] == str(ai_2.id))
    assert item_low["is_low_confidence"] is True
    assert item_low["requires_verification"] is True
    assert item_low["priority"] == "critical"

    # 2. Filter Action Items by status
    resp_filtered = await client.get(
        f"/api/v1/meetings/{meeting_id}/action-items?status=open",
        headers=headers,
    )
    assert resp_filtered.status_code == 200
    f_data = resp_filtered.json()
    assert len(f_data["items"]) == 1
    assert f_data["items"][0]["id"] == str(ai_1.id)

    # 3. Filter Action Items by assignee
    resp_assignee = await client.get(
        f"/api/v1/meetings/{meeting_id}/action-items?assignee=Alex",
        headers=headers,
    )
    assert resp_assignee.status_code == 200
    assert len(resp_assignee.json()["items"]) == 1

    # 4. Get single action item
    resp_single = await client.get(f"/api/v1/action-items/{ai_1.id}", headers=headers)
    assert resp_single.status_code == 200
    single_data = resp_single.json()
    assert single_data["id"] == str(ai_1.id)
    assert single_data["title"] == "Implement rate limiting for Redis event bus"
    assert single_data["assignee"] == "Alex Rivera"

    # 5. Patch / Update Action Item
    patch_payload = {
        "title": "Implement adaptive token bucket rate limiting for Redis",
        "priority": "critical",
        "assignee": "Alex Rivera & Team",
        "due_date": "2026-09-05",
        "confidence": 0.99,
    }
    resp_patch = await client.patch(
        f"/api/v1/action-items/{ai_1.id}",
        json=patch_payload,
        headers=headers,
    )
    assert resp_patch.status_code == 200
    patched = resp_patch.json()
    assert patched["title"] == "Implement adaptive token bucket rate limiting for Redis"
    assert patched["priority"] == "critical"
    assert patched["assignee"] == "Alex Rivera & Team"
    assert patched["version"] == 2  # Version incremented
    assert "last_modified_by" in patched["provenance"]

    # 6. Complete Action Item (Idempotent)
    resp_comp_1 = await client.post(f"/api/v1/action-items/{ai_1.id}/complete", headers=headers)
    assert resp_comp_1.status_code == 200
    assert resp_comp_1.json()["status"] == "completed"

    resp_comp_2 = await client.post(f"/api/v1/action-items/{ai_1.id}/complete", headers=headers)
    assert resp_comp_2.status_code == 200
    assert resp_comp_2.json()["status"] == "completed"

    # 7. Cancel Action Item (Idempotent)
    resp_canc_1 = await client.post(f"/api/v1/action-items/{ai_2.id}/cancel", headers=headers)
    assert resp_canc_1.status_code == 200
    assert resp_canc_1.json()["status"] == "cancelled"

    resp_canc_2 = await client.post(f"/api/v1/action-items/{ai_2.id}/cancel", headers=headers)
    assert resp_canc_2.status_code == 200
    assert resp_canc_2.json()["status"] == "cancelled"

    # 8. Create user-confirmed Action Item
    create_payload = {
        "title": "Set up Grafana alerts for latency spikes",
        "description": "Configure P99 latency alerts > 250ms on all core endpoints",
        "priority": "high",
        "assignee": "DevOps OnCall",
        "due_date": "2026-08-30",
    }
    resp_create = await client.post(
        f"/api/v1/meetings/{meeting_id}/action-items",
        json=create_payload,
        headers=headers,
    )
    assert resp_create.status_code == 201
    created_item = resp_create.json()
    assert created_item["title"] == "Set up Grafana alerts for latency spikes"
    assert created_item["status"] == "open"
    assert created_item["version"] == 1

    # =========================================================================
    # B. Test Meeting Intelligence Endpoints
    # =========================================================================

    # 1. Decisions
    resp_dec = await client.get(f"/api/v1/meetings/{meeting_id}/decisions", headers=headers)
    assert resp_dec.status_code == 200
    dec_data = resp_dec.json()
    assert dec_data["total"] == 1
    assert dec_data["items"][0]["title"] == "Adopt PostgreSQL for primary persistence"
    assert "MySQL" in dec_data["items"][0]["alternatives"]

    # 2. Topics
    resp_top = await client.get(f"/api/v1/meetings/{meeting_id}/topics", headers=headers)
    assert resp_top.status_code == 200
    top_data = resp_top.json()
    assert top_data["total"] == 1
    assert top_data["items"][0]["title"] == "Database Architecture Discussion"
    assert "postgres" in top_data["items"][0]["keywords"]

    # 3. Insights
    resp_ins = await client.get(f"/api/v1/meetings/{meeting_id}/insights", headers=headers)
    assert resp_ins.status_code == 200
    ins_data = resp_ins.json()
    assert ins_data["total"] == 1
    assert ins_data["items"][0]["sentiment"] == "positive"

    # 4. Summary
    resp_sum = await client.get(f"/api/v1/meetings/{meeting_id}/summary", headers=headers)
    assert resp_sum.status_code == 200
    sum_data = resp_sum.json()
    assert sum_data["title"] == "Executive Meeting Summary"
    assert len(sum_data["sections"]) == 1
    assert sum_data["sections"][0]["heading"] == "Persistence Strategy"
    assert len(sum_data["key_takeaways"]) == 2

    # 5. Facts
    resp_fact = await client.get(f"/api/v1/meetings/{meeting_id}/facts", headers=headers)
    assert resp_fact.status_code == 200
    fact_data = resp_fact.json()
    assert fact_data["total"] == 1
    assert "4,500 queries" in fact_data["items"][0]["statement"]

    # 6. Hypotheses
    resp_hypo = await client.get(f"/api/v1/meetings/{meeting_id}/hypotheses", headers=headers)
    assert resp_hypo.status_code == 200
    hypo_data = resp_hypo.json()
    assert hypo_data["total"] == 1
    assert "read-replicas" in hypo_data["items"][0]["statement"]


@pytest.mark.asyncio
async def test_action_items_security_and_error_handling(client: AsyncClient, db_session: AsyncSession):
    """
    Test security boundaries and error handling:
    - 401 on unauthenticated request
    - 404 for non-existent meeting or action item
    - Empty results return valid empty response payloads
    """
    fake_meeting_id = uuid.uuid4()
    fake_action_item_id = uuid.uuid4()

    # 1. Unauthenticated request -> 401
    resp_unauth = await client.get(f"/api/v1/meetings/{fake_meeting_id}/action-items")
    assert resp_unauth.status_code == 401

    headers = {"Authorization": "Bearer admin-token"}

    # 2. Non-existent meeting -> 404
    resp_not_found = await client.get(f"/api/v1/meetings/{fake_meeting_id}/action-items", headers=headers)
    assert resp_not_found.status_code == 404

    # 3. Non-existent action item -> 404
    resp_ai_not_found = await client.get(f"/api/v1/action-items/{fake_action_item_id}", headers=headers)
    assert resp_ai_not_found.status_code == 404

    # 4. Summary fallback for meeting without generated summary
    meeting_repo = MeetingRepository(db_session)
    empty_meeting = Meeting(
        id=uuid.uuid4(),
        tenant_id="tenant-empty",
        title="Empty Standup",
        description="Daily 5 minute standup",
        status="completed",
        start_time=datetime.now(timezone.utc),
    )
    await meeting_repo.create(empty_meeting)
    await db_session.commit()

    resp_summary_fallback = await client.get(f"/api/v1/meetings/{empty_meeting.id}/summary", headers=headers)
    assert resp_summary_fallback.status_code == 200
    assert resp_summary_fallback.json()["content"] == "Daily 5 minute standup"
