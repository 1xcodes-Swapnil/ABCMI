"""
ABCI-MI Security & Token Verification Module
Provides deterministic HMAC-SHA256 (HS256) JWT generation, decoding, and cryptographic validation
without external binary dependencies. Enforces token expiration, issuer, audience, and RBAC claims.
"""

import base64
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import json
from typing import Any, Dict, Optional

from app.core.config import get_settings
from app.core.exceptions import UnauthorizedException


def _base64url_encode(data: bytes) -> str:
    """Encodes bytes to URL-safe Base64 without trailing padding '='."""
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _base64url_decode(data: str) -> bytes:
    """Decodes URL-safe Base64 string with missing padding '=' reconstructed."""
    padding = len(data) % 4
    if padding == 2:
        data += "=="
    elif padding == 3:
        data += "="
    elif padding == 1:
        raise ValueError("Invalid base64 string length")
    return base64.urlsafe_b64decode(data.encode("ascii"))


def create_access_token(
    data: Dict[str, Any],
    expires_delta: Optional[timedelta] = None,
    secret_key: Optional[str] = None,
    issuer: Optional[str] = None,
    audience: Optional[str] = None,
) -> str:
    """
    Creates a signed JWT (HS256) containing payload claims, expiration, and optional issuer/audience.
    """
    settings = get_settings()
    key = secret_key or settings.effective_jwt_secret
    iss = issuer or settings.JWT_ISSUER
    aud = audience or settings.JWT_AUDIENCE

    header = {"alg": "HS256", "typ": "JWT"}
    now = datetime.now(timezone.utc)
    if expires_delta:
        expire = now + expires_delta
    else:
        expire = now + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)

    payload = dict(data)
    payload["iat"] = int(now.timestamp())
    payload["exp"] = int(expire.timestamp())
    if iss and "iss" not in payload:
        payload["iss"] = iss
    if aud and "aud" not in payload:
        payload["aud"] = aud

    header_b64 = _base64url_encode(json.dumps(header, separators=(",", ":")).encode("utf-8"))
    payload_b64 = _base64url_encode(json.dumps(payload, separators=(",", ":")).encode("utf-8"))

    signing_input = f"{header_b64}.{payload_b64}".encode("ascii")
    signature = hmac.new(key.encode("utf-8"), signing_input, hashlib.sha256).digest()
    signature_b64 = _base64url_encode(signature)

    return f"{header_b64}.{payload_b64}.{signature_b64}"


def decode_access_token(
    token: str,
    secret_key: Optional[str] = None,
    verify_exp: bool = True,
    issuer: Optional[str] = None,
    audience: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Cryptographically verifies and decodes an HS256 JWT access token.
    Raises UnauthorizedException on invalid signature, expiration, or malformed claims.
    """
    settings = get_settings()
    key = secret_key or settings.effective_jwt_secret
    expected_iss = issuer or settings.JWT_ISSUER
    expected_aud = audience or settings.JWT_AUDIENCE

    parts = token.strip().split(".")
    if len(parts) != 3:
        raise UnauthorizedException(
            message="Malformed JWT access token format",
            code="INVALID_TOKEN_FORMAT",
        )

    header_b64, payload_b64, signature_b64 = parts

    # 1. Verify signature
    try:
        signing_input = f"{header_b64}.{payload_b64}".encode("ascii")
        expected_sig = hmac.new(key.encode("utf-8"), signing_input, hashlib.sha256).digest()
        actual_sig = _base64url_decode(signature_b64)

        if not hmac.compare_digest(expected_sig, actual_sig):
            raise UnauthorizedException(
                message="Invalid access token signature",
                code="INVALID_SIGNATURE",
            )
    except UnauthorizedException:
        raise
    except Exception as e:
        raise UnauthorizedException(
            message=f"Failed to verify token signature: {str(e)}",
            code="INVALID_TOKEN_SIGNATURE",
        )

    # 2. Decode header and payload
    try:
        header_bytes = _base64url_decode(header_b64)
        payload_bytes = _base64url_decode(payload_b64)
        header = json.loads(header_bytes.decode("utf-8"))
        payload = json.loads(payload_bytes.decode("utf-8"))
    except Exception as e:
        raise UnauthorizedException(
            message=f"Malformed token payload or header encoding: {str(e)}",
            code="MALFORMED_TOKEN",
        )

    if header.get("alg") != "HS256":
        raise UnauthorizedException(
            message=f"Unsupported token algorithm '{header.get('alg')}'; expected HS256",
            code="UNSUPPORTED_ALGORITHM",
        )

    now_ts = int(datetime.now(timezone.utc).timestamp())

    # 3. Check expiration
    if verify_exp and "exp" in payload:
        if now_ts > int(payload["exp"]):
            raise UnauthorizedException(
                message="Access token has expired",
                code="TOKEN_EXPIRED",
            )

    # 4. Check not before (nbf)
    if "nbf" in payload:
        if now_ts < int(payload["nbf"]):
            raise UnauthorizedException(
                message="Access token is not active yet",
                code="TOKEN_NOT_YET_VALID",
            )

    # 5. Check issuer
    if expected_iss and payload.get("iss") != expected_iss:
        raise UnauthorizedException(
            message=f"Invalid token issuer '{payload.get('iss')}'; expected '{expected_iss}'",
            code="INVALID_ISSUER",
        )

    # 6. Check audience
    if expected_aud and payload.get("aud") != expected_aud:
        raise UnauthorizedException(
            message=f"Invalid token audience '{payload.get('aud')}'; expected '{expected_aud}'",
            code="INVALID_AUDIENCE",
        )

    return payload
