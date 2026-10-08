"""
ABCI-MI Common API Dependencies & Auth Verification
Provides authentication, RBAC, and request context verification dependencies.
"""

from typing import Any, Dict, Optional
import uuid
import secrets
from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.exceptions import UnauthorizedException
from app.core.security import decode_access_token
from app.infrastructure.database import get_async_db


async def verify_authentication(
    authorization: Optional[str] = Header(default=None),
    x_api_key: Optional[str] = Header(default=None),
    x_tenant_id: Optional[str] = Header(default=None),
    db: AsyncSession = Depends(get_async_db),
) -> Dict[str, Any]:
    """
    Verify authentication credentials via cryptographic JWT verification, configurable API keys,
    or development/test fixture tokens (when permitted).
    Ensures robust tenant isolation and RBAC claim enforcement.
    """
    settings = get_settings()

    token = None
    if authorization:
        parts = authorization.strip().split(" ")
        if len(parts) == 2 and parts[0].lower() == "bearer":
            token = parts[1].strip()
        else:
            token = authorization.strip()

    if not token and not x_api_key:
        raise UnauthorizedException(
            message="Authentication credentials (Bearer token or X-API-Key) required",
            code="UNAUTHORIZED",
        )

    # 1. Cryptographic JWT Verification (if token is 3-part dot-separated)
    if token and len(token.split(".")) == 3:
        try:
            payload = decode_access_token(
                token=token,
                secret_key=settings.effective_jwt_secret,
                issuer=settings.JWT_ISSUER,
                audience=settings.JWT_AUDIENCE,
            )
            user_id = payload.get("sub") or payload.get("user_id") or "00000000-0000-0000-0000-000000000001"
            role = payload.get("role", "member")
            # Prefer token-embedded tenant claim over unverified header
            tenant_id = payload.get("tenant_id") or x_tenant_id or "default-tenant"
            email = payload.get("email")
            if settings.EXECUTION_MODE.upper() == "REAL":
                from app.models.user import User
                if not payload.get("sub") or not payload.get("tenant_id") or not payload.get("exp"):
                    raise UnauthorizedException(message="Signed subject, tenant and expiration are required", code="INVALID_CLAIMS")
                if x_tenant_id and x_tenant_id != tenant_id:
                    raise UnauthorizedException(message="Tenant header differs from the signed session", code="INVALID_TENANT")
                user = await db.get(User, uuid.UUID(str(user_id)))
                if not user or not user.is_active:
                    raise UnauthorizedException(message="Account is unavailable or inactive", code="INVALID_ACCOUNT")
                # An old session must not retain permissions after a role change.
                role, email = user.role, user.email

            return {
                "user_id": user_id,
                "tenant_id": tenant_id,
                "role": role,
                "email": email,
                "authenticated": True,
                "token": token,
                "claims": payload,
            }
        except UnauthorizedException:
            raise
        except Exception as e:
            raise UnauthorizedException(
                message=f"Invalid token claims or decoding failure: {str(e)}",
                code="INVALID_TOKEN",
            )

    # 2. Configured Production API Keys
    configured_api_keys = set(settings.AUTH_API_KEYS)
    incoming_key = x_api_key or token
    if incoming_key and any(secrets.compare_digest(incoming_key, configured) for configured in configured_api_keys):
        if settings.EXECUTION_MODE.upper() == "REAL":
            from sqlalchemy import select
            from app.models.user import User
            from app.repositories.user_repo import UserRepository
            tenant_id = settings.AUTH_API_KEY_TENANT_ID
            try:
                principal_id = uuid.UUID(settings.AUTH_API_KEY_USER_ID or "")
            except ValueError:
                raise UnauthorizedException(message="API key has no configured account binding", code="INVALID_ACCOUNT") from None
            if not tenant_id or (x_tenant_id and x_tenant_id != tenant_id):
                raise UnauthorizedException(message="API key tenant binding is missing or mismatched", code="INVALID_TENANT")
            principal = (await db.execute(select(User).where(User.id == principal_id,
                UserRepository.tenant_membership(tenant_id)))).scalar_one_or_none()
            if principal is None or not principal.is_active:
                raise UnauthorizedException(message="API key account is unavailable in this tenant", code="INVALID_ACCOUNT")
            return {"user_id": str(principal.id), "tenant_id": tenant_id, "role": principal.role,
                    "email": principal.email, "authenticated": True, "token": incoming_key}
        return {
            "user_id": "00000000-0000-0000-0000-000000000001",
            "tenant_id": x_tenant_id or "default-tenant",
            "role": "admin",
            "authenticated": True,
            "token": incoming_key,
        }

    # 3. Development / Test Fixture Tokens (Guarded by environment & settings)
    test_tokens = {
        "test-token": ("00000000-0000-0000-0000-000000000001", "admin"),
        "admin-token": ("00000000-0000-0000-0000-000000000001", "admin"),
        "valid-jwt-token": ("00000000-0000-0000-0000-000000000001", "admin"),
        "user-token": ("00000000-0000-0000-0000-000000000002", "member"),
        "member-token": ("00000000-0000-0000-0000-000000000002", "member"),
        "host-token": ("00000000-0000-0000-0000-000000000003", "host"),
        "security-officer-token": ("00000000-0000-0000-0000-000000000004", "security_officer"),
        "security-auditor-token": ("00000000-0000-0000-0000-000000000005", "security_auditor"),
    }
    test_api_keys = {"skw-secret-api-key", "test-api-key", "admin-api-key"}

    if (token in test_tokens) or (incoming_key in test_api_keys):
        if settings.EXECUTION_MODE.upper() == "REAL" or not settings.test_tokens_enabled:
            raise UnauthorizedException(
                message="Test fixture credentials are not permitted in production environment",
                code="INVALID_CREDENTIALS",
            )

        if token in test_tokens:
            user_id, role = test_tokens[token]
        else:
            user_id, role = "00000000-0000-0000-0000-000000000001", "admin"

        return {
            "user_id": user_id,
            "tenant_id": x_tenant_id or "default-tenant",
            "role": role,
            "authenticated": True,
            "token": token or incoming_key,
        }

    raise UnauthorizedException(
        message="Invalid authentication credentials",
        code="INVALID_CREDENTIALS",
    )
