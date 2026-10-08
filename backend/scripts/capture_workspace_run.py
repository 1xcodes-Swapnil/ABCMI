"""Capture UI-run evidence and fresh readback; never starts model inference."""
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
import wave

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))


def save(path, value):
    with path.open("x", encoding="utf-8") as handle:
        json.dump(value, handle, indent=2, default=str)


async def capture(folder, meeting_id):
    folder = folder.resolve()
    os.environ.update(EXECUTION_MODE="REAL", DEBUG="false", LOG_LEVEL="CRITICAL", HF_HUB_OFFLINE="1")
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import async_sessionmaker
    from app.infrastructure.database import init_database, close_database_connections
    from app.models.meeting import Meeting
    from app.models.user import User
    from app.models.transcript import Transcript, TranscriptSegment
    from app.models.knowledge_object import KnowledgeObject
    from app.core.security import create_access_token
    import httpx
    result = {"timestamp": datetime.now(timezone.utc).isoformat(), "meeting_id": str(meeting_id),
              "capture_process_id": os.getpid(), "inference_started_by_capture": False}
    async with async_sessionmaker(init_database(), expire_on_commit=False)() as db:
        meeting = await db.get(Meeting, meeting_id)
        if not meeting or not meeting.host_id:
            raise RuntimeError("Meeting or authorized host unavailable")
        user = await db.get(User, meeting.host_id)
        if not user or not user.is_active:
            raise RuntimeError("Host is not active")
        token = create_access_token(data={"sub":str(user.id), "role":user.role, "tenant_id":meeting.tenant_id})
        canonical = (await db.execute(select(Transcript).where(Transcript.meeting_id == meeting_id)
            .order_by(Transcript.created_at.desc()))).scalars().first()
        segments = (await db.execute(select(TranscriptSegment).where(TranscriptSegment.meeting_id == meeting_id)
            .order_by(TranscriptSegment.start_time_ms, TranscriptSegment.end_time_ms))).scalars().all()
        result.update(meeting_status=meeting.status, canonical_transcript_id=str(canonical.id) if canonical else "NOT AVAILABLE",
            database_segments=[{"segment_id":str(s.id), "original_text":s.original_text,
                "start_time_ms":s.start_time_ms, "end_time_ms":s.end_time_ms, "speaker_label":s.speaker_label,
                "confidence":s.confidence} for s in segments])
        knowledge = (await db.execute(select(KnowledgeObject).where(KnowledgeObject.meeting_id == meeting_id))).scalars().all()
        point_ids = [str(k.qdrant_point_id) for k in knowledge if k.qdrant_point_id]
    if point_ids:
        from app.infrastructure.qdrant import get_qdrant_client, close_qdrant_client
        client = await get_qdrant_client()
        points = await client.retrieve(collection_name="abci_knowledge_objects", ids=point_ids,
            with_payload=True, with_vectors=False)
        result["qdrant_fresh_readback"] = [{"id":str(p.id), "payload":p.payload} for p in points]
        result["qdrant_ids_match"] = sorted(str(p.id) for p in points) == sorted(point_ids)
        await close_qdrant_client()
    else:
        result["qdrant_fresh_readback"] = "NOT AVAILABLE: no persisted point ID"
    from app.infrastructure.redis import check_redis_health
    redis = await check_redis_health()
    result["redis_connectivity"] = {key:redis.get(key) for key in ("status", "latency_ms")}
    result["redis_delivery_capture"] = "NOT AVAILABLE: no subscriber journal for this run"
    gpu = subprocess.run(["nvidia-smi", "--query-gpu=name,memory.total,memory.used,utilization.gpu", "--format=csv"],
                         text=True, capture_output=True)
    result["gpu_after_readback"] = gpu.stdout.strip() if gpu.returncode == 0 else "NOT AVAILABLE"
    async with httpx.AsyncClient(base_url="http://127.0.0.1:3000/api/v1", timeout=45,
            headers={"Authorization":"Bearer "+token}) as client:
        for name, suffix in {"pipeline":"pipeline", "transcript":"transcript", "audio":"",
                             "queries":"queries", "reports":"reports"}.items():
            response = await client.get(f"/meetings/{meeting_id}" + ("/"+suffix if suffix else ""))
            result[name] = {"http_status":response.status_code, "body":response.json()}
        response = await client.get(f"/knowledge/meeting/{meeting_id}")
        result["knowledge"] = {"http_status":response.status_code, "body":response.json()}
    api_rows = result["transcript"]["body"]
    result["fresh_readback_matches_api"] = bool(segments) and isinstance(api_rows, list) and sorted(
        [(s["segment_id"], s["original_text"], s["start_time_ms"], s["end_time_ms"]) for s in result["database_segments"]]
    ) == sorted([(str(s["segment_id"]), s["original_text"], s["start_time_ms"], s["end_time_ms"]) for s in api_rows])
    path = folder / ("readback_" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S_%fZ") + ".json")
    save(path, result)
    await close_database_connections()
    print(json.dumps({"meeting_id":str(meeting_id), "meeting_status":result["meeting_status"],
        "canonical_transcript_id":result["canonical_transcript_id"], "segments":len(segments),
        "fresh_readback_matches_api":result["fresh_readback_matches_api"], "artifact":str(path.relative_to(ROOT))}))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--audio", type=Path)
    parser.add_argument("--run", type=Path)
    parser.add_argument("--meeting", type=uuid.UUID)
    args = parser.parse_args()
    if args.meeting:
        if not args.run or not args.run.is_dir():
            parser.error("Capture requires the existing --run directory")
        try:
            asyncio.run(capture(args.run, args.meeting))
        except Exception as exc:
            # Preserve failure evidence without serializing connection credentials.
            path = args.run / ("readback_failed_" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S_%fZ") + ".json")
            result = {"status": "BLOCKED", "timestamp": datetime.now(timezone.utc).isoformat(),
                      "meeting_id": str(args.meeting), "error_type": type(exc).__name__,
                      "inference_started_by_capture": False,
                      "readback_verified": False}
            save(path, result)
            print(json.dumps({**result, "artifact": str(path)}))
            raise SystemExit(1) from None
        return
    if not args.audio or not args.audio.is_file():
        parser.error("Preparation requires an existing --audio file")
    folder = ROOT / "e2e_validation/runs" / ("workspace_dataset_" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"))
    folder.mkdir(parents=True, exist_ok=False)
    with wave.open(str(args.audio), "rb") as audio:
        metadata = {"duration_seconds":audio.getnframes()/audio.getframerate(), "sample_rate":audio.getframerate(),
                    "channels":audio.getnchannels()}
    save(folder / "input.json", {"run_id":folder.name, "timestamp":datetime.now(timezone.utc).isoformat(),
        "file":str(args.audio.relative_to(ROOT) if args.audio.is_absolute() else args.audio),
        "sha256":hashlib.sha256(args.audio.read_bytes()).hexdigest(), "size_bytes":args.audio.stat().st_size,
        **metadata, "execution_mode":"REAL", "git_commit":subprocess.check_output(["git","rev-parse","HEAD"],cwd=ROOT,text=True).strip(),
        "working_tree_changes":True, "status":"PREPARED; inference not yet attempted"})
    print(folder.relative_to(ROOT))


if __name__ == "__main__":
    main()
