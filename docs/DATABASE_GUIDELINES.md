# ABCI-MI Database & Persistence Guidelines

**Relational Engine:** PostgreSQL 16+ (via `asyncpg` & SQLAlchemy 2.0)  
**Vector Engine:** Qdrant Vector Database (Cosine Metric, HNSW Index)  
**Cache & Event Bus:** Redis 7+ (Pub/Sub & Key-Value Caching)  
**Document Version:** 2.0.0  
**Status:** Mandatory Engineering Standard

> **Note:** For the complete, field-level database, vector, and cryptographic schema specification, see [SCHEMA.md](SCHEMA.md).

---

## 1. Relational Persistence Architecture (PostgreSQL)

All relational models inherit from `BaseModel` (`app/models/base.py`) and use SQLAlchemy 2.0 declarative typing with `Mapped[...]` and `mapped_column(...)`.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                            PostgreSQL Core Tables                           │
├───────────────────┬───────────────────┬──────────────────┬──────────────────┤
│    `meetings`     │   `transcripts`   │  `action_items`  │   `decisions`    │
│  (Session Meta)   │  (Diarized Turns) │ (Tasks & Owners) │ (Consensus Items)│
├───────────────────┼───────────────────┼──────────────────┼──────────────────┤
│     `risks`       │  `translations`   │    `reports`     │ `notifications`  │
│ (Blockers/Hazards)│(Derived Locales)  │(PDF/MD/JSON Artifacts) (User Events)│
├───────────────────┼───────────────────┼──────────────────┼──────────────────┤
│  `query_records`  │   `audit_logs`    │    `projects`    │     `users`      │
│ (Grounded Q&A Log)│(SHA-256 Chained)  │(Multi-Meeting Hub) (RBAC Profiles)  │
└───────────────────┴───────────────────┴──────────────────┴──────────────────┘
```

### 1.1 Table Definitions & Relationships

| Table Name | Primary Key | Key Foreign Keys | Key Indexed Columns | Responsibility & Data Lifecycle |
| :--- | :--- | :--- | :--- | :--- |
| **`meetings`** | `id (UUID)` | `project_id`, `created_by` | `status`, `tenant_id`, `created_at` | Primary session entity tracking meeting title, status (`created`, `live`, `completed`), duration, language, and tenant isolation. |
| **`transcript_segments`** | `id (UUID)` | `meeting_id` | `meeting_id`, `start_time`, `speaker_id` | Chronological speaker turns with start/end millisecond offsets, speaker label, raw text, confidence score, and overlap flag. |
| **`knowledge_objects`** | `id (UUID)` | `meeting_id`, `supersedes_ko_id` | `tenant_id`, `meeting_id`, `ko_type`, `version` | Canonical knowledge units containing structured intelligence with revision lineage and supersession tracking. |
| **`action_items`** | `id (UUID)` | `meeting_id`, `assignee_id` | `meeting_id`, `status`, `due_date` | Actionable commitments extracted by ACE, containing title, assignee, deadline, status (`pending`, `in_progress`, `completed`), and priority. |
| **`decisions`** | `id (UUID)` | `meeting_id` | `meeting_id`, `created_at` | Explicit consensus decisions made during the session with rationale and supporting transcript citation references. |
| **`risks`** | `id (UUID)` | `meeting_id` | `meeting_id`, `severity` | Identified operational, technical, or timeline risks with severity ratings (`low`, `medium`, `high`, `critical`) and mitigation notes. |
| **`derived_translations`**| `id (UUID)`| `source_transcript_id`, `meeting_id` | `meeting_id`, `language_code` | Non-destructive localized transcripts across 17 languages linked to source turns without mutating original text. |
| **`reports`** | `id (UUID)` | `meeting_id` | `meeting_id`, `format`, `created_at` | Generated export artifacts (PDF 1.4, Markdown, JSON, TXT) with checksums, storage paths, and download metadata. |
| **`notifications`** | `id (UUID)` | `user_id`, `meeting_id` | `user_id`, `status`, `created_at` | In-app user notifications dispatched via Redis with deduplication keys and read status tracking. |
| **`query_records`** | `id (UUID)` | `meeting_id`, `user_id` | `tenant_id`, `created_at` | Grounded natural language query logs tracking questions, generated answers, citations, and confidence scores. |
| **`audit_logs`** | `id (UUID)` | `actor_id` | `tenant_id`, `action`, `created_at` | Cryptographically chained SHA-256 audit log records with secret redaction for enterprise compliance. |

---

## 2. Vector Persistence Architecture (Qdrant)

ABCI-MI utilizes **Qdrant** for dense vector similarity search, nearest-neighbor matching, and cross-meeting contextual memory retrieval.

### 2.1 Collection Schemas & Parameters

| Collection Name | Vector Dimensions | Distance Metric | Indexing Engine | Primary Content |
| :--- | :--- | :--- | :--- | :--- |
| **`meeting_knowledge_objects`** | **`768`** (`text-embedding-004`) or **`1024`** (`bge-m3`) | **Cosine** | **HNSW** (`m=16`, `ef_construct=100`) | Canonical Knowledge Objects (transcripts, decisions, summaries, action items, topic chunks). |
| **`speaker_voice_embeddings`** | **`192`** (`ECAPA-TDNN`) | **Cosine** | **HNSW** (`m=8`, `ef_construct=64`) | Speaker acoustic voice prints for cross-meeting speaker re-identification. |

### 2.2 Vector Payload Metadata Structure

Each vector point in `meeting_knowledge_objects` includes a structured, filterable JSON payload:

```json
{
  "point_id": "7b8e5c12-3a45-4e78-9012-3456789abcde",
  "tenant_id": "tenant-enterprise-prod-01",
  "meeting_id": "9e12a456-7890-4abc-def1-234567890123",
  "project_id": "proj-q3-architecture",
  "ko_type": "decision",
  "speaker_id": "spk_1",
  "speaker_name": "Dr. Aris Thorne",
  "start_seconds": 185.4,
  "end_seconds": 214.2,
  "confidence": 0.96,
  "version": 1,
  "created_at": "2026-08-25T10:15:30Z",
  "text": "Decided to adopt MOSS-Transcribe-Diarize with Sarvam-1 Indic LM on vLLM backend."
}
```

### 2.3 Vector Data Flow
1. **Entry**: ACE Blackboard promotes a verified hypothesis (e.g. Decision) to a canonical Knowledge Object.
2. **Processing**: SKW indexing service calls the embedding model to generate a dense vector and writes the point with payload to Qdrant.
3. **Forwarding**: Qdrant index enables sub-10ms similarity queries executed by `QueryInterfaceService` with strict tenant and meeting payload filters.

---

## 3. Caching & Real-Time Event Bus (Redis)

Redis 7+ powers transient caching, live audio chunk buffering, and multi-agent pub/sub messaging.

### 3.1 Redis Channel & Key Conventions

| Key / Channel Pattern | Type | TTL / Retention | Purpose |
| :--- | :--- | :--- | :--- |
| `meeting:{meeting_id}:live_state` | `Hash` | 24 Hours | Transient session state (status, current sequence index, active participants). |
| `channel:meeting:{meeting_id}:transcripts` | `Pub/Sub` | Real-time | Live broadcast of finalized transcript segments to connected WebSockets. |
| `channel:meeting:{meeting_id}:blackboard` | `Pub/Sub` | Real-time | Multi-agent hypothesis events dispatched between ACE knowledge sources. |
| `notification:dedup:{sha256_hash}` | `String` | 1 Hour | Idempotency guard preventing duplicate notification dispatch. |
| `rate_limit:{tenant_id}:{user_id}` | `String` | 60 Seconds | API rate limiting sliding window counter. |

---

## 4. Query Performance & Indexing Standards

1. **Composite Indexes for Multitenancy**: Every query filtering by `tenant_id` and `created_at` or `status` uses composite B-tree indexes:
   ```python
   Index("ix_meetings_tenant_status", "tenant_id", "status")
   Index("ix_transcripts_meeting_time", "meeting_id", "start_time")
   Index("ix_audit_tenant_time", "tenant_id", "created_at")
   ```
2. **Asynchronous Session Hygiene**: Database sessions must always be obtained via the async context manager `get_async_db()`. Sessions automatically roll back upon uncaught exceptions.
3. **No Direct Driver Calls**: Domain services must query repositories; direct raw SQL in API route handlers is strictly prohibited.
