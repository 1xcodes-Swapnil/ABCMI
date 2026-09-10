# ABCI-MI Security Architecture & Data Protection Standard

**Document Version:** 2.0.0  
**Status:** Mandatory Engineering Standard

---

## 1. Security Architecture Overview

ABCI-MI processes sensitive enterprise voice streams, meeting transcripts, and corporate decision graphs. Security is enforced through defense-in-depth across transport, identity, authorization, data isolation, and cryptographic auditing.

```
┌───────────────────────────────────────────────────────────┐
│               TLS 1.3 Transport Encryption                │
└─────────────────────────────┬─────────────────────────────┘
                              │
┌─────────────────────────────▼─────────────────────────────┐
│       Authentication & Role-Based Authorization Guard     │
│   (HS256 JWT, Claims Parsing, RBAC & Tenant Verification) │
└─────────────────────────────┬─────────────────────────────┘
                              │
┌─────────────────────────────▼─────────────────────────────┐
│   Input Sanitization, Size Limits & Pydantic Validation   │
│   (MIME Magic Bytes, Path Traversal Defense, Size Caps)   │
└─────────────────────────────┬─────────────────────────────┘
                              │
┌─────────────────────────────▼─────────────────────────────┐
│       Isolated Data & Cryptographic Audit Logging         │
│   (Tenant DB Scoping, Qdrant Filtering, SHA-256 Chains)   │
└───────────────────────────────────────────────────────────┘
```

---

## 2. Authentication, RBAC & Tenant Isolation

### 2.1 Cryptographic HS256 JWT Authentication
- All non-public REST endpoints and WebSocket handshakes require a valid HS256-signed JWT token supplied via `Authorization: Bearer <token>`.
- Token verification checks signature integrity (`hmac.compare_digest`), validity window (`exp`, `nbf`), and extracts `user_id`, `tenant_id`, and `role`.
- Production guards (`ENVIRONMENT=production`) strictly reject hardcoded test tokens.

### 2.2 Role-Based Access Control (RBAC) Matrix

| Role | Permissions & Access Scope |
| :--- | :--- |
| **`admin`** | Full platform management, tenant configuration, system telemetry, and audit log inspection. |
| **`security_officer`** / **`security_auditor`** | Read-only access to tamper-evident audit logs, access denial reports, and security metrics. |
| **`host`** | Create, start, pause, end meetings, upload audio, trigger intelligence synthesis, and delete owned sessions. |
| **`member`** | View meetings within their authorized tenant, query context, view finalized summaries, and download reports. |

### 2.3 Strict Multitenancy & Data Isolation
- Every database query and vector retrieval operation automatically injects the tenant filter:
  - PostgreSQL: `WHERE entity.tenant_id = :authenticated_tenant_id`
  - Qdrant: `Filter(must=[FieldCondition(key="tenant_id", match=MatchValue(value=authenticated_tenant_id))])`
- Any request attempting to access resources belonging to a different tenant is immediately blocked with HTTP 403 `TENANT_MISMATCH`.

---

## 3. Storage & Audio Upload Security

Audio and video ingestion is managed exclusively through `app.infrastructure.storage.StorageManager`:
1. **MIME & Magic Header Inspection**: Ingested files are validated against allowed binary signatures (`.wav`, `.mp3`, `.m4a`, `.flac`, `.ogg`, `.mp4`, `.webm`).
2. **Path Traversal Defense**: All stored files are assigned cryptographically random UUID filenames within sanitized, scoped directory trees (`data/audio/raw/{tenant_id}/{meeting_id}/{uuid}.wav`).
3. **Upload Size Caps**: Maximum batch upload size is capped at 500 MB (enforced via `MAX_UPLOAD_SIZE_MB`).
4. **Sequential Chunk Checksums**: Live audio chunks require a valid SHA-256 digest matching payload bytes to prevent tampered or malformed packets.

---

## 4. Secret Redaction & Cryptographically Chained Audit Logging

### 4.1 Automated Secret Redaction
Before logging or persisting audit records, payload attributes matching sensitive keys (`password`, `token`, `secret`, `api_key`, `authorization`, `private_key`) are masked with `[REDACTED]`.

### 4.2 Tamper-Evident SHA-256 Hash Chaining
Audit log entries in `audit_logs` table are cryptographically linked in an immutable chain:
$$H_i = \text{SHA256}(H_{i-1} \parallel \text{timestamp} \parallel \text{actor\_id} \parallel \text{action} \parallel \text{resource\_id} \parallel \text{status})$$

Any modification, deletion, or insertion of past audit records causes subsequent hash verification to fail, providing verifiable compliance auditing.
