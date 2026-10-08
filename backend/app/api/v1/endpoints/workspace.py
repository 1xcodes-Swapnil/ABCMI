"""Read models for the original UI, backed by existing production records."""
import json
from pathlib import Path
import sqlite3
import uuid
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.dependencies import verify_authentication
from app.infrastructure.database import get_async_db
from app.models.inference_job import InferenceJob
from app.services.meeting_service import MeetingService

router = APIRouter(tags=["Workspace"])


@router.get("/ai/text-status")
async def text_provider_status(auth=Depends(verify_authentication)):
    from app.core.config import get_settings
    settings = get_settings()
    return {"provider": settings.TEXT_AI_PROVIDER, "model": settings.GEMINI_MODEL,
            "credential": "present" if settings.GEMINI_API_KEY else "missing",
            "configured": settings.TEXT_AI_PROVIDER.lower() == "gemini" and bool(settings.GEMINI_API_KEY),
            "inference": "NOT VERIFIED", "data_destination": "Google Gemini API"}


@router.post("/meetings/{meeting_id}/intelligence/generate", status_code=202)
async def queue_text_intelligence(meeting_id: uuid.UUID, auth=Depends(verify_authentication), db: AsyncSession=Depends(get_async_db)):
    import hashlib
    from app.ai.gemini_text import GeminiTextProvider
    from app.ai.grounded_meeting_text import EXTRACTION_VERSION
    from app.models.meeting import Meeting
    from app.repositories.transcript_repo import TranscriptRepository
    provider = GeminiTextProvider()
    provider.require_configuration()
    meeting = await MeetingService(db).get_meeting(meeting_id, auth)
    await db.execute(select(Meeting.id).where(Meeting.id == meeting_id).with_for_update())
    canonical = await TranscriptRepository(db).get_latest_version(meeting_id)
    if not canonical or not canonical.is_final or not canonical.full_text.strip() or meeting.status != "completed":
        raise HTTPException(409, "A completed, persisted REAL transcript is required")
    if (canonical.provenance or {}).get("execution_mode") != "REAL":
        raise HTTPException(409, "Transcript does not carry REAL execution provenance")
    fingerprint = hashlib.sha256((str(canonical.id) + canonical.full_text + provider.model + EXTRACTION_VERSION).encode()).hexdigest()
    key = f"intelligence:{meeting_id}:{fingerprint}"
    existing = (await db.execute(select(InferenceJob).where(InferenceJob.job_key == key))).scalar_one_or_none()
    if existing:
        if existing.status == "failed":
            raise HTTPException(409, "This text-generation job failed. Inspect its saved error before retrying.")
        return {"job_id": str(existing.id), "status": existing.status, "result": existing.result}
    job = InferenceJob(id=uuid.uuid4(), job_key=key, kind="intelligence", meeting_id=meeting_id,
        status="queued", payload={"actor": {k: auth[k] for k in ("user_id", "tenant_id", "role", "authenticated")},
        "correlation_id": str(uuid.uuid4()), "canonical_transcript_id": str(canonical.id),
        "model": provider.model, "extraction_version": EXTRACTION_VERSION,
        "source_sha256": hashlib.sha256(canonical.full_text.encode()).hexdigest()})
    db.add(job)
    await db.commit()
    return {"job_id": str(job.id), "status": job.status, "meeting_id": str(meeting_id)}


@router.get("/openapi.json", include_in_schema=False)
async def authenticated_schema(request: Request, auth=Depends(verify_authentication)):
    return request.app.openapi()


@router.post("/meetings/{meeting_id}/process-async", status_code=202)
async def queue_meeting(meeting_id: uuid.UUID, auth=Depends(verify_authentication), db: AsyncSession=Depends(get_async_db)):
    from app.models.meeting import Meeting
    from app.core.config import get_settings
    if get_settings().EXECUTION_MODE.upper() != "REAL":
        raise HTTPException(409, "Production queue requires REAL execution mode")
    service = MeetingService(db)
    meeting = await service.get_meeting(meeting_id, auth)
    await db.execute(select(Meeting.id).where(Meeting.id == meeting_id).with_for_update())
    await db.refresh(meeting, ["status"])
    existing = (await db.execute(select(InferenceJob).where(InferenceJob.meeting_id == meeting_id,
        InferenceJob.status.in_(["queued", "running"])))).scalars().first()
    if existing:
        return {"job_id": str(existing.id), "status": existing.status, "meeting_id": str(meeting_id)}
    if meeting.status == "completed" or meeting.transcript_segments:
        raise HTTPException(409, "A transcript already exists. Create a new meeting to process different audio.")
    if not meeting.audio_recordings:
        raise HTTPException(422, "Upload real audio before processing")
    service.validate_transition(meeting.status, "processing_requested")
    job_id = uuid.uuid4()
    job = InferenceJob(id=job_id, job_key=f"batch:{job_id}", kind="batch", meeting_id=meeting_id,
        status="queued", payload={"actor": {k: auth[k] for k in ("user_id", "tenant_id", "role", "authenticated")},
        "correlation_id": str(uuid.uuid4()), "audio_id": str(max(meeting.audio_recordings, key=lambda a:a.created_at).id)})
    meeting.status = "processing_requested"
    db.add(job)
    await db.commit()
    return {"job_id": str(job.id), "status": job.status, "meeting_id": str(meeting_id)}


@router.get("/meetings/{meeting_id}/pipeline")
async def pipeline(meeting_id: uuid.UUID, auth=Depends(verify_authentication), db: AsyncSession=Depends(get_async_db)):
    meeting = await MeetingService(db).get_meeting(meeting_id, auth)
    jobs = (await db.execute(select(InferenceJob).where(InferenceJob.meeting_id == meeting_id)
                            .order_by(InferenceJob.created_at))).scalars().all()
    canonical = sorted(meeting.transcripts, key=lambda row: row.created_at, reverse=True)
    from app.core.config import get_settings
    state_root = get_settings().AUDIO_CHUNK_STATE_DIR
    chunk_progress = None
    if state_root:
        checkpoints = sorted((Path(state_root) / str(meeting_id)).glob("state_*.json"))
        if checkpoints:
            try:
                state = json.loads(checkpoints[-1].read_text(encoding="utf-8"))
                chunk_progress = {key: state.get(key) for key in (
                    "overall_status", "total_chunks", "completed_chunks_count",
                    "total_duration_seconds", "chunk_duration_seconds", "overlap_duration_seconds",
                    "checkpoint_version", "updated_at")}
            except (OSError, ValueError) as exc:
                chunk_progress = {"overall_status": "UNAVAILABLE", "error_type": type(exc).__name__}
    return {"meeting_id": str(meeting.id), "status": meeting.status,
            "chunk_progress": chunk_progress,
            "canonical_transcript_id": str(canonical[0].id) if canonical else None,
            "provenance": canonical[0].provenance if canonical else None,
            "jobs": [{"id": str(j.id), "chunk_id": str(j.chunk_id) if j.chunk_id else None,
                      "kind": j.kind, "status": j.status, "error": j.error,
                      "started_at": j.started_at, "finished_at": j.finished_at,
                      "result": j.result} for j in jobs]}


@router.post("/meetings/{meeting_id}/processing/cancel")
async def cancel_queued_meeting(meeting_id: uuid.UUID, auth=Depends(verify_authentication), db: AsyncSession=Depends(get_async_db)):
    meeting = await MeetingService(db).get_meeting(meeting_id, auth)
    jobs = (await db.execute(select(InferenceJob).where(InferenceJob.meeting_id == meeting_id,
        InferenceJob.status.in_(["queued", "running"])).with_for_update())).scalars().all()
    if any(j.status == "running" or j.kind != "batch" for j in jobs):
        raise HTTPException(409, "Running inference and live capture cannot be cancelled through the queued-upload control")
    if not jobs:
        raise HTTPException(409, "No queued batch job exists")
    for job in jobs:
        job.status = "cancelled"
    meeting.status = "created"
    await db.commit()
    return {"meeting_id":str(meeting_id), "cancelled_job_ids":[str(j.id) for j in jobs], "status":"created"}


@router.get("/meetings/{meeting_id}/audio/{audio_id}/content")
async def audio_content(meeting_id: uuid.UUID, audio_id: uuid.UUID,
                        auth=Depends(verify_authentication), db: AsyncSession=Depends(get_async_db)):
    meeting = await MeetingService(db).get_meeting(meeting_id, auth)
    record = next((a for a in meeting.audio_recordings if a.id == audio_id), None)
    if not record:
        raise HTTPException(404, "Audio record not found")
    from app.core.config import get_settings
    root = Path(get_settings().AUDIO_STORAGE_PATH).resolve()
    path = Path(record.file_path).resolve()
    if not path.is_relative_to(root) or not path.is_file():
        raise HTTPException(404, "Stored audio file is unavailable")
    return FileResponse(path, filename=record.file_name)


@router.get("/benchmarks/runs")
async def benchmark_runs(auth=Depends(verify_authentication)):
    if auth.get("role") != "admin":
        raise HTTPException(403, "Administrator access required for host benchmark evidence")
    from app.benchmarks.config import get_benchmark_config
    path = Path(get_benchmark_config().db_path).resolve()
    if not path.is_file():
        return {"items": [], "total": 0, "verification": "No stored benchmark runs"}
    with sqlite3.connect(path.as_uri() + "?mode=ro", uri=True) as connection:
        connection.row_factory = sqlite3.Row
        rows = [dict(row) for row in connection.execute("SELECT * FROM benchmark_runs ORDER BY created_at DESC LIMIT 100")]
        for row in rows:
            row["samples"] = [dict(sample) for sample in connection.execute(
                "SELECT * FROM benchmark_samples WHERE run_id = ? ORDER BY id", (row["run_id"],))]
            row["verification"] = "Stored evidence; accuracy provenance requires review"
    return {"items": rows, "total": len(rows)}


@router.get("/benchmarks/datasets")
async def benchmark_datasets(auth=Depends(verify_authentication)):
    from app.benchmarks.dataset_registry import get_dataset_registry
    return {"items": get_dataset_registry().list_datasets(),
            "execution": "Use the existing benchmark CLI after validating local audio and ground truth; UI does not launch unverified benchmarks."}
