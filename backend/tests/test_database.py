"""
ABCI-MI Database Integration & ORM Persistence Tests
Validates PostgreSQL/SQLAlchemy 2.x async models, repository pattern operations,
and schema relationships.
"""

from datetime import datetime, timezone
import uuid
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.models.meeting import Meeting
from app.models.participant import Participant
from app.models.audio import Audio
from app.models.transcript import Transcript, TranscriptSegment
from app.models.analytics import MeetingAnalytics
from app.models.audit_log import AuditLog
from app.models.configuration import SystemConfiguration
from app.models.knowledge_object import KnowledgeObject

from app.repositories.user_repo import UserRepository
from app.repositories.meeting_repo import MeetingRepository
from app.repositories.participant_repo import ParticipantRepository
from app.repositories.audio_repo import AudioRepository
from app.repositories.transcript_repo import TranscriptRepository, TranscriptSegmentRepository
from app.repositories.analytics_repo import AnalyticsRepository
from app.repositories.audit_log_repo import AuditLogRepository
from app.repositories.configuration_repo import ConfigurationRepository
from app.repositories.knowledge_object_repo import KnowledgeObjectRepository


@pytest.mark.asyncio
async def test_user_repository_crud(db_session: AsyncSession) -> None:
    """Test User persistence, status field, and UserRepository methods."""
    repo = UserRepository(db_session)

    user = User(
        email="alex.chen@example.com",
        full_name="Alex Chen",
        role="admin",
        status="active",
        preferences={"theme": "dark", "language": "en"},
    )
    created = await repo.create(user)
    assert created.id is not None
    assert created.email == "alex.chen@example.com"
    assert created.is_active is True
    assert created.status == "active"
    assert created.created_at is not None
    assert created.updated_at is not None

    # Fetch by email (case-insensitive)
    found = await repo.get_by_email("ALEX.CHEN@EXAMPLE.COM")
    assert found is not None
    assert found.id == created.id
    assert found.full_name == "Alex Chen"

    # List active
    active_users = await repo.list_active()
    assert len(active_users) >= 1
    assert any(u.id == created.id for u in active_users)

    # Inactive status check
    user2 = User(
        email="inactive@example.com",
        full_name="Inactive User",
        status="suspended",
    )
    await repo.create(user2)
    assert user2.is_active is False

    by_status = await repo.list_by_status("suspended")
    assert len(by_status) == 1
    assert by_status[0].email == "inactive@example.com"


@pytest.mark.asyncio
async def test_meeting_and_participant_relationships(db_session: AsyncSession) -> None:
    """Test Meeting, Host, and Participant relationships with display_name and speaking_duration."""
    user_repo = UserRepository(db_session)
    meeting_repo = MeetingRepository(db_session)
    participant_repo = ParticipantRepository(db_session)

    # 1. Create host
    host = await user_repo.create(
        User(
            email="host@example.com",
            full_name="Meeting Host",
            role="lead",
            status="active",
        )
    )

    # 2. Create meeting
    meeting = await meeting_repo.create(
        Meeting(
            title="Q3 Strategy Review",
            description="Quarterly alignment meeting",
            status="active",
            language="en",
            secondary_languages=["es", "ja"],
            host_id=host.id,
        )
    )
    assert meeting.id is not None
    assert meeting.host_id == host.id

    # 3. Add Participants
    p1 = await participant_repo.create(
        Participant(
            meeting_id=meeting.id,
            user_id=host.id,
            display_name="Meeting Host",
            email="host@example.com",
            role="host",
            speaker_label="SPEAKER_00",
            speaking_duration=125.5,
        )
    )
    p2 = await participant_repo.create(
        Participant(
            meeting_id=meeting.id,
            display_name="Guest Attendee",
            email="guest@external.org",
            role="attendee",
            speaker_label="SPEAKER_01",
            speaking_duration=45.0,
        )
    )

    # 4. Verify participant repo queries
    participants = await participant_repo.list_by_meeting(meeting.id)
    assert len(participants) == 2
    assert participants[0].display_name in ["Meeting Host", "Guest Attendee"]

    speaker_01 = await participant_repo.get_by_speaker_label(meeting.id, "SPEAKER_01")
    assert speaker_01 is not None
    assert speaker_01.display_name == "Guest Attendee"
    assert speaker_01.speaking_duration == 45.0

    host_participant = await participant_repo.get_by_user_id(meeting.id, host.id)
    assert host_participant is not None
    assert host_participant.id == p1.id

    # 5. List meetings by host
    hosted = await meeting_repo.list_by_host(host.id)
    assert len(hosted) == 1
    assert hosted[0].id == meeting.id

    # 6. List meetings by status
    active_meetings = await meeting_repo.list_by_status("active")
    assert len(active_meetings) == 1
    assert active_meetings[0].title == "Q3 Strategy Review"


@pytest.mark.asyncio
async def test_audio_recording_persistence(db_session: AsyncSession) -> None:
    """Test Audio recording model and AudioRepository with meeting association."""
    meeting_repo = MeetingRepository(db_session)
    audio_repo = AudioRepository(db_session)

    meeting = await meeting_repo.create(
        Meeting(title="Audio Test Session", status="in_progress")
    )

    audio1 = await audio_repo.create(
        Audio(
            meeting_id=meeting.id,
            file_path="/storage/audio/session_1_raw.wav",
            file_name="session_1_raw.wav",
            file_size_bytes=10485760,
            duration_seconds=655.2,
            format="wav",
            sample_rate=16000,
            channels=1,
            status="processed",
            meta_data={"codec": "pcm_s16le", "bitrate": 256000},
        )
    )
    assert audio1.id is not None
    assert audio1.meeting_id == meeting.id
    assert audio1.format == "wav"

    # Fetch recordings for meeting
    recordings = await audio_repo.list_by_meeting(meeting.id)
    assert len(recordings) == 1
    assert recordings[0].file_name == "session_1_raw.wav"

    latest = await audio_repo.get_latest_by_meeting(meeting.id)
    assert latest is not None
    assert latest.id == audio1.id


@pytest.mark.asyncio
async def test_transcript_segment_and_canonical_transcripts(db_session: AsyncSession) -> None:
    """Test streaming TranscriptSegment and canonical versioned Transcript models and repositories."""
    meeting_repo = MeetingRepository(db_session)
    segment_repo = TranscriptSegmentRepository(db_session)
    transcript_repo = TranscriptRepository(db_session)

    meeting = await meeting_repo.create(
        Meeting(title="Transcript Test Meeting", status="active")
    )

    # 1. Bulk create segments
    segments = [
        TranscriptSegment(
            meeting_id=meeting.id,
            speaker_label="SPEAKER_00",
            start_time_ms=0,
            end_time_ms=3500,
            language="en",
            original_text="Welcome everyone to the meeting.",
            confidence=0.98,
            sequence_number=1,
            words_payload=[
                {"word": "Welcome", "start": 0, "end": 500},
                {"word": "everyone", "start": 550, "end": 1200},
            ],
        ),
        TranscriptSegment(
            meeting_id=meeting.id,
            speaker_label="SPEAKER_01",
            start_time_ms=3600,
            end_time_ms=7200,
            language="en",
            original_text="Thank you. Let us review the action items.",
            confidence=0.95,
            sequence_number=2,
        ),
    ]
    await segment_repo.bulk_create_segments(segments)

    # 2. Verify sequence and listing
    max_seq = await segment_repo.get_latest_sequence(meeting.id)
    assert max_seq == 2

    meeting_segments = await segment_repo.list_by_meeting(meeting.id)
    assert len(meeting_segments) == 2
    assert meeting_segments[0].sequence_number == 1
    assert meeting_segments[1].sequence_number == 2

    # 3. Timerange query
    time_window = await segment_repo.list_in_timerange(
        meeting_id=meeting.id,
        start_ms=3000,
        end_ms=4000,
    )
    assert len(time_window) == 2  # Both overlap with 3000-4000ms

    # 4. Canonical full transcript creation and versioning
    t_v1 = await transcript_repo.create(
        Transcript(
            meeting_id=meeting.id,
            version=1,
            language="en",
            full_text="Welcome everyone to the meeting. Thank you. Let us review the action items.",
            is_final=False,
            confidence_score=0.965,
            word_count=13,
            provenance={"source": "realtime_asr_stream", "segment_count": 2},
        )
    )
    assert t_v1.id is not None
    assert t_v1.version == 1

    t_v2 = await transcript_repo.create(
        Transcript(
            meeting_id=meeting.id,
            version=2,
            language="en",
            full_text="Welcome everyone to the meeting. Thank you. Let us review the action items. [Finalized]",
            is_final=True,
            confidence_score=0.99,
            word_count=14,
            provenance={"source": "offline_whisper_pass", "model": "whisper-large-v3"},
        )
    )

    all_transcripts = await transcript_repo.list_by_meeting(meeting.id)
    assert len(all_transcripts) == 2
    assert all_transcripts[0].version == 2  # Ordered descending by version

    latest_transcript = await transcript_repo.get_latest_version(meeting.id)
    assert latest_transcript is not None
    assert latest_transcript.version == 2
    assert latest_transcript.is_final is True


@pytest.mark.asyncio
async def test_meeting_analytics_repository(db_session: AsyncSession) -> None:
    """Test MeetingAnalytics model, engagement score, pace_wpm, and upsert functionality."""
    meeting_repo = MeetingRepository(db_session)
    analytics_repo = AnalyticsRepository(db_session)

    meeting = await meeting_repo.create(
        Meeting(title="Analytics Test Meeting", status="completed")
    )

    # Initial upsert
    analytics = await analytics_repo.upsert_for_meeting(
        meeting_id=meeting.id,
        speaking_time_distribution={"SPEAKER_00": 70.0, "SPEAKER_01": 30.0},
        collaboration_score=0.85,
        participation_index=0.78,
        sentiment_score=0.65,
        productivity_score=0.91,
        sentiment_distribution={"positive": 0.6, "neutral": 0.3, "negative": 0.1},
        engagement_score=0.88,
        pace_wpm=142.5,
        turn_taking_metrics={"interruption_count": 2, "turn_switches": 15},
        topic_keywords=["architecture", "postgresql", "migrations"],
        summary_metrics={"total_words": 1500, "duration_minutes": 10.5},
    )
    assert analytics.id is not None
    assert analytics.meeting_id == meeting.id
    assert analytics.collaboration_score == 0.85
    assert analytics.participation_index == 0.78
    assert analytics.sentiment_score == 0.65
    assert analytics.productivity_score == 0.91
    assert analytics.engagement_score == 0.88
    assert analytics.pace_wpm == 142.5
    assert analytics.speaking_time_distribution["SPEAKER_00"] == 70.0

    # Retrieve
    retrieved = await analytics_repo.get_by_meeting_id(meeting.id)
    assert retrieved is not None
    assert retrieved.id == analytics.id
    assert retrieved.collaboration_score == 0.85
    assert retrieved.participation_index == 0.78
    assert retrieved.sentiment_score == 0.65
    assert retrieved.productivity_score == 0.91

    # Update through upsert
    updated = await analytics_repo.upsert_for_meeting(
        meeting_id=meeting.id,
        speaking_time_distribution={"SPEAKER_00": 60.0, "SPEAKER_01": 40.0},
        collaboration_score=0.90,
        participation_index=0.82,
        sentiment_score=0.72,
        productivity_score=0.95,
        engagement_score=0.92,
        pace_wpm=148.0,
    )
    assert updated.id == analytics.id
    assert updated.collaboration_score == 0.90
    assert updated.participation_index == 0.82
    assert updated.sentiment_score == 0.72
    assert updated.productivity_score == 0.95
    assert updated.engagement_score == 0.92
    assert updated.pace_wpm == 148.0
    assert updated.speaking_time_distribution["SPEAKER_00"] == 60.0


@pytest.mark.asyncio
async def test_audit_log_and_system_configuration(db_session: AsyncSession) -> None:
    """Test AuditLog security records and SystemConfiguration dynamic settings."""
    user_repo = UserRepository(db_session)
    meeting_repo = MeetingRepository(db_session)
    audit_repo = AuditLogRepository(db_session)
    config_repo = ConfigurationRepository(db_session)

    user = await user_repo.create(User(email="auditor@example.com", full_name="Auditor"))
    meeting = await meeting_repo.create(Meeting(title="Audited Session"))

    # Create audit logs
    log1 = await audit_repo.create(
        AuditLog(
            user_id=user.id,
            meeting_id=meeting.id,
            action="meeting.created",
            resource_type="Meeting",
            resource_id=str(meeting.id),
            details={"title": "Audited Session"},
            ip_address="192.168.1.100",
            user_agent="Mozilla/5.0",
        )
    )
    log2 = await audit_repo.create(
        AuditLog(
            user_id=user.id,
            meeting_id=meeting.id,
            action="meeting.recording_started",
            resource_type="Audio",
            details={"format": "wav"},
        )
    )

    meeting_logs = await audit_repo.list_by_meeting(meeting.id)
    assert len(meeting_logs) == 2

    user_logs = await audit_repo.list_by_user(user.id)
    assert len(user_logs) == 2

    action_logs = await audit_repo.list_by_action("meeting.created")
    assert len(action_logs) == 1
    assert action_logs[0].id == log1.id

    # Test SystemConfiguration
    config = await config_repo.upsert_key(
        key="asr.streaming_chunk_ms",
        value={"chunk_ms": 500, "sample_rate": 16000},
        category="asr",
        description="Streaming ASR chunk duration in milliseconds",
    )
    assert config.key == "asr.streaming_chunk_ms"
    assert config.value["chunk_ms"] == 500

    fetched_config = await config_repo.get_by_key("asr.streaming_chunk_ms")
    assert fetched_config is not None
    assert fetched_config.category == "asr"

    # Upsert update
    updated_config = await config_repo.upsert_key(
        key="asr.streaming_chunk_ms",
        value={"chunk_ms": 250, "sample_rate": 16000},
        category="asr",
    )
    assert updated_config.id == config.id
    assert updated_config.value["chunk_ms"] == 250

    asr_configs = await config_repo.list_by_category("asr")
    assert len(asr_configs) == 1


@pytest.mark.asyncio
async def test_knowledge_object_persistence_foundation(db_session: AsyncSession) -> None:
    """Test KnowledgeObject persistence foundation with version pointers and parent derivation."""
    meeting_repo = MeetingRepository(db_session)
    ko_repo = KnowledgeObjectRepository(db_session)

    meeting = await meeting_repo.create(Meeting(title="KO Meeting"))

    # Create root decision KO
    decision_v1 = await ko_repo.create(
        KnowledgeObject(
            meeting_id=meeting.id,
            object_type="decision",
            title="Adopt PostgreSQL Async Engine",
            content="Team decided to use SQLAlchemy 2.x async engine with asyncpg for persistence.",
            confidence=0.95,
            status="active",
            version=1,
            provenance={"extracted_by": "BlackboardDecisionAgent", "segment_ids": [1, 2]},
            payload={"consensus": "unanimous", "impact": "high"},
        )
    )
    assert decision_v1.id is not None
    assert decision_v1.version == 1
    assert decision_v1.status == "active"

    # Create updated revision pointing to parent
    decision_v2 = await ko_repo.create(
        KnowledgeObject(
            meeting_id=meeting.id,
            object_type="decision",
            title="Adopt PostgreSQL Async Engine with Connection Pooling",
            content="Team refined the decision to include NullPool for Alembic and queue pooling for API.",
            confidence=0.98,
            status="active",
            version=2,
            parent_id=decision_v1.id,
            provenance={"extracted_by": "BlackboardDecisionAgent", "supersedes": str(decision_v1.id)},
        )
    )

    # Mark old version as superseded
    decision_v1.status = "superseded"
    await db_session.flush()

    # Query active
    active_kos = await ko_repo.list_active(meeting.id)
    assert len(active_kos) == 1
    assert active_kos[0].id == decision_v2.id

    # Query derived objects by parent
    derived = await ko_repo.list_by_parent(decision_v1.id)
    assert len(derived) == 1
    assert derived[0].id == decision_v2.id

    # Query by meeting and object type
    all_decisions = await ko_repo.list_by_meeting(meeting.id, object_type="decision")
    assert len(all_decisions) == 2


@pytest.mark.asyncio
async def test_meeting_eager_loading_and_cascade_delete(db_session: AsyncSession) -> None:
    """Verify get_with_relations loads all children and cascade deletion removes orphans."""
    meeting_repo = MeetingRepository(db_session)
    user_repo = UserRepository(db_session)
    participant_repo = ParticipantRepository(db_session)
    audio_repo = AudioRepository(db_session)
    segment_repo = TranscriptSegmentRepository(db_session)
    transcript_repo = TranscriptRepository(db_session)
    analytics_repo = AnalyticsRepository(db_session)
    ko_repo = KnowledgeObjectRepository(db_session)

    host = await user_repo.create(User(email="host.full@example.com", full_name="Host Full"))
    meeting = await meeting_repo.create(Meeting(title="Full Tree Meeting", host_id=host.id))

    # Add children
    await participant_repo.create(
        Participant(meeting_id=meeting.id, display_name="Speaker A", speaking_duration=10.0)
    )
    await audio_repo.create(
        Audio(meeting_id=meeting.id, file_path="/storage/test.wav", format="wav")
    )
    await segment_repo.create(
        TranscriptSegment(
            meeting_id=meeting.id,
            start_time_ms=0,
            end_time_ms=1000,
            original_text="Hello",
            sequence_number=1,
        )
    )
    await transcript_repo.create(
        Transcript(meeting_id=meeting.id, version=1, full_text="Hello", word_count=1)
    )
    await analytics_repo.create(
        MeetingAnalytics(
            meeting_id=meeting.id,
            speaking_time_distribution={"Speaker A": 10.0},
            engagement_score=0.9,
        )
    )
    await ko_repo.create(
        KnowledgeObject(
            meeting_id=meeting.id,
            object_type="action_item",
            content="Deploy schema to PostgreSQL",
        )
    )

    # Test get_with_relations
    loaded_meeting = await meeting_repo.get_with_relations(meeting.id)
    assert loaded_meeting is not None
    assert loaded_meeting.host is not None
    assert loaded_meeting.host.email == "host.full@example.com"
    assert len(loaded_meeting.participants) == 1
    assert len(loaded_meeting.audio_recordings) == 1
    assert len(loaded_meeting.transcript_segments) == 1
    assert len(loaded_meeting.transcripts) == 1
    assert loaded_meeting.analytics is not None
    assert len(loaded_meeting.knowledge_objects) == 1

    # Test cascade delete
    await meeting_repo.delete(meeting.id)

    # Check children deleted
    assert len(await participant_repo.list_by_meeting(meeting.id)) == 0
    assert len(await audio_repo.list_by_meeting(meeting.id)) == 0
    assert len(await segment_repo.list_by_meeting(meeting.id)) == 0
    assert len(await transcript_repo.list_by_meeting(meeting.id)) == 0
    assert await analytics_repo.get_by_meeting_id(meeting.id) is None
    assert len(await ko_repo.list_by_meeting(meeting.id)) == 0

    # User should NOT be deleted (ondelete SET NULL)
    reloaded_user = await user_repo.get_by_id(host.id)
    assert reloaded_user is not None
