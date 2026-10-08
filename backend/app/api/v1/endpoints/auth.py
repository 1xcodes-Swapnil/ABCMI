"""
Authentication & Session Endpoints (Phase 4.15)
Provides login, current user session information, and authorization validation.
"""

from typing import Any, Dict, Optional
import asyncio
import time
from collections import OrderedDict, deque
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from app.infrastructure.database import get_async_db
from app.models.user import User
import uuid
from pydantic import Field

from app.api.dependencies import verify_authentication
from app.core.config import get_settings
from app.core.security import create_access_token
from app.schemas.base import CoreBaseModel

router = APIRouter(prefix="/auth", tags=["Authentication"])


class LoginRequest(CoreBaseModel):
    """Login request payload."""

    email: str = Field(..., min_length=3, max_length=255, description="User email address")
    password: str = Field(..., min_length=1, max_length=1024, repr=False, description="User password")
    use_jwt: Optional[bool] = Field(default=None, description="Force signed JWT generation")


class LoginResponse(CoreBaseModel):
    """Login response payload containing access token and user info."""

    access_token: str
    token_type: str = "bearer"
    user_id: str
    email: str
    role: str
    full_name: str


class UserInfoResponse(CoreBaseModel):
    """Current user session info response."""

    user_id: str
    email: str
    role: str
    full_name: str
    authenticated: bool
    tenant_id: str


@router.post("/login", response_model=LoginResponse, status_code=status.HTTP_200_OK)
async def login(payload: LoginRequest, request: Request,
                db: AsyncSession = Depends(get_async_db)) -> LoginResponse:
    """Authenticate user credentials and return bearer access token."""
    settings = get_settings()
    if settings.EXECUTION_MODE.upper() == "REAL":
        _limit_password_requests(request)
        from app.core.passwords import DUMMY_PASSWORD_HASH, verify_password
        users = (await db.execute(select(User).where(func.lower(User.email) == payload.email.strip().lower()))).scalars().all()
        user = users[0] if len(users) == 1 else None
        encoded = user.password_hash if user and user.password_hash else DUMMY_PASSWORD_HASH
        valid = await asyncio.to_thread(verify_password, payload.password, encoded)
        if not valid or not user or not user.is_active or not user.password_hash or not user.login_tenant_id:
            raise HTTPException(401, "Invalid email or password", headers={"WWW-Authenticate": "Bearer"})
        return _account_token(user, user.login_tenant_id)
    role = "admin" if "admin" in payload.email.lower() else "member"
    user_id = "00000000-0000-0000-0000-000000000001" if role == "admin" else "00000000-0000-0000-0000-000000000002"
    full_name = "Administrator User" if role == "admin" else "Standard Member"

    # In production or if explicitly requested or if test tokens disabled: generate signed JWT
    if payload.use_jwt or not settings.test_tokens_enabled:
        token = create_access_token(
            data={
                "sub": user_id,
                "email": payload.email,
                "role": role,
                "tenant_id": "default-tenant",
            }
        )
    else:
        token = "admin-token" if role == "admin" else "user-token"

    return LoginResponse(
        access_token=token,
        token_type="bearer",
        user_id=user_id,
        email=payload.email,
        role=role,
        full_name=full_name,
    )


@router.get("/me", response_model=UserInfoResponse, status_code=status.HTTP_200_OK)
async def get_current_user(auth_context: Dict[str, Any] = Depends(verify_authentication),
                           db: AsyncSession = Depends(get_async_db)) -> UserInfoResponse:
    """Retrieve current authenticated user and session metadata."""
    user_id = auth_context["user_id"]
    try:
        user = await db.get(User, uuid.UUID(str(user_id)))
    except ValueError:
        raise HTTPException(401, "Token subject must identify an existing user")
    if user is None or not user.is_active:
        raise HTTPException(401, "User does not exist or is inactive")
    role = auth_context["role"]
    return UserInfoResponse(
        user_id=str(user_id),
        email=user.email,
        role=role,
        full_name=user.full_name,
        authenticated=True,
        tenant_id=auth_context["tenant_id"],
    )


class ProfileUpdate(CoreBaseModel):
    full_name: str = Field(min_length=1, max_length=255)


@router.patch("/me", response_model=UserInfoResponse)
async def update_profile(payload: ProfileUpdate,
                         auth: Dict[str, Any] = Depends(verify_authentication),
                         db: AsyncSession = Depends(get_async_db)):
    await get_current_user(auth, db)
    user = await db.get(User, uuid.UUID(str(auth["user_id"])))
    user.full_name = payload.full_name.strip()
    if not user.full_name:
        raise HTTPException(422, "Name cannot be blank")
    await db.commit()
    return await get_current_user(auth, db)


_password_attempts = OrderedDict()


def _limit_password_requests(request: Request):
    """Bound expensive password checks per direct client; do not trust forwarded IPs."""
    key = request.client.host if request.client else "unknown"
    now = time.monotonic()
    attempts = _password_attempts.setdefault(key, deque())
    _password_attempts.move_to_end(key)
    while attempts and attempts[0] <= now - 60:
        attempts.popleft()
    if len(attempts) >= 10:
        raise HTTPException(429, "Too many password attempts; try again in one minute", headers={"Retry-After": "60"})
    attempts.append(now)
    while len(_password_attempts) > 10000:
        _password_attempts.popitem(last=False)


def _account_token(user: User, tenant_id: str) -> LoginResponse:
    token = create_access_token({"sub": str(user.id), "email": user.email,
                                 "role": user.role, "tenant_id": tenant_id})
    return LoginResponse(access_token=token, user_id=str(user.id), email=user.email,
                         role=user.role, full_name=user.full_name)


class PasswordUpdate(CoreBaseModel):
    current_password: Optional[str] = Field(default=None, max_length=1024, repr=False)
    new_password: str = Field(min_length=12, max_length=1024, repr=False)


@router.put("/me/password", response_model=LoginResponse)
async def set_password(payload: PasswordUpdate, request: Request,
                       auth: Dict[str, Any] = Depends(verify_authentication),
                       db: AsyncSession = Depends(get_async_db)):
    """Enroll from an authorized session; subsequent changes require the existing password."""
    _limit_password_requests(request)
    await get_current_user(auth, db)
    from app.core.passwords import hash_password, verify_password
    user = (await db.execute(select(User).where(User.id == uuid.UUID(str(auth["user_id"]))).with_for_update())).scalar_one()
    if user.password_hash and not await asyncio.to_thread(verify_password, payload.current_password or "", user.password_hash):
        raise HTTPException(401, "Current password is incorrect")
    if user.login_tenant_id and user.login_tenant_id != auth["tenant_id"]:
        raise HTTPException(403, "Password sign-in belongs to a different authorized workspace")
    user.password_hash = await asyncio.to_thread(hash_password, payload.new_password)
    user.login_tenant_id = auth["tenant_id"]
    await db.commit()
    return _account_token(user, user.login_tenant_id)
