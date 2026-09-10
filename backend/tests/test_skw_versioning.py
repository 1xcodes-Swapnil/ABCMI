"""
Comprehensive Unit & Integration Tests for Phase 4.6:
Knowledge Object Versioning and Lifecycle Management.
Verifies valid lifecycle transitions, invalid transition prevention, version creation,
version history chaining, historical version retrieval/restoration, confidence-based invalidation,
expiration, archival, and concurrent update protection.
"""

import uuid
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from app.skw.models.knowledge_object import SKWLifecycleState
from app.skw.services.version_manager import DefaultVersionManager
from app.core.exceptions import BadRequestException, NotFoundException
from app.models.meeting import Meeting
from app.repositories.meeting_repo import MeetingRepository


@pytest.mark.asyncio
async def test_valid_lifecycle_transitions(db_session: AsyncSession) -> None:
    """Verify all valid lifecycle transitions through the state machine graph."""
    meeting_repo = MeetingRepository(db_session)
    meeting = await meeting_repo.create(Meeting(title="Lifecycle Transitions Meeting"))
    vm = DefaultVersionManager(db_session)

    ko = await vm.create_version(
        meeting_id=meeting.id,
        object_type="decision",
        source_module="AudioIntelligence",
        content="Lifecycle transition test decision",
    )
    assert ko.status == SKWLifecycleState.CREATED.value

    # Created -> Validating
    ko = await vm.transition_lifecycle(ko.id, SKWLifecycleState.VALIDATING)
    assert ko.status == SKWLifecycleState.VALIDATING.value

    # Validating -> Accepted
    ko = await vm.transition_lifecycle(ko.id, SKWLifecycleState.ACCEPTED)
    assert ko.status == SKWLifecycleState.ACCEPTED.value

    # Accepted -> Indexed
    ko = await vm.transition_lifecycle(ko.id, SKWLifecycleState.INDEXED)
    assert ko.status == SKWLifecycleState.INDEXED.value

    # Indexed -> Published
    ko = await vm.transition_lifecycle(ko.id, SKWLifecycleState.PUBLISHED)
    assert ko.status == SKWLifecycleState.PUBLISHED.value

    # Published -> Shared
    ko = await vm.transition_lifecycle(ko.id, SKWLifecycleState.SHARED)
    assert ko.status == SKWLifecycleState.SHARED.value


@pytest.mark.asyncio
async def test_invalid_lifecycle_transition_rejected(db_session: AsyncSession) -> None:
    """Verify invalid lifecycle transitions are blocked with BadRequestException."""
    meeting_repo = MeetingRepository(db_session)
    meeting = await meeting_repo.create(Meeting(title="Invalid Transition Meeting"))
    vm = DefaultVersionManager(db_session)

    ko = await vm.create_version(
        meeting_id=meeting.id,
        object_type="decision",
        source_module="AudioIntelligence",
        content="Invalid transition test",
    )

    # Invalid: Created -> Published (skipped Validating, Accepted, Indexed)
    with pytest.raises(BadRequestException) as exc_info:
        await vm.transition_lifecycle(ko.id, SKWLifecycleState.PUBLISHED)

    assert exc_info.value.code == "INVALID_LIFECYCLE_TRANSITION"


@pytest.mark.asyncio
async def test_version_creation_and_history_chain(db_session: AsyncSession) -> None:
    """Verify version creation, revisioning (v1 -> v2), version history chaining, and non-destructive overwriting."""
    meeting_repo = MeetingRepository(db_session)
    meeting = await meeting_repo.create(Meeting(title="Versioning Meeting"))
    vm = DefaultVersionManager(db_session)

    v1 = await vm.create_version(
        meeting_id=meeting.id,
        object_type="decision",
        source_module="AgentA",
        content="Initial content v1",
        title="Title v1",
        confidence_score=0.90,
    )
    assert v1.version == 1
    assert v1.status == SKWLifecycleState.CREATED.value

    # Create new version v2
    v2 = await vm.create_new_version(
        v1.id,
        update_data={"content": "Updated content v2", "title": "Title v2", "confidence_score": 0.95},
        change_info={"reason": "Refinement"},
    )

    assert v2.version == 2
    assert v2.parent_id == v1.id
    assert v2.content == "Updated content v2"
    assert v2.status == SKWLifecycleState.UPDATED.value

    # Verify v1 is now versioned / superseded
    v1_refreshed = await vm.get_version(v1.id, version=1)
    assert v1_refreshed.status == SKWLifecycleState.VERSIONED.value

    # Verify version history
    history = await vm.get_version_history(v1.id)
    assert len(history) == 2
    assert history[0].version == 1
    assert history[1].version == 2

    # Verify current version
    current = await vm.get_current_version(v1.id)
    assert current.version == 2


@pytest.mark.asyncio
async def test_historical_version_retrieval_and_restoration(db_session: AsyncSession) -> None:
    """Verify historical version retrieval and restoration as a new branch without overwriting history."""
    meeting_repo = MeetingRepository(db_session)
    meeting = await meeting_repo.create(Meeting(title="Restoration Meeting"))
    vm = DefaultVersionManager(db_session)

    v1 = await vm.create_version(
        meeting_id=meeting.id,
        object_type="fact",
        source_module="AgentA",
        content="Original fact",
    )
    v2 = await vm.create_new_version(v1.id, update_data={"content": "Modified fact"})

    # Restore v1
    v3 = await vm.restore_version(v1.id, target_version=1)
    assert v3.version == 3
    assert v3.content == "Original fact"
    assert v3.parent_id == v1.id

    history = await vm.get_version_history(v1.id)
    assert len(history) == 3


@pytest.mark.asyncio
async def test_confidence_based_invalidation(db_session: AsyncSession) -> None:
    """Verify that if confidence falls below threshold, object transitions to invalid."""
    meeting_repo = MeetingRepository(db_session)
    meeting = await meeting_repo.create(Meeting(title="Confidence Invalidation Meeting"))
    vm = DefaultVersionManager(db_session, confidence_threshold=0.6)

    ko = await vm.create_version(
        meeting_id=meeting.id,
        object_type="decision",
        source_module="AgentA",
        content="High confidence decision",
        confidence_score=0.85,
    )
    ko = await vm.transition_lifecycle(ko.id, SKWLifecycleState.VALIDATING)
    ko = await vm.transition_lifecycle(ko.id, SKWLifecycleState.ACCEPTED)
    ko = await vm.transition_lifecycle(ko.id, SKWLifecycleState.INDEXED)
    ko = await vm.transition_lifecycle(ko.id, SKWLifecycleState.PUBLISHED)
    assert ko.status == SKWLifecycleState.PUBLISHED.value

    # Update confidence below threshold (0.6)
    ko_invalid = await vm.check_confidence_invalidation(ko.id, new_confidence=0.45)
    assert ko_invalid.confidence == 0.45
    assert ko_invalid.status == SKWLifecycleState.INVALID.value


@pytest.mark.asyncio
async def test_expiration_and_archival(db_session: AsyncSession) -> None:
    """Verify published -> expired -> archived alternative path."""
    meeting_repo = MeetingRepository(db_session)
    meeting = await meeting_repo.create(Meeting(title="Archival Meeting"))
    vm = DefaultVersionManager(db_session)

    ko = await vm.create_version(
        meeting_id=meeting.id,
        object_type="decision",
        source_module="AgentA",
        content="Expiring decision",
    )
    ko = await vm.transition_lifecycle(ko.id, SKWLifecycleState.VALIDATING)
    ko = await vm.transition_lifecycle(ko.id, SKWLifecycleState.ACCEPTED)
    ko = await vm.transition_lifecycle(ko.id, SKWLifecycleState.INDEXED)
    ko = await vm.transition_lifecycle(ko.id, SKWLifecycleState.PUBLISHED)

    # Published -> Expired
    ko = await vm.transition_lifecycle(ko.id, SKWLifecycleState.EXPIRED)
    assert ko.status == SKWLifecycleState.EXPIRED.value

    # Expired -> Archived
    ko = await vm.transition_lifecycle(ko.id, SKWLifecycleState.ARCHIVED)
    assert ko.status == SKWLifecycleState.ARCHIVED.value


@pytest.mark.asyncio
async def test_concurrent_update_protection(db_session: AsyncSession) -> None:
    """Verify concurrent update protection detects version mismatch and raises conflict error."""
    meeting_repo = MeetingRepository(db_session)
    meeting = await meeting_repo.create(Meeting(title="Concurrency Meeting"))
    vm = DefaultVersionManager(db_session)

    v1 = await vm.create_version(
        meeting_id=meeting.id,
        object_type="decision",
        source_module="AgentA",
        content="Concurrent test",
    )

    # Try creating new version with stale expected_version = 5 (current is 1)
    with pytest.raises(BadRequestException) as exc_info:
        await vm.create_new_version(
            v1.id,
            update_data={"content": "Stale update"},
            expected_version=5,
        )

    assert exc_info.value.code == "CONCURRENT_UPDATE_CONFLICT"
