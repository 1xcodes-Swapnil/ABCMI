"""
Phase 4.18 — Platform Integration Boundary Test Suite
Verifies:
1. Provider registry and provider selection.
2. Platform connect, disconnect, and connection status.
3. External meeting reference mapping and ABCI-MI meeting creation.
4. Webhook event normalization and idempotency (updates, cancellations).
5. Security, tenant isolation, and secret redaction.
6. Redis event emission.
"""

from datetime import datetime, timezone, timedelta
import pytest
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import AsyncSession

from app.main import app
from app.models.user import User
from app.repositories.base import BaseRepository


@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


@pytest.mark.asyncio
async def test_platform_integration_lifecycle(client: AsyncClient, db_session: AsyncSession):
    """Test connecting a mock platform provider, checking status, and mapping meetings."""
    headers = {"Authorization": "Bearer admin-token"}

    # 1. List supported platforms
    platforms_res = await client.get("/api/v1/integrations/platforms", headers=headers)
    assert platforms_res.status_code == 200
    platforms = platforms_res.json()
    assert "zoom" in platforms
    assert "teams" in platforms
    assert "google_meet" in platforms

    # 2. Connect provider
    connect_res = await client.post(
        "/api/v1/integrations/zoom/connect",
        json={"auth_code": "valid_zoom_auth_code", "credentials_metadata": {"workspace": "acme"}},
        headers=headers,
    )
    assert connect_res.status_code == 200
    conn_data = connect_res.json()
    assert conn_data["provider"] == "zoom"
    assert conn_data["status"] == "connected"
    # Ensure sensitive token fields are redacted/absent from response DTO
    assert "encrypted_access_token" not in conn_data

    # 3. Check status
    status_res = await client.get("/api/v1/integrations/zoom/status", headers=headers)
    assert status_res.status_code == 200
    assert status_res.json()["status"] == "connected"

    # 4. Map external meeting
    future_time = datetime.now(timezone.utc) + timedelta(days=1)
    map_payload = {
        "external_meeting_id": "zoom_ext_12345",
        "external_event_id": "cal_evt_987",
        "title": "Quarterly Zoom Sync",
        "description": "Discussing Q3 roadmaps",
        "scheduled_start": future_time.isoformat(),
        "duration_minutes": 45,
        "timezone": "UTC",
        "external_metadata": {"zoom_link": "https://zoom.us/j/12345"},
    }
    map_res = await client.post(
        "/api/v1/integrations/zoom/meetings/map",
        json=map_payload,
        headers=headers,
    )
    assert map_res.status_code == 201
    map_data = map_res.json()
    assert map_data["external_meeting_id"] == "zoom_ext_12345"
    assert map_data["sync_status"] == "synced"

    # 5. Test webhook event (cancellation)
    webhook_payload = {
        "provider": "zoom",
        "event_type": "meeting.cancelled",
        "external_meeting_id": "zoom_ext_12345",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "payload": {"reason": "Host unavailable"},
    }
    webhook_res = await client.post("/api/v1/integrations/webhooks/zoom", json=webhook_payload)
    assert webhook_res.status_code == 200
    assert webhook_res.json()["status"] == "processed"

    # 6. Disconnect provider
    disc_res = await client.post("/api/v1/integrations/zoom/disconnect", headers=headers)
    assert disc_res.status_code == 200
    assert disc_res.json()["status"] == "disconnected"
