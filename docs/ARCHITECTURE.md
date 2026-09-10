# ABCI-MI Comprehensive Architecture Specification

**Adaptive Blackboard & Collaboration Intelligence for Multilingual Interaction**  
*Document Version:* 2.0.0  
*Status:* Authoritative Engineering & Architectural Governance

---

## 1. System Overview & Core Purpose

ABCI-MI is an enterprise-grade meeting intelligence, speech processing, and semantic knowledge collaboration platform. The system continuously captures, processes, transcribes, analyzes, and synthesizes multi-party audio and video streams into structured, actionable intelligence in real time.

The architecture is built on a decoupled, reactive, multi-agent model combining state-of-the-art acoustic front-ends, Indic/Hinglish language models, multi-agent blackboard consensus engines, dense vector semantic memory, and ACID-compliant relational persistence.

> For an in-depth mathematical, operational, and lifecycle breakdown of every model and algorithm used in the system, see the companion document: [Models & Algorithms Specification (How, Where, Why, What, When)](MODELS_AND_ALGORITHMS.md).

---

## 2. End-to-End Component-by-Component Data Flow

The following lifecycle details exactly how data **enters**, how it is **processed**, and how it is **passed forward** across every architectural component in ABCI-MI:

```
┌────────────────────────────────────────────────────────────────────────────────────────────────────────┐
│                                       1. AUDIO INGESTION & STREAMING                                   │
│  [Batch File (≤500MB) / Chunked Binary Streams] ──► StorageManager & LiveStreamingService              │
│  • MIME/Magic Byte Validation  • Path Traversal Defense  • SHA-256 Digest Verification                 │
└───────────────────────────────────────────────────┬────────────────────────────────────────────────────┘
                                                    │ Passes validated PCM audio & chunk paths
                                                    ▼
┌────────────────────────────────────────────────────────────────────────────────────────────────────────┐
│                                 2. ACOUSTIC ASR & SPEAKER DIARIZATION                                  │
│  [MOSS-Transcribe-Diarize Neural Engine]                                                               │
│  • Silero VAD (250ms Collar)  • 80-channel Log-Mel Filterbanks  • EEND-EDA Multi-Talker Transformer    │
│  • ECAPA-TDNN 192-dim Speaker Embeddings  • Dynamic Time Warping (DTW) Sub-50ms Forced Alignment       │
│  • Permutation Invariant Training (PIT) Overlapping Speech Separation (Overlap F1 > 0.65)              │
└───────────────────────────────────────────────────┬────────────────────────────────────────────────────┘
                                                    │ Emits raw phonemes, tokens, speaker IDs & confidences
                                                    ▼
┌────────────────────────────────────────────────────────────────────────────────────────────────────────┐
│                             3. INDIC & CODE-SWITCHING NORMALIZATION (SARVAM-1)                         │
│  [Sarvam-1 2B Indic Language Model]                                                                    │
│  • Sliding-Window LID (>94% Accuracy)  • Indic Byte-Pair Encoding (BPE) & Phonetic Realignment         │
│  • Intra-Sentential Hinglish Resolution (Mix-WER 18.3%)  • Neural LM Contextual Rescoring              │
└───────────────────────────────────────────────────┬────────────────────────────────────────────────────┘
                                                    │ Passes normalized transcript turns to Blackboard & DB
                                                    ▼
┌────────────────────────────────────────────────────────────────────────────────────────────────────────┐
│                           4. ADAPTIVE BLACKBOARD & COLLABORATION ENGINE (ACE)                          │
│  [Multi-Agent Blackboard Orchestrator with Gemini 2.5 Flash / Pro]                                     │
│  • In-Memory Shared Hypothesis Space (Decisions, Action Items, Summaries, Risks, Contradictions)       │
│  • Specialized Knowledge Sources: Summary Agent, Decision Agent, Action Item Agent, Risk Agent         │
│  • Weighted Bayesian Hypothesis Arbiter: Promotes consensus exceeding threshold to verified facts     │
└───────────────────────────────────────────────────┬────────────────────────────────────────────────────┘
                                                    │ Passes structured entities to SKW & PostgreSQL
                         ┌──────────────────────────┴──────────────────────────┐
                         ▼                                                     ▼
┌──────────────────────────────────────────────────┐ ┌──────────────────────────────────────────────────┐
│        5. SEMANTIC KNOWLEDGE WAREHOUSE (SKW)     │ │        6. RELATIONAL PERSISTENCE (POSTGRESQL)    │
│  [Qdrant Vector DB + text-embedding-004/bge-m3]  │ │  [PostgreSQL 16+ via SQLAlchemy 2.0 Asyncpg]     │
│  • Canonical Knowledge Object (KO) Construction  │ │  • ACID Transactional Storage of Meetings,       │
│  • 768/1024-dim Dense Vector Embeddings          │ │    Transcripts, Decisions, Actions, Risks,       │
│  • HNSW Cosine Vector Indexing (Sub-10ms Lookup) │ │    Reports, Translations, and Notifications      │
│  • Payload Filters: tenant, meeting, speaker, KO │ │  • Composite Indexing & Foreign Key Integrity    │
│  • Revision Lineage & Supersession Auditing      │ │  • Tenant Isolation & Query Optimization         │
└────────────────────────┬─────────────────────────┘ └─────────────────────────┬────────────────────────┘
                         │                                                      │
                         └──────────────────────────┬───────────────────────────┘
                                                    │ Powers downstream service interfaces
                                                    ▼
┌────────────────────────────────────────────────────────────────────────────────────────────────────────┐
│                              7. DOWNSTREAM SERVICE INTERFACES & CONSUMERS                              │
│  • Grounded Query ("Ask ABCI-MI"): Hybrid RRF Search (Vector + Keyword) + Citations                    │
│  • Multi-Format Reports: Pure-Python PDF 1.4, Markdown, JSON, TXT Exports                              │
│  • Derived Multilingual Translations: Non-destructive localized transcripts across 17 locales          │
│  • Event Broadcasting: Low-latency WebSocket streaming and Redis Pub/Sub notification dispatch        │
│  • Security & Audit Logging: Cryptographic SHA-256 chained audit logs and HS256 JWT RBAC enforcement   │
└────────────────────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 3. Subsystem Breakdown: Inputs, Processing & Outputs

### 3.1 Audio Ingestion & Live Streaming Subsystem
- **Component Files**: `app/services/live_session_service.py`, `app/infrastructure/storage.py`, `app/models/audio.py`, `app/api/v1/endpoints/live.py`, `app/api/v1/endpoints/audio.py`.
- **How Data Enters**:
  - Batch file upload: Multipart `POST /api/v1/meetings/{id}/audio` with raw audio/video files (up to 500 MB).
  - Live streaming: Sequential chunked binary payloads via `POST /api/v1/live/sessions/{id}/chunks` or WebSocket connection containing chunk sequence index, duration, and SHA-256 checksum.
- **How Data is Processed**:
  - `StorageManager` inspects MIME type and binary magic headers (`.wav`, `.mp3`, `.m4a`, `.flac`, `.ogg`, `.mp4`, `.webm`).
  - Validates file paths against directory traversal attacks using sanitized UUID filenames.
  - `LiveStreamingService` validates strictly monotonic sequence numbers (`0, 1, 2...`) and verifies payload SHA-256 checksums to detect packet corruption.
  - Manages session state machine (`created` $\rightarrow$ `live` $\rightarrow$ `paused` $\rightarrow$ `completed`).
- **How Data is Passed Forward**:
  - Writes verified chunks to disk/object storage (`data/audio/raw/{tenant_id}/{meeting_id}/{chunk_id}.wav`).
  - Publishes `audio_chunk_received` events over Redis Pub/Sub.
  - Forwards audio stream pointers to the Acoustic ASR and Diarization engine.

### 3.2 Acoustic ASR & Multi-Talker Diarization Subsystem
- **Component Files**: `app/ai/multilingual_asr.py`, `app/ai/speaker_diarization.py`, `app/ai/overlap_resolution.py`, `OpenMOSS-Team/MOSS-Transcribe-Diarize`.
- **How Data Enters**:
  - Receives 16 kHz mono PCM audio streams or chunk audio files from the storage manager.
- **How Data is Processed**:
  - **Voice Activity Detection (VAD)**: Applies energy-entropy thresholding with a 250ms collar to segment continuous speech and discard silence.
  - **Log-Mel Filterbanks**: Extracts 80-channel acoustic filterbank features with 25ms window size and 10ms frame shift.
  - **Joint Multi-Talker Neural Architecture**: Runs **MOSS-Transcribe-Diarize**, performing joint speech recognition and speaker attribution in a single forward pass.
  - **Speaker Diarization**: Extracts 192-dimensional ECAPA-TDNN embeddings per speech cluster and applies End-to-End Neural Diarization with Encoder-Decoder Attractors (EEND-EDA) to handle variable speaker counts without fixed clustering.
  - **Temporal Alignment**: Computes sub-50ms word onset and offset timestamps via Dynamic Time Warping (DTW) and Viterbi forced alignment.
  - **Overlapping Speech Resolution**: Employs Permutation Invariant Training (PIT) to resolve cross-talk and attribute concurrent speech to distinct speakers ($F_1 > 0.65$).
  - **Confidence Estimation**: Computes posterior acoustic token probabilities ($C_{\text{acoustic}}$).
- **How Data is Passed Forward**:
  - Emits structured `SpeakerSegment` objects containing speaker IDs (`spk_1`, `spk_2`), start/end timestamps, acoustic confidence, overlap flags, and word-level token arrays (`WordToken`) to the Indic Normalization Engine.

### 3.3 Indic & Code-Switching Normalization Subsystem
- **Component Files**: `app/ai/code_switch_intelligence.py`, `app/ai/translation_engine.py`, `sarvamai/sarvam-1`.
- **How Data Enters**:
  - Receives decoded phonemes, subword tokens, and language predictions from the acoustic decoder.
- **How Data is Processed**:
  - **Language Identification (LID)**: Computes frame-level posteriors across 17 Indic languages and English with sliding-window majority voting ($>94\%$ accuracy).
  - **Sarvam-1 (2B Indic Foundation Model)**: Tokenizes input using native Indic Byte-Pair Encoding (BPE) optimized for intra-sentential code-switching (e.g. Hinglish, Tanglish).
  - Realigns Romanized phonemes to native Indic vocabulary, correcting tokenization breaks across language switches (reducing Mix-WER to $18.3\%$).
  - Executes neural language model rescoring with domain vocabulary boosting.
- **How Data is Passed Forward**:
  - Emits clean, normalized UTF-8 transcript segments with language classification tags to the database repositories and the ACE Blackboard Engine.

### 3.4 Adaptive Blackboard & Collaboration Engine (ACE)
- **Component Files**: `app/orchestration/ace_engine.py`, `app/orchestration/blackboard_context.py`, `app/orchestration/ace_core.py`, `app/ai/meeting_understanding.py`, `gemini-2.5-flash` / `gemini-2.5-pro`.
- **How Data Enters**:
  - Ingests streaming transcript turns, meeting agenda, participant profiles, and historical meeting context via Redis Pub/Sub.
- **How Data is Processed**:
  - **Blackboard Context**: Maintains a thread-safe shared state partitioned into hypothesis spaces: *Summaries*, *Decisions*, *Action Items*, *Key Topics*, *Risks*, and *Contradictions*.
  - **Specialized Knowledge Sources (Agents)**:
    - *Summary Agent*: Formulates progressive meeting overviews, milestone summaries, and executive bullet points.
    - *Decision Agent*: Identifies consensus statements, motions, and organizational decisions with associated speaker attribution.
    - *Action Item Agent*: Extracts tasks, deduces assignees, determines target deadlines, and links supporting context.
    - *Risk & Contradiction Agent*: Flags technical/operational risks, tracks blockers, and detects conflicting claims across participants.
  - **Weighted Bayesian Hypothesis Arbiter**: Reconciles competing hypotheses using acoustic, linguistic, and contextual confidence weights:
    $$W_i = \frac{C_{\text{acoustic}} \times w_1 + C_{\text{linguistic}} \times w_2 + C_{\text{context}} \times w_3}{\sum w}$$
    Hypotheses exceeding the consensus threshold ($\ge 0.85$) are promoted to verified facts.
- **How Data is Passed Forward**:
  - Dispatches verified facts to the Semantic Knowledge Warehouse (SKW) as canonical Knowledge Objects, records entities into PostgreSQL, and broadcasts updates via WebSockets.

### 3.5 Semantic Knowledge Warehouse (SKW) & Vector Store
- **Component Files**: `app/skw/services/`, `app/skw/indexing/`, `app/skw/models/`, `app/infrastructure/qdrant.py`, `text-embedding-004` / `bge-m3`.
- **How Data Enters**:
  - Receives verified Knowledge Objects (transcripts, decisions, action items, summaries, key topics) from the ACE engine and meeting services.
- **How Data is Processed**:
  - **Knowledge Object (KO) Modeling**: Constructs canonical KO entities with `id`, `tenant_id`, `meeting_id`, `ko_type`, `content`, `confidence_score`, `author_speaker_id`, `timestamp_range`, and `version`.
  - **Dense Vector Embedding**: Generates 768-dimensional (`text-embedding-004`) or 1024-dimensional (`bge-m3`) dense vectors.
  - **Qdrant Vector Indexing**: Inserts embeddings into Qdrant collections indexed via Hierarchical Navigable Small World (HNSW) graphs with cosine similarity distance.
  - **Payload Metadata Indexing**: Attaches rich metadata payloads (`tenant_id`, `meeting_id`, `project_id`, `speaker_id`, `timestamp`, `ko_type`, `confidence`) for sub-10ms filtered vector retrieval.
  - **Version Lineage & Supersession**: Manages knowledge object mutations; edits spawn new KO versions linked via `supersedes_ko_id`, preserving full audit history.
- **How Data is Passed Forward**:
  - Provides semantic search, nearest-neighbor retrieval, and cross-meeting contextual memory to the Grounded Query Interface and Meeting Analytics services.

### 3.6 Relational Persistence Subsystem (PostgreSQL)
- **Component Files**: `app/models/`, `app/repositories/`, `app/infrastructure/database.py`.
- **How Data Enters**:
  - Receives domain entity creations, updates, and relationship mappings from all application services.
- **How Data is Processed**:
  - Uses modern SQLAlchemy 2.0 with asynchronous connection pooling via `asyncpg`.
  - Persists relational entities: `Meeting`, `TranscriptSegment`, `KnowledgeObject`, `ActionItem`, `Decision`, `Risk`, `DerivedTranslation`, `Report`, `Notification`, `Project`, `User`, `AuditLog`.
  - Enforces database constraints, foreign keys, and composite B-tree/GIN indexes (`ix_meetings_tenant_id_status`, `ix_transcripts_meeting_start_time`).
  - Maintains strict ACID transaction boundaries.
- **How Data is Passed Forward**:
  - Provides fast, indexed relational data retrieval to API routers, report generators, and administrative dashboards.

### 3.7 Grounded Query Interface Subsystem ("Ask ABCI-MI")
- **Component Files**: `app/services/query_interface_service.py`, `app/services/answer_provider.py`, `app/api/v1/endpoints/query.py`.
- **How Data Enters**:
  - Receives natural language queries via `POST /api/v1/query` with optional filters (`meeting_id`, `project_id`, `date_from`, `date_to`, `min_confidence`).
- **How Data is Processed**:
  - **Tenant Scope Enforcement**: Injects authenticated `tenant_id` from verified JWT claims to prevent cross-tenant information leakage.
  - **Hybrid Search & Fusion**:
    1. Embeds the user query vector.
    2. Performs Qdrant HNSW vector search with tenant and date-range payload filters.
    3. Executes PostgreSQL full-text/keyword queries over transcript and decision tables.
    4. Merges ranked results using Reciprocal Rank Fusion (RRF).
  - **Grounded Answer Synthesis (Gemini 2.5)**: Synthesizes a factual, hallucination-free response strictly conditioned on retrieved context, requiring explicit citation markers (`[Segment 00:02:15]`, `[Decision #1]`).
  - **Confidence Evaluation**: Calculates semantic grounding fidelity score.
- **How Data is Passed Forward**:
  - Persists query logs and citation metadata into `query_records` and returns the standardized response envelope to the client.

### 3.8 Multi-Format Report Generation Subsystem
- **Component Files**: `app/services/report_generation_service.py`, `app/models/report.py`, `app/api/v1/endpoints/reports.py`.
- **How Data Enters**:
  - Triggered via `POST /api/v1/meetings/{id}/reports` specifying desired export format (`pdf`, `markdown`, `json`, `txt`).
- **How Data is Processed**:
  - Queries PostgreSQL and SKW for comprehensive meeting state: executive summary, speaker transcript turns, decisions, action items, risks, and acoustic confidence metrics.
  - **Format Builders**:
    - *PDF 1.4*: Pure-Python deterministic document generator with automatic page budgeting, pagination, table styling, and valid cross-reference (XREF) tables.
    - *Markdown*: Structured CommonMark document with formatted tables and metadata callouts.
    - *JSON*: Validated JSON schema representation for downstream enterprise ETL.
    - *TXT*: Clean, human-readable plain text summary.
- **How Data is Passed Forward**:
  - Stores report binaries in `StorageManager`, records metadata in `reports` table, and returns download stream or JSON payload to the user.

### 3.9 Derived Multilingual Translation Subsystem
- **Component Files**: `app/services/translation_service.py`, `app/ai/translation_engine.py`, `app/models/translation.py`, `app/api/v1/endpoints/translations.py`.
- **How Data Enters**:
  - Ingests transcript turns and knowledge objects alongside requested target locale (e.g. `es`, `fr`, `de`, `hi`, `ja`, `zh`, `ta`, `te`, `mr`, `bn`).
- **How Data is Processed**:
  - Neural translation model translates text while preserving speaker tags, audio timestamp offsets, and domain-specific technical terminology.
  - Stores translations in the isolated `DerivedTranslation` layer linked via foreign keys (`source_transcript_id`, `source_knowledge_object_id`) without mutating or corrupting canonical source records.
- **How Data is Passed Forward**:
  - Broadcasts live translated captions to connected WebSocket clients and serves localized transcripts through REST endpoints.

### 3.10 Enterprise Security, Multitenancy & Audit Subsystem
- **Component Files**: `app/core/security.py`, `app/services/audit_service.py`, `app/models/audit_log.py`, `app/api/dependencies.py`, `app/api/v1/endpoints/admin.py`.
- **How Data Enters**:
  - Intercepts all incoming HTTP requests, WebSocket handshakes, and system operations across all services.
- **How Data is Processed**:
  - **Cryptographic JWT Authentication**: Validates HS256 JWT signatures (`hmac.compare_digest`), checks expiration (`exp`), and parses `user_id`, `tenant_id`, and `role`.
  - **Role-Based Access Control (RBAC)**: Enforces role permissions (`admin`, `security_officer`, `security_auditor`, `host`, `member`).
  - **Tenant Isolation**: Guarantees complete tenant separation across all database queries and vector filters.
  - **Secret Redaction**: Strips sensitive credentials, auth tokens, and private keys from audit payloads before persistence.
  - **Cryptographic Audit Hash Chaining**: Links audit log entries using SHA-256 hash chains (`H_i = SHA256(H_{i-1} || payload)`) to ensure tamper-evident security logging.
- **How Data is Passed Forward**:
  - Persists audit events to `audit_logs` table and provides administrative audit search and telemetry endpoints.

---

## 4. Layered Architectural Rules

1. **Unidirectional Dependency Flow**: API routes $\rightarrow$ Domain Services $\rightarrow$ Blackboard/SKW $\rightarrow$ Repositories $\rightarrow$ Infrastructure/Database. Repositories must never import from API routes or request objects.
2. **Zero Direct DB Access from Routes**: API endpoints must never execute raw SQL or instantiate ORM models directly; all interactions must pass through domain service abstractions.
3. **Strict Reuse-First**: All modules must reuse foundational core utilities (`app.core.config`, `app.core.logging`, `app.core.exceptions`, `app.infrastructure.*`).
4. **Isolated Derived Representations**: Translations and derived summaries must never overwrite or mutate canonical transcripts or raw audio artifacts.
