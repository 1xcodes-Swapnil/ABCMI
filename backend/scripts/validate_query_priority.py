"""One real grounded answer over an existing transcript, with fresh-process readback."""
import asyncio
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import uuid

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
os.environ.update(EXECUTION_MODE="REAL", DEBUG="false", LOG_LEVEL="CRITICAL")


async def main():
    from httpx import AsyncClient, ASGITransport
    from sqlalchemy.ext.asyncio import async_sessionmaker
    from app.infrastructure.database import init_database, close_database_connections
    from app.models.meeting import Meeting
    from app.models.user import User
    from app.models.query_record import QueryRecord
    from app.core.security import create_access_token
    from app.main import app
    from app.infrastructure.redis import get_redis_client
    from app.services.notification_listener import consume_notification_event
    from app.models.notification import Notification
    from sqlalchemy import select

    sessions = async_sessionmaker(init_database(), expire_on_commit=False)
    if len(sys.argv) == 4 and sys.argv[1] == "--readback":
        async with sessions() as db:
            row = await db.get(QueryRecord, uuid.UUID(sys.argv[2]))
            data = None if row is None else {"query_id": str(row.id), "answer": row.answer,
                "status": row.status, "sources": row.sources, "provenance": row.provenance,
                "confidence": row.confidence, "correlation_id": row.correlation_id}
            Path(sys.argv[3]).write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
        await close_database_connections()
        return

    folder = ROOT / "e2e_validation/runs" / ("query_priority_" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"))
    folder.mkdir(parents=True, exist_ok=False)
    meeting_id = uuid.UUID("2126caea-4e13-4902-a02f-12a8260db0bd")
    correlation = str(uuid.uuid4())
    result = {"run_id": folder.name, "meeting_id": str(meeting_id), "correlation_id": correlation,
        "timestamp": datetime.now(timezone.utc).isoformat(), "audio_inference_executed": False,
        "status": "NOT VERIFIED", "redis_events": []}
    pubsub = None
    try:
        async with sessions() as db:
            meeting = await db.get(Meeting, meeting_id)
            user = await db.get(User, meeting.host_id)
            token = create_access_token({"sub": str(user.id), "role": user.role, "tenant_id": meeting.tenant_id})
        redis = await get_redis_client()
        if redis is None:
            raise RuntimeError("Redis unavailable")
        pubsub = redis.pubsub()
        await pubsub.psubscribe("abci.query.*")
        ack = await pubsub.get_message(timeout=5)
        if not ack or ack.get("type") != "psubscribe":
            raise RuntimeError("Redis subscription acknowledgement missing")
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://abci.local",
                headers={"Authorization": f"Bearer {token}"}) as client:
            started = time.perf_counter()
            response = await client.post("/api/v1/queries", json={
                "query": "What did the speakers confirm at the start of this meeting?",
                "meeting_id": str(meeting_id), "retrieval_mode": "structured", "correlation_id": correlation})
            result.update(http_status=response.status_code, response=response.json(),
                processing_seconds=time.perf_counter()-started)
            response.raise_for_status()
            body = response.json()
            if not body.get("sources") or not body.get("provenance", {}).get("citation_quotes_validated"):
                raise RuntimeError("No grounded generated answer")
            if body["confidence"] is not None or body["status"] == "failed":
                raise RuntimeError("Invalid answer state")
            for _ in range(8):
                event = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1)
                if event and event["type"] == "pmessage":
                    data = json.loads(event["data"])
                    if data.get("correlation_id") == correlation:
                        channel = event["channel"].decode() if isinstance(event["channel"], bytes) else event["channel"]
                        result["redis_events"].append({"channel": channel, "data": data})
                        await consume_notification_event(channel, data)
            fresh_path = folder / "fresh_process_readback.json"
            proc = await asyncio.to_thread(subprocess.run, [sys.executable, str(Path(__file__).resolve()),
                "--readback", body["query_id"], str(fresh_path)], cwd=ROOT, capture_output=True, text=True)
            result["readback_exit_code"] = proc.returncode
            if proc.returncode or not fresh_path.exists():
                raise RuntimeError("Fresh process readback failed")
            fresh = json.loads(fresh_path.read_text(encoding="utf-8"))
            result["fresh_process_matches"] = bool(fresh and all(fresh[k] == body[k] for k in
                ("query_id", "answer", "status", "sources", "provenance", "confidence", "correlation_id")))
            read = await client.get("/api/v1/queries/" + body["query_id"])
            result["readback_http_status"] = read.status_code
            result["api_readback_matches"] = read.status_code == 200 and read.json()["answer"] == body["answer"]
            async with sessions() as db:
                notifications = (await db.execute(select(Notification).where(Notification.correlation_id == correlation))).scalars().all()
                result["notifications"] = [{"id": str(n.id), "event_id": n.event_id, "title": n.title} for n in notifications]
            if result["fresh_process_matches"] and result["api_readback_matches"] and result["redis_events"] and result["notifications"]:
                result["status"] = "VERIFIED"
    except Exception as exc:
        result.update(status="BLOCKED", error_type=type(exc).__name__)
    finally:
        if pubsub is not None:
            await pubsub.aclose()
        with (folder / "result.json").open("x", encoding="utf-8") as handle:
            json.dump(result, handle, indent=2, default=str)
        await close_database_connections()
    print(json.dumps({k: result.get(k) for k in ("run_id", "status", "http_status", "processing_seconds", "error_type")}, indent=2))
    if result["status"] != "VERIFIED":
        raise SystemExit(1)


if __name__ == "__main__":
    asyncio.run(main())
