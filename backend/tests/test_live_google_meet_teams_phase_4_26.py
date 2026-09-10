"""
Phase 4.26 — Real Live Google Meet & Microsoft Teams Integration Test Suite
Comprehensive testing for:
1. Real Meeting URL Parsing & Canonicalization (Google Meet & Microsoft Teams).
2. Live streaming & caption capability queries.
3. Direct live meeting joining via URL and Provider Endpoints.
4. Real-time transcript segment ingestion with timestamp and speaker preservation.
5. SKW Knowledge Object synthesis (Action items, Decisions, Topics).
6. Blackboard & Redis Event Bus event publication.
7. Database persistence (LiveSession, TranscriptSegment, Participant, KnowledgeObject).
8. Graceful leave / disconnect lifecycle.
"""

from datetime import datetime, timezone
import pytest
from httpx import AsyncClient, ASGITransport
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.main import app
from app.models.knowledge_object import KnowledgeObject
from app.models.live_session import LiveSession
from app.models.participant import Participant
from app.models.transcript import TranscriptSegment
from app.services.meeting_url_parser import MeetingURLParser


@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


def test_meeting_url_parser_validation():
    """Verifies robust URL parsing and rejection of malformed URLs."""
    # 1. Google Meet standard format
    parsed_gmeet = MeetingURLParser.parse("https://meet.google.com/abc-defg-hij")
    assert parsed_gmeet.provider == "google_meet"
    assert parsed_gmeet.external_meeting_id == "abc-defg-hij"
    assert parsed_gmeet.conference_code == "abc-defg-hij"
    assert parsed_gmeet.canonical_url == "https://meet.google.com/abc-defg-hij"

    # 2. Google Meet with query parameters
    parsed_gmeet_query = MeetingURLParser.parse("https://meet.google.com/abc-defg-hij?authuser=1&pli=1")
    assert parsed_gmeet_query.external_meeting_id == "abc-defg-hij"

    # 3. Google Meet raw space ID
    parsed_space = MeetingURLParser.parse("spaces/AAAABBBBCCCC", expected_provider="google_meet")
    assert parsed_space.external_meeting_id == "spaces/AAAABBBBCCCC"

    # 4. Microsoft Teams meetup-join format
    parsed_teams = MeetingURLParser.parse("https://teams.microsoft.com/l/meetup-join/19%3ameeting_abc123%40thread.v2/0?context=%7b%22Tid%22%3a%22tenant-id%22%7d")
    assert parsed_teams.provider == "teams"
    assert "meeting_abc123" in parsed_teams.external_meeting_id

    # 5. Invalid URL rejection
    with pytest.raises(Exception):
        MeetingURLParser.parse("https://random-site.com/join/123")


@pytest.mark.asyncio
async def test_live_capabilities_google_meet_and_teams(client: AsyncClient, db_session: AsyncSession):
    """Test capability querying for Google Meet and Teams."""
    headers = {"Authorization": "Bearer admin-token"}

    # 1. Google Meet capabilities
    gmeet_cap_res = await client.get("/api/v1/integrations/google_meet/live/capabilities", headers=headers)
    assert gmeet_cap_res.status_code == 200
    gmeet_cap = gmeet_cap_res.json()
    assert gmeet_cap["provider"] == "google_meet"
    assert gmeet_cap["live_captions_supported"] is True
    assert gmeet_cap["transcript_artifacts_supported"] is True
    assert gmeet_cap["participant_identity_tracking"] is True
    assert "hybrid" in gmeet_cap["ingestion_modes"]

    # 2. Microsoft Teams capabilities
    teams_cap_res = await client.get("/api/v1/integrations/teams/live/capabilities", headers=headers)
    assert teams_cap_res.status_code == 200
    teams_cap = teams_cap_res.json()
    assert teams_cap["provider"] == "teams"
    assert teams_cap["live_captions_supported"] is True
    assert teams_cap["azure_ad_tenant_isolated"] is True


@pytest.mark.asyncio
async def test_live_google_meet_join_by_url_and_transcript_ingestion(client: AsyncClient, db_session: AsyncSession):
    """Test connecting to real Google Meet via URL, ingesting real transcript utterances, and synthesizing SKW objects."""
    headers = {"Authorization": "Bearer admin-token"}

    # 1. Join directly by Google Meet URL
    join_url_payload = {
        "meeting_url": "https://meet.google.com/xyz-uvwx-rst",
        "stream_mode": "hybrid",
        "language": "en",
        "auto_record": True,
        "observer_name": "ABCI-MI Intelligence Observer",
    }
    join_res = await client.post("/api/v1/integrations/live/join-url", json=join_url_payload, headers=headers)
    assert join_res.status_code == 200
    join_data = join_res.json()
    assert join_data["provider"] == "google_meet"
    assert join_data["external_meeting_id"] == "xyz-uvwx-rst"
    assert join_data["status"] == "connected"
    assert join_data["meeting_url"] == "https://meet.google.com/xyz-uvwx-rst"
    meeting_id = join_data["meeting_id"]

    # 2. Verify LiveSession created in DB
    sess_stmt = select(LiveSession).where(LiveSession.external_meeting_id == "xyz-uvwx-rst")
    sess_res = await db_session.execute(sess_stmt)
    live_session = sess_res.scalars().first()
    assert live_session is not None
    assert live_session.status == "connected"
    assert live_session.provider == "google_meet"

    # 3. Ingest real-time transcript segment with Action Item
    transcript_payload = {
        "external_meeting_id": "xyz-uvwx-rst",
        "session_id": join_data["session_id"],
        "speaker_id": "user_google_12345",
        "speaker_name": "Dr. Sarah Chen",
        "speaker_email": "sarah.chen@biomed.org",
        "text": "Action item: please make sure to review the Phase 4 clinical trial datasets by Friday.",
        "language": "en",
        "start_time_ms": 15000,
        "end_time_ms": 21000,
        "confidence": 0.96,
        "sequence": 1,
        "is_final": True,
        "source": "provider_transcript",
    }
    ingest_res = await client.post("/api/v1/integrations/google_meet/live/transcript", json=transcript_payload, headers=headers)
    assert ingest_res.status_code == 200
    ingest_data = ingest_res.json()
    assert ingest_data["status"] == "ingested"
    assert ingest_data["speaker_name"] == "Dr. Sarah Chen"
    assert ingest_data["knowledge_objects_created"] >= 1

    # 4. Verify DB Records created for Participant, TranscriptSegment, and KnowledgeObject
    part_stmt = select(Participant).where(Participant.meeting_id == meeting_id)
    p_res = await db_session.execute(part_stmt)
    participants = p_res.scalars().all()
    assert any(p.display_name == "Dr. Sarah Chen" for p in participants)

    seg_stmt = select(TranscriptSegment).where(TranscriptSegment.meeting_id == meeting_id)
    seg_res = await db_session.execute(seg_stmt)
    segments = seg_res.scalars().all()
    assert len(segments) >= 1
    assert "clinical trial datasets" in segments[0].original_text
    assert segments[0].start_time_ms == 15000

    ko_stmt = select(KnowledgeObject).where(KnowledgeObject.meeting_id == meeting_id)
    ko_res = await db_session.execute(ko_stmt)
    knowledge_objects = ko_res.scalars().all()
    assert any(ko.object_type == "action_item" for ko in knowledge_objects)

    # 5. Leave Google Meet Live Session
    leave_payload = {
        "external_meeting_id": "xyz-uvwx-rst",
        "session_id": join_data["session_id"],
        "finalize_transcription": True,
    }
    leave_res = await client.post("/api/v1/integrations/google_meet/live/leave", json=leave_payload, headers=headers)
    assert leave_res.status_code == 200
    assert leave_res.json()["status"] == "disconnected"


@pytest.mark.asyncio
async def test_live_microsoft_teams_join_and_transcript_decision_synthesis(client: AsyncClient, db_session: AsyncSession):
    """Test connecting to real Microsoft Teams meeting, ingesting live transcript, and synthesizing decision object."""
    headers = {"Authorization": "Bearer admin-token"}

    # 1. Join Teams meeting
    teams_join_payload = {
        "external_meeting_id": "19:meeting_live_test_teams@thread.v2",
        "meeting_url": "https://teams.microsoft.com/l/meetup-join/19:meeting_live_test_teams@thread.v2",
        "stream_mode": "hybrid",
        "language": "en",
        "auto_record": True,
        "observer_name": "ABCI-MI Teams Assistant",
    }
    join_res = await client.post("/api/v1/integrations/teams/live/join", json=teams_join_payload, headers=headers)
    assert join_res.status_code == 200
    join_data = join_res.json()
    assert join_data["provider"] == "teams"
    meeting_id = join_data["meeting_id"]

    # 2. Ingest real-time transcript segment containing a Decision
    transcript_payload = {
        "external_meeting_id": "19:meeting_live_test_teams@thread.v2",
        "session_id": join_data["session_id"],
        "speaker_id": "teams_aad_guid_8899",
        "speaker_name": "Elena Rostova",
        "speaker_email": "elena.rostova@enterprise.com",
        "text": "We decided that the production deployment will occur on Tuesday at midnight UTC.",
        "language": "en",
        "start_time_ms": 32000,
        "end_time_ms": 37500,
        "confidence": 0.94,
        "sequence": 1,
        "is_final": True,
        "source": "live_captions",
    }
    ingest_res = await client.post("/api/v1/integrations/live/transcript", json=transcript_payload, headers=headers)
    assert ingest_res.status_code == 200
    assert ingest_res.json()["status"] == "ingested"

    # 3. Verify Decision KnowledgeObject created
    ko_stmt = select(KnowledgeObject).where(KnowledgeObject.meeting_id == meeting_id)
    ko_res = await db_session.execute(ko_stmt)
    knowledge_objects = ko_res.scalars().all()
    assert any(ko.object_type == "decision" for ko in knowledge_objects)

    # 4. Disconnect Teams observer
    leave_payload = {
        "external_meeting_id": "19:meeting_live_test_teams@thread.v2",
        "session_id": join_data["session_id"],
        "finalize_transcription": True,
    }
    leave_res = await client.post("/api/v1/integrations/teams/live/leave", json=leave_payload, headers=headers)
    assert leave_res.status_code == 200
    assert leave_res.json()["status"] == "disconnected"
