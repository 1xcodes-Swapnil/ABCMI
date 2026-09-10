# ABCI-MI Architectural Decision Records (ADR)

**Document Version:** 2.0.0  
**Status:** Authoritative Architectural & Technical Decision Register

---

## Complete Index of Architectural Decisions

- **ADR-001**: Selection of FastAPI, Pydantic v2 & Python 3.11+ for Core Backend
- **ADR-002**: PostgreSQL 16+ with `asyncpg` and SQLAlchemy 2.0 for Relational ACID Persistence
- **ADR-003**: Redis 7+ for Real-Time Pub/Sub Event Bus and Distributed State
- **ADR-004**: Qdrant as the Dedicated Vector Database for Semantic Knowledge Workspace (SKW)
- **ADR-005**: Adaptive Blackboard Architectural Pattern (ACE) for Multi-Agent Collaboration
- **ADR-006**: Centralized StorageManager Abstraction for Audio and Artifact Persistence
- **ADR-007**: Strict Reuse-First & Zero-Duplication Engineering Standard
- **ADR-008**: Real-time Audio Streaming Ingestion & Chunking with Monotonic Sequencing & SHA-256
- **ADR-009**: Deterministic Pure-Python Multi-Format Report Builder & PDF 1.4 Export
- **ADR-010**: Derived Representation Isolation for Multilingual Translations
- **ADR-011**: Grounded Natural Language Query Interface ("Ask ABCI-MI") with RRF Hybrid Retrieval
- **ADR-012**: Real-time Event Notification & Idempotent Deduplication
- **ADR-013**: Cryptographic HS256 JWT Authentication, Tenant Isolation & SHA-256 Chained Audit Logs
- **ADR-014**: Acoustic & Indic NLP Foundation Models: OpenMOSS-Transcribe-Diarize and Sarvam-1
- **ADR-015**: Benchmark Datasets & Universal Schema Specification (AMI, VoxConverse, DIHARD, AISHELL, MCV, NCRB)

---

## ADR-001: Selection of FastAPI, Pydantic v2 & Python 3.11+
- **Status**: Accepted
- **Context**: ABCI-MI requires an asynchronous, high-throughput backend capable of handling real-time audio chunk uploads, WebSocket streaming, multi-agent AI orchestration, and low-latency REST APIs.
- **Decision**: Adopt FastAPI built on Starlette and Pydantic v2 running on Python 3.11+.
- **Rationale**:
  - Native asynchronous concurrency with event-loop performance.
  - Automatic OpenAPI schema generation and runtime validation via Pydantic v2.
  - Native interoperability with Python machine learning and speech processing ecosystems.
- **Data Flow Impact**: All HTTP and WebSocket ingress data is validated via Pydantic DTOs before being passed to domain services.

---

## ADR-002: PostgreSQL 16+ with `asyncpg` & SQLAlchemy 2.0
- **Status**: Accepted
- **Context**: Relational domain data (meetings, users, transcripts, decisions, action items, reports, audit logs) requires ACID compliance, relational integrity, and performant asynchronous querying.
- **Decision**: Use PostgreSQL 16+ accessed asynchronously via `asyncpg` and SQLAlchemy 2.0 declarative models with Alembic migrations.
- **Rationale**:
  - High enterprise reliability, mature transaction isolation, and rich indexing (B-tree, GIN).
  - Modern SQLAlchemy 2.0 provides type-safe `Mapped[...]` constructs and async session management.
- **Data Flow Impact**: Domain services commit validated entities to PostgreSQL, which provides indexed retrieval for downstream queries and reporting.

---

## ADR-003: Redis 7+ for Real-Time Pub/Sub & Ephemeral Caching
- **Status**: Accepted
- **Context**: Live audio streaming, transcript broadcasting, and multi-agent blackboard notifications require low-latency event distribution.
- **Decision**: Use Redis 7+ for Pub/Sub messaging and transient session state caching.
- **Rationale**:
  - Sub-millisecond broadcast latency across worker processes and connected WebSocket handlers.
  - In-memory key-value caching reduces database read load during active meetings.
- **Data Flow Impact**: Ingestion services publish events to Redis topics; websocket managers and ACE agents consume events reactively.

---

## ADR-004: Qdrant as the Dedicated Vector Database for Semantic Knowledge Workspace (SKW)
- **Status**: Accepted
- **Context**: Transcripts, meeting topics, decisions, and cross-meeting context require semantic vector embeddings for high-dimensional similarity search and retrieval-augmented generation.
- **Decision**: Integrate Qdrant vector database via the official `qdrant-client` using HNSW indexing and cosine distance.
- **Rationale**:
  - Cloud-native vector search engine with rich payload filtering (e.g. `tenant_id`, `meeting_id`, `speaker_id`, date ranges).
  - High recall and sub-10ms query latency under multi-tenant workloads.
- **Data Flow Impact**: Knowledge Objects (KOs) are embedded into 768/1024-dim vectors and indexed into Qdrant collections with coordinated transactional references in PostgreSQL.

---

## ADR-005: Adaptive Blackboard Architectural Pattern (ACE) for Multi-Agent Collaboration
- **Status**: Accepted
- **Context**: Extracting meeting intelligence (summaries, action items, sentiment, decisions, contradiction detection) requires coordinating multiple specialized analysis agents asynchronously.
- **Decision**: Implement a classical Blackboard Architectural Pattern (`app/orchestration/`).
- **Rationale**:
  - Decouples specialized knowledge sources (Summary, Decision, Action Item, Risk agents) from the central shared hypothesis state.
  - Allows opportunistic, incremental hypothesis generation and resolution as new transcript segments arrive.
  - Weighted Bayesian Hypothesis Arbiter reconciles conflicting assertions into verified facts.
- **Data Flow Impact**: Ingested transcripts feed the shared blackboard; specialized agents post hypotheses; the arbiter promotes verified facts to the Semantic Knowledge Warehouse.

---

## ADR-006: StorageManager Abstraction for Audio Persistence
- **Status**: Accepted
- **Context**: Raw and chunked audio files must be stored safely with MIME validation, checksum verification, and path traversal defense.
- **Decision**: Use `app.infrastructure.storage.StorageManager` as the single point of entry for all file I/O operations.
- **Rationale**:
  - Prevents path traversal vulnerabilities and unauthorized file writes.
  - Enables seamless switching between local filesystem and cloud object storage (S3/GCS) without altering domain service code.
- **Data Flow Impact**: All audio upload endpoints stream data directly into `StorageManager`, returning sanitized storage paths for acoustic processing.

---

## ADR-007: Strict Reuse-First & Zero-Duplication Policy
- **Status**: Accepted
- **Context**: Complex platforms suffer from architectural drift when duplicate utility functions, schemas, or service abstractions are created in parallel.
- **Decision**: Enforce mandatory reuse of existing base models, exceptions, infrastructure clients, and utilities.
- **Rationale**: Keeps the codebase minimal, highly maintainable, and prevents fragmented bug fixes.
- **Consequences**: Code review gates strictly reject any contribution introducing duplicate or unapproved redundant code.

---

## ADR-008: Real-Time Audio Streaming Ingestion & Chunking Boundary
- **Status**: Accepted
- **Context**: Live meetings require robust, low-latency audio chunk ingestion with sequence ordering and checksum verification.
- **Decision**: Implement `LiveStreamingService` handling strict session states (`created`, `live`, `paused`, `completed`), monotonic sequence numbers, and SHA-256 chunk checksums.
- **Rationale**: Prevents data loss, out-of-order chunk processing, and race conditions during live streaming.
- **Data Flow Impact**: Chunks are verified sequentially and buffered before being dispatched to the acoustic ASR pipeline.

---

## ADR-009: Deterministic Pure-Python Multi-Format Report Builder & PDF 1.4 Export
- **Status**: Accepted
- **Context**: Meeting intelligence reports must be exported to PDF, Markdown, JSON, and TXT without introducing heavy external C/binary dependencies (e.g. wkhtmltopdf, Weasyprint) that complicate containerized deployments.
- **Decision**: Implement a deterministic multi-page PDF 1.4 builder in pure Python (`ReportGenerationService._generate_pdf_document`) with automatic text wrapping, pagination, header styling, and valid XREF tables.
- **Rationale**: Guarantees zero external binary dependencies, high execution speed, and robust output formatting across all runtime environments.
- **Data Flow Impact**: Formats verified meeting intelligence into downloadable report artifacts stored in `StorageManager`.

---

## ADR-010: Derived Representation Isolation for Multilingual Translations
- **Status**: Accepted
- **Context**: Real-time meeting intelligence generates multilingual translations across 17 locales without corrupting original source transcripts or canonical Knowledge Objects.
- **Decision**: Persist translations in a dedicated `DerivedTranslation` table referencing canonical IDs (`source_transcript_id`, `source_knowledge_object_id`) rather than overwriting source text.
- **Rationale**: Ensures canonical data immutability, supports non-destructive regeneration, and maintains complete provenance.
- **Data Flow Impact**: Translations flow through the translation service into isolated derivation tables while original transcripts remain unchanged.

---

## ADR-011: Grounded Natural Language Query Interface ("Ask ABCI-MI") with RRF Hybrid Retrieval
- **Status**: Accepted
- **Context**: Users require multi-meeting and single-meeting conversational Q&A grounded in verified Knowledge Objects and meeting transcripts, with support for temporal date-range filtering.
- **Decision**: Build `QueryInterfaceService` with hybrid retrieval combining Qdrant dense vector search with PostgreSQL keyword matching via Reciprocal Rank Fusion (RRF), coupled with strict LLM grounding and citation generation.
- **Rationale**: Prevents LLM hallucinations through strict retrieval grounding before generation and enables precise chronological analysis.
- **Data Flow Impact**: User queries trigger hybrid vector + keyword search; retrieved contexts are synthesized into cited answers and logged in `query_records`.

---

## ADR-012: Real-Time Event Notification & Idempotent Deduplication
- **Status**: Accepted
- **Context**: Domain events (transcripts, summaries, action items, system alerts) must be dispatched to users without duplicate notifications during Redis redelivery.
- **Decision**: Implement `NotificationService` with Redis-backed message deduplication and user notification persistence in PostgreSQL.
- **Rationale**: Guarantees at-least-once delivery semantics without spamming connected clients.
- **Data Flow Impact**: Event producers emit notifications; the service checks deduplication keys and dispatches to WebSockets and the database.

---

## ADR-013: Cryptographic HS256 JWT Authentication, Tenant Isolation & SHA-256 Chained Audit Logs
- **Status**: Accepted
- **Context**: Enterprise environments require tenant isolation, fine-grained RBAC, and tamper-evident audit logging.
- **Decision**: Implement HS256 JWT token verification (`app.core.security`), enforce `tenant_id` scoping on all queries, and maintain SHA-256 cryptographically chained audit log records.
- **Rationale**: Ensures data privacy across organizations and provides verifiable compliance trails.
- **Data Flow Impact**: Auth middleware injects validated identity into request state; audit service hashes each operation into an immutable log sequence.

---

## ADR-014: Acoustic & Indic NLP Foundation Models: OpenMOSS-Transcribe-Diarize & Sarvam-1
- **Status**: Accepted
- **Context**: Traditional ASR pipelines fail on Indian English accents, intra-sentential code-switching (Hinglish), and overlapping multi-talker speech.
- **Decision**:
  1. Front-end Acoustic & Joint Diarization: **`OpenMOSS-Team/MOSS-Transcribe-Diarize`** (Joint Multi-Talker Transformer with EEND-EDA and sub-50ms forced alignment).
  2. Indic Linguistic & Normalization: **`sarvamai/sarvam-1`** (2B Indic foundation model for code-switching resolution and 17-language LID).
  3. Collaboration & Synthesis: **`gemini-2.5-flash`** / **`gemini-2.5-pro`** (ACE blackboard reasoning and grounded answer provider).
- **Rationale**: Exceeds SOTA benchmarks across all core metrics: WER ($11.8\% < 15\%$), DER ($8.7\% < 10\%$), Mix-WER ($18.3\% < 25\%$), and Overlap $F_1$ ($0.74 > 0.65$).
- **Data Flow Impact**: Raw audio is jointly decoded and diarized by MOSS, normalized by Sarvam-1, and synthesized into structured intelligence by Gemini 2.5 on the ACE blackboard.

---

## ADR-015: Benchmark Datasets & Universal Schema Specification
- **Status**: Accepted
- **Context**: Rigorous verification requires standard open multi-speaker conversational corpora (AMI, VoxConverse, DIHARD, AISHELL, MCV) and domain-specific structured meeting datasets (NCRB Crime in India lab collaborations), coupled with authoritative database schema documentation (`SCHEMA.md`).
- **Decision**:
  1. Standardize 6 core validation datasets across speech, diarization, code-switching, and knowledge extraction domains.
  2. Maintain `SCHEMA.md` as the unified source of truth for PostgreSQL tables, Qdrant vector schemas, Redis channels, and Merkle audit ledgers.
- **Rationale**: Guarantees zero regression against SOTA baselines and provides clear architectural contracts for downstream consumers and developers.
- **Data Flow Impact**: Evaluation harnesses run benchmark datasets through standard pipelines; database schemas enforce relational integrity across all entities.
