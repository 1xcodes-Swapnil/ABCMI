# ABCI-MI

Adaptive Blackboard & Collaboration Intelligence for Multilingual Interaction.

## Project overview

ABCI-MI is a meeting-intelligence application with a Python FastAPI backend, a React + Vite dashboard, and supporting validation/benchmark tooling. The current codebase includes:

- backend API in `backend/app/`
- React frontend in `src/`
- benchmark and validation helpers under `backend/cli.py`, root benchmark scripts, and `e2e_validation/`
- PostgreSQL, Redis, and Qdrant integrations for persistence and semantic workflows
- optional AI adapters for MOSS, PyAnnote, Sarvam-style normalization, and Gemini-based text processing

## Complete Component Data Flow & Engineering Architecture

```text
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
│  • Sliding-Window LID  • Indic Byte-Pair Encoding (BPE) & Phonetic Realignment                       │
│  • Intra-Sentential Hinglish Resolution  • Neural LM Contextual Rescoring                            │
└───────────────────────────────────────────────────┬────────────────────────────────────────────────────┘
                                                    │ Passes normalized transcript turns to Blackboard & DB
                                                    ▼
┌────────────────────────────────────────────────────────────────────────────────────────────────────────┐
│                           4. ADAPTIVE BLACKBOARD & COLLABORATION ENGINE (ACE)                          │
│  [Multi-Agent Blackboard Orchestrator]                                                                  │
│  • Shared Hypothesis Space  • Summary / Decision / Action Item / Risk orchestration                  │
│  • Knowledge coordination and downstream service hooks                                               │
└───────────────────────────────────────────────────┬────────────────────────────────────────────────────┘
                                                    │ Passes structured entities to SKW & PostgreSQL
                         ┌──────────────────────────┴──────────────────────────┐
                         ▼                                                     ▼
┌──────────────────────────────────────────────────┐ ┌──────────────────────────────────────────────────┐
│        5. SEMANTIC KNOWLEDGE WAREHOUSE (SKW)     │ │        6. RELATIONAL PERSISTENCE (POSTGRESQL)    │
│  [Qdrant Vector DB]                              │ │  [PostgreSQL 16+ via SQLAlchemy Async]           │
│  • Canonical Knowledge Object construction        │ │  • ACID storage of meetings, transcripts,        │
│  • Dense vector embeddings and retrieval           │ │    decisions, actions, risks, reports, and        │
│  • Query-time filtering and semantic memory        │ │    notifications                                  │
└────────────────────────┬─────────────────────────┘ └─────────────────────────┬────────────────────────┘
                         │                                                      │
                         └──────────────────────────┬───────────────────────────┘
                                                    │ Powers downstream service interfaces
                                                    ▼
┌────────────────────────────────────────────────────────────────────────────────────────────────────────┐
│                              7. DOWNSTREAM SERVICE INTERFACES & CONSUMERS                              │
│  • Grounded Query (Ask ABCI-MI): Hybrid retrieval + citations                                        │
│  • Multi-Format Reports: Markdown, JSON, TXT, and related exports                                    │
│  • Derived multilingual translations and notifications                                             │
│  • Event broadcasting, storage, and audit-style service integrations                                │
└────────────────────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## Reference benchmark targets (not guaranteed by this checkout)

The repository contains benchmark scripts and design notes for AI-quality targets. These numbers should be treated as project reference targets, not as verified claims for every environment in this checkout.

| Metric | Reference target | Notes |
| :--- | :--- | :--- |
| WER | `< 15.0%` | Target for ASR quality in project design notes |
| CER | `< 8.0%` | Target for character-level accuracy |
| DER | `< 10.0%` | Target for diarization robustness |
| Mix-WER | `< 25.0%` | Target for normalization quality |
| Overlap F1 | `> 0.65` | Target for overlapping-speech handling |
| LID accuracy | `> 90.0%` | Target for language ID accuracy |

---

## File upload specifications

| Parameter | Specification |
| :--- | :--- |
| Max file size | `500 MB` (configurable via `MAX_UPLOAD_SIZE_MB` in `backend/.env`) |
| Min file size | `1 byte` |
| Supported audio formats | `.wav`, `.mp3`, `.m4a`, `.aac`, `.flac`, `.ogg` |
| Supported video formats | `.mp4`, `.webm`, `.mkv` |
| Storage backend | `backend/app/infrastructure/storage.py` |

---

## Local development setup

### 1) Python backend

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

The backend loads environment values from `backend/.env` and falls back to defaults declared in `backend/app/core/config.py`.

### 2) Frontend

```bash
npm install
npm run dev -- --host 0.0.0.0 --port 3000
```

The Vite dev server is configured in `vite.config.ts` to proxy `/api` requests to the backend. In a local non-container setup, the default target is `http://localhost:8000`.

---

## Docker Compose startup

The repository already includes a compose setup for the core runtime in `backend/docker-compose.yml`.

### Copy the backend environment example

```bash
cd backend
cp .env.example .env
```

### Launch all required services

```bash
cd backend
docker compose up --build
```

This starts:

- PostgreSQL
- Redis
- Qdrant
- FastAPI backend on `http://localhost:8000`
- React frontend on `http://localhost:3000`

### Stop everything

```bash
cd backend
docker compose down -v
```

### Required environment values for Docker Compose

The compose file expects these service hostnames to resolve inside the docker network:

- PostgreSQL: `postgres`
- Redis: `redis`
- Qdrant: `qdrant`
- Backend: `backend`
- Frontend: `frontend`

The `backend/.env.example` file keeps those values ready for compose use.

---

## Application health checks

After startup, verify the services with:

```bash
curl http://localhost:8000/api/v1/health
curl http://localhost:8000/api/v1/health/live
curl http://localhost:8000/api/v1/health/ready
```

The backend health endpoints live in `backend/app/api/v1/endpoints/health.py` and are used by the Docker health checks.

## Notes

- The backend is the authoritative runtime for the API layer.
- The frontend is a Vite single-page app used to exercise the backend and display dashboard data.
- Optional AI modules and benchmark workloads depend on external model/data resources and matching local environment setup.
- The repo should be run with the appropriate Python, CUDA, and model cache dependencies before using REAL-mode AI features.
