"""Submit an existing uploaded REAL meeting once, capturing actual API/Redis evidence."""
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


async def run(args):
    import httpx
    from sqlalchemy.ext.asyncio import async_sessionmaker
    from app.infrastructure.database import init_database, close_database_connections
    from app.infrastructure.redis import get_redis_client
    from app.models.meeting import Meeting
    from app.models.user import User
    from app.core.security import create_access_token
    from app.cli import sanitize_error_text

    folder = args.run.resolve()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S_%fZ")
    evidence = folder / f"processing_{stamp}.json"
    event_path = folder / f"redis_events_{stamp}.jsonl"
    result = {"meeting_id": str(args.meeting), "timestamp": datetime.now(timezone.utc).isoformat(),
              "status": "NOT VERIFIED", "event_artifact": str(event_path.relative_to(ROOT))}
    pubsub = None
    event_task = None
    received = 0
    started = time.perf_counter()
    try:
        async with async_sessionmaker(init_database(), expire_on_commit=False)() as db:
            meeting = await db.get(Meeting, args.meeting)
            if not meeting or meeting.status != "created":
                raise RuntimeError("Only an existing created meeting may be submitted; inspect saved jobs first")
            user = await db.get(User, meeting.host_id)
            if not user or not user.is_active:
                raise RuntimeError("Existing authorized host is unavailable")
            token = create_access_token(data={"sub": str(user.id), "role": user.role, "tenant_id": meeting.tenant_id})

        redis = await get_redis_client()
        pubsub = redis.pubsub()
        await pubsub.psubscribe("*")

        async def collect():
            nonlocal received
            with event_path.open("x", encoding="utf-8") as handle:
                while True:
                    message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1)
                    if not message:
                        await asyncio.sleep(0.05)
                        continue
                    raw = message["data"]
                    if isinstance(raw, bytes):
                        raw = raw.decode("utf-8")
                    if str(args.meeting) not in str(raw):
                        continue
                    try:
                        event = json.loads(raw)
                    except (ValueError, TypeError):
                        continue
                    channel = message["channel"]
                    if isinstance(channel, bytes):
                        channel = channel.decode("utf-8")
                    handle.write(json.dumps({"received_at": datetime.now(timezone.utc).isoformat(),
                                             "channel": channel, "event": event}, default=str) + "\n")
                    handle.flush()
                    received += 1

        event_task = asyncio.create_task(collect())
        async with httpx.AsyncClient(base_url="http://127.0.0.1:3000/api/v1", timeout=30,
                headers={"Authorization": "Bearer " + token}) as client:
            response = await client.post(f"/meetings/{args.meeting}/process-async", json={})
            result["submission"] = {"http_status": response.status_code, "body": response.json()}
            response.raise_for_status()
            with evidence.open("x", encoding="utf-8") as handle:
                json.dump(result, handle, indent=2)
            print(json.dumps(result["submission"]), flush=True)
            deadline = time.monotonic() + getattr(args, "observation_seconds", 600)
            while time.monotonic() < deadline:
                response = await client.get(f"/meetings/{args.meeting}/pipeline")
                response.raise_for_status()
                pipeline = response.json()
                result["pipeline"] = pipeline
                if pipeline["status"] in {"completed", "failed"}:
                    result["status"] = "COMPLETED; fresh readback required" if pipeline["status"] == "completed" else "BLOCKED"
                    break
                await asyncio.sleep(5)
            else:
                result["status"] = "BLOCKED"
                result["error"] = "Observation deadline reached; inspect existing job before resuming. Do not resubmit."
    except Exception as exc:
        result.update(status="BLOCKED", error_type=type(exc).__name__, error=sanitize_error_text(str(exc)))
    finally:
        if event_task:
            event_task.cancel()
            try:
                await event_task
            except asyncio.CancelledError:
                pass
        if pubsub:
            await pubsub.aclose()
        await close_database_connections()
        result.update(received_events=received, elapsed_seconds=time.perf_counter() - started)
        final = folder / f"processing_result_{stamp}.json"
        with final.open("x", encoding="utf-8") as handle:
            json.dump(result, handle, indent=2, default=str)
        print(json.dumps({"status": result["status"], "received_events": received,
                          "artifact": str(final.relative_to(ROOT))}), flush=True)
    return 0 if result["status"].startswith("COMPLETED") else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--meeting", type=uuid.UUID, required=True)
    args = parser.parse_args()
    if not args.run.is_dir():
        parser.error("Use an existing evidence directory")
    raise SystemExit(asyncio.run(run(args)))
