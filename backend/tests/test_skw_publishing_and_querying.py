"""
Comprehensive Unit & Integration Tests for Phase 4.7:
Knowledge Publishing and Knowledge Querying.
Verifies publication prerequisites, structured search, semantic search, hybrid search result fusion,
version retrieval, authentication/unauthorized access, invalid IDs, empty results, and malformed queries.
"""

import uuid
import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import AsyncSession

from app.main import app
from app.skw.models.knowledge_object import SKWLifecycleState, CanonicalKnowledgeObject
from app.skw.services.version_manager import DefaultVersionManager
from app.skw.services.knowledge_publisher import KnowledgePublisher
from app.skw.services.knowledge_query_engine import KnowledgeQueryEngine
from app.skw.indexing.semantic_indexer import SemanticIndexer
from app.models.meeting import Meeting
from app.repositories.meeting_repo import MeetingRepository
from app.models.knowledge_object import KnowledgeObject as DBKnowledgeObject
from app.repositories.knowledge_object_repo import KnowledgeObjectRepository


from app.infrastructure.database import get_async_db
from typing import AsyncGenerator


@pytest_asyncio.fixture
async def async_client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    """Provide an HTTP async client for testing FastAPI endpoints with overridden DB session."""
    app.dependency_overrides[get_async_db] = lambda: db_session
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_knowledge_publication_prerequisites(db_session: AsyncSession) -> None:
    """Verify that knowledge objects can only be published when processing prerequisites are met."""
    meeting_repo = MeetingRepository(db_session)
    meeting = await meeting_repo.create(Meeting(title="Publication Meeting"))
    vm = DefaultVersionManager(db_session)

    # Create new object (status CREATED)
    ko = await vm.create_version(
        meeting_id=meeting.id,
        object_type="decision",
        source_module="AgentA",
        content="Test publication prerequisites",
    )
    assert ko.status == SKWLifecycleState.CREATED.value

    publisher = KnowledgePublisher(db_session)

    # Attempt publishing before validation/indexing should fail
    with pytest.raises(Exception):
        await publisher.publish_knowledge_object(ko.id)

    # Advance lifecycle to accepted -> indexed
    await vm.transition_lifecycle(ko.id, SKWLifecycleState.VALIDATING)
    await vm.transition_lifecycle(ko.id, SKWLifecycleState.ACCEPTED)
    await vm.transition_lifecycle(ko.id, SKWLifecycleState.INDEXED)

    # Now publishing should succeed
    published = await publisher.publish_knowledge_object(ko.id)
    assert published.status == SKWLifecycleState.PUBLISHED.value


@pytest.mark.asyncio
async def test_structured_and_semantic_query_engine(db_session: AsyncSession) -> None:
    """Verify structured filtering and semantic search via KnowledgeQueryEngine."""
    meeting_repo = MeetingRepository(db_session)
    meeting = await meeting_repo.create(Meeting(title="Query Engine Meeting"))
    ko_repo = KnowledgeObjectRepository(db_session)

    ko1 = await ko_repo.create(
        DBKnowledgeObject(
            meeting_id=meeting.id,
            object_type="decision",
            source_module="AudioModule",
            content="Use FastAPI for backend microservices.",
            title="FastAPI Decision",
            confidence=0.95,
            version=1,
            status="indexed",
        )
    )
    ko2 = await ko_repo.create(
        DBKnowledgeObject(
            meeting_id=meeting.id,
            object_type="action_item",
            source_module="TaskModule",
            content="Review security requirements.",
            title="Security Action",
            confidence=0.85,
            version=1,
            status="indexed",
        )
    )
    await db_session.commit()

    indexer = SemanticIndexer()
    await indexer.index_knowledge_object(
        CanonicalKnowledgeObject(
            knowledge_id=ko1.id,
            meeting_id=ko1.meeting_id,
            object_type=ko1.object_type,
            source_module=ko1.source_module,
            content=ko1.content,
            title=ko1.title,
            confidence_score=ko1.confidence,
            version=ko1.version,
            lifecycle_state=ko1.status,
        ),
        db_session,
    )
    await indexer.index_knowledge_object(
        CanonicalKnowledgeObject(
            knowledge_id=ko2.id,
            meeting_id=ko2.meeting_id,
            object_type=ko2.object_type,
            source_module=ko2.source_module,
            content=ko2.content,
            title=ko2.title,
            confidence_score=ko2.confidence,
            version=ko2.version,
            lifecycle_state=ko2.status,
        ),
        db_session,
    )

    query_engine = KnowledgeQueryEngine(db_session)

    # Structured query by meeting_id and object_type
    struct_res = await query_engine.structured_query(meeting_id=meeting.id, object_type="decision")
    assert len(struct_res) == 1
    assert struct_res[0].id == ko1.id

    # Semantic search query
    sem_res = await query_engine.semantic_query(query="FastAPI backend", meeting_id=meeting.id)
    assert len(sem_res) >= 1
    assert sem_res[0]["knowledge_id"] == str(ko1.id)


@pytest.mark.asyncio
async def test_hybrid_query_result_fusion(db_session: AsyncSession) -> None:
    """Verify hybrid query result fusion combining structured filters and semantic search."""
    meeting_repo = MeetingRepository(db_session)
    meeting = await meeting_repo.create(Meeting(title="Fusion Meeting"))
    ko_repo = KnowledgeObjectRepository(db_session)

    ko = await ko_repo.create(
        DBKnowledgeObject(
            meeting_id=meeting.id,
            object_type="decision",
            source_module="AIModule",
            content="Adopt Qdrant for vector retrieval.",
            title="Vector DB",
            confidence=0.92,
            version=1,
            status="indexed",
        )
    )
    await db_session.commit()

    query_engine = KnowledgeQueryEngine(db_session)
    fused = await query_engine.hybrid_query(
        query="vector retrieval Qdrant",
        meeting_id=meeting.id,
        object_type="decision",
        min_confidence=0.90,
    )

    assert len(fused) == 1
    assert fused[0]["knowledge_id"] == str(ko.id)
    assert "relevance_score" in fused[0]
    assert fused[0]["retrieval_source"] in {"hybrid_semantic", "hybrid_structured"}


@pytest.mark.asyncio
async def test_api_endpoints_integration(async_client: AsyncClient, db_session: AsyncSession) -> None:
    """Verify all REST API endpoints for knowledge creation, search, query, publishing, and versions."""
    meeting_repo = MeetingRepository(db_session)
    meeting = await meeting_repo.create(Meeting(title="API Meeting"))
    await db_session.commit()

    headers = {"Authorization": "Bearer test-token"}

    # 1. POST /knowledge
    payload = {
        "meeting_id": str(meeting.id),
        "object_type": "decision",
        "source_module": "TestClient",
        "content": "API test decision content",
        "title": "API Decision",
        "confidence_score": 0.94,
        "version": 1,
    }
    resp = await async_client.post("/api/v1/knowledge", json=payload, headers=headers)
    assert resp.status_code == 201
    data = resp.json()
    kid = data["knowledge_id"]
    assert data["content"] == "API test decision content"

    # 2. GET /knowledge/{id}
    resp = await async_client.get(f"/api/v1/knowledge/{kid}", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["knowledge_id"] == kid

    # 3. GET /knowledge/meeting/{meeting_id}
    resp = await async_client.get(f"/api/v1/knowledge/meeting/{meeting.id}", headers=headers)
    assert resp.status_code == 200
    assert len(resp.json()) >= 1

    # 4. GET /knowledge/type/{type}
    resp = await async_client.get(f"/api/v1/knowledge/type/decision", headers=headers)
    assert resp.status_code == 200
    assert len(resp.json()) >= 1

    # 5. POST /knowledge/search
    search_payload = {"query": "API test", "meeting_id": str(meeting.id)}
    resp = await async_client.post("/api/v1/knowledge/search", json=search_payload, headers=headers)
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)

    # 6. POST /knowledge/query (Hybrid)
    query_payload = {"query": "API test decision", "meeting_id": str(meeting.id), "object_type": "decision"}
    resp = await async_client.post("/api/v1/knowledge/query", json=query_payload, headers=headers)
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)

    # 7. GET /knowledge/{id}/versions
    resp = await async_client.get(f"/api/v1/knowledge/{kid}/versions", headers=headers)
    assert resp.status_code == 200
    assert len(resp.json()) >= 1

    # Transition object to indexed for publication test
    vm = DefaultVersionManager(db_session)
    await vm.transition_lifecycle(uuid.UUID(kid), SKWLifecycleState.VALIDATING)
    await vm.transition_lifecycle(uuid.UUID(kid), SKWLifecycleState.ACCEPTED)
    await vm.transition_lifecycle(uuid.UUID(kid), SKWLifecycleState.INDEXED)

    # 8. POST /knowledge/{id}/publish
    resp = await async_client.post(f"/api/v1/knowledge/{kid}/publish", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["lifecycle_state"] == SKWLifecycleState.PUBLISHED.value


@pytest.mark.asyncio
async def test_api_security_and_error_handling(async_client: AsyncClient, db_session: AsyncSession) -> None:
    """Verify unauthorized access, invalid knowledge IDs, empty results, and malformed queries."""
    # 1. Unauthorized access (missing token)
    resp = await async_client.get(f"/api/v1/knowledge/{uuid.uuid4()}")
    assert resp.status_code == 401

    headers = {"Authorization": "Bearer invalid-token"}
    resp = await async_client.get(f"/api/v1/knowledge/{uuid.uuid4()}", headers=headers)
    assert resp.status_code == 401

    valid_headers = {"Authorization": "Bearer test-token"}

    # 2. Invalid knowledge ID (404 Not Found)
    fake_id = uuid.uuid4()
    resp = await async_client.get(f"/api/v1/knowledge/{fake_id}", headers=valid_headers)
    assert resp.status_code == 404

    # 3. Malformed query (missing required query field in search)
    resp = await async_client.post("/api/v1/knowledge/search", json={}, headers=valid_headers)
    assert resp.status_code == 400

    # 4. Empty results test
    meeting_repo = MeetingRepository(db_session)
    meeting = await meeting_repo.create(Meeting(title="Empty Meeting"))
    await db_session.commit()

    resp = await async_client.get(f"/api/v1/knowledge/meeting/{meeting.id}", headers=valid_headers)
    assert resp.status_code == 200
    assert resp.json() == []
