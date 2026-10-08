"""Incremental REAL live validation; never runs long recordings or downloads."""
import argparse
import asyncio
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import uuid

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["DEBUG"] = "false"

def save(path, value):
    with path.open("x", encoding="utf-8") as file:
        json.dump(value, file, indent=2, default=str)


async def run(args):
    from sqlalchemy import select, text
    from sqlalchemy.ext.asyncio import async_sessionmaker
    from app.core.config import get_settings
    from app.infrastructure.database import init_database, close_database_connections
    settings = get_settings()
    folder = args.run.resolve()
    folder.mkdir(parents=True, exist_ok=True)
    result = {"stage": args.stage, "timestamp": datetime.now(timezone.utc).isoformat(),
        "git_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        "run_id": folder.name}
    sessions = async_sessionmaker(init_database(), expire_on_commit=False)
    try:
        if args.stage == "preflight":
            import torch
            import soundfile as sf
            audio = ROOT / "data/audio/raw/f01d7854-a29a-47b7-8c0f-741e2d1fad46_real_excerpt.wav"
            info = sf.info(audio)
            result.update(execution_mode=settings.EXECUTION_MODE, device=settings.OPENMOSS_DEVICE,
                cuda_available=torch.cuda.is_available(), audio=audio.name,
                duration=info.duration, sample_rate=info.samplerate, channels=info.channels,
                sha256=hashlib.sha256(audio.read_bytes()).hexdigest())
            async with sessions() as db:
                result["migration"] = list((await db.execute(text("select version_num from alembic_version"))).scalars())
                result["job_table"] = bool(await db.scalar(text("select to_regclass('public.inference_jobs')")))
                from app.models.user import User
                result["existing_user_count"] = await db.scalar(select(__import__('sqlalchemy').func.count()).select_from(User))
            if settings.EXECUTION_MODE.upper() != "REAL" or not settings.OPENMOSS_DEVICE.startswith("cuda") or not torch.cuda.is_available():
                raise RuntimeError("REAL CUDA configuration is required")
        elif args.stage == "ingest":
            import io
            import soundfile as sf
            from app.models.user import User
            from app.schemas.meeting import MeetingCreate
            from app.services.meeting_service import MeetingService
            from app.services.live_session_service import LiveSessionService
            audio = ROOT / "data/audio/raw/f01d7854-a29a-47b7-8c0f-741e2d1fad46_real_excerpt.wav"
            wave, rate = sf.read(audio, dtype="float32", always_2d=True)
            if len(wave)/rate > 10.01:
                raise RuntimeError("This validator permits only the existing 10-second excerpt")
            async with sessions() as db:
                user = (await db.execute(select(User).order_by(User.created_at).limit(1))).scalar_one_or_none()
                if not user:
                    raise RuntimeError("An existing authorized identity is required")
                from app.models.meeting import Meeting
                tenant = await db.scalar(select(Meeting.tenant_id).where(Meeting.host_id == user.id,
                    Meeting.tenant_id.is_not(None)).order_by(Meeting.created_at).limit(1))
                if not tenant:
                    raise RuntimeError("No existing authorized meeting tenant could be recovered")
                auth = {"user_id": str(user.id), "tenant_id": tenant, "role": "admin"}
                meeting = await MeetingService(db).create_meeting(MeetingCreate(title="REAL live worker short validation"), auth)
                live = LiveSessionService(db)
                session = await live.start_session(meeting.id, auth)
                result.update(meeting_id=str(meeting.id), session_id=str(session.id),
                    correlation_id=session.correlation_id, user_id=str(user.id), tenant_id=tenant, chunks=[])
                step = settings.LIVE_CHUNK_SECONDS-settings.LIVE_OVERLAP_SECONDS
                start = 0.0
                while start < len(wave)/rate:
                    end = min(start+settings.LIVE_CHUNK_SECONDS, len(wave)/rate)
                    buffer = io.BytesIO()
                    sf.write(buffer, wave[round(start*rate):round(end*rate)], rate, format="WAV", subtype="PCM_16")
                    chunk, _ = await live.ingest_chunk(meeting.id, len(result["chunks"]), round(start*1000), round(end*1000),
                        buffer.getvalue(), "chunk.wav", auth)
                    result["chunks"].append({"chunk_id": str(chunk.id), "start": start, "end": end, "sha256": chunk.checksum})
                    # Cheap idempotence check: no duplicate job or audio creation.
                    again, _ = await live.ingest_chunk(meeting.id, chunk.sequence_number, round(start*1000), round(end*1000),
                        buffer.getvalue(), "chunk.wav", auth)
                    assert again.id == chunk.id
                    if end == len(wave)/rate: break
                    start += step
                await live.stop_session(meeting.id, auth)
                await db.commit()
        elif args.stage in {"retry-dependency", "retry-auth"}:
            from app.models.inference_job import InferenceJob
            from app.models.live_session import LiveAudioChunk
            prior = json.loads((folder / "ingest.json").read_text())
            async with sessions() as db:
                jobs = (await db.execute(select(InferenceJob).where(
                    InferenceJob.session_id == uuid.UUID(prior["session_id"]),
                    InferenceJob.kind == ("chunk" if args.stage == "retry-dependency" else "finalize"),
                    InferenceJob.status == "failed").with_for_update())).scalars().all()
                expected_error = "No module named 'librosa'" if args.stage == "retry-dependency" else "ACE processing completed with status 'failed'"
                if len(jobs) != 1 or expected_error not in (jobs[0].error or ""):
                    raise RuntimeError("Expected the single pre-inference dependency failure; no work was requeued")
                job = jobs[0]
                result["previous_failure"] = {"job_id": str(job.id), "error": job.error, "finished_at": job.finished_at}
                job.status, job.error, job.lease_token, job.lease_until = "queued", None, None, None
                if job.chunk_id:
                    chunk = await db.get(LiveAudioChunk, job.chunk_id)
                    chunk.status = "queued"
                else:
                    from app.models.live_session import LiveSession
                    session = await db.get(LiveSession, job.session_id)
                    session.status = "stopping"
                await db.commit()
        elif args.stage in {"chunk", "finalize"}:
            from app.services.live_inference_worker import LiveInferenceWorker
            worker = LiveInferenceWorker()
            prior = json.loads((folder / "ingest.json").read_text())
            results = []
            while True:
                item = await worker.run_once(args.stage, uuid.UUID(prior["session_id"]))
                if item is None: break
                results.append(item)
                if item["status"] != "completed":
                    result["jobs"] = results
                    raise RuntimeError(item["error"])
                if args.stage == "finalize": break
            result["jobs"] = results
            if not results:
                raise RuntimeError("No queued work was executed")
        elif args.stage == "readback":
            from app.models.inference_job import InferenceJob
            from app.models.transcript import Transcript, TranscriptSegment
            from app.services.live_session_service import LiveSessionService
            prior = json.loads((folder / "ingest.json").read_text())
            meeting_id = uuid.UUID(prior["meeting_id"])
            async with sessions() as db:
                jobs = (await db.execute(select(InferenceJob).where(InferenceJob.meeting_id == meeting_id))).scalars().all()
                result["jobs"] = [{"job_id": str(j.id), "kind": j.kind, "status": j.status,
                    "chunk_id": str(j.chunk_id) if j.chunk_id else "NOT AVAILABLE", "result": j.result, "error": j.error} for j in jobs]
                segments = (await db.execute(select(TranscriptSegment).where(TranscriptSegment.meeting_id == meeting_id)
                    .order_by(TranscriptSegment.sequence_number))).scalars().all()
                canonical = (await db.execute(select(Transcript).where(Transcript.meeting_id == meeting_id))).scalar_one_or_none()
                result.update(meeting_id=str(meeting_id), final_segments=len(segments),
                    canonical_transcript_id=str(canonical.id) if canonical else "NOT AVAILABLE",
                    transcript=[{"id": str(s.id), "start": s.start_time_ms, "end": s.end_time_ms,
                        "speaker": s.speaker_label, "text": s.original_text} for s in segments])
                status = await LiveSessionService(db).get_session_status(meeting_id,
                    {"user_id": prior["user_id"], "tenant_id": prior["tenant_id"], "role": "admin"})
                result["live_status"] = status["session"].status
                if not canonical or not segments or status["session"].status != "completed":
                    raise RuntimeError("Complete persisted REAL transcript not present")
                if canonical.full_text != " ".join(s.original_text for s in segments):
                    raise RuntimeError("Canonical transcript differs from persisted segments")
        elif args.stage == "report":
            from app.infrastructure.database import Base
            from app.models.inference_job import InferenceJob
            prior = json.loads((folder / "ingest.json").read_text())
            mid = uuid.UUID(prior["meeting_id"])
            result["identifiers"] = {"meeting_id": str(mid), "session_id": prior["session_id"],
                "correlation_id": prior["correlation_id"], "run_id": folder.name,
                "benchmark_run_id": "NOT AVAILABLE", "benchmark_sample_id": "NOT AVAILABLE",
                "redis_stream_id": "NOT AVAILABLE (existing bus uses Pub/Sub)",
                "uncaptured_ace_event_ids": "NOT RECORDED; cannot recover historical Pub/Sub events"}
            async with sessions() as db:
                records = {}
                for name in ("meetings", "transcripts", "transcript_segments", "knowledge_objects", "notifications", "query_records", "project_meetings", "audio_recordings", "live_sessions", "inference_jobs"):
                    table = Base.metadata.tables.get(name)
                    if table is None: continue
                    column = table.c.id if name == "meetings" else table.c.get("meeting_id")
                    if column is None: continue
                    columns = [table.c.id]
                    for extra in ("qdrant_point_id", "project_id"):
                        if extra in table.c: columns.append(table.c[extra])
                    rows = (await db.execute(select(*columns).where(column == mid))).mappings().all()
                    records[name] = [dict(row) for row in rows] if rows else "NOT AVAILABLE"
                result["database_records"] = records
                jobs = (await db.execute(select(InferenceJob).where(InferenceJob.meeting_id == mid))).scalars().all()
                result["job_timings"] = [{"job_id": str(j.id), "kind": j.kind,
                    "created_at": j.created_at, "started_at": j.started_at, "finished_at": j.finished_at,
                    "wall_seconds": (j.finished_at-j.started_at).total_seconds() if j.finished_at and j.started_at else None,
                    "event_id": (j.result or {}).get("event_id", "NOT AVAILABLE")} for j in jobs]
        elif args.stage == "reconstruction":
            from app.ai.long_audio_processor import LongAudioProcessor, ChunkMetadata
            from app.ai.multilingual_asr import ASRSegment
            prior = json.loads((folder / "ingest.json").read_text())
            observed = json.loads((folder / "readback.json").read_text())
            jobs = {j["chunk_id"]: j for j in observed["jobs"] if j["kind"] == "chunk"}
            pairs = []
            for i, chunk in enumerate(prior["chunks"]):
                meta = ChunkMetadata(chunk_id=chunk["chunk_id"], chunk_index=i, total_chunks=len(prior["chunks"]),
                    start_time=chunk["start"], end_time=chunk["end"], duration=chunk["end"]-chunk["start"])
                pairs.append((meta, [ASRSegment.model_validate(s) for s in jobs[chunk["chunk_id"]]["result"]["segments"]]))
            processor = LongAudioProcessor(chunk_duration=settings.LIVE_CHUNK_SECONDS, overlap_duration=settings.LIVE_OVERLAP_SECONDS)
            reconciled, mapping = processor.reconcile_speakers_across_chunks(pairs)
            segments, removed = processor.merge_and_deduplicate_chunks([m for m, _ in pairs], reconciled)
            actual = [(round(s.start_time*1000), round(s.end_time*1000), s.transcript, s.speaker_id) for s in segments]
            expected = [(s["start"], s["end"], s["text"], s["speaker"]) for s in observed["transcript"]]
            assert actual == expected
            result.update(inference_repeated=False, matches_persisted_transcript=True, speaker_mapping=mapping,
                text_duplicates_removed=removed, decisions=processor.last_dedup_decisions)
        elif args.stage in {"api", "api-network"}:
            import httpx
            from app.core.security import create_access_token
            from app.main import app
            from app.models.live_session import LiveAudioChunk
            from app.models.inference_job import InferenceJob
            from sqlalchemy import func
            prior = json.loads((folder / "ingest.json").read_text())
            token = create_access_token({"sub": prior["user_id"], "tenant_id": prior["tenant_id"], "role": "admin"})
            headers = {"Authorization": "Bearer " + token}
            path = settings.API_V1_STR + "/meetings/" + prior["meeting_id"]
            network = args.stage == "api-network"
            async with httpx.AsyncClient(transport=None if network else httpx.ASGITransport(app=app),
                base_url="http://127.0.0.1:8000" if network else "http://localhost", timeout=30) as client:
                live = await client.get(path + "/live/status", headers=headers)
                transcript = await client.get(path + "/transcript", headers=headers)
                result.update(transport="HTTP localhost TCP" if network else "ASGI; real authentication/router/database; no browser or network listener",
                    live_http_status=live.status_code, transcript_http_status=transcript.status_code,
                    live_status=live.json().get("session", {}).get("status"),
                    api_transcript=transcript.json())
                assert live.status_code == 200 and live.json()["session"]["status"] == "completed"
                assert transcript.status_code == 200 and len(transcript.json()) > 0
                foreign = create_access_token({"sub": prior["user_id"], "tenant_id": "unauthorized-tenant", "role": "admin"})
                wrong = await client.get(path + "/live/status", headers={"Authorization": "Bearer " + foreign})
                protected = await client.get(path + "/transcript", headers={"Authorization": "Bearer " + foreign})
                rejected = await client.get(path + "/live/status", headers={"Authorization": "Bearer test-token"})
                result.update(cross_tenant_live=wrong.status_code, cross_tenant_transcript=protected.status_code,
                    fixture_auth=rejected.status_code)
                assert wrong.status_code == 403 and protected.status_code == 403 and rejected.status_code == 401
                async with sessions() as db:
                    chunk = await db.get(LiveAudioChunk, uuid.UUID(prior["chunks"][0]["chunk_id"]))
                    count_before = await db.scalar(select(func.count()).select_from(InferenceJob).where(InferenceJob.meeting_id == uuid.UUID(prior["meeting_id"])))
                    data = {"sequence_number": chunk.sequence_number, "timestamp_start_ms": chunk.timestamp_start_ms,
                        "timestamp_end_ms": chunk.timestamp_end_ms, "checksum": chunk.checksum}
                    uploaded = await client.post(path + "/live/chunks", headers=headers, data=data,
                        files={"file": ("chunk.wav", Path(chunk.file_path).read_bytes(), "audio/wav")})
                    await db.rollback()
                    count_after = await db.scalar(select(func.count()).select_from(InferenceJob).where(InferenceJob.meeting_id == uuid.UUID(prior["meeting_id"])))
                    result.update(duplicate_http_status=uploaded.status_code, duplicate_created_jobs=count_after-count_before)
                    assert uploaded.status_code == 201 and count_after == count_before
                no_token = await client.get(settings.API_V1_STR + "/worker/audio/" + prior["chunks"][0]["chunk_id"])
                result["unauthenticated_worker_audio"] = no_token.status_code
                assert no_token.status_code == 403
        result["status"] = "VERIFIED"
    except Exception as exc:
        from app.cli import sanitize_error_text
        result.update(status="BLOCKED", error_type=type(exc).__name__, reason=sanitize_error_text(str(exc)))
    finally:
        await close_database_connections()
        path = folder / f"{args.stage}.json"
        if path.exists(): path = folder / f"{args.stage}_{uuid.uuid4().hex[:8]}.json"
        save(path, result)
        print(json.dumps({k:v for k,v in result.items() if k not in {"jobs", "transcript", "api_transcript", "database_records", "job_timings"}}, default=str))
    return 0 if result["status"] == "VERIFIED" else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("stage", choices=["preflight", "ingest", "retry-dependency", "retry-auth", "chunk", "finalize", "readback", "reconstruction", "api", "api-network", "report"])
    parser.add_argument("--run", type=Path, required=True)
    raise SystemExit(asyncio.run(run(parser.parse_args())))
