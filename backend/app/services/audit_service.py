"""
Audit Service (Phase 4.25)
Authoritative, immutable audit logging, event ingestion, and security-query service.
Enforces multi-tenant scoping, strict credential sanitization, stable event idempotency,
and security role verification.
"""

from datetime import datetime, timedelta, timezone
import json
import re
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple, Union
import uuid
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ForbiddenException, NotFoundException
from app.core.logging import get_logger
from app.events.redis_bus import RedisEventBus, get_event_bus
from app.models.audit_log import AuditLog
from app.repositories.audit_repo import AuditLogRepository
from app.schemas.admin_audit import (
    AccessDenialEventResponse,
    AccessDenialListResponse,
    AuditLogCreate,
    AuditLogListResponse,
    AuditLogResponse,
    SecuritySummaryResponse,
)

logger = get_logger("services.audit_service")


class AuditService:
    """
    Authoritative service managing the immutable audit log and security queries.
    Provides append-only persistence, recursive depth-bounded secret sanitization,
    event bus integration with idempotency, and tenant-scoped retrieval.
    """

    # Catalog of secret identifiers and sensitive key names
    SECRET_KEYS: Set[str] = {
        "password",
        "pass",
        "secret",
        "secret_key",
        "client_secret",
        "token",
        "access_token",
        "refresh_token",
        "id_token",
        "api_key",
        "apikey",
        "x-api-key",
        "authorization",
        "auth",
        "cookie",
        "jwt",
        "private_key",
        "priv_key",
        "session_id",
        "credentials",
        "connection_string",
        "database_url",
        "db_url",
        "redis_password",
    }

    # RBAC Security Roles
    SECURITY_ROLES: Set[str] = {"admin", "security_officer", "security_auditor"}
    ADMIN_ROLES: Set[str] = {"admin"}

    def __init__(
        self,
        db: AsyncSession,
        event_bus: Optional[RedisEventBus] = None,
    ) -> None:
        self.db = db
        self.repo = AuditLogRepository(db)
        self.event_bus = event_bus or get_event_bus()

    # -------------------------------------------------------------------------
    # Authentication & Scope Extraction
    # -------------------------------------------------------------------------

    def _extract_auth_context(self, auth_context: Dict[str, Any]) -> Tuple[str, Optional[uuid.UUID], str]:
        """Extracts tenant_id, user_id, and role from auth context safely."""
        if not auth_context or not auth_context.get("authenticated", False):
            raise ForbiddenException(message="Authentication credentials required", code="UNAUTHORIZED")

        tenant_id = auth_context.get("tenant_id")
        if not tenant_id:
            tenant_id = auth_context.get("user_id") or "tenant-default"
        tenant_id = str(tenant_id)

        user_id_raw = auth_context.get("user_id")
        user_id: Optional[uuid.UUID] = None
        if user_id_raw:
            try:
                user_id = uuid.UUID(str(user_id_raw))
            except ValueError:
                user_id = None

        role = str(auth_context.get("role", "user")).lower()
        return tenant_id, user_id, role

    # -------------------------------------------------------------------------
    # Security Sanitization
    # -------------------------------------------------------------------------

    def _sanitize_text(self, text: Optional[str]) -> str:
        """
        Strips potential internal secrets, authorization tokens, database URIs,
        private keys, internal filesystem paths, SQL statements, and exception stack traces.
        """
        if not text:
            return ""

        sanitized = str(text)

        # 1. Mask Authorization / Bearer / Basic tokens
        sanitized = re.sub(r"(Bearer\s+)[A-Za-z0-9\-\._~+/]+=*", r"\1[REDACTED]", sanitized, flags=re.IGNORECASE)
        sanitized = re.sub(r"(Basic\s+)[A-Za-z0-9+/=]+", r"\1[REDACTED]", sanitized, flags=re.IGNORECASE)

        # 2. Mask explicit API keys and token parameters
        sanitized = re.sub(r"((?:x-)?api[_-]?key\s*[:=]\s*)[A-Za-z0-9\-\._~+/]+", r"\1[REDACTED]", sanitized, flags=re.IGNORECASE)
        sanitized = re.sub(r"((?:access_|refresh_|id_)?token\s*[:=]\s*)[^\s,;'\"]+", r"\1[REDACTED]", sanitized, flags=re.IGNORECASE)
        sanitized = re.sub(r"(password\s*[:=]\s*)[^\s,;'\"]+", r"\1[REDACTED]", sanitized, flags=re.IGNORECASE)
        sanitized = re.sub(r"(secret(?:_key)?\s*[:=]\s*)[^\s,;'\"]+", r"\1[REDACTED]", sanitized, flags=re.IGNORECASE)

        # 3. Mask JWT tokens
        sanitized = re.sub(r"eyJ[A-Za-z0-9-_=]+\.eyJ[A-Za-z0-9-_=]+\.[A-Za-z0-9-_.+/=]*", "[JWT_TOKEN_REDACTED]", sanitized)

        # 4. Mask Private Key blocks
        sanitized = re.sub(r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z ]*PRIVATE KEY-----", "[PRIVATE_KEY_REDACTED]", sanitized)

        # 5. Mask Database / Broker connection URIs
        sanitized = re.sub(
            r"(?:postgresql|postgres|redis|mysql|sqlite|mongodb|amqp|qdrant)(\+[a-z0-9]+)?://[^\s,;'\"]+",
            "[DATABASE_URI_REDACTED]",
            sanitized,
            flags=re.IGNORECASE,
        )

        # 6. Mask internal server file paths
        sanitized = re.sub(r"(?:/(?:backend|app|usr|etc|var|home|root)/[^\s:,]+|[A-Za-z]:\\[^\s:,]+)", "[SERVER_PATH]", sanitized)

        # 7. Mask exception stack traces
        sanitized = re.sub(r"Traceback \(most recent call last\):[\s\S]*?(?:Error|Exception):[^\n]*", "[EXCEPTION_STACK_TRACE_REDACTED]", sanitized)

        # 8. Mask raw SQL queries if present in error strings
        sanitized = re.sub(r"\b(?:SELECT|INSERT\s+INTO|UPDATE|DELETE\s+FROM|DROP\s+TABLE|ALTER\s+TABLE)\b[\s\S]*?;?", "[SQL_STATEMENT_REDACTED]", sanitized, flags=re.IGNORECASE)

        # Cap length to prevent unbounded payload storage
        return sanitized[:3000].strip()

    def _sanitize_dict(self, data: Any, depth: int = 0) -> Any:
        """
        Recursively sanitizes structured metadata dictionaries and lists.
        Redacts secret-bearing keys case-insensitively and cleans all string values.
        Bounded to a maximum recursion depth of 10.
        """
        if depth > 10:
            return "[MAX_DEPTH_REACHED]"

        if isinstance(data, dict):
            clean_dict: Dict[str, Any] = {}
            for k, v in data.items():
                key_str = str(k).strip()
                key_lower = key_str.lower()
                # Check exact match or presence in secret key catalog
                if key_lower in self.SECRET_KEYS or any(secret in key_lower for secret in ["secret", "password", "token", "apikey", "api_key"]):
                    clean_dict[key_str] = "[REDACTED]"
                else:
                    clean_dict[key_str] = self._sanitize_dict(v, depth + 1)
            return clean_dict

        if isinstance(data, (list, tuple, set)):
            return [self._sanitize_dict(item, depth + 1) for item in data]

        if isinstance(data, str):
            return self._sanitize_text(data)

        if isinstance(data, (int, float, bool)) or data is None:
            return data

        if isinstance(data, uuid.UUID):
            return str(data)

        if isinstance(data, datetime):
            return data.isoformat()

        # Fallback for arbitrary objects
        return self._sanitize_text(str(data))

    # -------------------------------------------------------------------------
    # DTO Mapping
    # -------------------------------------------------------------------------

    def _map_to_dto(self, model: AuditLog) -> AuditLogResponse:
        """Maps an internal AuditLog ORM model to a sanitized public DTO."""
        return AuditLogResponse(
            id=model.id,
            tenant_id=model.tenant_id,
            user_id=model.user_id,
            event_type=model.event_type,
            category=model.category,
            severity=model.severity,
            action=model.action,
            outcome=model.outcome,
            resource_type=model.resource_type,
            resource_id=model.resource_id,
            meeting_id=model.meeting_id,
            project_id=model.project_id,
            correlation_id=model.correlation_id,
            request_id=model.request_id,
            event_id=model.event_id,
            ip_address=model.ip_address,
            user_agent=model.user_agent,
            details=self._sanitize_dict(model.details or {}),
            metadata=self._sanitize_dict(model.metadata_json or {}),
            created_at=model.created_at,
            updated_at=model.updated_at,
        )

    # -------------------------------------------------------------------------
    # Ingestion & Recording (Append-Only)
    # -------------------------------------------------------------------------

    async def log_event(
        self,
        payload: AuditLogCreate,
    ) -> AuditLogResponse:
        """
        Appends an immutable audit log record with idempotency and sanitization.
        """
        tenant_id = str(payload.tenant_id).strip()

        # 1. Check idempotency if event_id is supplied
        if payload.event_id:
            existing = await self.repo.get_by_event_id(tenant_id=tenant_id, event_id=payload.event_id)
            if existing:
                logger.info(f"Audit log entry with event_id '{payload.event_id}' already exists. Idempotent return.")
                return self._map_to_dto(existing)

        # 2. Sanitize details and metadata
        clean_details = self._sanitize_dict(payload.details or {})
        clean_metadata = self._sanitize_dict(payload.metadata or {})
        sanitized_action = self._sanitize_text(payload.action)
        sanitized_ip = self._sanitize_text(payload.ip_address) if payload.ip_address else None
        sanitized_ua = self._sanitize_text(payload.user_agent) if payload.user_agent else None

        # 3. Create AuditLog model
        audit_entry = AuditLog(
            tenant_id=tenant_id,
            user_id=payload.user_id,
            event_type=payload.event_type.strip(),
            category=payload.category.lower().strip(),
            severity=payload.severity.lower().strip(),
            action=sanitized_action,
            outcome=payload.outcome.lower().strip(),
            resource_type=payload.resource_type.strip(),
            resource_id=str(payload.resource_id).strip() if payload.resource_id else None,
            meeting_id=payload.meeting_id,
            project_id=payload.project_id,
            correlation_id=payload.correlation_id,
            request_id=payload.request_id,
            event_id=payload.event_id,
            ip_address=sanitized_ip,
            user_agent=sanitized_ua,
            details=clean_details,
            metadata_json=clean_metadata,
        )

        persisted = await self.repo.create(audit_entry)
        await self.db.commit()
        await self.db.refresh(persisted)

        return self._map_to_dto(persisted)

    async def ingest_event(
        self,
        event_type: str,
        event_data: Dict[str, Any],
    ) -> Optional[AuditLogResponse]:
        """
        Parses domain / security / operational events from RedisEventBus and creates an immutable audit record.
        Extracts stable event_id, correlation_id, and resource identifiers.
        """
        tenant_id = str(event_data.get("tenant_id") or "tenant-default").strip()

        # Parse user ID
        user_id_raw = event_data.get("user_id") or event_data.get("actor_id")
        user_id: Optional[uuid.UUID] = None
        if user_id_raw:
            try:
                user_id = uuid.UUID(str(user_id_raw))
            except ValueError:
                user_id = None

        # Parse meeting and project UUIDs
        meeting_id_raw = event_data.get("meeting_id")
        meeting_id: Optional[uuid.UUID] = None
        if meeting_id_raw:
            try:
                meeting_id = uuid.UUID(str(meeting_id_raw))
            except ValueError:
                meeting_id = None

        project_id_raw = event_data.get("project_id")
        project_id: Optional[uuid.UUID] = None
        if project_id_raw:
            try:
                project_id = uuid.UUID(str(project_id_raw))
            except ValueError:
                project_id = None

        # Tracing identifiers
        correlation_id_raw = (
            event_data.get("correlation_id")
            or event_data.get("metadata", {}).get("correlation_id")
            or event_data.get("context", {}).get("correlation_id")
        )
        correlation_id = str(correlation_id_raw).strip() if correlation_id_raw else None

        request_id_raw = (
            event_data.get("request_id")
            or event_data.get("metadata", {}).get("request_id")
        )
        request_id = str(request_id_raw).strip() if request_id_raw else None

        # Resource references (handles UUIDs and external platforms like Zoom/Teams)
        resource_id_raw = (
            event_data.get("resource_id")
            or event_data.get("external_id")
            or event_data.get("zoom_id")
            or event_data.get("teams_id")
            or event_data.get("knowledge_id")
            or meeting_id_raw
            or project_id_raw
        )
        resource_id = str(resource_id_raw).strip() if resource_id_raw is not None else None

        resource_type = str(
            event_data.get("resource_type")
            or ("meeting" if meeting_id else ("project" if project_id else "system"))
        ).strip()

        # Stable event idempotency key
        event_id_raw = (
            event_data.get("event_id")
            or event_data.get("event_uuid")
            or event_data.get("id")
        )
        if event_id_raw:
            event_id = str(event_id_raw).strip()
        elif correlation_id:
            event_id = f"audit:{tenant_id}:{event_type}:{correlation_id}:{resource_id or ''}"
        else:
            event_id = f"audit:{tenant_id}:{event_type}:{resource_id or ''}"

        # Action and outcome determination
        action = str(event_data.get("action") or event_type).strip()
        outcome = str(event_data.get("outcome") or "success").strip()
        if "fail" in event_type.lower() or "denied" in event_type.lower() or "denial" in event_type.lower():
            outcome = "denied" if "deni" in event_type.lower() else "failure"

        # Category and severity
        category = str(event_data.get("category") or "system").strip().lower()
        if any(sec in event_type.lower() for sec in ["auth", "security", "denial", "permission", "login"]):
            category = "security" if "security" in event_type.lower() else "auth"

        severity = str(event_data.get("severity") or "info").strip().lower()
        if outcome == "denied" or "security" in event_type.lower():
            severity = "security"
        elif outcome == "failure":
            severity = "warning"

        create_payload = AuditLogCreate(
            tenant_id=tenant_id,
            user_id=user_id,
            event_type=event_type,
            category=category,
            severity=severity,
            action=action,
            outcome=outcome,
            resource_type=resource_type,
            resource_id=resource_id,
            meeting_id=meeting_id,
            project_id=project_id,
            correlation_id=correlation_id,
            request_id=request_id,
            event_id=event_id,
            ip_address=event_data.get("ip_address"),
            user_agent=event_data.get("user_agent"),
            details=event_data.get("details", {}),
            metadata=event_data.get("metadata", {}),
        )

        return await self.log_event(create_payload)

    # -------------------------------------------------------------------------
    # Query Operations (Tenant-Scoped & RBAC Enforced)
    # -------------------------------------------------------------------------

    async def list_audit_logs(
        self,
        auth_context: Dict[str, Any],
        user_id: Optional[uuid.UUID] = None,
        event_type: Optional[str] = None,
        category: Optional[str] = None,
        severity: Optional[str] = None,
        outcome: Optional[str] = None,
        resource_type: Optional[str] = None,
        resource_id: Optional[str] = None,
        meeting_id: Optional[uuid.UUID] = None,
        project_id: Optional[uuid.UUID] = None,
        correlation_id: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> AuditLogListResponse:
        """
        Lists tenant-scoped audit logs with granular filters.
        Enforces admin or security role access.
        """
        tenant_id, _, role = self._extract_auth_context(auth_context)
        if role not in self.SECURITY_ROLES:
            raise ForbiddenException("Audit trail querying requires administrative or security privileges.", code="INSUFFICIENT_ROLE")

        items, total = await self.repo.list_audit_logs(
            tenant_id=tenant_id,
            user_id=user_id,
            event_type=event_type,
            category=category,
            severity=severity,
            outcome=outcome,
            resource_type=resource_type,
            resource_id=resource_id,
            meeting_id=meeting_id,
            project_id=project_id,
            correlation_id=correlation_id,
            start_date=start_date,
            end_date=end_date,
            limit=limit,
            offset=offset,
        )

        return AuditLogListResponse(
            items=[self._map_to_dto(item) for item in items],
            total=total,
            limit=limit,
            offset=offset,
        )

    async def get_audit_log(
        self,
        audit_id: uuid.UUID,
        auth_context: Dict[str, Any],
    ) -> AuditLogResponse:
        """
        Fetches an individual audit log by ID.
        Enforces 404 for missing and 403 for cross-tenant or unprivileged access.
        """
        tenant_id, _, role = self._extract_auth_context(auth_context)
        if role not in self.SECURITY_ROLES:
            raise ForbiddenException("Audit trail querying requires administrative or security privileges.", code="INSUFFICIENT_ROLE")

        audit_entry = await self.repo.get_by_id(audit_id)
        if not audit_entry:
            raise NotFoundException(f"Audit log '{audit_id}' not found.", code="AUDIT_NOT_FOUND")

        if audit_entry.tenant_id != tenant_id:
            raise ForbiddenException("Access to this audit log is forbidden.", code="TENANT_MISMATCH")

        return self._map_to_dto(audit_entry)

    async def list_security_events(
        self,
        auth_context: Dict[str, Any],
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> AuditLogListResponse:
        """Lists security audit records strictly for security roles."""
        tenant_id, _, role = self._extract_auth_context(auth_context)
        if role not in self.SECURITY_ROLES:
            raise ForbiddenException("Security audit querying requires security auditor or admin privileges.", code="INSUFFICIENT_ROLE")

        items, total = await self.repo.list_security_events(
            tenant_id=tenant_id,
            start_date=start_date,
            end_date=end_date,
            limit=limit,
            offset=offset,
        )

        return AuditLogListResponse(
            items=[self._map_to_dto(item) for item in items],
            total=total,
            limit=limit,
            offset=offset,
        )

    async def list_resource_history(
        self,
        resource_id: str,
        auth_context: Dict[str, Any],
        resource_type: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> AuditLogListResponse:
        """Lists chronological audit history for a specific resource identifier."""
        tenant_id, _, role = self._extract_auth_context(auth_context)
        if role not in self.SECURITY_ROLES:
            raise ForbiddenException("Resource audit trail querying requires administrative or security privileges.", code="INSUFFICIENT_ROLE")

        items, total = await self.repo.list_resource_history(
            tenant_id=tenant_id,
            resource_id=resource_id,
            resource_type=resource_type,
            limit=limit,
            offset=offset,
        )

        return AuditLogListResponse(
            items=[self._map_to_dto(item) for item in items],
            total=total,
            limit=limit,
            offset=offset,
        )

    async def list_access_denials(
        self,
        auth_context: Dict[str, Any],
        user_id: Optional[uuid.UUID] = None,
        resource_type: Optional[str] = None,
        resource_id: Optional[str] = None,
        meeting_id: Optional[uuid.UUID] = None,
        project_id: Optional[uuid.UUID] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> AccessDenialListResponse:
        """Lists access denial events for security auditing."""
        tenant_id, _, role = self._extract_auth_context(auth_context)
        if role not in self.SECURITY_ROLES:
            raise ForbiddenException("Access denial querying requires security privileges.", code="INSUFFICIENT_ROLE")

        items, total = await self.repo.list_access_denials(
            tenant_id=tenant_id,
            user_id=user_id,
            resource_type=resource_type,
            resource_id=resource_id,
            meeting_id=meeting_id,
            project_id=project_id,
            start_date=start_date,
            end_date=end_date,
            limit=limit,
            offset=offset,
        )

        denials: List[AccessDenialEventResponse] = []
        for item in items:
            reason = item.details.get("reason") if item.details else None
            if not reason and item.metadata_json:
                reason = item.metadata_json.get("reason")
            denials.append(
                AccessDenialEventResponse(
                    id=item.id,
                    tenant_id=item.tenant_id,
                    user_id=item.user_id,
                    event_type=item.event_type,
                    action=item.action,
                    resource_type=item.resource_type,
                    resource_id=item.resource_id,
                    meeting_id=item.meeting_id,
                    project_id=item.project_id,
                    correlation_id=item.correlation_id,
                    reason=self._sanitize_text(reason) if reason else "Access unauthorized or forbidden",
                    created_at=item.created_at,
                    updated_at=item.updated_at,
                )
            )

        return AccessDenialListResponse(
            items=denials,
            total=total,
            limit=limit,
            offset=offset,
        )

    async def get_security_summary(
        self,
        auth_context: Dict[str, Any],
        days: int = 7,
    ) -> SecuritySummaryResponse:
        """Generates aggregated security summary metrics for a tenant."""
        tenant_id, _, role = self._extract_auth_context(auth_context)
        if role not in self.SECURITY_ROLES:
            raise ForbiddenException("Security summary aggregation requires security privileges.", code="INSUFFICIENT_ROLE")

        now = datetime.now(timezone.utc)
        start_date = now - timedelta(days=max(1, min(days, 365)))

        summary_data = await self.repo.get_security_summary(
            tenant_id=tenant_id,
            start_date=start_date,
            end_date=now,
        )

        return SecuritySummaryResponse(
            tenant_id=tenant_id,
            window_days=days,
            start_date=start_date,
            end_date=now,
            authentication_failures=summary_data["authentication_failures"],
            authorization_failures=summary_data["authorization_failures"],
            access_denials=summary_data["access_denials"],
            security_alerts=summary_data["security_alerts"],
            affected_users=summary_data["affected_users"],
            affected_resources=summary_data["affected_resources"],
        )
