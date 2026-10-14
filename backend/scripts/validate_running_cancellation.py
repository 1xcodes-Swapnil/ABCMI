"""Cancel a REAL meeting at its first observed chunk start; preserve actual journals."""
import argparse
import asyncio
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
import time
import uuid

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
os.environ.update(EXECUTION_MODE="REAL", DEBUG="false", LOG_LEVEL="CRITICAL", HF_HUB_OFFLINE="1")


async def main(args):
    import httpx
    from sqlalchemy.ext.asyncio import async_sessionmaker
    from app.infrastructure.database import init_database, close_database_connections
    from app.infrastructure.redis import get_redis_client, close_redis_client
    from app.models.meeting import Meeting
    from app.models.user import User
    from app.core.config import get_settings
    from app.core.security import create_access_token
    sessions = async_sessionmaker(init_database())
    async with sessions() as db:
        meeting = await db.get(Meeting, args.meeting)
        if meeting.status != "created":
            raise RuntimeError("Use a newly uploaded real meeting; never resubmit an active job")
        user = await db.get(User, meeting.host_id)
        if not user or not user.is_active:
            raise RuntimeError("Authorized existing host required")
        token = create_access_token({"sub": str(user.id), "role": user.role, "tenant_id": meeting.tenant_id})
    redis = await get_redis_client()
    pubsub = redis.pubsub()
    await pubsub.psubscribe("*")
    events, cancel_sent = [], False
    started = time.perf_counter()
    try:
        async with httpx.AsyncClient(base_url="http://127.0.0.1:3000/api/v1", timeout=30,
                headers={"Authorization": "Bearer " + token}) as client:
            response = await client.post(f"/meetings/{args.meeting}/process-async", json={})
            response.raise_for_status()
            job_id = response.json()["job_id"]
            (args.run / "running_cancel_submitted.json").write_text(json.dumps(response.json()), encoding="utf-8")
            print(json.dumps({"job_id": job_id, "meeting_id": str(args.meeting)}), flush=True)
            while time.perf_counter()-started < 150:
                message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1)
                if message and str(args.meeting) in str(message["data"]):
                    event = json.loads(message["data"])
                    events.append(event)
                    if event.get("event_type") == "chunk_started" and not cancel_sent:
                        response = await client.post(f"/meetings/{args.meeting}/cancel",
                            json={"reason": "REAL running-cancellation validation after first chunk starts"})
                        response.raise_for_status()
                        cancel_sent = True
                        print("Cancellation accepted after actual chunk_started event", flush=True)
                if cancel_sent:
                    response = await client.get(f"/meetings/{args.meeting}/pipeline")
                    response.raise_for_status()
                    pipeline = response.json()
                    job = next(j for j in pipeline["jobs"] if j["id"] == job_id)
                    history = Path(get_settings().AUDIO_CHUNK_STATE_DIR) / str(args.meeting)
                    states = sorted(history.glob("state_*.json"))
                    stopped_at_boundary = bool(states and json.loads(states[-1].read_text(encoding="utf-8"))["overall_status"] == "cancelled")
                    if job["status"] in {"completed", "failed"} or (job["status"] == "cancelled" and stopped_at_boundary):
                        break
                await asyncio.sleep(.1)
            else:
                raise RuntimeError("Cancellation observation deadline; inspect saved job before any further action")
            history = Path(get_settings().AUDIO_CHUNK_STATE_DIR) / str(args.meeting)
            state_file = sorted(history.glob("state_*.json"))[-1]
            state = json.loads(state_file.read_text(encoding="utf-8"))
            inference_files = list(history.glob("inference_*.json"))
            assert cancel_sent and job["status"] == "cancelled" and pipeline["status"] == "cancelled"
            assert pipeline["canonical_transcript_id"] is None
            assert state["overall_status"] == "cancelled" and state["completed_chunks_count"] == 1
            assert len(inference_files) == 1
            inference = json.loads(inference_files[0].read_text(encoding="utf-8"))
            assert inference["raw_moss_output"] and inference["segment_payloads"]
            report = {"status": "VERIFIED", "gate": "running cancellation", "timestamp": datetime.now(timezone.utc).isoformat(),
                "meeting_id": str(args.meeting), "job_id": job_id, "meeting_status": pipeline["status"],
                "job_status": job["status"], "planned_chunks": state["total_chunks"], "completed_chunks": 1,
                "chunk_ids": [c["chunk_id"] for c in state["chunks"]], "canonical_transcript_id": "NOT AVAILABLE",
                "moss_generation_completed": True, "actual_cached_segments": len(inference["segment_payloads"]),
                "remaining_chunks_inferred": False, "checkpoint": str(state_file.relative_to(ROOT)),
                "raw_inference_artifact": str(inference_files[0].relative_to(ROOT)),
                "elapsed_seconds": time.perf_counter()-started, "pipeline": pipeline}
            with (args.run / "running_cancellation.json").open("x", encoding="utf-8") as output:
                json.dump(report, output, indent=2)
            print(json.dumps({k: v for k, v in report.items() if k != "pipeline"}), flush=True)
    except Exception as exc:
        from app.cli import sanitize_error_text
        with (args.run / "running_cancel_failure.json").open("x", encoding="utf-8") as output:
            json.dump({"status": "NOT VERIFIED", "error_type": type(exc).__name__,
                "reason": sanitize_error_text(str(exc)), "meeting_id": str(args.meeting)}, output, indent=2)
        raise
    finally:
        with (args.run / "running_cancel_events.json").open("x", encoding="utf-8") as output:
            json.dump(events, output, indent=2)
        await pubsub.aclose()
        await close_redis_client()
        await close_database_connections()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", required=True, type=Path)
    parser.add_argument("--meeting", required=True, type=uuid.UUID)
    asyncio.run(main(parser.parse_args()))
