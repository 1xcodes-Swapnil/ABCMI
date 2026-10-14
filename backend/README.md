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
   - REAL ASR uses **MOSS-Transcribe-Diarize**; speaker validation uses the PyAnnote 3.1 pipeline.
   - Timestamps come from actual MOSS output. Local alignment accuracy and overlap separation accuracy are not verified.
3. **Indic Normalization (`app/ai/code_switch_intelligence.py`)**:
   - **Sarvam-1** is a text-completion model used by the existing normalization adapter. Local normalization accuracy is not verified; no local Mix-WER result has been established.
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
cd backend
python -m venv .venv
# Windows
# .venv\Scripts\activate
# macOS/Linux
# source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

The backend reads configuration from `backend/.env`, and defaults are defined in `backend/app/core/config.py`.

## Docker Compose startup

```bash
cd backend
cp .env.example .env
docker compose up --build
```

This starts the database, Redis, Qdrant, backend API, and the frontend dev server through the Compose file in `backend/docker-compose.yml`.

## Runtime dependencies that are explicitly modeled in code

The repository currently configures these runtime pieces in code:

- PostgreSQL via SQLAlchemy async engine
- Redis for event bus and cache usage
- Qdrant for semantic vector storage
- Local filesystem storage for uploaded audio and generated artifacts

## Optional and external AI integrations

The backend also includes code paths and benchmark tooling for:

- MOSS-Transcribe-Diarize ASR
- PyAnnote diarization verification
- Sarvam-style language normalization work
- Google Gemini-based text processing

These features depend on external model/data availability and are intentionally optional. If they are not configured in the runtime environment, the backend can still start with its core API and infrastructure defaults, but some AI features will be unavailable or degraded.

## Health checks

```bash
curl http://localhost:8000/api/v1/health
curl http://localhost:8000/api/v1/health/live
curl http://localhost:8000/api/v1/health/ready
```

## Test and validation

```bash
cd backend
pytest
```

The repository includes additional benchmark/validation utilities in `backend/cli.py` and the root-level benchmark scripts. Those are useful for environment probes, not a replacement for a normal application smoke test.
