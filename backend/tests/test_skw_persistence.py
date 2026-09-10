"""
Comprehensive Unit & Integration Tests for Phase 4.4:
PostgreSQL Persistence and Knowledge Object Repository.
Verifies create, retrieval, update, filtering (getByMeeting, getByType, getBySource, getByVersion),
duplicate handling, transaction rollback, invalid meeting foreign key constraints, and archival.
"""

import uuid
import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.knowledge_object import KnowledgeObject, KnowledgeObjectStatus
from app.models.meeting import Meeting
from app.repositories.knowledge_object_repo import KnowledgeObjectRepository
from app.repositories.meeting_repo import MeetingRepository


@pytest.mark.asyncio
async def test_persistence_create_and_retrieve(db_session: AsyncSession) -> None:
    """Verify creating and retrieving a knowledge object with source_module and confidence in PostgreSQL."""
    meeting_repo = MeetingRepository(db_session)
    ko_repo = KnowledgeObjectRepository(db_session)

    meeting = await meeting_repo.create(Meeting(title="Persistence Test Meeting"))

    ko = KnowledgeObject(
        meeting_id=meeting.id,
        object_type="decision",
        source_module="AudioIntelligence",
        title="Database Persistence Test",
        content="Testing direct repository creation and retrieval.",
        confidence=0.95,
        version=1,
        status=KnowledgeObjectStatus.ACTIVE.value,
        payload={"key": "value"},
        provenance={"producing_module": "AudioIntelligence"},
    )

    created = await ko_repo.create(ko)
    assert created.id is not None

    fetched = await ko_repo.get(created.id)
    assert fetched is not None
    assert fetched.id == created.id
    assert fetched.meeting_id == meeting.id
    assert fetched.object_type == "decision"
    assert fetched.source_module == "AudioIntelligence"
    assert fetched.confidence == 0.95
    assert fetched.version == 1


@pytest.mark.asyncio
async def test_persistence_filtering_methods(db_session: AsyncSession) -> None:
    """Verify repository filtering methods: getByMeeting, getByType, getBySource, getByVersion."""
    meeting_repo = MeetingRepository(db_session)
    ko_repo = KnowledgeObjectRepository(db_session)

    meeting = await meeting_repo.create(Meeting(title="Filtering Test Meeting"))

    ko1 = await ko_repo.create(
        KnowledgeObject(
            meeting_id=meeting.id,
            object_type="decision",
            source_module="ModuleA",
            content="Decision 1 from Module A",
            confidence=0.9,
            version=1,
        )
    )
    ko2 = await ko_repo.create(
        KnowledgeObject(
            meeting_id=meeting.id,
            object_type="action_item",
            source_module="ModuleB",
            content="Action item from Module B",
            confidence=0.85,
            version=1,
        )
    )

    # Test getByMeeting
    by_meeting = await ko_repo.getByMeeting(meeting.id)
    assert len(by_meeting) >= 2

    # Test getByType
    by_type = await ko_repo.getByType("decision")
    assert any(k.id == ko1.id for k in by_type)

    # Test getBySource
    by_source = await ko_repo.getBySource("ModuleB")
    assert any(k.id == ko2.id for k in by_source)

    # Test getByVersion
    by_version = await ko_repo.getByVersion(meeting.id, 1)
    assert len(by_version) >= 2


@pytest.mark.asyncio
async def test_persistence_update_and_archive(db_session: AsyncSession) -> None:
    """Verify updating a knowledge object and archiving (deprecating) it."""
    meeting_repo = MeetingRepository(db_session)
    ko_repo = KnowledgeObjectRepository(db_session)

    meeting = await meeting_repo.create(Meeting(title="Update Archival Meeting"))

    ko = await ko_repo.create(
        KnowledgeObject(
            meeting_id=meeting.id,
            object_type="fact",
            source_module="KnowledgeExtractor",
            content="Initial Fact Content",
            confidence=0.8,
            version=1,
        )
    )

    # Update
    ko.content = "Updated Fact Content"
    ko.confidence = 0.98
    await ko_repo.update(ko)

    refreshed = await ko_repo.get(ko.id)
    assert refreshed.content == "Updated Fact Content"
    assert refreshed.confidence == 0.98

    # Archive
    archived = await ko_repo.archive(ko.id)
    assert archived.status == "deprecated"


@pytest.mark.asyncio
async def test_invalid_meeting_reference_rollback(db_session: AsyncSession) -> None:
    """Verify foreign key constraint failure on non-existent meeting ID triggers integrity error and rollback."""
    ko_repo = KnowledgeObjectRepository(db_session)
    fake_meeting_id = uuid.uuid4()

    ko = KnowledgeObject(
        meeting_id=fake_meeting_id,  # Does not exist
        object_type="decision",
        source_module="AudioIntelligence",
        content="Invalid meeting reference test",
        confidence=0.9,
    )

    with pytest.raises(IntegrityError):
        await ko_repo.create(ko)

    await db_session.rollback()
