"""
Tests for Phase 3A: Knowledge Object Persistence, Domain Foundation, Schemas, and Repository
Validates confidence boundaries, version constraints, lifecycle states, structured provenance,
Qdrant point ID mapping, version history, lineage tracking, and schema validation.
"""

from typing import Dict
import uuid
import pytest
from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.knowledge_object import KnowledgeObject, KnowledgeObjectStatus
from app.models.meeting import Meeting
from app.repositories.knowledge_object_repo import KnowledgeObjectRepository
from app.repositories.meeting_repo import MeetingRepository
from app.schemas.knowledge_object import (
    KnowledgeObjectCreate,
    KnowledgeObjectFilter,
    KnowledgeObjectResponse,
    KnowledgeObjectUpdate,
    ProvenanceMetadataSchema,
)


@pytest.mark.asyncio
async def test_knowledge_object_creation_and_fields(db_session: AsyncSession) -> None:
    """Verify standard KnowledgeObject creation with full field integrity."""
    meeting_repo = MeetingRepository(db_session)
    ko_repo = KnowledgeObjectRepository(db_session)

    meeting = await meeting_repo.create(Meeting(title="KO Base Test Meeting"))

    ko = KnowledgeObject(
        meeting_id=meeting.id,
        object_type="decision",
        title="Persist Knowledge Objects in PostgreSQL",
        content="All structured collaboration artifacts must be persisted in PostgreSQL.",
        confidence=0.92,
        status=KnowledgeObjectStatus.ACTIVE.value,
        version=1,
        payload={"impact": "critical", "category": "architecture"},
        provenance={"producing_module": "BlackboardDecisionAgent"},
        qdrant_point_id=None,
    )
    saved_ko = await ko_repo.create(ko)

    assert saved_ko.id is not None
    assert saved_ko.meeting_id == meeting.id
    assert saved_ko.object_type == "decision"
    assert saved_ko.title == "Persist Knowledge Objects in PostgreSQL"
    assert saved_ko.content == "All structured collaboration artifacts must be persisted in PostgreSQL."
    assert saved_ko.confidence == 0.92
    assert saved_ko.status == "active"
    assert saved_ko.version == 1
    assert saved_ko.payload["impact"] == "critical"
    assert saved_ko.provenance["producing_module"] == "BlackboardDecisionAgent"
    assert saved_ko.created_at is not None
    assert saved_ko.updated_at is not None


@pytest.mark.asyncio
async def test_knowledge_object_confidence_boundaries_valid(db_session: AsyncSession) -> None:
    """Verify confidence values at exact boundary conditions (0.0, 0.5, 1.0, None) succeed."""
    meeting_repo = MeetingRepository(db_session)
    ko_repo = KnowledgeObjectRepository(db_session)

    meeting = await meeting_repo.create(Meeting(title="Confidence Boundary Meeting"))

    # 1. Lower boundary: 0.0
    ko_zero = await ko_repo.create(
        KnowledgeObject(
            meeting_id=meeting.id,
            object_type="hypothesis",
            title="Zero Confidence Hypothesis",
            content="Speculative item with zero confidence.",
            confidence=0.0,
            status=KnowledgeObjectStatus.DRAFT.value,
        )
    )
    assert ko_zero.confidence == 0.0

    # 2. Upper boundary: 1.0
    ko_one = await ko_repo.create(
        KnowledgeObject(
            meeting_id=meeting.id,
            object_type="fact",
            title="Max Confidence Fact",
            content="Verified ground truth fact with 1.0 confidence.",
            confidence=1.0,
            status=KnowledgeObjectStatus.VALIDATED.value,
        )
    )
    assert ko_one.confidence == 1.0

    # 3. None (unscored)
    ko_none = await ko_repo.create(
        KnowledgeObject(
            meeting_id=meeting.id,
            object_type="topic",
            title="Unscored Topic",
            content="Topic discussion without confidence metric.",
            confidence=None,
            status=KnowledgeObjectStatus.ACTIVE.value,
        )
    )
    assert ko_none.confidence is None


@pytest.mark.asyncio
async def test_knowledge_object_confidence_out_of_bounds_rejected(db_session: AsyncSession) -> None:
    """Verify confidence values outside [0.0, 1.0] are rejected by DB constraint and Pydantic schema."""
    meeting_repo = MeetingRepository(db_session)
    ko_repo = KnowledgeObjectRepository(db_session)

    meeting = await meeting_repo.create(Meeting(title="Confidence Constraint Meeting"))

    # Pydantic schema validation: below 0.0
    with pytest.raises(ValidationError):
        KnowledgeObjectCreate(
            meeting_id=meeting.id,
            object_type="decision",
            content="Negative confidence test",
            confidence=-0.05,
        )

    # Pydantic schema validation: above 1.0
    with pytest.raises(ValidationError):
        KnowledgeObjectCreate(
            meeting_id=meeting.id,
            object_type="decision",
            content="Excessive confidence test",
            confidence=1.05,
        )

    # Database constraint check (negative)
    ko_invalid_low = KnowledgeObject(
        meeting_id=meeting.id,
        object_type="decision",
        content="Invalid negative confidence DB test",
        confidence=-0.1,
    )
    with pytest.raises(IntegrityError):
        await ko_repo.create(ko_invalid_low)

    await db_session.rollback()

    # Database constraint check (excessive)
    ko_invalid_high = KnowledgeObject(
        meeting_id=meeting.id,
        object_type="decision",
        content="Invalid excessive confidence DB test",
        confidence=1.5,
    )
    with pytest.raises(IntegrityError):
        await ko_repo.create(ko_invalid_high)

    await db_session.rollback()


@pytest.mark.asyncio
async def test_knowledge_object_version_positive_constraint(db_session: AsyncSession) -> None:
    """Verify version must be >= 1 at both database and schema boundaries."""
    meeting_repo = MeetingRepository(db_session)
    ko_repo = KnowledgeObjectRepository(db_session)

    meeting = await meeting_repo.create(Meeting(title="Version Constraint Meeting"))

    # Pydantic schema check: version=0
    with pytest.raises(ValidationError):
        KnowledgeObjectCreate(
            meeting_id=meeting.id,
            object_type="decision",
            content="Zero version test",
            version=0,
        )

    # Database constraint check: version=0
    ko_zero_ver = KnowledgeObject(
        meeting_id=meeting.id,
        object_type="decision",
        content="Zero version DB test",
        version=0,
    )
    with pytest.raises(IntegrityError):
        await ko_repo.create(ko_zero_ver)

    await db_session.rollback()


@pytest.mark.asyncio
async def test_knowledge_object_all_lifecycle_states(db_session: AsyncSession) -> None:
    """Verify that all SDD-specified lifecycle states are supported and persisted."""
    meeting_repo = MeetingRepository(db_session)
    ko_repo = KnowledgeObjectRepository(db_session)

    meeting = await meeting_repo.create(Meeting(title="Lifecycle States Meeting"))

    sdd_states = [
        KnowledgeObjectStatus.DRAFT,
        KnowledgeObjectStatus.ACTIVE,
        KnowledgeObjectStatus.VALIDATED,
        KnowledgeObjectStatus.SUPERSEDED,
        KnowledgeObjectStatus.REJECTED,
        KnowledgeObjectStatus.DEPRECATED,
    ]

    for status_enum in sdd_states:
        ko = await ko_repo.create(
            KnowledgeObject(
                meeting_id=meeting.id,
                object_type="action_item",
                title=f"Task for state {status_enum.value}",
                content=f"Verifying lifecycle state {status_enum.value}",
                status=status_enum.value,
                version=1,
            )
        )
        assert ko.status == status_enum.value
        fetched = await ko_repo.get_by_id(ko.id)
        assert fetched is not None
        assert fetched.status == status_enum.value


@pytest.mark.asyncio
async def test_knowledge_object_structured_provenance_persistence(db_session: AsyncSession) -> None:
    """Verify structured provenance preserving producing module, model info, source segments, and lineage."""
    meeting_repo = MeetingRepository(db_session)
    ko_repo = KnowledgeObjectRepository(db_session)

    meeting = await meeting_repo.create(Meeting(title="Provenance Test Meeting"))

    provenance_payload = {
        "producing_module": "BlackboardDecisionAgent",
        "model_name": "gemini-1.5-pro",
        "model_version": "002",
        "source_segments": [101, 102, 103],
        "source_intervals": [{"start_ms": 12500, "end_ms": 25000}],
        "lineage": {
            "root_ko_id": None,
            "derivation_type": "direct_extraction",
            "notes": "Extracted with high confidence from conclusive speaker consensus",
        },
        "processing_metadata": {
            "latency_ms": 185,
            "tokens_used": 420,
            "temperature": 0.0,
        },
    }

    # Verify Pydantic schema validation of provenance
    validated_provenance = ProvenanceMetadataSchema(**provenance_payload)
    assert validated_provenance.producing_module == "BlackboardDecisionAgent"
    assert validated_provenance.model_name == "gemini-1.5-pro"
    assert len(validated_provenance.source_segments) == 3

    ko = await ko_repo.create(
        KnowledgeObject(
            meeting_id=meeting.id,
            object_type="decision",
            title="Adopt Cloud Infrastructure",
            content="Team reached unanimous agreement on Cloud Run hosting.",
            confidence=0.96,
            status=KnowledgeObjectStatus.ACTIVE.value,
            provenance=provenance_payload,
        )
    )

    fetched = await ko_repo.get_by_id(ko.id)
    assert fetched is not None
    assert fetched.provenance["producing_module"] == "BlackboardDecisionAgent"
    assert fetched.provenance["model_name"] == "gemini-1.5-pro"
    assert fetched.provenance["source_segments"] == [101, 102, 103]
    assert fetched.provenance["processing_metadata"]["latency_ms"] == 185


@pytest.mark.asyncio
async def test_knowledge_object_qdrant_point_id_mapping_and_retrieval(db_session: AsyncSession) -> None:
    """Verify deterministic Qdrant point ID reference and lookup in PostgreSQL repository."""
    meeting_repo = MeetingRepository(db_session)
    ko_repo = KnowledgeObjectRepository(db_session)

    meeting = await meeting_repo.create(Meeting(title="Qdrant Mapping Meeting"))

    new_id = uuid.uuid4()
    deterministic_qdrant_point_id = str(new_id)

    ko = await ko_repo.create(
        KnowledgeObject(
            id=new_id,
            meeting_id=meeting.id,
            object_type="topic",
            title="Qdrant Vector Indexing",
            content="Vector indexing links relational KO with Qdrant collection point.",
            confidence=0.88,
            status=KnowledgeObjectStatus.ACTIVE.value,
            qdrant_point_id=deterministic_qdrant_point_id,
        )
    )

    assert str(ko.id) == deterministic_qdrant_point_id
    assert ko.qdrant_point_id == deterministic_qdrant_point_id

    # Lookup by Qdrant point ID
    found_ko = await ko_repo.get_by_qdrant_point_id(deterministic_qdrant_point_id)
    assert found_ko is not None
    assert found_ko.id == ko.id
    assert found_ko.title == "Qdrant Vector Indexing"


@pytest.mark.asyncio
async def test_knowledge_object_repository_list_by_type_and_status(db_session: AsyncSession) -> None:
    """Verify repository filtering by meeting_id, object_type, and status."""
    meeting_repo = MeetingRepository(db_session)
    ko_repo = KnowledgeObjectRepository(db_session)

    meeting = await meeting_repo.create(Meeting(title="Filter Query Meeting"))

    # Seed different types and statuses
    await ko_repo.create(
        KnowledgeObject(
            meeting_id=meeting.id,
            object_type="action_item",
            title="Task 1",
            content="Active action item",
            status=KnowledgeObjectStatus.ACTIVE.value,
        )
    )
    await ko_repo.create(
        KnowledgeObject(
            meeting_id=meeting.id,
            object_type="action_item",
            title="Task 2",
            content="Draft action item",
            status=KnowledgeObjectStatus.DRAFT.value,
        )
    )
    await ko_repo.create(
        KnowledgeObject(
            meeting_id=meeting.id,
            object_type="decision",
            title="Decision 1",
            content="Active decision",
            status=KnowledgeObjectStatus.ACTIVE.value,
        )
    )

    # Filter by object_type and status
    active_actions = await ko_repo.list_by_type_and_status(
        meeting_id=meeting.id,
        object_type="action_item",
        status="active",
    )
    assert len(active_actions) == 1
    assert active_actions[0].title == "Task 1"

    # Filter by status only
    all_active = await ko_repo.list_by_type_and_status(
        meeting_id=meeting.id,
        status="active",
    )
    assert len(all_active) == 2

    # Filter by object_type only
    all_actions = await ko_repo.list_by_type_and_status(
        meeting_id=meeting.id,
        object_type="action_item",
    )
    assert len(all_actions) == 2


@pytest.mark.asyncio
async def test_knowledge_object_version_history_chain_and_supersession(db_session: AsyncSession) -> None:
    """
    Verify immutable version history:
    v1 -> v2 (points to v1, v1 marked superseded) -> v3 (points to v2, v2 marked superseded).
    Verify get_history reconstructs the full chronological chain.
    """
    meeting_repo = MeetingRepository(db_session)
    ko_repo = KnowledgeObjectRepository(db_session)

    meeting = await meeting_repo.create(Meeting(title="Version Chain Meeting"))

    # Version 1
    v1 = await ko_repo.create(
        KnowledgeObject(
            meeting_id=meeting.id,
            object_type="decision",
            title="Database Choice v1",
            content="Initial proposal to use SQLite.",
            confidence=0.75,
            status=KnowledgeObjectStatus.ACTIVE.value,
            version=1,
            parent_id=None,
        )
    )

    # Version 2
    v2 = await ko_repo.create(
        KnowledgeObject(
            meeting_id=meeting.id,
            object_type="decision",
            title="Database Choice v2",
            content="Updated decision to use PostgreSQL for production.",
            confidence=0.90,
            status=KnowledgeObjectStatus.ACTIVE.value,
            version=2,
            parent_id=v1.id,
            provenance={"supersedes": str(v1.id), "producing_module": "SynthesisEngine"},
        )
    )
    v1.status = KnowledgeObjectStatus.SUPERSEDED.value
    await db_session.flush()

    # Version 3
    v3 = await ko_repo.create(
        KnowledgeObject(
            meeting_id=meeting.id,
            object_type="decision",
            title="Database Choice v3",
            content="Final decision: PostgreSQL + Qdrant for semantic search.",
            confidence=0.99,
            status=KnowledgeObjectStatus.VALIDATED.value,
            version=3,
            parent_id=v2.id,
            provenance={"supersedes": str(v2.id), "producing_module": "UserApproval"},
        )
    )
    v2.status = KnowledgeObjectStatus.SUPERSEDED.value
    await db_session.flush()

    # Retrieve history from latest version v3
    history = await ko_repo.get_history(v3.id)
    assert len(history) == 3
    assert history[0].id == v1.id
    assert history[0].version == 1
    assert history[0].status == "superseded"
    assert history[1].id == v2.id
    assert history[1].version == 2
    assert history[1].status == "superseded"
    assert history[2].id == v3.id
    assert history[2].version == 3
    assert history[2].status == "validated"

    # Only v3 is non-superseded
    active_items = await ko_repo.list_active(meeting.id)
    # v3 is validated, list_active searches status == 'active'
    active_only = await ko_repo.list_by_type_and_status(meeting.id, status="active")
    assert len(active_only) == 0  # v1, v2 superseded, v3 validated


@pytest.mark.asyncio
async def test_knowledge_object_derivation_lineage_relationship(db_session: AsyncSession) -> None:
    """
    Verify derivation relationship between distinct object types:
    An ActionItem is derived from a parent Decision, maintaining parent_id and lineage metadata.
    """
    meeting_repo = MeetingRepository(db_session)
    ko_repo = KnowledgeObjectRepository(db_session)

    meeting = await meeting_repo.create(Meeting(title="Derivation Lineage Meeting"))

    # Parent decision
    decision = await ko_repo.create(
        KnowledgeObject(
            meeting_id=meeting.id,
            object_type="decision",
            title="Implement Rate Limiting",
            content="Decision to protect API with Redis-backed rate limiting.",
            confidence=0.94,
            status=KnowledgeObjectStatus.VALIDATED.value,
            version=1,
        )
    )

    # Derived Action Item
    action_item = await ko_repo.create(
        KnowledgeObject(
            meeting_id=meeting.id,
            object_type="action_item",
            title="Configure Redis Rate Limiter",
            content="Setup Redis token bucket middleware in FastAPI pipeline.",
            confidence=0.91,
            status=KnowledgeObjectStatus.ACTIVE.value,
            version=1,
            parent_id=decision.id,
            payload={"assignee": "Backend Lead", "priority": "high"},
            provenance={
                "producing_module": "ActionItemDerivationModule",
                "lineage": {
                    "derived_from_ko_id": str(decision.id),
                    "derivation_reason": "Action item created automatically from validated decision.",
                },
            },
        )
    )

    # Query derived children from the decision
    derived_objects = await ko_repo.list_by_parent(decision.id)
    assert len(derived_objects) == 1
    assert derived_objects[0].id == action_item.id
    assert derived_objects[0].object_type == "action_item"
    assert derived_objects[0].provenance["lineage"]["derived_from_ko_id"] == str(decision.id)


def test_knowledge_object_pydantic_schemas() -> None:
    """Verify serialization and validation rules across all Knowledge Object Pydantic schemas."""
    meeting_uuid = uuid.uuid4()
    parent_uuid = uuid.uuid4()

    # 1. Valid KnowledgeObjectCreate
    create_schema = KnowledgeObjectCreate(
        meeting_id=meeting_uuid,
        object_type="action_item",
        title="Draft schema",
        content="Write thorough Pydantic schemas",
        confidence=0.85,
        status=KnowledgeObjectStatus.ACTIVE,
        version=1,
        parent_id=parent_uuid,
        provenance=ProvenanceMetadataSchema(
            producing_module="SchemaValidator",
            model_name="gemini-1.5-pro",
            source_segments=[1, 2],
        ),
        payload={"assignee": "Engineer A"},
    )
    assert create_schema.confidence == 0.85
    assert create_schema.status == KnowledgeObjectStatus.ACTIVE

    # 2. KnowledgeObjectUpdate
    update_schema = KnowledgeObjectUpdate(
        title="Updated schema title",
        confidence=0.95,
        status=KnowledgeObjectStatus.VALIDATED,
    )
    assert update_schema.confidence == 0.95
    assert update_schema.status == KnowledgeObjectStatus.VALIDATED

    # 3. KnowledgeObjectFilter
    filter_schema = KnowledgeObjectFilter(
        meeting_id=meeting_uuid,
        object_type="action_item",
        status=KnowledgeObjectStatus.ACTIVE,
        min_confidence=0.5,
        max_confidence=1.0,
        skip=0,
        limit=50,
    )
    assert filter_schema.limit == 50
    assert filter_schema.min_confidence == 0.5
