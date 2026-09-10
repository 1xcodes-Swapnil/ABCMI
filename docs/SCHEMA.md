# Database & Vector Architecture Schema Specification (ABCI-MI)

## 1. Overview & Architecture Topology

The ABCI-MI (Adaptive Blackboard Collaborative Intelligence for Meeting Intelligence) persistence architecture implements a high-throughput, multi-tenant relational and vector data tier:

1. **Relational Tier (PostgreSQL 16+)**: ACID-compliant transactional persistence for tenants, users, meetings, audio metadata, hierarchical transcripts, analytics, knowledge objects, and cryptographic audit ledgers.
2. **Vector Tier (Qdrant)**: High-dimensional semantic indexing using HNSW (Hierarchical Navigable Small World) graphs with dense vector embeddings ($d=768$ / $d=1024$) for real-time grounded RAG and semantic search.
3. **Cache & Pub/Sub Tier (Redis 7+)**: Sub-millisecond state caching, Blackboard agent event broadcasting, and rate-limiting.

```
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                              ABCI-MI DATABASE TOPOLOGY                                 │
├──────────────────────────────────────────┬─────────────────────────────────────────────┤
│ Storage Engine                           │ Responsibility / Subsystems                 │
├──────────────────────────────────────────┼─────────────────────────────────────────────┤
│ PostgreSQL 16+ (SQLAlchemy Async ORM)    │ Users, Meetings, Transcripts, SKW Objects,   │
│                                          │ Reports, Audit Merkle Chains, System Config │
├──────────────────────────────────────────┼─────────────────────────────────────────────┤
│ Qdrant Vector Engine                     │ HNSW Dense Semantic Embeddings, Citations,  │
│                                          │ Cross-Meeting Retrieval & RRF Ranking       │
├──────────────────────────────────────────┼─────────────────────────────────────────────┤
│ Redis 7+ Pub/Sub                         │ Live Hypothesis Blackboard, WebSocket Push  │
└──────────────────────────────────────────┴─────────────────────────────────────────────┘
```

---

## 2. Entity-Relationship Diagram (ERD)

```
┌──────────────┐          ┌──────────────────┐          ┌─────────────────────┐
│    users     │1       * │     meetings     │1       * │     transcripts     │
│──────────────│──────────│──────────────────│──────────│─────────────────────│
│ id (PK UUID) │          │ id (PK UUID)     │          │ id (PK UUID)        │
│ email        │          │ host_id (FK)     │          │ meeting_id (FK)     │
│ role         │          │ title            │          │ status              │
│ tenant_id    │          │ status           │          │ language            │
└──────┬───────┘          │ language         │          └──────────┬──────────┘
       │                  └─────────┬────────┘                     │ 1
       │ 1                          │ 1                            │
       │                            │                              │ *
       │ *                          │ *                 ┌──────────▼──────────┐
┌──────▼───────┐          ┌─────────▼────────┐          │ transcript_segments │
│  audit_logs  │          │   participants   │          │─────────────────────│
│──────────────│          │──────────────────│          │ id (PK UUID)        │
│ id (PK UUID) │          │ id (PK UUID)     │          │ transcript_id (FK)  │
│ user_id (FK) │          │ meeting_id (FK)  │          │ speaker_label       │
│ prev_hash    │          │ user_id (FK)     │          │ start_time / end_time│
│ curr_hash    │          │ display_name     │          │ text / confidence   │
└──────────────┘          └──────────────────┘          └─────────────────────┘
       ▲
       │ 1
       │                  ┌──────────────────┐          ┌─────────────────────┐
       │ *                │ knowledge_objects│1       * │derived_translations │
       ├──────────────────│──────────────────│──────────│─────────────────────│
       │                  │ id (PK UUID)     │          │ id (PK UUID)        │
       │                  │ meeting_id (FK)  │          │ meeting_id (FK)     │
       │                  │ object_type      │          │ language_code       │
       │                  │ confidence_score │          │ translated_summary  │
       │                  │ status           │          │ payload (JSONB)     │
       │                  └──────────────────┘          └─────────────────────┘
```

---

## 3. Relational Table Specifications (PostgreSQL 16+)

### 3.1 `users` Table
Stores authenticated user identities, role-based access control (RBAC), and tenant groupings.

| Column Name | Type | Constraints | Default | Description |
| :--- | :--- | :--- | :--- | :--- |
| `id` | `UUID` | **PRIMARY KEY** | `gen_random_uuid()` | Unique user identifier |
| `email` | `VARCHAR(255)` | **NOT NULL, UNIQUE, INDEX** | — | User email address |
| `hashed_password` | `VARCHAR(255)` | **NOT NULL** | — | Argon2id / bcrypt password hash |
| `full_name` | `VARCHAR(255)` | `NULL` | `NULL` | User display name |
| `role` | `VARCHAR(50)` | **NOT NULL, INDEX** | `'participant'` | RBAC role (`admin`, `organizer`, `participant`, `auditor`) |
| `tenant_id` | `VARCHAR(100)` | **NOT NULL, INDEX** | `'default'` | Multi-tenant isolation partition identifier |
| `is_active` | `BOOLEAN` | **NOT NULL** | `TRUE` | Account active flag |
| `created_at` | `TIMESTAMPTZ` | **NOT NULL** | `NOW()` | Record creation timestamp |
| `updated_at` | `TIMESTAMPTZ` | **NOT NULL** | `NOW()` | Record modification timestamp |

---

### 3.2 `meetings` Table
Represents collaboration sessions, scheduled calls, and live audio processing jobs.

| Column Name | Type | Constraints | Default | Description |
| :--- | :--- | :--- | :--- | :--- |
| `id` | `UUID` | **PRIMARY KEY** | `gen_random_uuid()` | Unique meeting identifier |
| `title` | `VARCHAR(255)` | **NOT NULL** | — | Meeting title |
| `description` | `TEXT` | `NULL` | `NULL` | Meeting agenda or context description |
| `status` | `VARCHAR(50)` | **NOT NULL, INDEX** | `'created'` | State (`created`, `live`, `processing`, `completed`, `failed`) |
| `language` | `VARCHAR(10)` | **NOT NULL** | `'en'` | Primary session language code (`en`, `hi`, etc.) |
| `secondary_languages`| `JSONB` | `NULL` | `'[]'` | List of secondary languages for code-switching |
| `host_id` | `UUID` | **FOREIGN KEY (`users.id`)** | `NULL` | Meeting organizer / owner |
| `scheduled_start` | `TIMESTAMPTZ` | `NULL, INDEX` | `NULL` | Scheduled session start time |
| `actual_start` | `TIMESTAMPTZ` | `NULL` | `NULL` | Actual audio intake start timestamp |
| `actual_end` | `TIMESTAMPTZ` | `NULL` | `NULL` | Audio intake completion timestamp |
| `duration_seconds` | `INTEGER` | `NULL` | `NULL` | Total duration of audio stream in seconds |
| `tenant_id` | `VARCHAR(100)` | **NOT NULL, INDEX** | `'default'` | Multi-tenant isolation partition identifier |
| `metadata_json` | `JSONB` | `NULL` | `'{}'` | Custom platform flags and metadata |
| `created_at` | `TIMESTAMPTZ` | **NOT NULL** | `NOW()` | Record creation timestamp |
| `updated_at` | `TIMESTAMPTZ` | **NOT NULL** | `NOW()` | Record modification timestamp |

---

### 3.3 `transcripts` & `transcript_segments` Tables
Maintains hierarchical speech-to-text outputs with exact word timestamps and acoustic confidence scores.

#### `transcripts`
| Column Name | Type | Constraints | Default | Description |
| :--- | :--- | :--- | :--- | :--- |
| `id` | `UUID` | **PRIMARY KEY** | `gen_random_uuid()` | Unique transcript identifier |
| `meeting_id` | `UUID` | **FOREIGN KEY (`meetings.id`)**, **INDEX** | — | Parent meeting reference |
| `version` | `INTEGER` | **NOT NULL** | `1` | Transcript version sequence counter |
| `status` | `VARCHAR(50)` | **NOT NULL** | `'completed'` | Status (`in_progress`, `completed`, `verified`) |
| `overall_confidence`| `FLOAT` | `NULL` | `NULL` | Weighted mean confidence across all utterances |
| `primary_language` | `VARCHAR(10)` | **NOT NULL** | `'en'` | Dominant transcript language |
| `word_count` | `INTEGER` | **NOT NULL** | `0` | Total recognized word count |
| `created_at` | `TIMESTAMPTZ` | **NOT NULL** | `NOW()` | Record creation timestamp |
| `updated_at` | `TIMESTAMPTZ` | **NOT NULL** | `NOW()` | Record modification timestamp |

#### `transcript_segments`
| Column Name | Type | Constraints | Default | Description |
| :--- | :--- | :--- | :--- | :--- |
| `id` | `UUID` | **PRIMARY KEY** | `gen_random_uuid()` | Unique utterance segment identifier |
| `transcript_id` | `UUID` | **FOREIGN KEY (`transcripts.id`)**, **INDEX**| — | Parent transcript container |
| `sequence_number`| `INTEGER` | **NOT NULL, INDEX** | — | Sequential order in audio timeline |
| `speaker_label` | `VARCHAR(100)`| **NOT NULL, INDEX** | `'Speaker_0'` | Diarization cluster tag |
| `start_time` | `FLOAT` | **NOT NULL, INDEX** | — | Utterance onset timestamp (seconds) |
| `end_time` | `FLOAT` | **NOT NULL, INDEX** | — | Utterance offset timestamp (seconds) |
| `text` | `TEXT` | **NOT NULL** | — | Utterance transcript text |
| `confidence` | `FLOAT` | **NOT NULL** | `1.0` | Acoustic Conformer CTC posterior confidence |
| `language` | `VARCHAR(10)` | **NOT NULL** | `'en'` | Frame-level classified language ID |
| `is_code_switched`| `BOOLEAN` | **NOT NULL** | `FALSE` | Intra-sentential code-switch detected flag |
| `words_json` | `JSONB` | `NULL` | `'[]'` | Word-level array `[{word, start, end, conf}]` |
| `created_at` | `TIMESTAMPTZ` | **NOT NULL** | `NOW()` | Record creation timestamp |

---

### 3.4 `knowledge_objects` Table (Structured Knowledge Workspace - SKW)
Stores verified, typed cognitive outputs generated by ACE multi-agent reasoning.

| Column Name | Type | Constraints | Default | Description |
| :--- | :--- | :--- | :--- | :--- |
| `id` | `UUID` | **PRIMARY KEY** | `gen_random_uuid()` | Unique knowledge object identifier |
| `meeting_id` | `UUID` | **FOREIGN KEY (`meetings.id`)**, **INDEX** | — | Parent meeting reference |
| `object_type` | `VARCHAR(50)` | **NOT NULL, INDEX** | — | Type (`decision`, `action_item`, `risk`, `insight`, `summary`) |
| `title` | `VARCHAR(255)` | `NULL` | `NULL` | Short object headline |
| `content` | `TEXT` | **NOT NULL** | — | Full textual content / description |
| `confidence_score`| `FLOAT` | **NOT NULL** | `0.0` | Multi-signal fused confidence ($C_{\text{fused}} \in [0.0, 1.0]$) |
| `status` | `VARCHAR(50)` | **NOT NULL, INDEX** | `'draft'` | Lifecycle state (`draft`, `active`, `superseded`, `archived`) |
| `assignee` | `VARCHAR(255)`| `NULL, INDEX` | `NULL` | Responsible participant (for action items) |
| `due_date` | `TIMESTAMPTZ` | `NULL` | `NULL` | Due date timestamp (for action items) |
| `provenance_json` | `JSONB` | `NULL` | `'{}'` | Grounding links: `{segment_ids: [], timestamps: []}` |
| `version` | `INTEGER` | **NOT NULL** | `1` | Version sequence number for immutable lineage |
| `parent_id` | `UUID` | **FOREIGN KEY (`knowledge_objects.id`)** | `NULL` | Ancestor knowledge object if superseded |
| `created_at` | `TIMESTAMPTZ` | **NOT NULL** | `NOW()` | Record creation timestamp |
| `updated_at` | `TIMESTAMPTZ` | **NOT NULL** | `NOW()` | Record modification timestamp |

---

### 3.5 `derived_translations` Table
Stores non-destructive localized meeting representations across 17 supported locales.

| Column Name | Type | Constraints | Default | Description |
| :--- | :--- | :--- | :--- | :--- |
| `id` | `UUID` | **PRIMARY KEY** | `gen_random_uuid()` | Unique translation record identifier |
| `meeting_id` | `UUID` | **FOREIGN KEY (`meetings.id`)**, **INDEX** | — | Parent meeting reference |
| `language_code` | `VARCHAR(10)` | **NOT NULL, INDEX** | — | Target ISO-639 locale code (`es`, `ja`, `hi`, etc.) |
| `language_name` | `VARCHAR(100)`| **NOT NULL** | — | Human-readable language & script name |
| `translated_summary`| `TEXT` | **NOT NULL** | — | Localized executive summary |
| `payload` | `JSONB` | **NOT NULL** | `'{}'` | Full translation payload (decisions, actions, segments) |
| `created_at` | `TIMESTAMPTZ` | **NOT NULL** | `NOW()` | Record creation timestamp |
| `updated_at` | `TIMESTAMPTZ` | **NOT NULL** | `NOW()` | Record modification timestamp |

---

### 3.6 `audit_logs` Table (Cryptographic SHA-256 Merkle Chain)
Maintains a tamper-evident cryptographic ledger of all sensitive state transitions and operations.

| Column Name | Type | Constraints | Default | Description |
| :--- | :--- | :--- | :--- | :--- |
| `id` | `UUID` | **PRIMARY KEY** | `gen_random_uuid()` | Unique audit event identifier |
| `user_id` | `UUID` | **FOREIGN KEY (`users.id`)**, **INDEX** | `NULL` | Acting user reference |
| `tenant_id` | `VARCHAR(100)` | **NOT NULL, INDEX** | `'default'` | Tenant partition |
| `action` | `VARCHAR(100)`| **NOT NULL, INDEX** | — | Event type (`MEETING_CREATE`, `AUTH_LOGIN`, `TRANSLATION_SYNTHESIZE`) |
| `resource_type` | `VARCHAR(100)`| **NOT NULL** | — | Target entity (`meeting`, `knowledge_object`, `user`) |
| `resource_id` | `VARCHAR(255)`| **NOT NULL** | — | Target entity primary key |
| `status` | `VARCHAR(50)` | **NOT NULL** | `'SUCCESS'` | Outcome (`SUCCESS`, `FAILURE`, `DENIED`) |
| `details` | `JSONB` | `NULL` | `'{}'` | Event parameters and metadata payload |
| `ip_address` | `VARCHAR(45)` | `NULL` | `NULL` | Client IP address |
| `user_agent` | `TEXT` | `NULL` | `NULL` | Client user agent |
| `prev_hash` | `VARCHAR(64)` | **NOT NULL** | — | SHA-256 hash of previous ledger block ($H_{i-1}$) |
| `curr_hash` | `VARCHAR(64)` | **NOT NULL, UNIQUE** | — | SHA-256 hash of current block ($H_i$) |
| `created_at` | `TIMESTAMPTZ` | **NOT NULL, INDEX** | `NOW()` | Event timestamp |

---

## 4. Vector Database Schema (Qdrant)

### 4.1 Collection: `meeting_knowledge_embeddings`
Indexes knowledge objects, summaries, decisions, and segmented transcripts for Reciprocal Rank Fusion (RRF) search.

```json
{
  "collection_name": "meeting_knowledge_embeddings",
  "vectors": {
    "size": 768,
    "distance": "Cosine"
  },
  "hnsw_config": {
    "m": 16,
    "ef_construct": 100,
    "full_scan_threshold": 10000,
    "max_indexing_threads": 4
  },
  "optimizers_config": {
    "deleted_threshold": 0.2,
    "vacuum_min_vector_number": 1000,
    "default_segment_number": 2
  }
}
```

### 4.2 Vector Payload Structure
```json
{
  "id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
  "vector": [0.0124, -0.0452, 0.0891, "... (768 dimensions)"],
  "payload": {
    "meeting_id": "7a4cb6f8-2c52-4023-ad32-53b9a3bad142",
    "tenant_id": "default",
    "object_type": "decision",
    "knowledge_object_id": "d1c2b3a4-0000-4000-8000-000000000001",
    "text": "Adopt Crime in India dataset over Tourism data for the lab assignment.",
    "speaker_label": "Speaker_0",
    "start_time": 45.2,
    "end_time": 52.8,
    "confidence": 0.98,
    "language": "en",
    "created_at": "2026-08-25T10:00:00Z"
  }
}
```

---

## 5. Indexes, Constraints & Partitioning Strategy

1. **Foreign Key Indexes**: Every foreign key (`meeting_id`, `transcript_id`, `user_id`, `host_id`) is explicitly indexed with B-Tree indices to prevent sequential scan bottlenecks on joins.
2. **Tenant Partitioning**: Multi-tenant queries filter on `tenant_id` via composite indices `(tenant_id, created_at DESC)` and `(tenant_id, status)`.
3. **Temporal Search**: Time-window retrieval on transcript segments utilizes compound indices `(transcript_id, start_time ASC, end_time ASC)`.
4. **Cryptographic Integrity**: `curr_hash` enforces a `UNIQUE` index ensuring no two conflicting blocks can occupy the Merkle audit chain.
