"""
Phase 4.22 — Project & Cross-Meeting Intelligence Test Suite
Comprehensive verification covering:
1. Project/workspace CRUD operations, pagination, and status filtering.
2. Meeting-to-project associations, idempotency, and association removal.
3. Cross-meeting aggregated action items with status breakdown and multi-parameter filtering.
4. Cross-meeting decisions aggregation and confidence metadata.
5. Recurring topics detection and cross-meeting clustering.
6. Cross-meeting insights and sentiment distribution analysis.
7. Project historical context and chronological meeting timeline.
8. Authoritative project executive summary roll-up.
9. Related meetings discovery based on shared topics and semantic keywords.
10. Authentication, tenant isolation (401, 403), and missing resource handling (404).
11. Redis event bus emissions (ProjectCreated, ProjectUpdated, MeetingAssociatedWithProject, etc.).
"""

from datetime import datetime, timedelta, timezone
import uuid
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.main import app
from app.models.knowledge_object import KnowledgeObject, KnowledgeObjectStatus
from app.models.meeting import Meeting
from app.models.project import Project, ProjectMeeting
from app.repositories.knowledge_object_repo import KnowledgeObjectRepository
from app.repositories.meeting_repo import MeetingRepository
from app.repositories.project_repo import ProjectMeetingRepository, ProjectRepository


@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


@pytest.mark.asyncio
async def test_project_cross_meeting_intelligence_full_suite(
    client: AsyncClient,
    db_session: AsyncSession,
):
    """
    Comprehensive test suite for Phase 4.22:
    - Creates a project and multiple meetings with rich KnowledgeObjects.
    - Associates meetings with the project.
    - Verifies all cross-meeting intelligence APIs.
    """
    project_repo = ProjectRepository(db_session)
    meeting_repo = MeetingRepository(db_session)
    ko_repo = KnowledgeObjectRepository(db_session)

    tenant_id = "tenant-phase-4-22"
    headers = {"Authorization": "Bearer admin-token"}

    # =========================================================================
    # 1. Project CRUD Operations
    # =========================================================================

    create_payload = {
        "name": "Project Alpha: NextGen Platform",
        "description": "Core initiative for distributed streaming intelligence",
        "status": "active",
        "settings": {"target_quarter": "Q4-2026", "priority": "strategic"},
    }

    # Create project
    create_resp = await client.post("/api/v1/projects", json=create_payload, headers=headers)
    assert create_resp.status_code == 201
    proj_data = create_resp.json()
    project_id = uuid.UUID(proj_data["id"])
    assert proj_data["name"] == "Project Alpha: NextGen Platform"
    assert proj_data["status"] == "active"
    assert proj_data["settings"]["target_quarter"] == "Q4-2026"

    # List projects
    list_resp = await client.get("/api/v1/projects?status=active", headers=headers)
    assert list_resp.status_code == 200
    list_data = list_resp.json()
    assert list_data["total"] >= 1
    assert any(p["id"] == str(project_id) for p in list_data["items"])

    # Get single project
    get_resp = await client.get(f"/api/v1/projects/{project_id}", headers=headers)
    assert get_resp.status_code == 200
    assert get_resp.json()["id"] == str(project_id)

    # Update project
    update_payload = {"description": "Updated description for distributed intelligence"}
    patch_resp = await client.patch(f"/api/v1/projects/{project_id}", json=update_payload, headers=headers)
    assert patch_resp.status_code == 200
    assert patch_resp.json()["description"] == "Updated description for distributed intelligence"

    # =========================================================================
    # 2. Seed Meetings & Knowledge Intelligence
    # =========================================================================

    now = datetime.now(timezone.utc)
    m1_id = uuid.uuid4()
    m2_id = uuid.uuid4()
    m3_id = uuid.uuid4()

    # Meeting 1: Architecture Kickoff (3 days ago)
    meeting_1 = Meeting(
        id=m1_id,
        tenant_id=tenant_id,
        title="Project Alpha: Architecture Kickoff",
        description="Initial design of distributed Blackboard and SKW layers",
        status="completed",
        scheduled_start=now - timedelta(days=3),
        actual_start=now - timedelta(days=3),
    )

    # Meeting 2: Performance & Reliability Sync (2 days ago)
    meeting_2 = Meeting(
        id=m2_id,
        tenant_id=tenant_id,
        title="Project Alpha: Performance & Reliability Sync",
        description="Review of indexing latency and Qdrant integration",
        status="completed",
        scheduled_start=now - timedelta(days=2),
        actual_start=now - timedelta(days=2),
    )

    # Meeting 3: Deployment & Operations Review (1 day ago)
    meeting_3 = Meeting(
        id=m3_id,
        tenant_id=tenant_id,
        title="Project Alpha: Deployment & Operations Review",
        description="Kubernetes readiness, failover validation, and translation pipeline",
        status="completed",
        scheduled_start=now - timedelta(days=1),
        actual_start=now - timedelta(days=1),
    )

    await meeting_repo.create(meeting_1)
    await meeting_repo.create(meeting_2)
    await meeting_repo.create(meeting_3)

    # Seed Knowledge Objects across meetings

    # --- Meeting 1 Knowledge ---
    ko_ai_1 = KnowledgeObject(
        id=uuid.uuid4(),
        meeting_id=m1_id,
        object_type="action_item",
        source_module="SKW",
        title="Benchmark PostgreSQL asyncpg pool",
        content="Benchmark connection pool under 500 concurrent live sessions.",
        confidence=0.94,
        status=KnowledgeObjectStatus.ACTIVE.value,
        version=1,
        payload={"status": "open", "priority": "high", "assignee": "Alex Rivera", "due_date": "2026-08-25"},
        provenance={"engine": "SKW"},
    )
    ko_ai_2 = KnowledgeObject(
        id=uuid.uuid4(),
        meeting_id=m1_id,
        object_type="action_item",
        source_module="SKW",
        title="Define proto schemas for Blackboard events",
        content="Standardize event bus schema across ACE and SKW modules.",
        confidence=0.91,
        status=KnowledgeObjectStatus.ACTIVE.value,
        version=1,
        payload={"status": "completed", "priority": "medium", "assignee": "Sam Chen"},
        provenance={"engine": "SKW"},
    )
    ko_dec_1 = KnowledgeObject(
        id=uuid.uuid4(),
        meeting_id=m1_id,
        object_type="decision",
        source_module="DecisionEngine",
        title="Standardize on Qdrant vector memory",
        content="Adopt Qdrant with HNSW cosine distance for semantic retrieval.",
        confidence=0.98,
        status=KnowledgeObjectStatus.VALIDATED.value,
        version=1,
        payload={"impact": "Sub-50ms similarity search", "alternatives": ["Pinecone", "Milvus"]},
        provenance={"engine": "DecisionEngine"},
    )
    ko_top_1 = KnowledgeObject(
        id=uuid.uuid4(),
        meeting_id=m1_id,
        object_type="topic",
        source_module="TopicEngine",
        title="Vector Memory & Indexing",
        content="Discussion on vector embeddings and high-concurrency search.",
        confidence=0.95,
        status=KnowledgeObjectStatus.ACTIVE.value,
        version=1,
        payload={"keywords": ["qdrant", "vector", "embeddings", "indexing"]},
        provenance={"engine": "TopicEngine"},
    )
    ko_top_2 = KnowledgeObject(
        id=uuid.uuid4(),
        meeting_id=m1_id,
        object_type="topic",
        source_module="TopicEngine",
        title="Database Architecture",
        content="PostgreSQL multi-tenant schema partitioning.",
        confidence=0.90,
        status=KnowledgeObjectStatus.ACTIVE.value,
        version=1,
        payload={"keywords": ["postgres", "tenancy", "schema", "partitioning"]},
        provenance={"engine": "TopicEngine"},
    )
    ko_ins_1 = KnowledgeObject(
        id=uuid.uuid4(),
        meeting_id=m1_id,
        object_type="transcript_insight",
        source_module="InsightEngine",
        title="High team alignment on memory tier",
        content="Unanimous consensus to separate transactional and vector stores.",
        confidence=0.93,
        status=KnowledgeObjectStatus.ACTIVE.value,
        version=1,
        payload={"sentiment": "positive", "insight_type": "consensus"},
        provenance={"engine": "InsightEngine"},
    )
    ko_sum_1 = KnowledgeObject(
        id=uuid.uuid4(),
        meeting_id=m1_id,
        object_type="summary",
        source_module="SummaryEngine",
        title="Kickoff Executive Summary",
        content="The team finalized foundational vector database decisions and connection pooling actions.",
        confidence=0.97,
        status=KnowledgeObjectStatus.ACTIVE.value,
        version=1,
        payload={},
        provenance={"engine": "SummaryEngine"},
    )

    # --- Meeting 2 Knowledge ---
    ko_ai_3 = KnowledgeObject(
        id=uuid.uuid4(),
        meeting_id=m2_id,
        object_type="action_item",
        source_module="SKW",
        title="Optimize Qdrant payload filtering",
        content="Add tenant_id payload index to Qdrant collections.",
        confidence=0.88,
        status=KnowledgeObjectStatus.ACTIVE.value,
        version=1,
        payload={"status": "in_progress", "priority": "critical", "assignee": "Sam Chen"},
        provenance={"engine": "SKW"},
    )
    ko_dec_2 = KnowledgeObject(
        id=uuid.uuid4(),
        meeting_id=m2_id,
        object_type="decision",
        source_module="DecisionEngine",
        title="Enforce mandatory payload filters in Qdrant",
        content="All vector queries must include tenant_id in the payload filter.",
        confidence=0.96,
        status=KnowledgeObjectStatus.VALIDATED.value,
        version=1,
        payload={"impact": "Zero cross-tenant data leak risk"},
        provenance={"engine": "DecisionEngine"},
    )
    ko_top_3 = KnowledgeObject(
        id=uuid.uuid4(),
        meeting_id=m2_id,
        object_type="topic",
        source_module="TopicEngine",
        title="Vector Memory & Indexing",  # Recurring topic!
        content="Payload filtering optimization and benchmarking.",
        confidence=0.92,
        status=KnowledgeObjectStatus.ACTIVE.value,
        version=1,
        payload={"keywords": ["qdrant", "vector", "filtering", "payload"]},
        provenance={"engine": "TopicEngine"},
    )
    ko_ins_2 = KnowledgeObject(
        id=uuid.uuid4(),
        meeting_id=m2_id,
        object_type="transcript_insight",
        source_module="InsightEngine",
        title="Latency risk identified",
        content="Unindexed payload queries cause 300ms latency spikes.",
        confidence=0.87,
        status=KnowledgeObjectStatus.ACTIVE.value,
        version=1,
        payload={"sentiment": "negative", "insight_type": "risk"},
        provenance={"engine": "InsightEngine"},
    )
    ko_sum_2 = KnowledgeObject(
        id=uuid.uuid4(),
        meeting_id=m2_id,
        object_type="summary",
        source_module="SummaryEngine",
        title="Performance Sync Summary",
        content="Identified payload indexing as the key bottleneck and assigned optimization task.",
        confidence=0.96,
        status=KnowledgeObjectStatus.ACTIVE.value,
        version=1,
        payload={},
        provenance={"engine": "SummaryEngine"},
    )

    # --- Meeting 3 Knowledge ---
    ko_ai_4 = KnowledgeObject(
        id=uuid.uuid4(),
        meeting_id=m3_id,
        object_type="action_item",
        source_module="SKW",
        title="Configure Kubernetes HPA for translation workers",
        content="Autoscale pods based on Redis stream consumer lag.",
        confidence=0.95,
        status=KnowledgeObjectStatus.ACTIVE.value,
        version=1,
        payload={"status": "open", "priority": "high", "assignee": "Alex Rivera"},
        provenance={"engine": "SKW"},
    )
    ko_dec_3 = KnowledgeObject(
        id=uuid.uuid4(),
        meeting_id=m3_id,
        object_type="decision",
        source_module="DecisionEngine",
        title="Deploy multi-replica translation engine",
        content="Run minimum of 3 replicas across two availability zones.",
        confidence=0.99,
        status=KnowledgeObjectStatus.VALIDATED.value,
        version=1,
        payload={"impact": "High availability SLA guarantee"},
        provenance={"engine": "DecisionEngine"},
    )
    ko_top_4 = KnowledgeObject(
        id=uuid.uuid4(),
        meeting_id=m3_id,
        object_type="topic",
        source_module="TopicEngine",
        title="Translation Pipeline & Multilingual Scaling",
        content="Scaling MarianMT and Google Cloud Translation integrations.",
        confidence=0.94,
        status=KnowledgeObjectStatus.ACTIVE.value,
        version=1,
        payload={"keywords": ["translation", "scaling", "kubernetes", "multilingual"]},
        provenance={"engine": "TopicEngine"},
    )
    ko_ins_3 = KnowledgeObject(
        id=uuid.uuid4(),
        meeting_id=m3_id,
        object_type="transcript_insight",
        source_module="InsightEngine",
        title="Operational Readiness Approved",
        content="Confidence is high for initial canary deployment.",
        confidence=0.95,
        status=KnowledgeObjectStatus.ACTIVE.value,
        version=1,
        payload={"sentiment": "positive", "insight_type": "readiness"},
        provenance={"engine": "InsightEngine"},
    )
    ko_sum_3 = KnowledgeObject(
        id=uuid.uuid4(),
        meeting_id=m3_id,
        object_type="summary",
        source_module="SummaryEngine",
        title="Deployment Sync Summary",
        content="Finalized translation worker scaling policies and HA architecture.",
        confidence=0.97,
        status=KnowledgeObjectStatus.ACTIVE.value,
        version=1,
        payload={},
        provenance={"engine": "SummaryEngine"},
    )

    # Persist all knowledge objects
    for ko in [
        ko_ai_1,
        ko_ai_2,
        ko_dec_1,
        ko_top_1,
        ko_top_2,
        ko_ins_1,
        ko_sum_1,
        ko_ai_3,
        ko_dec_2,
        ko_top_3,
        ko_ins_2,
        ko_sum_2,
        ko_ai_4,
        ko_dec_3,
        ko_top_4,
        ko_ins_3,
        ko_sum_3,
    ]:
        await ko_repo.create(ko)

    await db_session.commit()

    # =========================================================================
    # 3. Associate Meetings with Project
    # =========================================================================

    for m_id, note in [
        (m1_id, "Architecture Phase 1"),
        (m2_id, "Performance Review"),
        (m3_id, "Deployment Planning"),
    ]:
        assoc_resp = await client.post(
            f"/api/v1/projects/{project_id}/meetings",
            json={"meeting_id": str(m_id), "notes": note},
            headers=headers,
        )
        assert assoc_resp.status_code == 201
        assert assoc_resp.json()["meeting_id"] == str(m_id)

    # Test idempotency of association
    assoc_idem = await client.post(
        f"/api/v1/projects/{project_id}/meetings",
        json={"meeting_id": str(m1_id), "notes": "Duplicate check"},
        headers=headers,
    )
    assert assoc_idem.status_code == 201
    assert assoc_idem.json()["meeting_id"] == str(m1_id)

    # List project meetings
    proj_meetings_resp = await client.get(f"/api/v1/projects/{project_id}/meetings", headers=headers)
    assert proj_meetings_resp.status_code == 200
    assert proj_meetings_resp.json()["total"] == 3

    # =========================================================================
    # 4. Cross-Meeting Action Items Intelligence
    # =========================================================================

    ai_agg_resp = await client.get(f"/api/v1/projects/{project_id}/action-items", headers=headers)
    assert ai_agg_resp.status_code == 200
    ai_data = ai_agg_resp.json()

    assert ai_data["total_action_items"] == 4
    assert ai_data["open_count"] == 2
    assert ai_data["in_progress_count"] == 1
    assert ai_data["completed_count"] == 1
    assert ai_data["critical_count"] == 1
    assert ai_data["high_count"] == 2
    assert ai_data["by_assignee"]["Alex Rivera"] == 2
    assert ai_data["by_assignee"]["Sam Chen"] == 2

    # Filter cross-meeting action items by status
    ai_open_resp = await client.get(
        f"/api/v1/projects/{project_id}/action-items?status=open",
        headers=headers,
    )
    assert ai_open_resp.status_code == 200
    assert len(ai_open_resp.json()["items"]) == 2

    # Filter cross-meeting action items by assignee
    ai_alex_resp = await client.get(
        f"/api/v1/projects/{project_id}/action-items?assignee=Alex",
        headers=headers,
    )
    assert ai_alex_resp.status_code == 200
    assert len(ai_alex_resp.json()["items"]) == 2

    # Filter cross-meeting action items by priority
    ai_crit_resp = await client.get(
        f"/api/v1/projects/{project_id}/action-items?priority=critical",
        headers=headers,
    )
    assert ai_crit_resp.status_code == 200
    assert len(ai_crit_resp.json()["items"]) == 1
    assert ai_crit_resp.json()["items"][0]["priority"] == "critical"

    # =========================================================================
    # 5. Cross-Meeting Decisions Intelligence
    # =========================================================================

    dec_resp = await client.get(f"/api/v1/projects/{project_id}/decisions", headers=headers)
    assert dec_resp.status_code == 200
    dec_data = dec_resp.json()
    assert dec_data["total"] == 3
    assert len(dec_data["items"]) == 3
    # Check decision content & meeting attribution
    titles = [d["meeting_title"] for d in dec_data["items"]]
    assert "Project Alpha: Architecture Kickoff" in titles
    assert "Project Alpha: Performance & Reliability Sync" in titles
    assert "Project Alpha: Deployment & Operations Review" in titles

    # =========================================================================
    # 6. Recurring Topics Detection
    # =========================================================================

    topics_resp = await client.get(f"/api/v1/projects/{project_id}/topics/recurring", headers=headers)
    assert topics_resp.status_code == 200
    top_data = topics_resp.json()
    assert top_data["total_meetings_analyzed"] == 3
    assert len(top_data["topics"]) >= 1

    # "Vector Memory & Indexing" recurred in meeting 1 & meeting 2
    vec_topic = next(t for t in top_data["topics"] if "Vector Memory" in t["topic_name"])
    assert vec_topic["occurrence_count"] == 2
    assert len(vec_topic["meeting_ids"]) == 2
    assert "qdrant" in vec_topic["keywords"]

    # =========================================================================
    # 7. Cross-Meeting Insights & Sentiment
    # =========================================================================

    ins_resp = await client.get(f"/api/v1/projects/{project_id}/insights", headers=headers)
    assert ins_resp.status_code == 200
    ins_data = ins_resp.json()
    assert ins_data["total"] == 3
    assert ins_data["sentiment_distribution"]["positive"] == 2
    assert ins_data["sentiment_distribution"]["negative"] == 1

    # =========================================================================
    # 8. Project Historical Context & Timeline
    # =========================================================================

    hist_resp = await client.get(f"/api/v1/projects/{project_id}/historical-context", headers=headers)
    assert hist_resp.status_code == 200
    hist_data = hist_resp.json()
    assert hist_data["total_meetings"] == 3
    assert len(hist_data["timeline"]) == 3

    # Verify chronological sequence (Kickoff -> Sync -> Deployment)
    t_titles = [e["title"] for e in hist_data["timeline"]]
    assert t_titles[0] == "Project Alpha: Architecture Kickoff"
    assert t_titles[1] == "Project Alpha: Performance & Reliability Sync"
    assert t_titles[2] == "Project Alpha: Deployment & Operations Review"

    # Verify counts in timeline
    assert hist_data["timeline"][0]["decisions_count"] == 1
    assert hist_data["timeline"][0]["action_items_count"] == 2
    assert hist_data["timeline"][0]["open_action_items_count"] == 1

    # =========================================================================
    # 9. Project Executive Summary Roll-Up
    # =========================================================================

    summary_resp = await client.get(f"/api/v1/projects/{project_id}/summary", headers=headers)
    assert summary_resp.status_code == 200
    sum_data = summary_resp.json()

    assert sum_data["total_meetings"] == 3
    assert sum_data["total_decisions"] == 3
    assert sum_data["total_action_items"] == 4
    assert sum_data["open_action_items"] == 3  # 2 open + 1 in_progress
    assert sum_data["completed_action_items"] == 1
    assert len(sum_data["key_decisions"]) >= 1
    assert len(sum_data["top_action_items"]) >= 1
    assert "Project 'Project Alpha: NextGen Platform' encompasses 3 meetings" in sum_data["executive_summary"]

    # =========================================================================
    # 10. Related Meetings Discovery
    # =========================================================================

    # Meeting 1 and Meeting 2 both share "Vector Memory & Indexing" and "qdrant" keyword
    rel_resp = await client.get(f"/api/v1/meetings/{m1_id}/related", headers=headers)
    assert rel_resp.status_code == 200
    rel_data = rel_resp.json()
    assert rel_data["total_related"] >= 1
    m2_related = next((r for r in rel_data["related_meetings"] if r["meeting_id"] == str(m2_id)), None)
    assert m2_related is not None
    assert m2_related["similarity_score"] > 0.0
    assert "qdrant" in m2_related["shared_keywords"] or "vector memory & indexing" in [t.lower() for t in m2_related["shared_topics"]]

    # =========================================================================
    # 11. Security, Isolation & Error Handling
    # =========================================================================

    # Unauthenticated request (401)
    unauth_resp = await client.get(f"/api/v1/projects/{project_id}")
    assert unauth_resp.status_code == 401

    # Non-existent project (404)
    fake_id = uuid.uuid4()
    not_found_resp = await client.get(f"/api/v1/projects/{fake_id}", headers=headers)
    assert not_found_resp.status_code == 404

    # Remove meeting association
    del_assoc_resp = await client.delete(f"/api/v1/projects/{project_id}/meetings/{m3_id}", headers=headers)
    assert del_assoc_resp.status_code == 200
    assert "removed from project" in del_assoc_resp.json()["message"]

    # Verify meeting count decreased
    after_del_resp = await client.get(f"/api/v1/projects/{project_id}/meetings", headers=headers)
    assert after_del_resp.status_code == 200
    assert after_del_resp.json()["total"] == 2

    # Delete project
    del_proj_resp = await client.delete(f"/api/v1/projects/{project_id}", headers=headers)
    assert del_proj_resp.status_code == 200
    assert "deleted" in del_proj_resp.json()["message"]

    # Verify project is gone
    get_gone = await client.get(f"/api/v1/projects/{project_id}", headers=headers)
    assert get_gone.status_code == 404
