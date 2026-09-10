"""
Tests for Phase 3B: Knowledge Object Domain Service, Immutable Versioning,
Lifecycle State Machine, Version History vs Derivation Lineage Distinction, and Transactions.
"""

import uuid
import pytest
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import BadRequestException, NotFoundException
from app.knowledge.knowledge_service import KnowledgeObjectService
from app.models.knowledge_object import KnowledgeObjectStatus
from app.models.meeting import Meeting
from app.repositories.meeting_repo import MeetingRepository
from app.schemas.knowledge_object import (
    KnowledgeObjectCreate,
    KnowledgeObjectUpdate,
    ProvenanceMetadataSchema,
)


@pytest.mark.asyncio
async def test_service_create_and_confidence_validation(db_session: AsyncSession) -> None:
    """Verify service validates confidence and successfully creates Knowledge Objects."""
    meeting_repo = MeetingRepository(db_session)
    meeting = await meeting_repo.create(Meeting(title="Service Test Meeting"))
    service = KnowledgeObjectService(db_session)

    # Valid creation
    create_dto = KnowledgeObjectCreate(
        meeting_id=meeting.id,
        object_type="decision",
        title="Service Decision",
        content="Testing service creation flow.",
        confidence=0.88,
        status=KnowledgeObjectStatus.ACTIVE,
        version=1,
    )
    ko = await service.create_knowledge_object(create_dto)
    assert ko.id is not None
    assert ko.confidence == 0.88
    assert ko.status == "active"

    # Invalid confidence rejected by Pydantic schema validation before service
    with pytest.raises(ValidationError):
        KnowledgeObjectCreate(
            meeting_id=meeting.id,
            object_type="decision",
            content="Invalid confidence",
            confidence=1.2,
        )


@pytest.mark.asyncio
async def test_service_lifecycle_state_machine_transitions(db_session: AsyncSession) -> None:
    """Verify valid lifecycle transitions succeed and invalid transitions are rejected."""
    meeting_repo = MeetingRepository(db_session)
    meeting = await meeting_repo.create(Meeting(title="Lifecycle State Machine Meeting"))
    service = KnowledgeObjectService(db_session)

    ko = await service.create_knowledge_object(
        KnowledgeObjectCreate(
            meeting_id=meeting.id,
            object_type="hypothesis",
            content="State transition test item",
            status=KnowledgeObjectStatus.DRAFT,
            version=1,
        )
    )
    assert ko.status == "draft"

    # 1. Valid: DRAFT -> ACTIVE
    ko_active = await service.update_lifecycle_status(ko.id, KnowledgeObjectStatus.ACTIVE)
    assert ko_active.status == "active"

    # 2. Valid: ACTIVE -> VALIDATED
    ko_validated = await service.update_lifecycle_status(ko.id, KnowledgeObjectStatus.VALIDATED)
    assert ko_validated.status == "validated"

    # 3. Invalid: VALIDATED -> DRAFT (not allowed)
    with pytest.raises(BadRequestException) as exc_info:
        await service.update_lifecycle_status(ko.id, KnowledgeObjectStatus.DRAFT)
    assert exc_info.value.code == "INVALID_LIFECYCLE_TRANSITION"


@pytest.mark.asyncio
async def test_service_immutable_versioning(db_session: AsyncSession) -> None:
    """Verify immutable revisioning creates new version, supersedes old, and preserves provenance."""
    meeting_repo = MeetingRepository(db_session)
    meeting = await meeting_repo.create(Meeting(title="Immutable Versioning Meeting"))
    service = KnowledgeObjectService(db_session)

    v1 = await service.create_knowledge_object(
        KnowledgeObjectCreate(
            meeting_id=meeting.id,
            object_type="decision",
            title="Architecture Decision v1",
            content="Initial architecture draft.",
            confidence=0.80,
            status=KnowledgeObjectStatus.ACTIVE,
            version=1,
            provenance=ProvenanceMetadataSchema(producing_module="AgentA"),
        )
    )

    # Revise v1 to v2
    v2 = await service.revise_knowledge_object(
        v1.id,
        KnowledgeObjectUpdate(
            title="Architecture Decision v2",
            content="Revised architecture with enhanced security.",
            confidence=0.95,
            status=KnowledgeObjectStatus.VALIDATED,
            provenance=ProvenanceMetadataSchema(producing_module="AgentB"),
        ),
    )

    # Fetch v1 and verify it became superseded
    v1_refreshed = await service.get_knowledge_object(v1.id)
    assert v1_refreshed.status == "superseded"

    # Verify v2 properties
    assert v2.id != v1.id
    assert v2.version == 2
    assert v2.parent_id == v1.id
    assert v2.status == "validated"
    assert v2.confidence == 0.95
    assert v2.provenance["lineage"]["revised_from_id"] == str(v1.id)
    assert v2.provenance["lineage"]["previous_version"] == 1


@pytest.mark.asyncio
async def test_service_version_history_vs_derivation_lineage(db_session: AsyncSession) -> None:
    """
    Verify strict separation between:
    1. Version history (Decision v1 -> Decision v2)
    2. Derivation lineage (Decision v1 -> Action Item)
    An Action Item must NOT appear in Decision's version history, and vice versa.
    """
    meeting_repo = MeetingRepository(db_session)
    meeting = await meeting_repo.create(Meeting(title="Lineage Separation Meeting"))
    service = KnowledgeObjectService(db_session)

    # Decision v1
    dec_v1 = await service.create_knowledge_object(
        KnowledgeObjectCreate(
            meeting_id=meeting.id,
            object_type="decision",
            title="Decision v1",
            content="Adopt Python backend.",
            confidence=0.90,
            status=KnowledgeObjectStatus.ACTIVE,
            version=1,
        )
    )

    # Decision v2 (Revision)
    dec_v2 = await service.revise_knowledge_object(
        dec_v1.id,
        KnowledgeObjectUpdate(
            title="Decision v2",
            content="Adopt Python + FastAPI backend.",
            confidence=0.95,
        ),
    )

    # Derive Action Item from Decision v2
    action_item = await service.derive_knowledge_object(
        parent_id=dec_v2.id,
        object_type="action_item",
        title="Implement FastAPI Endpoints",
        content="Create REST routes for core endpoints.",
        confidence=0.92,
    )

    # 1. Version history of Action Item must NOT include Decision v2 or v1
    action_history = await service.get_version_history(action_item.id)
    assert len(action_history) == 1
    assert action_history[0].id == action_item.id
    assert action_history[0].object_type == "action_item"

    # 2. Version history of Decision v2 must include Decision v1 and v2, but NOT the Action Item
    dec_history = await service.get_version_history(dec_v2.id)
    assert len(dec_history) == 2
    assert dec_history[0].id == dec_v1.id
    assert dec_history[1].id == dec_v2.id
    assert all(item.object_type == "decision" for item in dec_history)

    # 3. Derivation lineage trace correctly links parent source and derived children
    lineage = await service.get_derivation_lineage(action_item.id)
    assert lineage["parent_source"] is not None
    assert lineage["parent_source"].id == dec_v2.id
    assert lineage["parent_source"].object_type == "decision"

    dec_lineage = await service.get_derivation_lineage(dec_v2.id)
    assert len(dec_lineage["derived_children"]) == 1
    assert dec_lineage["derived_children"][0].id == action_item.id
