"""Separate, warm GPU worker. Run with python -m app.services.live_inference_worker.

PostgreSQL stores jobs/results. SKIP LOCKED distributes jobs across workers.
Failures are never automatically requeued (in particular CUDA OOM). Expired
leases fail visibly; a late worker cannot mark a failed job successful.
"""
import argparse
import asyncio
from datetime import datetime, timedelta, timezone
import hashlib
import io
import json
import gc
import sys
from pathlib import Path
import threading
import time
import uuid

from sqlalchemy import create_engine, select, update, exists
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlalchemy.pool import NullPool

from app.core.config import get_settings
from app.infrastructure.database import init_database, close_database_connections
from app.models.inference_job import InferenceJob
from app.models.live_session import LiveAudioChunk, LiveSession


def utcnow():
    return datetime.now(timezone.utc)


class LiveInferenceWorker:
    def __init__(self):
        self.settings = get_settings()
        if self.settings.EXECUTION_MODE.upper() != "REAL":
            raise RuntimeError("Live worker requires EXECUTION_MODE=REAL")
        if not self.settings.OPENMOSS_DEVICE.startswith("cuda"):
            raise RuntimeError("Live worker requires explicit CUDA; CPU fallback is forbidden")
        if self.settings.LIVE_WORKER_LEASE_SECONDS < 30:
            raise RuntimeError("Worker lease must be at least 30 seconds")
        self.sessions = async_sessionmaker(init_database(), expire_on_commit=False)
        self.provider = None
        self.failure_evidence = None

    def release_models(self, capability=None):
        """Release completed stages in this single-job GPU process.

        Live chunks retain MOSS for the next window. Deferred ACE stages retain
        only their serializable outputs; keeping all three model caches alive
        would unnecessarily compete for this worker's VRAM.
        """
        caches = {
            "multilingual_asr": ("app.ai.multilingual_asr", "OpenMOSSProvider",
                ("_cached_model", "_cached_processor", "_cached_model_key")),
            "speaker_representation": ("app.ai.speaker_diarization", "SpeakerDiarizationEngine",
                ("_cached_pipeline", "_cached_pipeline_key")),
            "code_switch_intelligence": ("app.ai.code_switch_intelligence", "CodeSwitchIntelligenceEngine",
                ("_cached_sarvam_model", "_cached_sarvam_tokenizer")),
        }
        for name, (module_name, class_name, attributes) in caches.items():
            if capability is not None and capability != name:
                continue
            if name == "multilingual_asr":
                if self.provider is not None:
                    self.provider.model = self.provider.processor = None
                self.provider = None
            module = sys.modules.get(module_name)
            if module is not None:
                provider_class = getattr(module, class_name)
                for attribute in attributes:
                    setattr(provider_class, attribute, None)
        gc.collect()
        torch = sys.modules.get("torch")
        if torch is not None and torch.cuda.is_initialized():
            torch.cuda.empty_cache()

    def release_after_stages(self, ace):
        for capability in ("multilingual_asr", "speaker_representation", "code_switch_intelligence"):
            handler = ace.module_runner._handlers[capability]
            async def releasing(payload, original=handler, name=capability):
                try:
                    return await original(payload)
                finally:
                    self.release_models(name)
            ace.module_runner.register_capability_handler(capability, releasing)

    async def claim(self, kind="all", session_id=None, job_id=None):
        async with self.sessions() as db:
            # Do not repeat expensive work automatically following a lost lease.
            expired = (await db.execute(update(InferenceJob).where(InferenceJob.status == "running",
                InferenceJob.lease_until < utcnow()).values(status="failed",
                error="Worker lease expired; inspect saved output before an explicit recovery", finished_at=utcnow())
                .returning(InferenceJob.meeting_id, InferenceJob.session_id))).all()
            for meeting_id, live_id in expired:
                from app.models.meeting import Meeting
                await db.execute(update(Meeting).where(Meeting.id == meeting_id,
                    Meeting.status.in_(["processing_requested", "running"])).values(status="failed"))
                if live_id:
                    await db.execute(update(LiveSession).where(LiveSession.id == live_id).values(status="failed"))
            other = InferenceJob.__table__.alias("pending_chunk")
            unfinished = exists(select(other.c.id).where(other.c.session_id == InferenceJob.session_id,
                other.c.kind == "chunk", other.c.status.in_(["queued", "running"])))
            statement = select(InferenceJob).where(InferenceJob.status == "queued",
                (InferenceJob.kind == "chunk") | ~unfinished)
            if kind != "all":
                statement = statement.where(InferenceJob.kind == kind)
            if session_id is not None:
                statement = statement.where(InferenceJob.session_id == session_id)
            if job_id is not None:
                statement = statement.where(InferenceJob.id == job_id)
            job = (await db.execute(statement.order_by(InferenceJob.kind, InferenceJob.created_at)
                .with_for_update(skip_locked=True).limit(1))).scalar_one_or_none()
            if job:
                job.status = "running"
                job.started_at = utcnow()
                job.lease_token = uuid.uuid4()
                job.lease_until = utcnow() + timedelta(seconds=self.settings.LIVE_WORKER_LEASE_SECONDS)
            await db.commit()
            return job

    def heartbeat(self, job, stop):
        # Dedicated connection/thread also runs while a model blocks Python's
        # async event loop. No credential or URL is written to output.
        url = make_url(self.settings.async_database_url).set(drivername="postgresql+psycopg2")
        engine = create_engine(url, poolclass=NullPool, connect_args={"connect_timeout": 10})
        try:
            while not stop.wait(self.settings.LIVE_WORKER_LEASE_SECONDS / 3):
                try:
                    with engine.begin() as db:
                        renewed = db.execute(update(InferenceJob).where(InferenceJob.id == job.id,
                            InferenceJob.lease_token == job.lease_token, InferenceJob.status == "running")
                            .values(lease_until=utcnow() + timedelta(seconds=self.settings.LIVE_WORKER_LEASE_SECONDS)))
                        if renewed.rowcount != 1:
                            return
                except Exception:
                    print("Worker heartbeat unavailable; completion still requires a valid lease", flush=True)
        finally:
            engine.dispose()

    def resolve_persisted_audio_path(self, persisted_path):
        path = Path(persisted_path)
        if path.is_file():
            return path
        normalized = str(path).replace("\\", "/")
        prefix = "/app/data/audio/"
        if normalized.startswith(prefix):
            path = Path(self.settings.AUDIO_STORAGE_PATH).resolve() / Path(normalized[len(prefix):])
        return path.resolve()

    async def audio_path(self, chunk):
        if not chunk.checksum:
            raise RuntimeError("Chunk has no persisted SHA-256")
        if self.settings.LIVE_WORKER_API_URL:
            import httpx
            from urllib.parse import urlsplit
            base = self.settings.LIVE_WORKER_API_URL.rstrip("/")
            parsed = urlsplit(base)
            if parsed.scheme != "https" and parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
                raise RuntimeError("Remote worker audio transfer requires HTTPS")
            if not self.settings.LIVE_WORKER_TOKEN:
                raise RuntimeError("Remote worker audio transfer requires LIVE_WORKER_TOKEN")
            path = Path(self.settings.AUDIO_STORAGE_PATH) / "worker-cache" / f"{chunk.id}.wav"
            path.parent.mkdir(parents=True, exist_ok=True)
            if not path.exists():
                async with httpx.AsyncClient(timeout=60) as client:
                    response = await client.get(f"{base}/worker/audio/{chunk.id}",
                        headers={"X-Worker-Token": self.settings.LIVE_WORKER_TOKEN})
                    response.raise_for_status()
                    data = response.content
                if hashlib.sha256(data).hexdigest() != chunk.checksum:
                    raise RuntimeError("Downloaded audio checksum mismatch")
                path.write_bytes(data)
        else:
            path = self.resolve_persisted_audio_path(chunk.file_path)
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != chunk.checksum:
            raise RuntimeError("Persisted audio missing or SHA-256 differs")
        return path

    async def transcribe_chunk(self, job):
        import torch
        import soundfile as sf
        from app.ai.multilingual_asr import OpenMOSSProvider
        if not torch.cuda.is_available():
            raise RuntimeError("CUDA is unavailable; no CPU or fixture fallback")
        async with self.sessions() as db:
            chunk = await db.get(LiveAudioChunk, job.chunk_id)
        path = await self.audio_path(chunk)
        info = sf.info(path)
        if self.provider is None:
            self.provider = OpenMOSSProvider({"model_id": self.settings.OPENMOSS_MODEL_ID,
                "device": self.settings.OPENMOSS_DEVICE, "cache_dir": self.settings.OPENMOSS_CACHE_DIR,
                "token": self.settings.HF_TOKEN})
        started = time.perf_counter()
        segments = await self.provider.transcribe(str(path))
        elapsed = time.perf_counter() - started
        if not segments:
            raise RuntimeError("Real MOSS returned no transcript segments")
        offset = chunk.timestamp_start_ms / 1000
        from app.ai.long_audio_processor import LongAudioProcessor
        global_segments = LongAudioProcessor.offset_segments_to_global_time(segments, offset)
        return {"execution_mode": "REAL", "is_fixture": False, "model": self.provider.model_id,
            "chunk_id": str(chunk.id), "sha256": chunk.checksum, "duration": info.duration,
            "sample_rate": info.samplerate, "channels": info.channels,
            "local_segments": [s.model_dump(mode="json") for s in segments],
            "segments": [s.model_dump(mode="json") for s in global_segments],
            "speaker_scope": "chunk_local_provisional", "raw_moss_output": self.provider.last_raw_output,
            "inference": self.provider.last_inference, "elapsed_seconds": elapsed, "rtf": elapsed / info.duration}

    async def finalize(self, job):
        import numpy as np
        import soundfile as sf
        from app.ai.long_audio_processor import LongAudioProcessor, ChunkMetadata
        from app.ai.multilingual_asr import ASRSegment
        from app.cli import get_cli_ace_orchestrator
        from app.models.meeting import Meeting
        from app.models.transcript import Transcript
        from app.schemas.meeting import MeetingProcessingRequest
        from app.services.meeting_service import MeetingService

        async with self.sessions() as db:
            session = await db.get(LiveSession, job.session_id)
            meeting = await db.get(Meeting, job.meeting_id)
            rows = (await db.execute(select(LiveAudioChunk, InferenceJob).join(InferenceJob,
                InferenceJob.chunk_id == LiveAudioChunk.id).where(LiveAudioChunk.session_id == session.id)
                .order_by(LiveAudioChunk.sequence_number))).all()
            if not rows or any(j.status != "completed" or not j.result or j.result.get("is_fixture") is not False for _, j in rows):
                raise RuntimeError("Finalization requires all chunks to have completed real inference")
            processor = LongAudioProcessor(chunk_duration=self.settings.LIVE_CHUNK_SECONDS,
                overlap_duration=self.settings.LIVE_OVERLAP_SECONDS)
            results, blocks, rate, frames = [], [], None, 0
            for index, (chunk, chunk_job) in enumerate(rows):
                if chunk.sequence_number != index:
                    raise RuntimeError("Live sequence contains a gap")
                path = await self.audio_path(chunk)
                audio, sr = sf.read(path, dtype="float32", always_2d=True)
                if rate is not None and rate != sr:
                    raise RuntimeError("Sample rate changed within the live session")
                rate = sr
                start_frame = round(chunk.timestamp_start_ms * sr / 1000)
                if start_frame > frames:
                    raise RuntimeError("Live audio coverage has a gap")
                skip = frames - start_frame
                if skip >= len(audio):
                    raise RuntimeError("Chunk contributes no new audio")
                blocks.append(audio[skip:])
                frames += len(audio) - skip
                meta = ChunkMetadata(chunk_id=chunk.id, chunk_index=index, total_chunks=len(rows),
                    start_time=chunk.timestamp_start_ms / 1000, end_time=chunk.timestamp_end_ms / 1000,
                    duration=len(audio) / sr, overlap_start_seconds=skip / sr,
                    overlap_end_seconds=max(0, (chunk.timestamp_end_ms - rows[index+1][0].timestamp_start_ms)/1000) if index+1 < len(rows) else 0,
                    status="completed")
                results.append((meta, [ASRSegment.model_validate(s) for s in chunk_job.result["segments"]]))
            reconciled, mapping = processor.reconcile_speakers_across_chunks(results)
            segments, removed = processor.merge_and_deduplicate_chunks([m for m, _ in results], reconciled)
            segments.sort(key=lambda s: (s.start_time, s.end_time))
            if not segments:
                raise RuntimeError("Reconstruction returned no real segments")
            buffer = io.BytesIO()
            sf.write(buffer, np.concatenate(blocks), rate, format="WAV", subtype="PCM_16")
            audio_bytes = buffer.getvalue()
            service = MeetingService(db)
            auth = {"role": "admin", "user_id": str(meeting.host_id) if meeting.host_id else None,
                "tenant_id": meeting.tenant_id, "correlation_id": session.correlation_id,
                "authenticated": True, "meeting_id": str(meeting.id)}
            actor = (session.session_metadata or {}).get("authorized_actor")
            if actor:
                if actor.get("tenant_id") != meeting.tenant_id:
                    raise RuntimeError("Persisted live job actor tenant differs from meeting")
                auth.update(actor)
            elif not meeting.host_id:
                raise RuntimeError("Live job has no persisted authorized actor or meeting host")
            # Keep original audio intake and the existing ACE/PyAnnote/SKW pipeline.
            await service.upload_audio(meeting.id, "live_capture.wav", audio_bytes,
                sample_rate=rate, channels=1, auth_context=auth)
            await db.commit()
            ace = get_cli_ace_orchestrator(db)
            async def reuse_actual_moss(payload):
                return {"status": "SUCCESS", "capability": "multilingual_asr", "confidence_score": None,
                    "correlation_id": session.correlation_id, "result_data": {
                        "transcript": " ".join(s.transcript for s in segments),
                        "segments": [s.model_dump(mode="json") for s in segments],
                        "detected_languages": sorted({s.detected_language for s in segments if s.detected_language}),
                        "metadata": {"is_fixture": False, "model_name": self.settings.OPENMOSS_MODEL_ID,
                            "chunk_count": len(rows), "source_job_ids": [str(j.id) for _, j in rows],
                            "speaker_mapping": mapping, "deduplicated_segments_count": removed,
                            "deduplication_decisions": processor.last_dedup_decisions,
                            "chunks": [m.model_dump(mode="json") for m, _ in results]}}}
            ace.module_runner.register_capability_handler("multilingual_asr", reuse_actual_moss)
            # Bind the assembled bytes explicitly, avoiding ambiguous raw-directory lookup.
            for capability in ("audio_intelligence", "speaker_representation"):
                original = ace.module_runner._handlers[capability]
                async def bound_audio(payload, handler=original):
                    payload = {**payload, "input": {**payload["input"], "audio_payload": audio_bytes}}
                    return await handler(payload)
                ace.module_runner.register_capability_handler(capability, bound_audio)
            self.release_after_stages(ace)
            response = await service.process_meeting(meeting.id,
                MeetingProcessingRequest(request_id=job.id, correlation_id=session.correlation_id), auth, ace)
            board = ace.blackboards[meeting.id]
            self.failure_evidence = {"execution_mode": "REAL", "blackboard_state": board.execution_state,
                "ace_tasks": [{"id": str(task.task_id), "capability": task.required_capability,
                    "status": getattr(task.status, "value", task.status), "output": task.metadata}
                    for task in board.list_tasks()]}
            if response.status != "completed":
                raise RuntimeError(response.message)
            canonical = (await db.execute(select(Transcript).where(Transcript.meeting_id == meeting.id)
                .order_by(Transcript.created_at.desc()).limit(1))).scalar_one()
            return {"execution_mode": "REAL", "canonical_transcript_id": str(canonical.id),
                "final_segments": len(segments), "speaker_mapping": mapping,
                "deduplicated_segments_count": removed, "duration": frames / rate,
                "deduplication_decisions": processor.last_dedup_decisions,
                "ace_status": response.status, "request_id": str(response.request_id),
                "blackboard_state": board.execution_state,
                "ace_tasks": [{"id": str(task.task_id), "capability": task.required_capability,
                    "status": getattr(task.status, "value", task.status), "output": task.metadata}
                    for task in board.list_tasks()]}

    async def run_once(self, kind="all", session_id=None, job_id=None):
        job = await self.claim(kind, session_id, job_id)
        if job is None:
            return None
        self.failure_evidence = None
        stop = threading.Event()
        pulse = threading.Thread(target=self.heartbeat, args=(job, stop), daemon=True)
        pulse.start()
        result, error = None, None
        try:
            if job.kind == "batch":
                result = await self.process_batch(job)
            elif job.kind == "intelligence":
                self.release_models()
                result = await self.process_intelligence(job)
            elif job.kind == "chunk":
                result = await self.transcribe_chunk(job)
            elif job.kind == "finalize":
                # Persisted MOSS output is reused; its weights are not needed.
                self.release_models()
                result = await self.finalize(job)
            else:
                raise RuntimeError(f"Unsupported inference job kind: {job.kind}")
        except Exception as exc:
            from app.cli import sanitize_error_text
            error = sanitize_error_text(str(exc))[:4000]
            result = self.failure_evidence
        finally:
            if job.kind != "chunk" or error:
                self.release_models()
            stop.set()
            pulse.join(timeout=1)
        result = json.loads(json.dumps(result, default=str)) if result is not None else None
        event_id = str(uuid.uuid4())
        if result is not None:
            result["event_id"] = event_id
        journal = Path(self.settings.AUDIO_STORAGE_PATH) / "live-results"
        journal.mkdir(parents=True, exist_ok=True)
        with (journal / f"{job.id}_{job.lease_token}.json").open("x", encoding="utf-8") as file:
            json.dump({"job_id": str(job.id), "meeting_id": str(job.meeting_id),
                "event_id": event_id, "result": result, "error": error}, file, indent=2)
        async with self.sessions() as db:
            current = await db.get(InferenceJob, job.id, with_for_update=True)
            if current.status != "running" or current.lease_token != job.lease_token or current.lease_until < utcnow():
                raise RuntimeError("Worker lost its lease; completion was not accepted")
            current.status = "failed" if error else "completed"
            current.result, current.error, current.finished_at = result, error, utcnow()
            if job.chunk_id:
                chunk = await db.get(LiveAudioChunk, job.chunk_id)
                chunk.status = current.status
            elif job.session_id:
                session = await db.get(LiveSession, job.session_id)
                session.status = current.status
            elif error and job.kind == "batch":
                from app.models.meeting import Meeting
                meeting = await db.get(Meeting, job.meeting_id)
                meeting.status = "failed"
            await db.commit()
        from app.events.redis_bus import RedisEventBus
        await RedisEventBus().publish(f"events:meetings:{job.meeting_id}:live",
            {"event_type": "LiveInferenceFinished", "event_id": event_id,
             "job_id": str(job.id), "meeting_id": str(job.meeting_id), "status": current.status})
        return {"job_id": str(job.id), "meeting_id": str(job.meeting_id), "status": current.status, "error": error}

    async def process_intelligence(self, job):
        """Use the persisted transcript through existing understanding and SKW boundaries."""
        from app.ai.meeting_understanding import MeetingUnderstandingEngine
        from app.ai.grounded_meeting_text import EXTRACTION_VERSION
        from app.models.transcript import Transcript, TranscriptSegment
        from app.models.user import User
        from app.services.meeting_service import MeetingService
        from app.orchestration.skw_client import BlackboardSKWClient
        from app.skw.services.knowledge_query_engine import KnowledgeQueryEngine
        started = time.perf_counter()
        async with self.sessions() as db:
            actor = dict((job.payload or {}).get("actor") or {})
            user = await db.get(User, uuid.UUID(str(actor.get("user_id"))))
            if not user or not user.is_active:
                raise RuntimeError("Queued text job actor is no longer active")
            actor["role"] = user.role
            await MeetingService(db).get_meeting(job.meeting_id, actor)
            canonical = await db.get(Transcript, uuid.UUID(job.payload["canonical_transcript_id"]))
            if not canonical or canonical.meeting_id != job.meeting_id or hashlib.sha256(canonical.full_text.encode()).hexdigest() != job.payload["source_sha256"]:
                raise RuntimeError("Queued transcript changed or is unavailable")
            if self.settings.GEMINI_MODEL != job.payload["model"] or self.settings.TEXT_AI_PROVIDER.lower() != "gemini":
                raise RuntimeError("Text provider configuration changed after enqueue")
            if job.payload.get("extraction_version") != EXTRACTION_VERSION:
                raise RuntimeError("Text extraction version changed after enqueue; submit the current version explicitly")
            segments = (await db.execute(select(TranscriptSegment).where(TranscriptSegment.meeting_id == job.meeting_id)
                .order_by(TranscriptSegment.sequence_number))).scalars().all()
            turns = [{"segment_id": str(s.id), "text": s.original_text, "start_ms": s.start_time_ms,
                      "end_ms": s.end_time_ms, "speaker": s.speaker_label} for s in segments]
            if " ".join(s.original_text for s in segments) != canonical.full_text:
                raise RuntimeError("Saved segments differ from the queued canonical transcript")
            context = {"turns": turns, "source_segments": [t["segment_id"] for t in turns],
                       "source_intervals": [{"start_ms": t["start_ms"], "end_ms": t["end_ms"]} for t in turns]}
            result = await MeetingUnderstandingEngine().analyze_meeting(job.meeting_id, canonical.full_text,
                context_data=context, correlation_id=job.payload["correlation_id"], use_fixture=False)
            self.failure_evidence = {"execution_mode": "REAL", "audio_inference_executed": False,
                "canonical_transcript_id": str(canonical.id), "correlation_id": job.payload["correlation_id"],
                "generation": result.model_dump(mode="json"), "stored": []}
            # Journal actual generation before indexing can fail. Never rerun audio to recover text work.
            journal = Path(self.settings.AUDIO_STORAGE_PATH) / "live-results"
            journal.mkdir(parents=True, exist_ok=True)
            with (journal / f"{job.id}_{job.lease_token}_generation.json").open("x", encoding="utf-8") as file:
                json.dump(self.failure_evidence, file, indent=2, default=str)
            client = BlackboardSKWClient(KnowledgeQueryEngine(db))
            for item in result.knowledge_objects:
                if item.object_type == "transcript_insight":
                    continue  # Existing canonical transcript insight is already persisted.
                raw = item.model_dump(mode="json")
                raw.update(source_module="meeting_understanding", confidence_score=None)
                stored = await client.store_real_knowledge_object(job.meeting_id, raw, actor, job.payload["correlation_id"])
                self.failure_evidence["stored"].append(stored)
            self.failure_evidence["elapsed_seconds"] = time.perf_counter() - started
            return self.failure_evidence

    async def process_batch(self, job):
        from app.cli import get_cli_ace_orchestrator
        from app.services.meeting_service import MeetingService
        from app.schemas.meeting import MeetingProcessingRequest
        started = time.perf_counter()
        async with self.sessions() as db:
            actor = (job.payload or {}).get("actor")
            if not actor or not actor.get("authenticated"):
                raise RuntimeError("Queued meeting has no authorized actor")
            service = MeetingService(db)
            meeting = await service.get_meeting(job.meeting_id, actor)
            audio = next((a for a in meeting.audio_recordings if str(a.id) == job.payload.get("audio_id")), None)
            if audio is None:
                raise RuntimeError("Queued audio record is unavailable")
            path = self.resolve_persisted_audio_path(audio.file_path)
            if not path.is_relative_to(Path(self.settings.AUDIO_STORAGE_PATH).resolve()):
                raise RuntimeError("Audio path is outside configured storage")
            ace = get_cli_ace_orchestrator(db)
            for capability in ("multilingual_asr", "audio_intelligence", "speaker_representation"):
                original = ace.module_runner._handlers[capability]
                async def bound(payload, handler=original):
                    return await handler({**payload, "input": {**payload["input"], "audio_file_path": str(path)}})
                ace.module_runner.register_capability_handler(capability, bound)
            self.release_after_stages(ace)
            result = await service.process_meeting(meeting.id, MeetingProcessingRequest(
                request_id=job.id, correlation_id=job.payload["correlation_id"], force_reprocess=True), actor, ace)
            board = ace.blackboards.get(meeting.id)
            self.failure_evidence = {"execution_mode": "REAL", "elapsed_seconds": time.perf_counter()-started,
                "ace_status": result.status, "ace_tasks": [{"id": str(t.task_id), "capability": t.required_capability,
                "status": getattr(t.status, "value", t.status), "output": t.metadata} for t in board.list_tasks()] if board else []}
            if result.status != "completed":
                for task in self.failure_evidence["ace_tasks"]:
                    if str(task["status"]).upper() != "FAILED":
                        continue
                    output = task.get("output") or {}
                    detail = output.get("error_message") if isinstance(output, dict) else None
                    if detail:
                        self.failure_evidence["first_failure"] = {
                            "task_id": task["id"], "capability": task["capability"],
                            "error": str(detail),
                        }
                        raise RuntimeError(f"{task['capability']} failed: {detail}")
                raise RuntimeError(result.message)
            return {**self.failure_evidence, "blackboard_state": board.execution_state,
                    "canonical_transcript_id": board.execution_state.get("transcript_persistence", {}).get("canonical_transcript_id")}


async def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--kind", choices=["all", "chunk", "finalize", "batch", "intelligence"], default="all")
    parser.add_argument("--session-id", type=uuid.UUID)
    parser.add_argument("--warmup", action="store_true", help="Load cached CUDA MOSS before accepting jobs")
    args = parser.parse_args()
    worker = LiveInferenceWorker()
    try:
        if args.warmup and args.kind not in {"finalize", "intelligence"}:
            import torch
            from app.ai.multilingual_asr import OpenMOSSProvider
            if not torch.cuda.is_available():
                raise RuntimeError("CUDA unavailable; no CPU fallback")
            worker.provider = OpenMOSSProvider({"model_id": worker.settings.OPENMOSS_MODEL_ID,
                "device": worker.settings.OPENMOSS_DEVICE, "cache_dir": worker.settings.OPENMOSS_CACHE_DIR,
                "token": worker.settings.HF_TOKEN})
            worker.provider._load_model()
            print(json.dumps({"status": "READY", "model_loaded": True, "inference_executed": False}), flush=True)
        while True:
            result = await worker.run_once(args.kind, args.session_id)
            if result:
                print(json.dumps(result), flush=True)
            if args.once:
                if result is None:
                    print(json.dumps({"status": "IDLE", "inference_executed": False}), flush=True)
                if result and result["status"] != "completed":
                    raise SystemExit(1)
                return
            if result is None:
                await asyncio.sleep(1)
    finally:
        await close_database_connections()


if __name__ == "__main__":
    asyncio.run(main())
