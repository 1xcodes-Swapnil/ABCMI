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
# 1. Install dependencies
pip install -r requirements.txt

# 2. Run database migrations
alembic upgrade head

# 3. Start development server
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

# 4. Run test suite
pytest -v --cov=app
```

## Local REAL validation checkpoint

Run commands from the repository root with the Python environment containing the
existing compatible torch/CUDA packages. Additional adapter dependencies are in
`backend/requirements-real.txt`. The recorded local environment uses Python 3.11.9,
torch/torchaudio 2.6.0+cu124, Transformers 5.16.1, pyannote.audio 4.0.7 and
PyAV 17.1.0. The version-checked `backend/scripts/patch_pyannote_407.py` fixes
the unused PLDA load for the 3.1 agglomerative pipeline; its original is backed up.
No cached model files are modified.

Configure `EXECUTION_MODE=REAL`, `HF_HOME`, `HUGGINGFACE_HUB_CACHE`,
`OPENMOSS_CACHE_DIR`, `OPENMOSS_DEVICE` and a valid `HF_TOKEN` in the existing
backend environment file. Shared local cache: `F:/hf-cache/hub`.

```powershell
# Inspect; provisioning reuses valid existing files and downloads missing files only.
py -3.11 backend/scripts/provision_real_models.py --dry-run
py -3.11 -m backend.cli --check-real-models
py -3.11 -m backend.cli --check-real-mode

# Use an actual recording under data/audio/raw. Keep stage arguments identical.
py -3.11 -m backend.cli real-smoke --stage moss --audio data/audio/raw/ES2002a.Mix-Headset.wav --duration 15
py -3.11 -m backend.cli real-smoke --stage pyannote --audio data/audio/raw/ES2002a.Mix-Headset.wav --duration 15
py -3.11 -m backend.cli real-smoke --stage sarvam --audio data/audio/raw/ES2002a.Mix-Headset.wav --duration 15
```

`--check-real-models` checks required files and weight shards, not inference.
`--check-real-mode` checks imports, processor loading and device allocation, not
generation. `real-smoke` invokes existing adapters; it returns exit 1 on failure
and saves structural traces and actual model output under `e2e_validation/real_local`.
Unavailable confidence/language remain null; timestamps are never manufactured.
Windows MOSS decoding uses its official PyAV alternative when torchcodec is unusable;
PyAnnote receives actual preloaded waveform tensors.

Local REAL production transcript validation passed on ES2014a at 71–81 seconds:
MOSS generated three retained segments, PyAnnote executed, all 13 ACE tasks completed,
and PostgreSQL commit plus an independent session read-back matched the CLI transcript.
SKW, learned Qdrant embeddings and Redis publication also completed. Evidence:
`e2e_validation/real_local/ES2014a.Mix-Headset_71_10_9d29e308566b/production_meeting.json`.
The same excerpt passed a separate two-chunk REAL ASR run (8 s chunks, 3 s overlap).
This verifies a short persisted transcript, not full-length meeting processing,
semantic summary quality, or speaker accuracy. MOSS and PyAnnote disagreed on one
speaker turn. RTTM comparison had zero eligible matched intervals; timestamp
accuracy remains NOT VERIFIED. Sarvam bounded generation passed; normalization
accuracy remains NOT VERIFIED and original MOSS text is preserved.

Cached FLEURS Parquet snapshots are supported locally via `FLEURS_DATASET_ROOT`
pointing to the snapshot directory; selected original audio bytes are materialized
under `BENCHMARK_DATA_DIR`, outside the shared cache. No dataset download is needed.
Benchmark success requires nonempty REAL output and successful required diarization;
failures return CLI exit 1. Kaggle notebook evidence is not local evidence.
