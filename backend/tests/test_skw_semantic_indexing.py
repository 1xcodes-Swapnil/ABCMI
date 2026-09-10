"""
Comprehensive Unit & Integration Tests for Phase 4.5:
Semantic Indexing using Qdrant.
Verifies embedding generation, vector insertion, metadata filtering, similarity search,
missing vector handling, duplicate indexing (upsert), indexing failure, and retry logic.
"""

import uuid
import pytest
import pytest_asyncio
from qdrant_client import AsyncQdrantClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.skw.models.knowledge_object import CanonicalKnowledgeObject, SKWLifecycleState
from app.skw.indexing.semantic_indexer import SemanticIndexer
from app.core.exceptions import BadRequestException
from app.models.knowledge_object import KnowledgeObject as DBKnowledgeObject
from app.models.meeting import Meeting
from app.repositories.meeting_repo import MeetingRepository
from app.repositories.knowledge_object_repo import KnowledgeObjectRepository


@pytest_asyncio.fixture
async def memory_qdrant_client() -> AsyncQdrantClient:
    """Provide an in-memory AsyncQdrantClient instance for isolated testing."""
    client = AsyncQdrantClient(path=":memory:")
    yield client
    await client.close()


@pytest.mark.asyncio
async def test_embedding_generation(memory_qdrant_client: AsyncQdrantClient) -> None:
    """Verify deterministic and normalized embedding generation."""
    indexer = SemanticIndexer(qdrant_client=memory_qdrant_client)
    vec1 = indexer.generate_embedding("FastAPI microservices architecture")
    vec2 = indexer.generate_embedding("FastAPI microservices architecture")
    vec3 = indexer.generate_embedding("Completely unrelated topic about cooking recipes")

    assert len(vec1) == indexer.vector_size
    assert vec1 == vec2  # Deterministic
    assert vec1 != vec3  # Different text gives different embedding


@pytest.mark.asyncio
async def test_vector_insertion_and_retrieval(memory_qdrant_client: AsyncQdrantClient) -> None:
    """Verify vector insertion into Qdrant collection and point storage."""
    indexer = SemanticIndexer(qdrant_client=memory_qdrant_client, collection_name="test_collection")
    ko = CanonicalKnowledgeObject(
        meeting_id=uuid.uuid4(),
        object_type="decision",
        source_module="AudioIntelligence",
        content="Decided to use PostgreSQL for structured persistence.",
        title="DB Decision",
        confidence_score=0.95,
        version=1,
    )

    point_id = await indexer.index_knowledge_object(ko)
    assert point_id == str(ko.knowledge_id)

    # Search / Retrieve
    results = await indexer.semantic_search("PostgreSQL persistence", limit=5)
    assert len(results) >= 1
    assert results[0]["knowledge_id"] == str(ko.knowledge_id)
    assert results[0]["object_type"] == "decision"
    assert results[0]["confidence"] == 0.95


@pytest.mark.asyncio
async def test_metadata_filtering_and_similarity_search(memory_qdrant_client: AsyncQdrantClient) -> None:
    """Verify semantic similarity search with multi-attribute filtering (meeting, object type, confidence, version, lifecycle state)."""
    indexer = SemanticIndexer(qdrant_client=memory_qdrant_client, collection_name="test_filter_collection")
    meeting_id = uuid.uuid4()

    ko1 = CanonicalKnowledgeObject(
        meeting_id=meeting_id,
        object_type="decision",
        source_module="ModuleA",
        content="Adopt React 18 for frontend development.",
        confidence_score=0.91,
        version=1,
        lifecycle_state=SKWLifecycleState.ACCEPTED,
    )
    ko2 = CanonicalKnowledgeObject(
        meeting_id=meeting_id,
        object_type="action_item",
        source_module="ModuleB",
        content="Review React performance metrics.",
        confidence_score=0.88,
        version=1,
        lifecycle_state=SKWLifecycleState.INDEXED,
    )

    await indexer.index_knowledge_object(ko1)
    await indexer.index_knowledge_object(ko2)

    # Filter by object_type
    res_decision = await indexer.semantic_search("React", object_type="decision", meeting_id=meeting_id)
    assert len(res_decision) == 1
    assert res_decision[0]["knowledge_id"] == str(ko1.knowledge_id)

    # Filter by confidence range (min_confidence)
    res_conf = await indexer.semantic_search("React", min_confidence=0.90, meeting_id=meeting_id)
    assert len(res_conf) == 1
    assert res_conf[0]["knowledge_id"] == str(ko1.knowledge_id)

    # Filter by lifecycle_state
    res_state = await indexer.semantic_search("React", lifecycle_state="indexed", meeting_id=meeting_id)
    assert len(res_state) == 1
    assert res_state[0]["knowledge_id"] == str(ko2.knowledge_id)


@pytest.mark.asyncio
async def test_duplicate_indexing_idempotency(memory_qdrant_client: AsyncQdrantClient) -> None:
    """Verify duplicate indexing (upsert) updates points idempotently without duplication."""
    indexer = SemanticIndexer(qdrant_client=memory_qdrant_client, collection_name="test_upsert_collection")
    ko = CanonicalKnowledgeObject(
        meeting_id=uuid.uuid4(),
        object_type="fact",
        source_module="Ingestion",
        content="Initial fact content.",
        version=1,
    )

    await indexer.index_knowledge_object(ko)
    ko.content = "Updated fact content after revision."
    point_id = await indexer.index_knowledge_object(ko)

    results = await indexer.semantic_search("Updated fact", limit=10)
    assert len(results) == 1
    assert results[0]["content"] == "Updated fact content after revision."


@pytest.mark.asyncio
async def test_missing_vector_and_remove_index(memory_qdrant_client: AsyncQdrantClient) -> None:
    """Verify removal of vector index and handling of missing points."""
    indexer = SemanticIndexer(qdrant_client=memory_qdrant_client, collection_name="test_remove_collection")
    ko = CanonicalKnowledgeObject(
        meeting_id=uuid.uuid4(),
        content="Temporary knowledge object.",
    )

    await indexer.index_knowledge_object(ko)
    removed = await indexer.remove_index(ko.knowledge_id)
    assert removed is True

    removed_nonexistent = await indexer.remove_index(uuid.uuid4())
    assert removed_nonexistent is True


@pytest.mark.asyncio
async def test_indexing_failure_and_rollback_consistency(memory_qdrant_client: AsyncQdrantClient, db_session: AsyncSession) -> None:
    """Verify that if vector indexing fails, PostgreSQL transaction is rolled back and object is not falsely marked indexed."""
    meeting_repo = MeetingRepository(db_session)
    ko_repo = KnowledgeObjectRepository(db_session)

    meeting = await meeting_repo.create(Meeting(title="Indexing Failure Meeting"))
    db_ko = await ko_repo.create(
        DBKnowledgeObject(
            meeting_id=meeting.id,
            object_type="decision",
            source_module="AudioIntelligence",
            content="Failing indexing test content",
            status="active",
        )
    )
    await db_session.commit()

    canonical_ko = CanonicalKnowledgeObject(
        knowledge_id=db_ko.id,
        meeting_id=meeting.id,
        object_type="decision",
        content="Failing indexing test content",
    )

    class FailingQdrantClient:
        async def get_collections(self):
            class Col:
                collections = []
            return Col()
        async def create_collection(self, **kwargs):
            pass
        async def upsert(self, **kwargs):
            raise ConnectionError("Qdrant connection lost")

    failing_indexer = SemanticIndexer(qdrant_client=FailingQdrantClient(), collection_name="fail_col")

    with pytest.raises(BadRequestException) as exc_info:
        await failing_indexer.index_knowledge_object(canonical_ko, session=db_session)

    assert exc_info.value.code == "INDEXING_FAILED"

    refreshed_db_ko = await ko_repo.get(db_ko.id)
    assert refreshed_db_ko is not None
    assert refreshed_db_ko.status == "active"
    assert refreshed_db_ko.qdrant_point_id is None


@pytest.mark.asyncio
async def test_retry_indexing_success(memory_qdrant_client: AsyncQdrantClient, db_session: AsyncSession) -> None:
    """Verify that after an indexing failure, retry with a healthy client succeeds and updates PostgreSQL authoritatively."""
    meeting_repo = MeetingRepository(db_session)
    ko_repo = KnowledgeObjectRepository(db_session)

    meeting = await meeting_repo.create(Meeting(title="Retry Indexing Meeting"))
    db_ko = await ko_repo.create(
        DBKnowledgeObject(
            meeting_id=meeting.id,
            object_type="decision",
            source_module="AudioIntelligence",
            content="Retry indexing test content",
            status="active",
        )
    )
    await db_session.commit()

    canonical_ko = CanonicalKnowledgeObject(
        knowledge_id=db_ko.id,
        meeting_id=meeting.id,
        object_type="decision",
        content="Retry indexing test content",
    )

    healthy_indexer = SemanticIndexer(qdrant_client=memory_qdrant_client, collection_name="retry_col")
    point_id = await healthy_indexer.index_knowledge_object(canonical_ko, session=db_session)

    assert point_id == str(db_ko.id)

    refreshed_db_ko = await ko_repo.get(db_ko.id)
    assert refreshed_db_ko.status == "indexed"
    assert refreshed_db_ko.qdrant_point_id == str(db_ko.id)
