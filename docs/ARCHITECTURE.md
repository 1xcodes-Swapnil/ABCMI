# ABCI-MI Architecture Notes

This document reflects the implementation that is present in this checkout. It intentionally avoids claiming production guarantees or model-performance numbers that are not supported by the code and the validation artifacts in this repo.

## Architecture summary

The repository has two main runtime layers:

1. A Python FastAPI backend in `backend/` that exposes the meeting-intelligence API and manages storage, persistence, and orchestration.
2. A React + Vite frontend in `src/` used for system health, meeting dashboards, knowledge views, and API exploration.

The backend uses a modular service-oriented structure. The current implementation includes:

- `app/api/v1` for endpoint registration and versioning
- `app/services` for workflow orchestration and business logic
- `app/models` / `app/repositories` for persistence and data access
- `app/skw` for semantic-knowledge indexing and query logic
- `app/infrastructure` for PostgreSQL, Qdrant, Redis, and storage access
- `app/ai` for optional model adapters and benchmark-oriented logic

## Operational reality

Some of the code paths are designed around external infrastructure and model providers, including:

- PostgreSQL for relational persistence
- Redis for notifications and event flow
- Qdrant for vector indexing and semantic retrieval
- MOSS / PyAnnote / Sarvam / Gemini integrations for specialized AI tasks

These components are present in the repo and can be configured for local validation, but their availability depends on matching environment setup and external dependencies. In other words, this repository supports a broad architecture, but the exact functionality of every AI module depends on the runtime environment and the available model/data assets.

## Current-endpoint view

The current application is organized around core meeting workflows and knowledge retrieval, including:

- meeting intake and lifecycle management
- auth and session handling
- reporting and translation flows
- notification and event plumbing
- knowledge search and semantic memory access
- admin and health endpoints

This is the implementation surface visible in `backend/app/api/v1/router.py` and the corresponding endpoint modules in `backend/app/api/v1/endpoints`.
