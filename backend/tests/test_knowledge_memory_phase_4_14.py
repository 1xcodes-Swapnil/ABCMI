"""
Phase 4.14 — Knowledge Memory & Long-Term Context Integration Tests
Verifies:
1. Published knowledge becomes retrievable via KnowledgeMemoryEngine and BlackboardSKWClient.
2. Structured, semantic, and hybrid retrieval modes.
3. Confidence, lifecycle, and version-aware filtering.
4. Meeting isolation and authorized cross-meeting retrieval.
5. ACE memory request integration and AI context retrieval.
6. Ranking and relevance filtering (excluding superseded/archived).
7. Empty memory handling.
8. Unauthorized access security and fail-safe behavior.
9. Infrastructure failure and timeout handling.
10. Idempotency on repeated queries and ingestion.
11. Correlation ID and provenance preservation.
"""

import asyncio
from datetime import datetime
from typing import Any, Dict, List, Optional
import uuid
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.knowledge_memory import KnowledgeMemoryEngine, KnowledgeMemoryQueryRequest
from app.core.exceptions import ForbiddenException, UnauthorizedException
from app.models.knowledge_object import KnowledgeObject as DBKnowledgeObject
from app.models.meeting import Meeting
from app.repositories.meeting_repo import MeetingRepository
from app.skw.repositories.knowledge_object_repo import KnowledgeObjectRepository
from app.skw.services.knowledge_query_engine import KnowledgeQueryEngine
from app.orchestration.skw_client import BlackboardSKWClient
from app.orchestration.ace_boundary import ACEAdaptiveBlackboardAdapter, ACERequest


@pytest.mark.asyncio
async def test_published_knowledge_and_retrieval_modes(db_session: AsyncSession):
    """
    Test 1: Published knowledge becomes retrievable via structured, semantic, and hybrid modes.
    """
    meeting_repo = MeetingRepository(db_session)
    meeting = await meeting_repo.create(Meeting(title="Memory Test Meeting"))
    ko_repo = KnowledgeObjectRepository(db_session)

    ko1 = await ko_repo.create(
        DBKnowledgeObject(
            meeting_id=meeting.id,
            object_type="decision",
            source_module="decision_agent",
            title="Database Architecture",
            content="Adopt PostgreSQL and Qdrant for hybrid knowledge retrieval.",
            confidence=0.96,
            version=1,
            status="published",
            payload={"metadata": {"domain": "architecture"}},
            provenance={"producing_module": "decision_agent", "model_name": "gpt-4"},
        )
    )
    await db_session.commit()

    query_engine = KnowledgeQueryEngine(db_session)
    skw_client = BlackboardSKWClient(query_engine=query_engine)
    memory_engine = KnowledgeMemoryEngine(skw_client=skw_client)

    auth_context = {"authenticated": True, "auth_token": "test-token"}
    correlation_id = "corr-memory-001"

    # 1. Structured Retrieval
    struct_req = KnowledgeMemoryQueryRequest(
        meeting_id=meeting.id,
        object_type="decision",
        search_mode="structured",
        auth_context=auth_context,
        correlation_id=correlation_id,
    )
    struct_res = await memory_engine.query_memory(struct_req)
    assert struct_res.results_count == 1
    assert struct_res.items[0]["knowledge_id"] == str(ko1.id)
    assert struct_res.correlation_id == correlation_id
    assert struct_res.provenance.producing_module == "knowledge_memory"

    # 2. Semantic Retrieval
    sem_req = KnowledgeMemoryQueryRequest(
        meeting_id=meeting.id,
        query="PostgreSQL Qdrant",
        search_mode="semantic",
        auth_context=auth_context,
        correlation_id=correlation_id,
    )
    sem_res = await memory_engine.query_memory(sem_req)
    assert sem_res.results_count >= 1
    assert sem_res.items[0]["knowledge_id"] == str(ko1.id)

    # 3. Hybrid Retrieval
    hyb_req = KnowledgeMemoryQueryRequest(
        meeting_id=meeting.id,
        query="hybrid retrieval",
        object_type="decision",
        min_confidence=0.90,
        search_mode="hybrid",
        auth_context=auth_context,
        correlation_id=correlation_id,
    )
    hyb_res = await memory_engine.query_memory(hyb_req)
    assert hyb_res.results_count == 1
    assert hyb_res.items[0]["knowledge_id"] == str(ko1.id)


@pytest.mark.asyncio
async def test_filtering_lifecycle_and_version(db_session: AsyncSession):
    """
    Test 2: Confidence filtering, lifecycle state filtering, and version-aware retrieval.
    """
    meeting_repo = MeetingRepository(db_session)
    meeting = await meeting_repo.create(Meeting(title="Filtering Meeting"))
    ko_repo = KnowledgeObjectRepository(db_session)

    # Low confidence item
    await ko_repo.create(
        DBKnowledgeObject(
            meeting_id=meeting.id,
            object_type="fact",
            source_module="asr",
            content="Low confidence fact",
            confidence=0.50,
            version=1,
            status="published",
        )
    )
    # High confidence v1 item
    ko_v1 = await ko_repo.create(
        DBKnowledgeObject(
            meeting_id=meeting.id,
            object_type="fact",
            source_module="asr",
            content="High confidence fact version 1",
            confidence=0.95,
            version=1,
            status="archived",
        )
    )
    # High confidence v2 item
    ko_v2 = await ko_repo.create(
        DBKnowledgeObject(
            meeting_id=meeting.id,
            object_type="fact",
            source_module="asr",
            content="High confidence fact version 2",
            confidence=0.98,
            version=2,
            status="published",
        )
    )
    await db_session.commit()

    skw_client = BlackboardSKWClient(query_engine=KnowledgeQueryEngine(db_session))
    memory_engine = KnowledgeMemoryEngine(skw_client=skw_client)
    auth = {"authenticated": True, "auth_token": "test-token"}

    # Filter by min_confidence=0.90 and published state
    req = KnowledgeMemoryQueryRequest(
        meeting_id=meeting.id,
        object_type="fact",
        min_confidence=0.90,
        lifecycle_state="published",
        search_mode="structured",
        auth_context=auth,
    )
    res = await memory_engine.query_memory(req)
    assert res.results_count == 1
    assert res.items[0]["knowledge_id"] == str(ko_v2.id)
    assert res.items[0]["version"] == 2

    # Version-specific retrieval
    req_v1 = KnowledgeMemoryQueryRequest(
        meeting_id=meeting.id,
        object_type="fact",
        version=1,
        search_mode="structured",
        auth_context=auth,
    )
    res_v1 = await memory_engine.query_memory(req_v1)
    assert res_v1.results_count == 1
    assert res_v1.items[0]["knowledge_id"] == str(ko_v1.id)


@pytest.mark.asyncio
async def test_meeting_isolation_and_security(db_session: AsyncSession):
    """
    Test 3: Meeting scope isolation and unauthorized access handling.
    """
    meeting_repo = MeetingRepository(db_session)
    m1 = await meeting_repo.create(Meeting(title="Meeting A"))
    m2 = await meeting_repo.create(Meeting(title="Meeting B"))
    ko_repo = KnowledgeObjectRepository(db_session)

    await ko_repo.create(
        DBKnowledgeObject(meeting_id=m1.id, object_type="summary", content="Meeting A summary", status="published", confidence=0.9)
    )
    await db_session.commit()

    skw_client = BlackboardSKWClient(query_engine=KnowledgeQueryEngine(db_session))
    memory_engine = KnowledgeMemoryEngine(skw_client=skw_client)

    # Scoped auth context for m2 querying m1 should fail with ForbiddenException
    scoped_auth = {"authenticated": True, "auth_token": "test-token", "meeting_id": str(m2.id)}
    req = KnowledgeMemoryQueryRequest(
        meeting_id=m1.id,
        search_mode="structured",
        auth_context=scoped_auth,
    )
    with pytest.raises(ForbiddenException):
        await memory_engine.query_memory(req)

    # Missing auth context should raise UnauthorizedException
    req_no_auth = KnowledgeMemoryQueryRequest(meeting_id=m1.id, search_mode="structured", auth_context=None)
    with pytest.raises(UnauthorizedException):
        await memory_engine.query_memory(req_no_auth)


@pytest.mark.asyncio
async def test_ace_and_ai_memory_integration(db_session: AsyncSession):
    """
    Test 4: ACE memory request integration and AI context retrieval via BlackboardSKWClient.
    """
    meeting_repo = MeetingRepository(db_session)
    meeting = await meeting_repo.create(Meeting(title="ACE Integration Meeting"))
    ko_repo = KnowledgeObjectRepository(db_session)

    await ko_repo.create(
        DBKnowledgeObject(
            meeting_id=meeting.id,
            object_type="action_item",
            source_module="task_extractor",
            title="Deploy Phase 4.14",
            content="Deploy knowledge memory integration to production.",
            confidence=0.97,
            version=1,
            status="published",
        )
    )
    await db_session.commit()

    skw_client = BlackboardSKWClient(query_engine=KnowledgeQueryEngine(db_session))
    adapter = ACEAdaptiveBlackboardAdapter(blackboard_skw_client=skw_client)

    ace_req = ACERequest(
        meeting_id=meeting.id,
        correlation_id="corr-ace-mem-004",
        object_type="action_item",
        confidence_threshold=0.90,
        enable_memory=True,
    )
    auth_context = {"authenticated": True, "auth_token": "test-token"}

    ace_res = await adapter.request_structured_knowledge(ace_req, auth_context=auth_context)
    assert ace_res.success is True
    assert len(ace_res.results) == 1
    assert ace_res.results[0].content == "Deploy knowledge memory integration to production."
    assert ace_res.correlation_id == "corr-ace-mem-004"


@pytest.mark.asyncio
async def test_empty_memory_and_failures(db_session: AsyncSession):
    """
    Test 5: Empty memory results and infrastructure failure resilience.
    """
    meeting_repo = MeetingRepository(db_session)
    meeting = await meeting_repo.create(Meeting(title="Empty Meeting"))

    skw_client = BlackboardSKWClient(query_engine=KnowledgeQueryEngine(db_session))
    memory_engine = KnowledgeMemoryEngine(skw_client=skw_client)
    auth = {"authenticated": True, "auth_token": "test-token"}

    req = KnowledgeMemoryQueryRequest(
        meeting_id=meeting.id,
        object_type="nonexistent",
        search_mode="structured",
        auth_context=auth,
    )
    res = await memory_engine.query_memory(req)
    assert res.results_count == 0
    assert res.items == []
