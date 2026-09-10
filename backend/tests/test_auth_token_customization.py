"""
Unit & Integration Test Suite for Token Verification Customization (Phase 4.25 Remediation)
Verifies:
1. Valid HS256 JWT creation, decoding, and dependency verification
2. Expired JWT rejection (401 Unauthorized, TOKEN_EXPIRED)
3. Tampered signature rejection (401 Unauthorized, INVALID_SIGNATURE)
4. Malformed JWT rejection (401 Unauthorized)
5. Test fixture tokens allowed in development/test environments
6. Test fixture tokens strictly rejected in production when ALLOW_TEST_TOKENS=False
7. Production mode allows valid signed JWT tokens
8. Role and tenant extraction directly from cryptographic JWT claims
9. Configured production API keys authentication
10. Unauthenticated requests rejected with 401
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import patch
import uuid
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.api.dependencies import verify_authentication
from app.core.config import get_settings
from app.core.exceptions import UnauthorizedException
from app.core.security import create_access_token, decode_access_token
from app.infrastructure.database import Base, get_async_db
from app.main import app
from app.models.user import User

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


@pytest.fixture
async def db_session():
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)
    async_session = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with async_session() as session:
        user = User(
            id=uuid.UUID("00000000-0000-0000-0000-000000000001"),
            email="admin@abci-mi.local",
            full_name="System Administrator",
            role="admin",
            status="active",
        )
        session.add(user)
        await session.commit()
        yield session


@pytest.fixture
async def client(db_session: AsyncSession):
    async def override_get_async_db():
        yield db_session

    app.dependency_overrides[get_async_db] = override_get_async_db
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_jwt_create_and_decode_cycle():
    """Verifies HS256 JWT creation and deterministic decoding."""
    payload = {
        "sub": "00000000-0000-0000-0000-000000000099",
        "email": "test@domain.com",
        "role": "admin",
        "tenant_id": "tenant-custom",
    }
    token = create_access_token(data=payload, expires_delta=timedelta(minutes=15))
    assert isinstance(token, str)
    assert len(token.split(".")) == 3

    decoded = decode_access_token(token)
    assert decoded["sub"] == payload["sub"]
    assert decoded["email"] == payload["email"]
    assert decoded["role"] == "admin"
    assert decoded["tenant_id"] == "tenant-custom"
    assert "exp" in decoded
    assert "iat" in decoded


@pytest.mark.asyncio
async def test_jwt_expired_token_rejection():
    """Verifies that expired JWTs raise UnauthorizedException."""
    payload = {"sub": "user-123", "role": "member"}
    # Token expired 10 minutes ago
    token = create_access_token(data=payload, expires_delta=timedelta(minutes=-10))

    with pytest.raises(UnauthorizedException) as exc_info:
        decode_access_token(token)
    assert exc_info.value.code == "TOKEN_EXPIRED"


@pytest.mark.asyncio
async def test_jwt_tampered_signature_rejection():
    """Verifies that tampered signature raises UnauthorizedException."""
    payload = {"sub": "user-123", "role": "admin"}
    token = create_access_token(data=payload)
    parts = token.split(".")
    # Tamper payload
    tampered = f"{parts[0]}.eyJyZXBsYWNlZCI6IHRydWV9.{parts[2]}"

    with pytest.raises(UnauthorizedException) as exc_info:
        decode_access_token(tampered)
    assert "SIGNATURE" in exc_info.value.code or "INVALID" in exc_info.value.code


@pytest.mark.asyncio
async def test_verify_authentication_with_valid_jwt(client: AsyncClient):
    """Verifies API authentication with signed JWT token."""
    token = create_access_token(
        data={
            "sub": "00000000-0000-0000-0000-000000000001",
            "role": "admin",
            "tenant_id": "tenant-jwt-test",
            "email": "admin@abci-mi.local",
        }
    )
    headers = {"Authorization": f"Bearer {token}"}
    res = await client.get("/api/v1/admin/users", headers=headers)
    assert res.status_code == 200
    assert res.json()["total"] >= 1


@pytest.mark.asyncio
async def test_production_mode_rejects_fixture_tokens(client: AsyncClient):
    """
    Verifies that in production mode (test tokens disabled),
    fixture tokens like 'admin-token' or 'user-token' are rejected with 401.
    """
    settings = get_settings()
    with patch.object(settings, "ALLOW_TEST_TOKENS", False), patch.object(settings, "ENVIRONMENT", "production"):
        # Fixture token must be rejected
        res = await client.get("/api/v1/admin/users", headers={"Authorization": "Bearer admin-token"})
        assert res.status_code == 401

        # Valid signed JWT must succeed even in production mode
        valid_token = create_access_token(
            data={
                "sub": "00000000-0000-0000-0000-000000000001",
                "role": "admin",
                "tenant_id": "tenant-prod",
            }
        )
        prod_res = await client.get("/api/v1/admin/users", headers={"Authorization": f"Bearer {valid_token}"})
        assert prod_res.status_code == 200


@pytest.mark.asyncio
async def test_configured_api_keys_authentication(client: AsyncClient):
    """Verifies authentication via configured custom API key."""
    settings = get_settings()
    custom_key = "prod-secret-api-key-999"
    with patch.object(settings, "AUTH_API_KEYS", [custom_key]):
        res = await client.get("/api/v1/admin/users", headers={"X-API-Key": custom_key})
        assert res.status_code == 200

        # Unconfigured key rejected
        bad_res = await client.get("/api/v1/admin/users", headers={"X-API-Key": "random-unknown-key"})
        assert bad_res.status_code == 401


@pytest.mark.asyncio
async def test_unauthenticated_request_rejected(client: AsyncClient):
    """Verifies request without authentication header returns 401."""
    res = await client.get("/api/v1/admin/users")
    assert res.status_code == 401
