# ABCI-MI REST & WebSocket API Guidelines

**Base Path:** `/api/v1/`  
**Protocol:** HTTP/1.1, HTTP/2, WebSocket (WSS)  
**Document Version:** 2.0.0  
**Status:** Authoritative API Standard

---

## 1. API Architecture & Envelope Conventions

All REST endpoints return standardized JSON response envelopes adhering to `app/schemas/base.py`:

### 1.1 Success Response Envelope (`StandardResponse[T]`)
```json
{
  "success": true,
  "data": { ... },
  "message": "Operation completed successfully"
}
```

### 1.2 Paginated List Envelope (`PaginatedResponse[T]`)
```json
{
  "success": true,
  "data": [ ... ],
  "meta": {
    "page": 1,
    "page_size": 20,
    "total_items": 142,
    "total_pages": 8,
    "has_next": true,
    "has_prev": false
  },
  "message": null
}
```

### 1.3 Error Response Envelope (`ErrorResponse`)
```json
{
  "success": false,
  "error": {
    "code": "TENANT_MISMATCH",
    "message": "Resource does not belong to authorized tenant.",
    "details": {},
    "timestamp": "2026-08-25T10:15:30.123456Z"
  }
}
```

---

## 2. Complete Endpoint Catalog

### 2.1 Health & Diagnostic Endpoints
| HTTP Verb | Path | Description | Auth Required |
| :--- | :--- | :--- | :--- |
| `GET` | `/api/v1/health` | Multi-tier health check (PostgreSQL, Redis, Qdrant, Storage) | None |
| `GET` | `/api/v1/health/liveness` | Kubernetes liveness probe | None |
| `GET` | `/api/v1/health/readiness`| Kubernetes readiness probe | None |

### 2.2 Authentication & Security Endpoints
| HTTP Verb | Path | Description | Auth Required |
| :--- | :--- | :--- | :--- |
| `POST` | `/api/v1/auth/token` | Issue HS256 JWT access token for user/tenant | None (Credentials) |
| `GET` | `/api/v1/auth/me` | Retrieve authenticated user profile and permissions | Bearer JWT |

### 2.3 Meeting Management Endpoints
| HTTP Verb | Path | Description | Auth Required |
| :--- | :--- | :--- | :--- |
| `GET` | `/api/v1/meetings` | List meetings with pagination, status, and date filters | Bearer JWT |
| `POST` | `/api/v1/meetings` | Create and schedule a new meeting session | Bearer JWT |
| `GET` | `/api/v1/meetings/{id}` | Retrieve comprehensive meeting metadata by ID | Bearer JWT |
| `PATCH`| `/api/v1/meetings/{id}` | Update meeting title, agenda, language, or status | Bearer JWT |
| `DELETE`| `/api/v1/meetings/{id}` | Soft-delete meeting and related artifacts | Bearer JWT (Host/Admin) |
| `POST` | `/api/v1/meetings/{id}/start` | Transition meeting state to `in_progress` | Bearer JWT (Host) |
| `POST` | `/api/v1/meetings/{id}/end` | Finalize meeting and trigger ACE synthesis | Bearer JWT (Host) |

### 2.4 Audio Ingestion & Live Streaming Endpoints
| HTTP Verb | Path | Description | Auth Required |
| :--- | :--- | :--- | :--- |
| `POST` | `/api/v1/meetings/{id}/audio` | Ingest batch audio/video recording (up to 500 MB) | Bearer JWT |
| `POST` | `/api/v1/live/sessions` | Initialize a new real-time live streaming session | Bearer JWT |
| `POST` | `/api/v1/live/sessions/{id}/chunks` | Ingest sequential audio chunk with SHA-256 digest | Bearer JWT |
| `POST` | `/api/v1/live/sessions/{id}/end` | Terminate live streaming session | Bearer JWT |
| `GET` | `/api/v1/live/sessions/{id}/status` | Query live streaming session status and metrics | Bearer JWT |

### 2.5 Transcript & Speaker Turn Endpoints
| HTTP Verb | Path | Description | Auth Required |
| :--- | :--- | :--- | :--- |
| `GET` | `/api/v1/meetings/{id}/transcripts` | Retrieve chronological diarized speaker segments | Bearer JWT |
| `GET` | `/api/v1/meetings/{id}/speakers` | List unique speakers and speaking duration stats | Bearer JWT |
| `PATCH`| `/api/v1/transcripts/{id}` | Correct transcript text and verify acoustic confidence | Bearer JWT |

### 2.6 Meeting Intelligence (ACE) Endpoints
| HTTP Verb | Path | Description | Auth Required |
| :--- | :--- | :--- | :--- |
| `GET` | `/api/v1/meetings/{id}/intelligence` | Retrieve full ACE synthesis (Summary, Decisions, Actions, Risks) | Bearer JWT |
| `POST` | `/api/v1/meetings/{id}/intelligence/synthesize` | Trigger manual re-synthesis of meeting intelligence | Bearer JWT |
| `GET` | `/api/v1/meetings/{id}/decisions` | Retrieve verified organizational decisions | Bearer JWT |
| `GET` | `/api/v1/meetings/{id}/action-items`| Retrieve extracted action items with assignees | Bearer JWT |
| `PATCH`| `/api/v1/action-items/{id}` | Update action item status (`completed`, `in_progress`) | Bearer JWT |
| `GET` | `/api/v1/meetings/{id}/risks` | Retrieve operational risks and blockers | Bearer JWT |

### 2.7 Grounded Query Interface ("Ask ABCI-MI") Endpoints
| HTTP Verb | Path | Description | Auth Required |
| :--- | :--- | :--- | :--- |
| `POST` | `/api/v1/query` | Submit natural language question grounded in SKW | Bearer JWT |
| `GET` | `/api/v1/query/history` | Retrieve past query history with citation references | Bearer JWT |

### 2.8 Multi-Format Report Generation Endpoints
| HTTP Verb | Path | Description | Auth Required |
| :--- | :--- | :--- | :--- |
| `POST` | `/api/v1/meetings/{id}/reports` | Generate report in PDF 1.4, Markdown, JSON, or TXT | Bearer JWT |
| `GET` | `/api/v1/reports/{id}/download` | Download generated report binary | Bearer JWT |

### 2.9 Multilingual Translation Endpoints
| HTTP Verb | Path | Description | Auth Required |
| :--- | :--- | :--- | :--- |
| `POST` | `/api/v1/translations/meetings/{id}` | Translate meeting transcripts into target locale | Bearer JWT |
| `GET` | `/api/v1/translations/meetings/{id}` | Retrieve localized derived transcript turns | Bearer JWT |

### 2.10 Admin, Audit & Platform Integration Endpoints
| HTTP Verb | Path | Description | Auth Required |
| :--- | :--- | :--- | :--- |
| `GET` | `/api/v1/admin/audit-logs` | Query SHA-256 chained audit logs with filters | Bearer JWT (Admin) |
| `GET` | `/api/v1/admin/telemetry` | Query platform performance and error metrics | Bearer JWT (Admin) |
| `POST` | `/api/v1/integrations/webhooks/{provider}` | Ingest platform webhooks (Zoom, Meet, Teams) | Webhook Secret |

---

## 3. Real-Time WebSocket Protocols

### 3.1 Live Meeting Stream (`/api/v1/ws/meetings/{meeting_id}`)
- **Connection Handshake**: Subprotocol or query token authentication (`?token=<JWT>`).
- **Events Emitted by Server**:
  - `transcript_segment`: Live finalized speaker turn with timestamps and confidence.
  - `speaker_activity`: Current active speaker indication and volume meter.
  - `blackboard_update`: Incremental ACE decision, action item, or summary update.
  - `session_state_change`: Transition between `live`, `paused`, and `completed`.
