"""Recover only a failed English identity stage; never load an audio/LM provider.

Requires all other production stages completed and the exact published canonical
transcript. Keeps the failed attempt and creates a separately recorded recovery.
"""
import argparse
import asyncio
import copy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
import time
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


async def recover(args, evidence):
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import async_sessionmaker
    from app.core.config import get_settings
    from app.infrastructure.database import init_database, close_database_connections
    from app.models.inference_job import InferenceJob
    from app.models.transcript import Transcript, TranscriptSegment
    from app.services.meeting_service import MeetingService
    from app.orchestration.module_runner import AIModuleRunner
    from app.ai.code_switch_intelligence import declared_english_identity
    if get_settings().EXECUTION_MODE != "REAL":
        raise RuntimeError("Recovery requires REAL mode")
    sessions = async_sessionmaker(init_database(), expire_on_commit=False)
    started = time.perf_counter()
    try:
        async with sessions() as db:
            old = await db.get(InferenceJob, uuid.UUID(args.job_id))
            if not old or old.kind != "batch" or old.status != "failed":
                raise RuntimeError("Source must be the exact failed batch attempt")
            actor = (old.payload or {}).get("actor")
            if not actor or not actor.get("authenticated"):
                raise RuntimeError("No saved authorized actor")
            service = MeetingService(db)
            meeting = await service.get_meeting(old.meeting_id, actor)
            if meeting.status != "failed":
                raise RuntimeError("Only a failed meeting can use this recovery")
            active = (await db.execute(select(InferenceJob.id).where(
                InferenceJob.meeting_id == meeting.id,
                InferenceJob.status.in_(["queued", "running", "processing"])))).first()
            if active:
                raise RuntimeError("This meeting has another active attempt; recovery deferred")
            tasks = copy.deepcopy((old.result or {}).get("ace_tasks", []))
            if ({t["capability"] for t in tasks} != set(AIModuleRunner.SUPPORTED_CAPABILITIES)
                    or len(tasks) != len(AIModuleRunner.SUPPORTED_CAPABILITIES)
                    or any(t["status"] != ("FAILED" if t["capability"] == "code_switch_intelligence" else "COMPLETED") for t in tasks)):
                raise RuntimeError("Recovery requires exactly one failed code-switch stage and every other stage completed")
            upstream = {t["capability"]: t["output"] for t in tasks if t["status"] == "COMPLETED"}
            asr = upstream["multilingual_asr"]
            if asr.get("metadata", {}).get("is_fixture") is not False:
                raise RuntimeError("Saved ASR lacks REAL provenance")
            languages = list(dict.fromkeys([meeting.language, *(meeting.secondary_languages or [])]))
            if declared_english_identity(asr["transcript"], asr["segments"], languages, asr.get("detected_languages")) is None:
                raise RuntimeError("This tool permits explicit English identity only; no translation model fallback")
            canonical = (await db.execute(select(Transcript).where(Transcript.meeting_id == meeting.id)
                                         .order_by(Transcript.version.desc()))).scalars().first()
            if (not canonical or str(canonical.id) != args.canonical_id
                    or old.result.get("canonical_transcript_id") != args.canonical_id):
                raise RuntimeError("Published canonical transcript differs from the supplied failure")
            signature_query = select(TranscriptSegment).where(TranscriptSegment.meeting_id == meeting.id).order_by(TranscriptSegment.sequence_number)
            rows = (await db.execute(signature_query)).scalars().all()
            signature = lambda items: [(str(r.id), r.original_text, r.start_time_ms, r.end_time_ms, r.speaker_label) for r in items]
            before = signature(rows)
            if not before or canonical.full_text != " ".join(r.original_text for r in rows):
                raise RuntimeError("Published transcript/segments do not match")
            # Same immutable upload only. A later upload must use its own pipeline.
            audio = max(meeting.audio_recordings, key=lambda a: a.created_at)
            if str(audio.id) != old.payload.get("audio_id"):
                raise RuntimeError("Meeting has a different upload; saved audio stages cannot be reused")
            job_id, task_id, correlation = uuid.uuid4(), uuid.uuid4(), str(uuid.uuid4())
            result = await AIModuleRunner().execute_task("code_switch_intelligence", task_id,
                meeting.id, job_id, {"upstream_results": upstream, "target_languages": languages}, correlation)
            if result["result_data"].get("generation_executed") is not False:
                raise RuntimeError("Unexpected model generation in identity recovery")
            for task in tasks:
                if task["capability"] == "code_switch_intelligence":
                    task.update(id=str(task_id), status="COMPLETED", output=result["result_data"])
            now = datetime.now(timezone.utc)
            recovery = {"source_job_id": str(old.id), "job_id": str(job_id), "task_id": str(task_id),
                        "correlation_id": correlation, "timestamp": now.isoformat(),
                        "operation": "declared_english_identity", "audio_inference_executed": False,
                        "model_generation_executed": False}
            provenance = dict(canonical.provenance or {})
            provenance["stage_recoveries"] = [*(provenance.get("stage_recoveries") or []),
                {**recovery, "previous_stage_statuses": provenance.get("stage_statuses", [])}]
            provenance.update(meeting_processing_status="completed",
                stage_statuses=[{k:t[k] for k in ("id", "capability", "status")} for t in tasks])
            canonical.provenance = provenance
            meeting.status = "completed"
            job_result = {"execution_mode": "REAL", "ace_status": "completed", "ace_tasks": tasks,
                          "canonical_transcript_id": str(canonical.id), "recovery": recovery,
                          "elapsed_seconds": time.perf_counter() - started}
            new_job = InferenceJob(id=job_id, job_key=f"english-stage-recovery:{old.id}:{job_id}",
                kind="batch", meeting_id=meeting.id,
                payload={**old.payload, "correlation_id": correlation, "recovery_source_job_id": str(old.id)},
                status="completed", result=job_result, started_at=now, finished_at=now)
            db.add(new_job)
            await db.commit()
            async with sessions() as reader:
                after = (await reader.execute(signature_query)).scalars().all()
                saved = await reader.get(Transcript, canonical.id)
                saved_job = await reader.get(InferenceJob, job_id)
                if (signature(after) != before or saved.full_text != canonical.full_text
                        or saved.provenance != provenance or saved_job.status != "completed"):
                    raise RuntimeError("Fresh recovery readback differs")
            evidence.update(status="VERIFIED", **recovery, meeting_id=str(meeting.id),
                canonical_transcript_id=str(canonical.id), segments_preserved=len(rows),
                transcript_sha256=hashlib.sha256(canonical.full_text.encode()).hexdigest(),
                transcript_unchanged=True, previous_attempt_status=old.status,
                completed_stages=len(tasks), fresh_readback="PASSED")
    finally:
        await close_database_connections()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--job-id", required=True)
    parser.add_argument("--canonical-id", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    evidence = {"run_id": str(uuid.uuid4()), "status": "RUNNING", "source_job_id": args.job_id,
                "audio_inference_executed": False, "model_generation_executed": False}
    with args.output.open("x", encoding="utf-8") as file:
        json.dump(evidence, file)
    try:
        asyncio.run(recover(args, evidence))
    except Exception as exc:
        evidence.update(status="BLOCKED", error_type=type(exc).__name__, reason=str(exc))
    temporary = args.output.with_suffix(".tmp")
    temporary.write_text(json.dumps(evidence, indent=2), encoding="utf-8")
    temporary.replace(args.output)
    print(json.dumps(evidence))
    return 0 if evidence["status"] == "VERIFIED" else 1


if __name__ == "__main__":
    sys.exit(main())
