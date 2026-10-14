# System & Data Flow Architecture

This file describes the workflow implemented in the current repository. It should be read as a code-grounded architecture description, not as a blanket guarantee that every optional AI integration is active in every deployment.

## Repository-level flow

The runtime flow in this project is currently organized as follows:

1. Client requests or CLI actions reach the FastAPI backend in `backend/app/main.py`.
2. API routers in `backend/app/api/v1/endpoints` handle domain workflows such as auth, meetings, queries, reports, and notifications.
3. Service, repository, and model layers process the request and persist or query data.
4. Redis and Qdrant are used for event-driven and vector-based workflows when configured.
5. Optional AI modules under `backend/app/ai` process audio, text, or semantic tasks when the required runtime dependencies and data are present.

## Implementation notes

The repository includes both production-oriented service code and benchmark-oriented validation paths. That means some files exist to support local verification of ASR and diarization workflows, while others are part of the core operational API. The exact behavior of those benchmark paths depends on the environment, external models, and datasets available at runtime.

## Current design emphasis

The code is currently oriented toward:

- meeting ingestion and processing
- user and workspace metadata management
- notification/event workflows
- semantic knowledge indexing and retrieval
- reporting, translation, and query workflows
- validation and benchmarking pipelines for heavy AI tasks

These capabilities are visible in the backend routers, frontend dashboard, and supporting benchmark scripts in this repository.
