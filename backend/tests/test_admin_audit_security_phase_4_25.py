"""
Unit & Integration Test Suite for Phase 4.25: Admin, Audit & Security APIs
Tests:
- Admin user listing, detail query, status filtering, pagination, and RBAC
- Application roles listing and permission capability verification
- Sanitized system operational and infrastructure status aggregation
- Immutable audit log ingestion, stable event_id idempotency, and correlation preservation
- Multi-tenant isolation and 403 cross-tenant access enforcement
- Security event stream querying, access denial audit history, and security summary aggregation
- Strict recursive credential, token, path, SQL, and database URI sanitization
- Error handling (401 unauthorized, 403 forbidden, 404 not found)
"""

from datetime import datetime, timedelta, timezone
import uuid
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.api.dependencies import verify_authentication
from app.core.config import get_settings
from app.events.redis_bus import RedisEventBus
from app.infrastructure.database import Base, get_async_db
from app.main import app
from app.models.audit_log import AuditLog
from app.models.user import User
from app.schemas.admin_audit import AuditLogCreate
from app.services.admin_service import AdminService
from app.services.audit_service import AuditService

# Test Database Engine (SQLite Async in-memory for testing)
TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


@pytest.fixture
async def db_session():
    """Creates isolated in-memory test database session."""
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)
    async_session = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with async_session() as session:
        # Seed test users
        admin_user = User(
            id=uuid.UUID("00000000-0000-0000-0000-000000000001"),
            email="admin@abci-mi.local",
            full_name="System Administrator",
            role="admin",
            status="active",
        )
        standard_user = User(
            id=uuid.UUID("00000000-0000-0000-0000-000000000002"),
            email="member@abci-mi.local",
            full_name="Workspace Member",
            role="member",
            status="active",
        )
        session.add(admin_user)
        session.add(standard_user)
        await session.commit()

        yield session

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest.fixture
def test_event_bus():
    """Returns an isolated test event bus running in local mode."""
    return RedisEventBus()


@pytest.fixture
async def async_client(db_session):
    """Provides test ASGI HTTP client overriding the database dependency."""
    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_async_db] = override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
    app.dependency_overrides.clear()


# =============================================================================
# 1. Admin API Tests
# =============================================================================

@pytest.mark.asyncio
async def test_admin_list_users(async_client: AsyncClient):
    """Test GET /api/v1/admin/users with admin credentials."""
    response = await async_client.get(
        "/api/v1/admin/users",
        headers={"Authorization": "Bearer admin-token"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["total"] >= 2
    assert len(data["items"]) >= 2
    assert any(u["email"] == "admin@abci-mi.local" for u in data["items"])


@pytest.mark.asyncio
async def test_admin_list_users_rbac_forbidden(async_client: AsyncClient):
    """Test GET /api/v1/admin/users forbidden for regular member."""
    response = await async_client.get(
        "/api/v1/admin/users",
        headers={"Authorization": "Bearer member-token"},
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_admin_get_user_by_id(async_client: AsyncClient):
    """Test GET /api/v1/admin/users/{user_id}."""
    response = await async_client.get(
        "/api/v1/admin/users/00000000-0000-0000-0000-000000000001",
        headers={"Authorization": "Bearer admin-token"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == "00000000-0000-0000-0000-000000000001"
    assert data["email"] == "admin@abci-mi.local"
    assert data["role"] == "admin"


@pytest.mark.asyncio
async def test_admin_get_user_not_found(async_client: AsyncClient):
    """Test GET /api/v1/admin/users/{user_id} returns 404 for nonexistent user."""
    response = await async_client.get(
        f"/api/v1/admin/users/{uuid.uuid4()}",
        headers={"Authorization": "Bearer admin-token"},
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_admin_list_roles(async_client: AsyncClient):
    """Test GET /api/v1/admin/roles returns application RBAC matrix."""
    response = await async_client.get(
        "/api/v1/admin/roles",
        headers={"Authorization": "Bearer admin-token"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["total"] >= 5
    role_names = [r["role"] for r in data["roles"]]
    assert "admin" in role_names
    assert "security_officer" in role_names
    assert "security_auditor" in role_names
    assert "host" in role_names
    assert "member" in role_names


@pytest.mark.asyncio
async def test_admin_system_status(async_client: AsyncClient):
    """Test GET /api/v1/admin/system/status aggregates health and event bus info."""
    response = await async_client.get(
        "/api/v1/admin/system/status",
        headers={"Authorization": "Bearer admin-token"},
    )
    assert response.status_code == 200
    data = response.json()
    assert "status" in data
    assert "database" in data
    assert "redis" in data
    assert "qdrant" in data
    assert "storage" in data
    assert "event_bus" in data
    # Ensure credentials or internal URLs are NOT in payload
    assert "password" not in str(data).lower()
    assert "postgresql://" not in str(data)
    assert "redis://" not in str(data)


# =============================================================================
# 2. Immutable Audit & Ingestion Tests
# =============================================================================

@pytest.mark.asyncio
async def test_audit_log_ingest_and_idempotency(db_session: AsyncSession, test_event_bus: RedisEventBus):
    """Test AuditService log_event and stable event_id idempotency."""
    service = AuditService(db_session, test_event_bus)

    event_id = f"evt-{uuid.uuid4()}"
    correlation_id = f"corr-{uuid.uuid4()}"

    payload = AuditLogCreate(
        tenant_id="tenant-alpha",
        user_id=uuid.UUID("00000000-0000-0000-0000-000000000001"),
        event_type="auth.login.success",
        category="auth",
        severity="info",
        action="user_login",
        outcome="success",
        resource_type="user",
        resource_id="00000000-0000-0000-0000-000000000001",
        correlation_id=correlation_id,
        event_id=event_id,
        details={"ip": "127.0.0.1", "auth_method": "password", "token": "secret-jwt-123"},
    )

    # First ingestion
    audit1 = await service.log_event(payload)
    assert audit1.id is not None
    assert audit1.event_id == event_id
    assert audit1.correlation_id == correlation_id
    assert audit1.details["token"] == "[REDACTED]"

    # Duplicate ingestion (idempotent replay)
    audit2 = await service.log_event(payload)
    assert audit2.id == audit1.id


@pytest.mark.asyncio
async def test_audit_ingest_event_from_bus(db_session: AsyncSession, test_event_bus: RedisEventBus):
    """Test AuditService ingest_event from Redis event payload with external platform ID."""
    service = AuditService(db_session, test_event_bus)

    event_data = {
        "tenant_id": "tenant-alpha",
        "actor_id": "00000000-0000-0000-0000-000000000001",
        "action": "meeting.recording.uploaded",
        "zoom_id": "zoom-meeting-998877",
        "correlation_id": "corr-zoom-100",
        "metadata": {
            "file_size": 1048576,
            "api_key": "raw-api-key-value",
            "db_url": "postgresql://user:pass@localhost:5432/db",
        },
    }

    audit = await service.ingest_event("meeting.recording.uploaded", event_data)
    assert audit is not None
    assert audit.resource_id == "zoom-meeting-998877"
    assert audit.correlation_id == "corr-zoom-100"
    # Verify sanitization
    assert audit.metadata["api_key"] == "[REDACTED]"
    assert audit.metadata["db_url"] == "[REDACTED]"


@pytest.mark.asyncio
async def test_audit_query_and_tenant_isolation(async_client: AsyncClient, db_session: AsyncSession):
    """Test GET /api/v1/admin/audit with tenant isolation and 403 cross-tenant."""
    service = AuditService(db_session)

    # Create audit records in two separate tenants
    audit_alpha = await service.log_event(
        AuditLogCreate(
            tenant_id="tenant-alpha",
            event_type="document.viewed",
            action="view",
            resource_type="document",
            resource_id="doc-123",
        )
    )
    audit_beta = await service.log_event(
        AuditLogCreate(
            tenant_id="tenant-beta",
            event_type="document.viewed",
            action="view",
            resource_type="document",
            resource_id="doc-456",
        )
    )

    # Query tenant-alpha audit logs
    resp_alpha = await async_client.get(
        "/api/v1/admin/audit",
        headers={"Authorization": "Bearer admin-token", "X-Tenant-Id": "tenant-alpha"},
    )
    assert resp_alpha.status_code == 200
    items_alpha = resp_alpha.json()["items"]
    assert any(i["id"] == str(audit_alpha.id) for i in items_alpha)
    assert not any(i["id"] == str(audit_beta.id) for i in items_alpha)

    # Direct fetch by ID cross-tenant must fail with 403
    resp_cross = await async_client.get(
        f"/api/v1/admin/audit/{audit_beta.id}",
        headers={"Authorization": "Bearer admin-token", "X-Tenant-Id": "tenant-alpha"},
    )
    assert resp_cross.status_code == 403


@pytest.mark.asyncio
async def test_audit_resource_history(async_client: AsyncClient, db_session: AsyncSession):
    """Test GET /api/v1/admin/audit/resource/{resource_id}."""
    service = AuditService(db_session)

    target_res = "teams-call-100200"
    await service.log_event(
        AuditLogCreate(
            tenant_id="tenant-gamma",
            event_type="meeting.started",
            action="start",
            resource_type="meeting",
            resource_id=target_res,
        )
    )
    await service.log_event(
        AuditLogCreate(
            tenant_id="tenant-gamma",
            event_type="meeting.ended",
            action="end",
            resource_type="meeting",
            resource_id=target_res,
        )
    )

    resp = await async_client.get(
        f"/api/v1/admin/audit/resource/{target_res}",
        headers={"Authorization": "Bearer security-officer-token", "X-Tenant-Id": "tenant-gamma"},
    )
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert len(items) == 2
    assert all(i["resource_id"] == target_res for i in items)


# =============================================================================
# 3. Security Telemetry & Access Denial Tests
# =============================================================================

@pytest.mark.asyncio
async def test_security_access_denials_and_summary(async_client: AsyncClient, db_session: AsyncSession):
    """Test GET /api/v1/admin/security/access-denials and /security/summary."""
    service = AuditService(db_session)

    tenant = "tenant-sec"
    # Seed access denial event
    await service.log_event(
        AuditLogCreate(
            tenant_id=tenant,
            user_id=uuid.UUID("00000000-0000-0000-0000-000000000002"),
            event_type="security.access_denied",
            category="security",
            severity="security",
            action="unauthorized_read",
            outcome="denied",
            resource_type="meeting",
            resource_id="meet-restricted-01",
            details={"reason": "User lacks secret project clearance"},
        )
    )

    # Seed auth failure event
    await service.log_event(
        AuditLogCreate(
            tenant_id=tenant,
            user_id=None,
            event_type="auth.login.failed",
            category="auth",
            severity="warning",
            action="login_attempt",
            outcome="failure",
            resource_type="auth",
            resource_id="unknown_user",
            details={"reason": "Invalid password supplied"},
        )
    )

    # 1. Query access denials
    resp_denials = await async_client.get(
        "/api/v1/admin/security/access-denials",
        headers={"Authorization": "Bearer security-auditor-token", "X-Tenant-Id": tenant},
    )
    assert resp_denials.status_code == 200
    denials = resp_denials.json()["items"]
    assert len(denials) >= 1
    assert denials[0]["resource_id"] == "meet-restricted-01"
    assert "User lacks secret project clearance" in denials[0]["reason"]

    # 2. Query security summary
    resp_summary = await async_client.get(
        "/api/v1/admin/security/summary?days=7",
        headers={"Authorization": "Bearer security-officer-token", "X-Tenant-Id": tenant},
    )
    assert resp_summary.status_code == 200
    summary = resp_summary.json()
    assert summary["tenant_id"] == tenant
    assert summary["access_denials"] >= 1
    assert summary["authentication_failures"] >= 1
    assert summary["security_alerts"] >= 1


# =============================================================================
# 4. Strict Sanitization & Secret Redaction Tests
# =============================================================================

@pytest.mark.asyncio
async def test_audit_sanitization_masks_all_secret_vectors(db_session: AsyncSession):
    """Verifies that tokens, passwords, database URIs, filesystem paths, SQL, and private keys are scrubbed."""
    service = AuditService(db_session)

    dirty_payload = AuditLogCreate(
        tenant_id="tenant-clean",
        event_type="system.internal.error",
        action="execute_query",
        outcome="error",
        details={
            "authorization": "Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.doNotLeakThisToken",
            "connection_string": "postgresql://postgres:MySuperSecretPassword@prod-db.internal:5432/abci_mi",
            "stack_trace": "Traceback (most recent call last):\n  File '/backend/app/secret.py', line 10\nException: Bad Error",
            "raw_query": "SELECT * FROM users WHERE password_hash = 'secret';",
            "nested": {
                "api_key": "sk-1234567890abcdef",
                "nested_path": "/var/secrets/private_key.pem",
                "redis_url": "redis://:masterauth@redis-cluster:6379/0",
            },
        },
        metadata={
            "priv_key": "-----BEGIN RSA PRIVATE KEY-----\nMIIEowIBAAKCAQEA0...\n-----END RSA PRIVATE KEY-----",
        },
    )

    audit = await service.log_event(dirty_payload)

    # Verify root level keys
    assert audit.details["authorization"] == "[REDACTED]"
    assert audit.details["connection_string"] == "[REDACTED]"
    assert audit.details["nested"]["api_key"] == "[REDACTED]"
    assert audit.details["nested"]["redis_url"] == "[REDACTED]"
    assert audit.metadata["priv_key"] == "[REDACTED]"

    # Verify string pattern scrubbing in non-secret keys
    sanitized_stack = service._sanitize_text(dirty_payload.details["stack_trace"])
    assert "[SERVER_PATH]" in sanitized_stack
    assert "[EXCEPTION_STACK_TRACE_REDACTED]" in sanitized_stack or "Traceback" not in sanitized_stack

    sanitized_sql = service._sanitize_text(dirty_payload.details["raw_query"])
    assert "[SQL_STATEMENT_REDACTED]" in sanitized_sql


# =============================================================================
# 5. Error & Failure Handling Tests
# =============================================================================

@pytest.mark.asyncio
async def test_audit_unauthenticated_request(async_client: AsyncClient):
    """Test 401 Unauthorized for missing authentication."""
    resp = await async_client.get("/api/v1/admin/audit")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_audit_forbidden_for_regular_member(async_client: AsyncClient):
    """Test 403 Forbidden for member without security/admin role."""
    resp = await async_client.get(
        "/api/v1/admin/audit",
        headers={"Authorization": "Bearer member-token"},
    )
    assert resp.status_code == 403
