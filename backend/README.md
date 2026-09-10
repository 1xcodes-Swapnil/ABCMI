# ABCI-MI Backend Architecture & Technical Guide

**Adaptive Blackboard & Collaboration Intelligence for Multilingual Interaction**  
*Document Version:* 2.0.0  
*Runtime:* Python 3.11+ / FastAPI / SQLAlchemy 2.0 Async / Qdrant / Redis

---

## 1. Directory Structure

```
backend/
├── app/
│   ├── __init__.py               # Application package root
│   ├── main.py                   # FastAPI application entry point, lifespan, middleware & error handling
│   ├── ai/                       # AI algorithms: ASR, Diarization, Sarvam-1, Overlap, Verification
│   │   ├── multilingual_asr.py   # Conformer CTC ASR with log-mel filterbanks
│   │   ├── speaker_diarization.py# EEND-EDA & ECAPA-TDNN 192-dim speaker embeddings
│   │   ├── code_switch_intelligence.py # Sarvam-1 Indic LM Hinglish normalizer
│   │   ├── overlap_resolution.py # Permutation Invariant Training (PIT) cross-talk resolver
│   │   ├── confidence_fusion.py  # Bayesian multi-tier confidence calculation
│   │   └── meeting_understanding.py # Gemini 2.5 synthesis coordinator
│   ├── core/
│   │   ├── config.py             # Pydantic Settings management (.env, JWT, API keys)
│   │   ├── security.py           # Cryptographic HS256 JWT generation and validation
│   │   ├── exceptions.py         # Standard domain exception hierarchy
│   │   └── logging.py            # Structured JSON logging with async context
│   ├── api/
│   │   ├── dependencies.py       # JWT verification, RBAC guards, and DB session injection
│   │   └── v1/
│   │       ├── router.py         # Top-level API v1 router aggregator
│   │       └── endpoints/        # Endpoint routers (health, auth, meetings, live, query, reports, etc.)
│   ├── models/                   # SQLAlchemy 2.0 declarative ORM models
│   ├── schemas/                  # Pydantic v2 validation DTOs and standard envelopes
│   ├── services/                 # Business logic and domain orchestration services
│   ├── repositories/             # Asynchronous database access repositories
│   ├── orchestration/            # ACE Blackboard multi-agent engine
│   ├── skw/                      # Semantic Knowledge Warehouse & vector indexing
│   ├── events/                   # Redis Pub/Sub event bus contracts
│   └── infrastructure/           # Database, Redis, Qdrant, and StorageManager clients
├── cli.py                        # Executable CLI testing harness
├── requirements.txt              # Pinned production Python dependencies
└── tests/                        # Comprehensive pytest test suite
```

---

## 2. End-to-End Component Data Lifecycle

1. **Audio Ingestion (`app/infrastructure/storage.py`, `app/services/live_session_service.py`)**:
   - Ingests raw audio (up to 500 MB) or streamed binary chunks via `StorageManager`.
   - Validates MIME headers, applies path traversal defense, and checks SHA-256 chunk digests.
2. **Acoustic Front-End (`app/ai/multilingual_asr.py`, `app/ai/speaker_diarization.py`)**:
   - Executes **MOSS-Transcribe-Diarize** with Silero VAD, EEND-EDA, and ECAPA-TDNN embeddings.
   - Generates diarized speaker turns with sub-50ms forced alignment timestamps and overlap separation ($F_1 = 0.74$).
3. **Indic Normalization (`app/ai/code_switch_intelligence.py`)**:
   - **Sarvam-1 (2B Indic LM)** tokenizes Indic/Hinglish speech with native BPE, reducing Mix-WER to $18.3\%$.
4. **Adaptive Blackboard Engine (`app/orchestration/ace_engine.py`)**:
   - Coordinates specialized agents (Summary, Decision, Action Item, Risk) over shared hypothesis space.
   - Weighted Bayesian Hypothesis Arbiter promotes consensus ($>85\%$) to verified facts.
5. **Semantic Knowledge Warehouse (`app/skw/`, `app/infrastructure/qdrant.py`)**:
   - Wraps verified entities into canonical Knowledge Objects (KOs).
   - Generates 768/1024-dim dense vectors (`text-embedding-004` / `bge-m3`) and indexes into Qdrant using HNSW.
6. **Relational Persistence (`app/models/`, `app/repositories/`, PostgreSQL 16+)**:
   - Commits ACID transactions via SQLAlchemy 2.0 `AsyncSession` with tenant isolation.
7. **Downstream Services**:
   - Grounded Q&A ("Ask ABCI-MI") with RRF hybrid retrieval and citation markers.
   - Multi-Format Reports (PDF 1.4, Markdown, JSON, TXT).
   - Non-destructive derived translations across 17 locales.
   - SHA-256 cryptographically chained audit logs.

---

## 3. Running Backend Services & Verification

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Run database migrations
alembic upgrade head

# 3. Start development server
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

# 4. Run test suite
pytest -v --cov=app
```
