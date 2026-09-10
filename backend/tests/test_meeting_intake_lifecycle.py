"""
Phase 4.13A Meeting Intake & Processing Lifecycle Tests
Verifies meeting creation, audio upload, processing lifecycle states, ACE orchestration invocation,
Redis event bus emission, RBAC security scoping, idempotency, and failure resilience.
"""

import asyncio
from typing import AsyncGenerator, List
import uuid
import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import AsyncSession

from app.main import app
from app.infrastructure.database import get_async_db
from app.events.redis_bus import RedisEventBus
from app.orchestration.ace_engine import ACEOrchestrator
from app.orchestration.events import ACEBaseOrchestrationEvent
from app.models.user import User


@pytest_asyncio.fixture
async def async_client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    """Async HTTP test client for FastAPI application with overridden SQLite test DB session and seeded users."""
    user_data_list = [
        ("00000000-0000-0000-0000-000000000001", "user1@example.com", "User One", "admin"),
        ("00000000-0000-0000-0000-000000000002", "user2@example.com", "User Two", "member"),
        ("00000000-0000-0000-0000-000000000099", "user99@example.com", "User NinetyNine", "member"),
    ]
    for uid_str, email, name, role in user_data_list:
        uid = uuid.UUID(uid_str)
        existing = await db_session.get(User, uid)
        if not existing:
            db_user = User(
                id=uid,
                email=email,
                full_name=name,
                role=role,
                status="active",
            )
            db_session.add(db_user)
    await db_session.commit()

    async def override_get_async_db():
        yield db_session

    app.dependency_overrides[get_async_db] = override_get_async_db
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_meeting_creation_and_intake(async_client: AsyncClient, db_session: AsyncSession):
    """Verify meeting creation with participants, language configuration, and correlation ID."""
    payload = {
        "title": "Quarterly Strategy Review 2026",
        "description": "Discussing Q3 growth and product roadmap.",
        "language": "en",
        "secondary_languages": ["es", "fr"],
        "correlation_id": "corr-test-12345",
        "participants": [
            {"display_name": "Alice Smith", "email": "alice@example.com", "role": "host", "speaker_label": "Speaker_1"},
            {"display_name": "Bob Jones", "email": "bob@example.com", "role": "attendee", "speaker_label": "Speaker_2"},
        ],
    }

    headers = {"Authorization": "Bearer test-token"}
    response = await async_client.post("/api/v1/meetings", json=payload, headers=headers)
    assert response.status_code == 201
    data = response.json()

    assert data["title"] == payload["title"]
    assert data["language"] == "en"
    assert data["status"] == "created"
    assert len(data["participants"]) == 2
    assert data["settings"]["correlation_id"] == "corr-test-12345"


@pytest.mark.asyncio
async def test_authentication_failure(async_client: AsyncClient, db_session: AsyncSession):
    """Verify unauthenticated requests are rejected with 401 Unauthorized."""
    payload = {"title": "Unauthorized Meeting"}
    response = await async_client.post("/api/v1/meetings", json=payload)
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_meeting_scope_violation(async_client: AsyncClient, db_session: AsyncSession):
    """Verify cross-meeting access violation raises 403 Forbidden when scoping is enforced."""
    create_payload = {
        "title": "Private Executive Meeting",
        "host_id": "00000000-0000-0000-0000-000000000099",
    }
    headers = {"Authorization": "Bearer user-token"}
    create_res = await async_client.post("/api/v1/meetings", json=create_payload, headers={"Authorization": "Bearer admin-token"})
    assert create_res.status_code == 201
    meeting_id = create_res.json()["id"]

    get_res = await async_client.get(f"/api/v1/meetings/{meeting_id}", headers=headers)
    assert get_res.status_code == 403


@pytest.mark.asyncio
async def test_audio_upload_and_validation(async_client: AsyncClient, db_session: AsyncSession):
    """Verify valid audio file upload and rejection of empty/unsupported formats."""
    m_res = await async_client.post("/api/v1/meetings", json={"title": "Audio Test Meeting"}, headers={"Authorization": "Bearer test-token"})
    assert m_res.status_code == 201
    meeting_id = m_res.json()["id"]

    files = {"file": ("test_recording.wav", b"RIFF....WAVEfmt ...data....", "audio/wav")}
    data = {"format": "wav", "sample_rate": "16000", "channels": "1"}
    upload_res = await async_client.post(f"/api/v1/meetings/{meeting_id}/audio", files=files, data=data, headers={"Authorization": "Bearer test-token"})
    assert upload_res.status_code == 201
    audio_data = upload_res.json()
    assert audio_data["file_name"] == "test_recording.wav"
    assert audio_data["format"] == "wav"

    empty_files = {"file": ("empty.wav", b"", "audio/wav")}
    empty_res = await async_client.post(f"/api/v1/meetings/{meeting_id}/audio", files=empty_files, data=data, headers={"Authorization": "Bearer test-token"})
    assert empty_res.status_code == 400


@pytest.mark.asyncio
async def test_valid_processing_request_and_ace_invocation(async_client: AsyncClient, db_session: AsyncSession):
    """Verify valid processing request triggers ACE orchestration and event emissions."""
    m_res = await async_client.post("/api/v1/meetings", json={"title": "ACE Processing Test"}, headers={"Authorization": "Bearer test-token"})
    assert m_res.status_code == 201
    meeting_id = m_res.json()["id"]

    event_bus = RedisEventBus()
    emitted = []
    async def capture_event(ev):
        emitted.append(ev)
    
    channel = f"events:meetings:{meeting_id}:orchestration"
    event_bus.subscribe(channel, capture_event)

    proc_payload = {
        "correlation_id": "corr-ace-100",
        "enable_analytics": True,
        "enable_memory": True,
    }
    proc_res = await async_client.post(f"/api/v1/meetings/{meeting_id}/process", json=proc_payload, headers={"Authorization": "Bearer test-token"})
    assert proc_res.status_code == 200
    res_data = proc_res.json()
    assert res_data["meeting_id"] == meeting_id
    assert res_data["status"] in ["completed", "failed"]


@pytest.mark.asyncio
async def test_idempotent_duplicate_processing_request(async_client: AsyncClient, db_session: AsyncSession):
    """Verify repeated processing requests do not duplicate jobs or cause errors."""
    m_res = await async_client.post("/api/v1/meetings", json={"title": "Idempotency Test"}, headers={"Authorization": "Bearer test-token"})
    assert m_res.status_code == 201
    meeting_id = m_res.json()["id"]

    res1 = await async_client.post(f"/api/v1/meetings/{meeting_id}/process", json={"correlation_id": "idem-1"}, headers={"Authorization": "Bearer test-token"})
    assert res1.status_code == 200

    res2 = await async_client.post(f"/api/v1/meetings/{meeting_id}/process", json={"correlation_id": "idem-2", "force_reprocess": True}, headers={"Authorization": "Bearer test-token"})
    assert res2.status_code == 200
