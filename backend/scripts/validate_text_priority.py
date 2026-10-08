"""One REAL text job on an existing transcript. No audio inference or fixture data."""
import asyncio
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
import uuid

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
os.environ.update(EXECUTION_MODE="REAL", DEBUG="false", LOG_LEVEL="CRITICAL", HF_HUB_OFFLINE="1",
                  TRANSFORMERS_OFFLINE="1", OPENMOSS_DEVICE="cuda", SEMANTIC_EMBEDDING_DEVICE="cuda")


async def main(meeting_id):
    from httpx import AsyncClient, ASGITransport
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import async_sessionmaker
    from app.infrastructure.database import init_database, close_database_connections
    from app.models.meeting import Meeting
    from app.models.user import User
    from app.models.inference_job import InferenceJob
    from app.models.knowledge_object import KnowledgeObject
    from app.core.security import create_access_token
    from app.main import app
    from app.services.live_inference_worker import LiveInferenceWorker
    run_id = "text_priority_" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    folder = ROOT / "e2e_validation/runs" / run_id
    folder.mkdir(parents=True, exist_ok=False)
    sessions = async_sessionmaker(init_database(), expire_on_commit=False)
    evidence = {"run_id": run_id, "meeting_id": str(meeting_id), "audio_inference_executed": False,
                "timestamp": datetime.now(timezone.utc).isoformat(), "status": "NOT VERIFIED"}
    try:
        async with sessions() as db:
            meeting = await db.get(Meeting, meeting_id)
            user = await db.get(User, meeting.host_id)
            token = create_access_token({"sub": str(user.id), "role": user.role, "tenant_id": meeting.tenant_id})
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://abci.local",
                               headers={"Authorization": f"Bearer {token}"}) as client:
            response = await client.post(f"/api/v1/meetings/{meeting_id}/intelligence/generate")
            evidence["enqueue"] = {"http_status": response.status_code, "body": response.json()}
            if response.status_code != 202:
                raise RuntimeError(f"Enqueue HTTP {response.status_code}")
            job_id = uuid.UUID(response.json()["job_id"])
            evidence["job_id"] = str(job_id)
            with (folder / "enqueued.json").open("x", encoding="utf-8") as file:
                json.dump(evidence, file, indent=2)
            if response.json()["status"] == "queued":
                evidence["worker"] = await LiveInferenceWorker().run_once("intelligence", job_id=job_id)
            async with sessions() as db:
                job = await db.get(InferenceJob, job_id)
                evidence["job_status"], evidence["error"] = job.status, job.error
                evidence["result"] = job.result
                ids = [uuid.UUID(s["knowledge_id"]) for s in (job.result or {}).get("stored", [])]
                stored = (await db.execute(select(KnowledgeObject).where(KnowledgeObject.id.in_(ids)))).scalars().all() if ids else []
                evidence["readback"] = [{"id": str(k.id), "object_type": k.object_type,
                    "content": k.content, "confidence": k.confidence, "provenance": k.provenance,
                    "qdrant_point_id": k.qdrant_point_id} for k in stored]
                evidence["fresh_session_count_matches"] = len(stored) == len(ids)
                if job.status != "completed":
                    raise RuntimeError("Text worker failed; see persisted error")
            summary = await client.get(f"/api/v1/meetings/{meeting_id}/summary")
            evidence["summary_api"] = {"http_status": summary.status_code, "body": summary.json()}
            evidence["status"] = "VERIFIED" if summary.status_code == 200 and stored else "NOT VERIFIED"
    except Exception as exc:
        evidence["status"] = "BLOCKED"
        evidence["error_type"] = type(exc).__name__
        # Omit arbitrary exception messages to avoid credential-bearing diagnostics.
    finally:
        with (folder / "result.json").open("x", encoding="utf-8") as file:
            json.dump(evidence, file, indent=2, default=str)
        await close_database_connections()
    print(json.dumps({k: evidence.get(k) for k in ("run_id", "meeting_id", "job_id", "status", "job_status", "error_type", "error")}, indent=2))
    print(f"Evidence: {folder.relative_to(ROOT)}")
    if evidence["status"] != "VERIFIED":
        raise SystemExit(1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--meeting", type=uuid.UUID, default=uuid.UUID("2126caea-4e13-4902-a02f-12a8260db0bd"))
    asyncio.run(main(parser.parse_args().meeting))
