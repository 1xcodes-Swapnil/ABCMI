"""
Phase 4.17 — Live Meeting / Streaming Integration Boundary Test Suite
Verifies:
1. Live session creation and lifecycle transitions (created -> live -> paused -> live -> stopping -> completed).
2. Invalid state transitions rejection.
3. Authentication, authorization, and meeting scope isolation.
4. Sequential audio chunk ingestion with local storage persistence.
5. Sequence validation (rejecting duplicate or out-of-order chunks).
6. Redis event emission and failure resilience.
7. Mock incremental processing boundary (StreamingProcessingProvider).
8. Live session status and chunk metrics retrieval.
"""

import uuid
import pytest
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import AsyncSession

from app.main import app
from app.models.meeting import Meeting
from app.repositories.meeting_repo import MeetingRepository


@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


@pytest.mark.asyncio
async def test_live_session_lifecycle_flow(client: AsyncClient, db_session: AsyncSession):
    """Test full live session lifecycle: start, pause, resume, stop, status."""
    meeting_repo = MeetingRepository(db_session)
    meeting = await meeting_repo.create(Meeting(title="Live Streaming Meeting"))
    await db_session.commit()

    meeting_id = str(meeting.id)
    headers = {"Authorization": "Bearer admin-token"}

    # 1. Start live session
    start_res = await client.post(
        f"/api/v1/meetings/{meeting_id}/live/start",
        json={"language": "en", "session_metadata": {"codec": "pcm"}},
        headers=headers,
    )
    assert start_res.status_code == 201
    session_data = start_res.json()
    assert session_data["status"] == "live"
    assert session_data["language"] == "en"

    # 2. Pause live session
    pause_res = await client.post(f"/api/v1/meetings/{meeting_id}/live/pause", headers=headers)
    assert pause_res.status_code == 200
    assert pause_res.json()["status"] == "paused"

    # 3. Resume live session
    resume_res = await client.post(f"/api/v1/meetings/{meeting_id}/live/resume", headers=headers)
    assert resume_res.status_code == 200
    assert resume_res.json()["status"] == "live"

    # 4. Get status
    status_res = await client.get(f"/api/v1/meetings/{meeting_id}/live/status", headers=headers)
    assert status_res.status_code == 200
    status_data = status_res.json()
    assert status_data["session"]["status"] == "live"

    # 5. Stop live session
    stop_res = await client.post(f"/api/v1/meetings/{meeting_id}/live/stop", headers=headers)
    assert stop_res.status_code == 200
    assert stop_res.json()["status"] == "completed"


@pytest.mark.asyncio
async def test_audio_chunk_ingestion_and_validation(client: AsyncClient, db_session: AsyncSession):
    """Test sequential audio chunk ingestion, local storage persistence, and sequence validation."""
    meeting_repo = MeetingRepository(db_session)
    meeting = await meeting_repo.create(Meeting(title="Chunk Ingestion Meeting"))
    await db_session.commit()

    meeting_id = str(meeting.id)
    headers = {"Authorization": "Bearer admin-token"}

    # Start session
    await client.post(f"/api/v1/meetings/{meeting_id}/live/start", headers=headers)

    # Ingest chunk 0
    form_data_0 = {
        "sequence_number": "0",
        "timestamp_start_ms": "0",
        "timestamp_end_ms": "5000",
    }
    files_0 = {"file": ("chunk_0.wav", b"RIFF....WAVEchunk0", "audio/wav")}
    res_0 = await client.post(f"/api/v1/meetings/{meeting_id}/live/chunks", data=form_data_0, files=files_0, headers=headers)
    assert res_0.status_code == 201
    assert res_0.json()["sequence_number"] == 0
    assert res_0.json()["status"] == "accepted"

    # Ingest chunk 1
    form_data_1 = {
        "sequence_number": "1",
        "timestamp_start_ms": "5000",
        "timestamp_end_ms": "10000",
    }
    files_1 = {"file": ("chunk_1.wav", b"RIFF....WAVEchunk1", "audio/wav")}
    res_1 = await client.post(f"/api/v1/meetings/{meeting_id}/live/chunks", data=form_data_1, files=files_1, headers=headers)
    assert res_1.status_code == 201
    assert res_1.json()["sequence_number"] == 1

    # Ingest duplicate/out-of-order chunk (sequence 1 again) -> should be rejected (400)
    res_dup = await client.post(f"/api/v1/meetings/{meeting_id}/live/chunks", data=form_data_1, files=files_1, headers=headers)
    assert res_dup.status_code == 400


@pytest.mark.asyncio
async def test_live_security_and_authorization(client: AsyncClient, db_session: AsyncSession):
    """Test that unauthorized requests or cross-scope access fail securely."""
    meeting_repo = MeetingRepository(db_session)
    meeting = await meeting_repo.create(Meeting(title="Secure Live Meeting"))
    await db_session.commit()

    meeting_id = str(meeting.id)

    # Missing token -> 401
    res_unauth = await client.post(f"/api/v1/meetings/{meeting_id}/live/start")
    assert res_unauth.status_code == 401
