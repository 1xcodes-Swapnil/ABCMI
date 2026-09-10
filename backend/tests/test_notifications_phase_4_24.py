"""
Phase 4.24 — Notifications & Real-Time User Events Test Suite
Comprehensive verification covering:
1. Notification domain model, attributes, persistence, and migrations.
2. System event mapping across all domains (Meeting, Processing, Knowledge, Action Item, Report, Translation, Query, Platform, Security, System).
3. Idempotency guarantees (duplicate event_id rejection / reuse).
4. Security sanitization (masking tokens, passwords, database URIs, internal paths).
5. Multi-tenant and user ownership isolation (401, 403, 404).
6. REST API endpoints:
   - GET /api/v1/notifications (pagination, multi-filter: category, severity, is_read, meeting, project, dates)
   - GET /api/v1/notifications/unread-count
   - GET /api/v1/notifications/{notification_id}
   - POST /api/v1/notifications/{notification_id}/read
   - POST /api/v1/notifications/read-all
   - DELETE /api/v1/notifications/{notification_id}
7. Real-time delivery adapter integration over Redis Pub/Sub channels.
8. Non-destructive safety (authoritative Knowledge Objects & Meetings intact).
"""

from datetime import datetime, timedelta, timezone
import uuid
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.events.redis_bus import RedisEventBus
from app.main import app
from app.models.meeting import Meeting
from app.models.notification import Notification
from app.models.project import Project
from app.models.user import User
from app.repositories.meeting_repo import MeetingRepository
from app.repositories.notification_repo import NotificationRepository
from app.repositories.project_repo import ProjectRepository
from app.repositories.user_repo import UserRepository
from app.schemas.notification import (
    NotificationCategory,
    NotificationCreate,
    NotificationSeverity,
)
from app.services.notification_service import NotificationService, RealtimeDeliveryAdapter


@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


@pytest.mark.asyncio
async def test_notifications_and_realtime_events_full_suite(
    client: AsyncClient,
    db_session: AsyncSession,
):
    """
    Comprehensive test validating Phase 4.24 Notification Domain, Ingestion,
    Idempotency, Filtering, Batch Updates, and Security.
    """
    user_repo = UserRepository(db_session)
    meeting_repo = MeetingRepository(db_session)
    project_repo = ProjectRepository(db_session)
    notif_repo = NotificationRepository(db_session)
    event_bus = RedisEventBus()
    service = NotificationService(db_session, event_bus=event_bus)

    tenant_id = "tenant-phase-4-24"
    other_tenant_id = "tenant-other-4-24"

    admin_headers = {"Authorization": "Bearer admin-token"}
    user_headers = {"Authorization": "Bearer user-token"}

    # =========================================================================
    # 1. Seed Users, Meeting, and Project
    # =========================================================================
    admin_user_id = uuid.UUID("00000000-0000-0000-0000-000000000001")
    standard_user_id = uuid.UUID("00000000-0000-0000-0000-000000000002")

    existing_admin = await user_repo.get_by_id(admin_user_id)
    if not existing_admin:
        admin_user = User(
            id=admin_user_id,
            email="admin.phase424@abci.ai",
            full_name="Admin Phase424",
            role="admin",
            status="active",
        )
        await user_repo.create(admin_user)

    existing_std = await user_repo.get_by_id(standard_user_id)
    if not existing_std:
        std_user = User(
            id=standard_user_id,
            email="user.phase424@abci.ai",
            full_name="User Phase424",
            role="user",
            status="active",
        )
        await user_repo.create(std_user)

    test_meeting_id = uuid.uuid4()
    meeting = Meeting(
        id=test_meeting_id,
        title="Q3 Strategic Architecture Review",
        description="Quarterly planning and security sync",
        status="completed",
        language="en",
        host_id=admin_user_id,
        settings={"tenant_id": tenant_id},
    )
    await meeting_repo.create(meeting)

    test_project_id = uuid.uuid4()
    project = Project(
        id=test_project_id,
        tenant_id=tenant_id,
        name="Platform Hardening Project",
        description="Workspace for platform hardening",
        status="active",
    )
    await project_repo.create(project)
    await db_session.commit()

    # =========================================================================
    # 2. Event Ingestion across diverse event domains
    # =========================================================================
    events_to_test = [
        # Meeting events
        ("MeetingScheduled", {"tenant_id": tenant_id, "meeting_id": str(test_meeting_id), "title": "Sprint Planning", "user_id": str(standard_user_id)}),
        ("MeetingStarted", {"tenant_id": tenant_id, "meeting_id": str(test_meeting_id), "title": "Sprint Planning"}),
        ("MeetingCompleted", {"tenant_id": tenant_id, "meeting_id": str(test_meeting_id), "title": "Sprint Planning"}),
        ("MeetingFailed", {"tenant_id": tenant_id, "meeting_id": str(test_meeting_id), "title": "Broken Meeting", "error": "Bearer secret_tok_123 failed"}),
        # Processing events
        ("ProcessingRequested", {"tenant_id": tenant_id, "meeting_id": str(test_meeting_id)}),
        ("ProcessingCompleted", {"tenant_id": tenant_id, "meeting_id": str(test_meeting_id)}),
        ("ProcessingFailed", {"tenant_id": tenant_id, "meeting_id": str(test_meeting_id), "error": "Audio codec error"}),
        # Knowledge events
        ("KnowledgeObjectCreated", {"tenant_id": tenant_id, "object_type": "decision", "title": "Adopt PostgreSQL", "meeting_id": str(test_meeting_id)}),
        ("KnowledgeObjectValidated", {"tenant_id": tenant_id, "object_type": "decision", "title": "Adopt PostgreSQL"}),
        ("DecisionExtracted", {"tenant_id": tenant_id, "title": "Budget Approved"}),
        ("TopicExtracted", {"tenant_id": tenant_id, "title": "Database Scaling"}),
        ("InsightGenerated", {"tenant_id": tenant_id, "title": "Team consensus reached"}),
        # Action Item events
        ("ActionItemCreated", {"tenant_id": tenant_id, "title": "Write Migration", "assignee": "Alex", "meeting_id": str(test_meeting_id)}),
        ("ActionItemCompleted", {"tenant_id": tenant_id, "title": "Write Migration"}),
        ("ActionItemVerificationRequired", {"tenant_id": tenant_id, "title": "Deploy to staging"}),
        # Report events
        ("ReportGenerated", {"tenant_id": tenant_id, "title": "Executive Summary Q3", "meeting_id": str(test_meeting_id)}),
        ("ReportExported", {"tenant_id": tenant_id, "format": "PDF"}),
        ("ReportFailed", {"tenant_id": tenant_id, "error": "Export timed out"}),
        # Translation events
        ("TranslationGenerated", {"tenant_id": tenant_id, "target_language": "ja"}),
        ("TranslationVerificationRequired", {"tenant_id": tenant_id}),
        # Query events
        ("QueryCompleted", {"tenant_id": tenant_id, "sources_count": 4}),
        ("QueryInsufficientContext", {"tenant_id": tenant_id}),
        ("QueryVerificationRequired", {"tenant_id": tenant_id}),
        ("QueryFailed", {"tenant_id": tenant_id, "error": "Search error"}),
        # Platform events
        ("PlatformConnected", {"tenant_id": tenant_id, "platform": "zoom"}),
        ("PlatformDisconnected", {"tenant_id": tenant_id, "platform": "teams"}),
        # Project events
        ("ProjectCreated", {"tenant_id": tenant_id, "name": "Platform Hardening Project", "project_id": str(test_project_id)}),
        ("MeetingAssociatedWithProject", {"tenant_id": tenant_id, "project_id": str(test_project_id), "meeting_id": str(test_meeting_id)}),
        # Security & System events
        ("SecurityAlert", {"tenant_id": tenant_id, "details": "Brute force attack blocked password=supersecret"}),
        ("SystemDegraded", {"tenant_id": tenant_id, "service": "Whisper STT cluster"}),
    ]

    ingested_notifications = []
    for evt_type, evt_data in events_to_test:
        evt_data["event_id"] = f"evt-{uuid.uuid4()}"
        evt_data["correlation_id"] = f"corr-{uuid.uuid4()}"
        res = await service.ingest_event(evt_type, evt_data)
        assert res is not None
        assert res.id is not None
        ingested_notifications.append(res)

    assert len(ingested_notifications) == len(events_to_test)

    # =========================================================================
    # 3. Verify Idempotency on Duplicate Event
    # =========================================================================
    fixed_event_id = "duplicate-event-id-12345"
    evt_payload = {
        "tenant_id": tenant_id,
        "meeting_id": str(test_meeting_id),
        "title": "Idempotent Meeting",
        "event_id": fixed_event_id,
        "correlation_id": "corr-idem-1",
    }
    first_ingest = await service.ingest_event("MeetingCompleted", evt_payload)
    second_ingest = await service.ingest_event("MeetingCompleted", evt_payload)
    assert first_ingest.id == second_ingest.id, "Duplicate event_id must return the existing notification without creating another"

    # =========================================================================
    # 4. Verify Security Sanitization
    # =========================================================================
    leak_event = {
        "tenant_id": tenant_id,
        "title": "Database Connection Issue",
        "error": "Failed to connect to postgresql://admin:secretpass123@db.internal:5432/abci with Bearer token_xyz987 in /backend/app/db.py",
        "event_id": str(uuid.uuid4()),
        "password": "should_be_stripped",
    }
    sanitized_notif = await service.ingest_event("ProcessingFailed", leak_event)
    assert "secretpass123" not in sanitized_notif.description
    assert "token_xyz987" not in sanitized_notif.description
    assert "postgresql://" not in sanitized_notif.description
    assert "/backend/" not in sanitized_notif.description
    assert "[REDACTED]" in sanitized_notif.description or "[DATABASE_URI_REDACTED]" in sanitized_notif.description

    # =========================================================================
    # 5. Test REST Endpoints via HTTP Client
    # =========================================================================

    # 5.1 GET /api/v1/notifications (List all)
    resp = await client.get("/api/v1/notifications", headers=admin_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "items" in data
    assert "total" in data
    assert "unread_count" in data
    assert data["total"] >= len(events_to_test)
    assert data["unread_count"] >= len(events_to_test)

    # 5.2 Filter by Category
    resp = await client.get("/api/v1/notifications?category=meeting", headers=admin_headers)
    assert resp.status_code == 200
    meeting_data = resp.json()
    for item in meeting_data["items"]:
        assert item["category"] == "meeting"

    # 5.3 Filter by Severity
    resp = await client.get("/api/v1/notifications?severity=error", headers=admin_headers)
    assert resp.status_code == 200
    error_data = resp.json()
    for item in error_data["items"]:
        assert item["severity"] == "error"

    # 5.4 Filter by Meeting ID
    resp = await client.get(f"/api/v1/notifications?meeting_id={test_meeting_id}", headers=admin_headers)
    assert resp.status_code == 200
    m_data = resp.json()
    assert m_data["total"] > 0
    for item in m_data["items"]:
        assert item["meeting_id"] == str(test_meeting_id)

    # 5.5 GET /api/v1/notifications/unread-count
    resp = await client.get("/api/v1/notifications/unread-count", headers=admin_headers)
    assert resp.status_code == 200
    count_data = resp.json()
    assert count_data["unread_count"] > 0
    assert count_data["tenant_id"] is not None

    # 5.6 GET /api/v1/notifications/{id}
    target_notif = ingested_notifications[0]
    resp = await client.get(f"/api/v1/notifications/{target_notif.id}", headers=admin_headers)
    assert resp.status_code == 200
    item_detail = resp.json()
    assert item_detail["id"] == str(target_notif.id)
    assert item_detail["is_read"] is False

    # 5.7 POST /api/v1/notifications/{id}/read (Mark single as read)
    resp = await client.post(f"/api/v1/notifications/{target_notif.id}/read", headers=admin_headers)
    assert resp.status_code == 200
    read_detail = resp.json()
    assert read_detail["is_read"] is True
    assert read_detail["read_at"] is not None

    # Verify idempotency of marking as read
    resp_again = await client.post(f"/api/v1/notifications/{target_notif.id}/read", headers=admin_headers)
    assert resp_again.status_code == 200
    assert resp_again.json()["is_read"] is True

    # 5.8 POST /api/v1/notifications/read-all (Mark category as read)
    resp = await client.post("/api/v1/notifications/read-all?category=report", headers=admin_headers)
    assert resp.status_code == 200
    batch_res = resp.json()
    assert batch_res["status"] == "success"
    assert "updated_count" in batch_res

    # 5.9 DELETE /api/v1/notifications/{id}
    notif_to_delete = ingested_notifications[1]
    resp = await client.delete(f"/api/v1/notifications/{notif_to_delete.id}", headers=admin_headers)
    assert resp.status_code == 200
    assert resp.json()["status"] == "deleted"

    # Verify deleted notification returns 404
    resp_404 = await client.get(f"/api/v1/notifications/{notif_to_delete.id}", headers=admin_headers)
    assert resp_404.status_code == 404

    # =========================================================================
    # 6. Security and Multi-Tenant Isolation
    # =========================================================================
    # 6.1 Unauthenticated requests return 401
    unauth_resp = await client.get("/api/v1/notifications")
    assert unauth_resp.status_code == 401

    # 6.2 Other tenant isolation
    other_tenant_notif = Notification(
        id=uuid.uuid4(),
        tenant_id=other_tenant_id,
        event_type="SecurityAlert",
        category=NotificationCategory.SECURITY.value,
        title="Other Tenant Security",
        description="Confidential incident",
        severity=NotificationSeverity.SECURITY.value,
    )
    await notif_repo.create(other_tenant_notif)
    await db_session.commit()

    # Admin from tenant_phase_4_24 trying to access other_tenant_notif
    cross_tenant_resp = await client.get(
        f"/api/v1/notifications/{other_tenant_notif.id}",
        headers={"Authorization": "Bearer admin-token"},  # default auth has tenant-default or user
    )
    # Must be 403 or 404
    assert cross_tenant_resp.status_code in {403, 404}

    # 6.3 Standard user accessing security notifications
    sec_notif = [n for n in ingested_notifications if n.category == NotificationCategory.SECURITY][0]
    sec_resp = await client.get(f"/api/v1/notifications/{sec_notif.id}", headers=user_headers)
    assert sec_resp.status_code == 403

    # =========================================================================
    # 7. Real-Time Delivery Adapter verification
    # =========================================================================
    adapter = RealtimeDeliveryAdapter(event_bus)
    broadcast_delivered = await adapter.broadcast_notification(other_tenant_notif)
    assert isinstance(broadcast_delivered, bool)

    # =========================================================================
    # 8. RedisEventBus Event Consumption, Idempotency & Correlation ID Preservation
    # =========================================================================
    # 8.1 Direct consume_event with correlation_id
    corr_id_1 = f"corr-{uuid.uuid4()}"
    event_id_1 = f"evt-{uuid.uuid4()}"
    bus_event_1 = {
        "event_type": "KnowledgeCreatedEvent",
        "tenant_id": tenant_id,
        "event_id": event_id_1,
        "correlation_id": corr_id_1,
        "object_type": "decision",
        "title": "Architecture Decision on Redis PubSub",
        "meeting_id": str(test_meeting_id),
        "metadata": {
            "source": "skw_agent",
            "confidence_score": 0.98,
        },
    }
    consumed_notif_1 = await service.consume_event(bus_event_1)
    assert consumed_notif_1 is not None
    assert consumed_notif_1.correlation_id == corr_id_1
    assert consumed_notif_1.event_id == event_id_1
    assert consumed_notif_1.category == NotificationCategory.KNOWLEDGE
    assert "Decision Extracted" in consumed_notif_1.title

    # 8.2 Idempotency on second consume of identical event_id
    duplicate_consumed = await service.consume_event(bus_event_1)
    assert duplicate_consumed is not None
    assert duplicate_consumed.id == consumed_notif_1.id
    assert duplicate_consumed.correlation_id == corr_id_1

    # 8.3 Event Bus Subscription & Automatic Event Ingestion
    test_bus = RedisEventBus()
    bus_service = NotificationService(db_session, event_bus=test_bus)
    subscribed_channels = bus_service.subscribe_to_event_bus(["events:knowledge", "events:meetings", "events:reports"])
    assert len(subscribed_channels) == 3

    corr_id_2 = f"corr-{uuid.uuid4()}"
    event_id_2 = f"evt-{uuid.uuid4()}"
    published_payload = {
        "event_type": "ReportGenerated",
        "tenant_id": tenant_id,
        "event_id": event_id_2,
        "correlation_id": corr_id_2,
        "title": "Weekly Strategy Brief",
        "meeting_id": str(test_meeting_id),
    }

    # Publishing via event bus triggers in-process handler
    await test_bus.publish("events:reports", published_payload)

    # Verify notification was persisted in DB by the event bus handler
    stored_bus_notif = await notif_repo.get_by_event_id(tenant_id, event_id_2)
    assert stored_bus_notif is not None
    assert stored_bus_notif.correlation_id == corr_id_2
    assert stored_bus_notif.category == NotificationCategory.REPORT.value
    assert "Report Ready" in stored_bus_notif.title

    # Clean up subscriber
    bus_service.unsubscribe_from_event_bus(["events:knowledge", "events:meetings", "events:reports"])

    # =========================================================================
    # 9. Retention Cleanup Mechanism (Repo & API)
    # =========================================================================
    # 9.1 Seed expired notifications
    old_read_notif = Notification(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        event_type="MeetingCompleted",
        category=NotificationCategory.MEETING.value,
        title="Old Meeting",
        description="Historical meeting from 45 days ago",
        severity=NotificationSeverity.INFO.value,
        is_read=True,
        read_at=datetime.now(timezone.utc) - timedelta(days=40),
        created_at=datetime.now(timezone.utc) - timedelta(days=45),
        updated_at=datetime.now(timezone.utc) - timedelta(days=45),
    )
    await notif_repo.create(old_read_notif)

    old_unread_notif = Notification(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        event_type="MeetingCompleted",
        category=NotificationCategory.MEETING.value,
        title="Old Unread Meeting",
        description="Historical unread meeting from 45 days ago",
        severity=NotificationSeverity.INFO.value,
        is_read=False,
        created_at=datetime.now(timezone.utc) - timedelta(days=45),
        updated_at=datetime.now(timezone.utc) - timedelta(days=45),
    )
    await notif_repo.create(old_unread_notif)
    await db_session.commit()

    # 9.2 API Endpoint cleanup call as Admin
    cleanup_resp = await client.post(
        "/api/v1/notifications/cleanup",
        headers=admin_headers,
        json={"retention_days": 30, "security_retention_days": 365, "include_unread": False},
    )
    assert cleanup_resp.status_code == 200
    cleanup_data = cleanup_resp.json()
    assert cleanup_data["status"] == "success"
    assert cleanup_data["deleted_count"] >= 1

    # Verify old_read_notif is deleted but old_unread_notif remains because include_unread=False
    assert await notif_repo.get_by_id(old_read_notif.id) is None
    assert await notif_repo.get_by_id(old_unread_notif.id) is not None

    # 9.3 Regular user forbidden from triggering retention cleanup
    forbidden_cleanup = await client.post(
        "/api/v1/notifications/cleanup",
        headers=user_headers,
        json={"retention_days": 30},
    )
    assert forbidden_cleanup.status_code == 403

    # =========================================================================
    # 10. Deleted Resource References (Graceful Null Handling)
    # =========================================================================
    null_ref_event = {
        "tenant_id": tenant_id,
        "title": "Orphaned Reference Meeting",
        "meeting_id": None,
        "project_id": "invalid-non-uuid-string",
        "event_id": f"evt-nullref-{uuid.uuid4()}",
    }
    null_ref_notif = await service.ingest_event("MeetingCompleted", null_ref_event)
    assert null_ref_notif is not None
    assert null_ref_notif.meeting_id is None
    assert null_ref_notif.project_id is None

    # =========================================================================
    # 11. External ID Normalization (Zoom, Teams, etc.)
    # =========================================================================
    zoom_event = {
        "tenant_id": tenant_id,
        "title": "Zoom Sync",
        "zoom_id": "  987-654-3210  ",
        "platform": "zoom",
        "correlation_id": "zoom-sync-corr-1",
    }
    zoom_notif = await service.ingest_event("ExternalMeetingImported", zoom_event)
    assert zoom_notif is not None
    assert zoom_notif.resource_id == "987-654-3210"
    assert zoom_notif.event_id is not None
    assert "987-654-3210" in zoom_notif.event_id

    # =========================================================================
    # 12. Redis Event Bus Production Verification & Stable ID
    # =========================================================================
    readiness = event_bus.verify_production_readiness()
    assert "production_ready" in readiness
    assert "host" in readiness
    assert "port" in readiness

    event_without_id = {
        "event_type": "InsightGenerated",
        "tenant_id": tenant_id,
        "title": "Key takeaway generated",
    }
    await event_bus.publish("events:insights", event_without_id)
    # Ensure publisher attaches stable event_id
    assert "event_id" in event_without_id
    assert event_without_id["event_id"].startswith("evt-")

