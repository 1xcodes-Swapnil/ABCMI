"""Read existing REAL results through the frontend proxy, without inference."""
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
os.environ.update(EXECUTION_MODE="REAL", DEBUG="false", LOG_LEVEL="CRITICAL")


async def main(args):
    import httpx
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import async_sessionmaker
    from app.infrastructure.database import init_database, close_database_connections
    from app.models.inference_job import InferenceJob
    from app.models.meeting import Meeting
    from app.models.user import User
    from app.core.security import create_access_token
    from app.cli import sanitize_error_text

    folder = ROOT / "e2e_validation/runs" / ("priority_workspace_" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ"))
    folder.mkdir()
    report = {"run_id": folder.name, "timestamp": datetime.now(timezone.utc).isoformat(),
              "meeting_id": str(args.meeting_id), "inference_executed": False, "endpoints": {}}
    try:
        async with async_sessionmaker(init_database(), expire_on_commit=False)() as db:
            meeting = await db.get(Meeting, uuid.UUID(report["meeting_id"]))
            user = await db.get(User, meeting.host_id)
            assert user and user.is_active
            token = create_access_token({"sub": str(user.id), "role": user.role, "tenant_id": meeting.tenant_id})
            jobs = (await db.execute(select(InferenceJob).where(InferenceJob.status.in_(["queued", "running"])))).scalars().all()
            report["active_jobs"] = [{"id": str(job.id), "kind": job.kind, "status": job.status} for job in jobs]
        async with httpx.AsyncClient(base_url=args.base_url, timeout=30,
                                     headers={"Authorization": "Bearer " + token}) as client:
            for name in ("transcript", "analytics", "summary", "decisions", "topics", "facts", "hypotheses", "insights", "pipeline"):
                response = await client.get(f"/meetings/{meeting.id}/{name}")
                data = response.json()
                item = {"http_status": response.status_code, "response_type": type(data).__name__}
                if response.is_success:
                    if isinstance(data, list):
                        item["records"] = len(data)
                    else:
                        item["keys"] = sorted(data)
                        if "items" in data:
                            item["records"] = len(data["items"])
                        if name == "pipeline":
                            item["canonical_transcript_id"] = data.get("canonical_transcript_id")
                    if name == "transcript":
                        item["required_result_valid"] = isinstance(data, list) and bool(data)
                    elif name == "analytics":
                        item["required_result_valid"] = bool(data.get("speaking_time_distribution"))
                    elif name == "summary":
                        item["required_result_valid"] = bool(str(data.get("content") or "").strip())
                    elif name == "pipeline":
                        item["required_result_valid"] = bool(data.get("canonical_transcript_id")) and (data.get("provenance") or {}).get("execution_mode") == "REAL"
                    # Persist actual results for structural inspection; never print transcripts/tokens.
                    with (folder / f"{name}.json").open("x", encoding="utf-8") as handle:
                        json.dump(data, handle, indent=2)
                else:
                    item["error"] = sanitize_error_text(str(data))[:1000]
                report["endpoints"][name] = item
            report["status"] = "READBACK VERIFIED" if all(x["http_status"] == 200 and x.get("required_result_valid", True)
                for x in report["endpoints"].values()) else "NOT VERIFIED"
    except Exception as exc:
        report.update(status="BLOCKED", error_type=type(exc).__name__, error=sanitize_error_text(str(exc)))
    finally:
        await close_database_connections()
        with (folder / "result.json").open("x", encoding="utf-8") as handle:
            json.dump(report, handle, indent=2)
        print(json.dumps(report))
    if report["status"] != "READBACK VERIFIED":
        raise SystemExit(1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--meeting-id", type=uuid.UUID, default=uuid.UUID("bd07f8be-1416-469f-ac12-2fd37d6989fd"))
    parser.add_argument("--base-url", default="http://127.0.0.1:3000/api/v1")
    asyncio.run(main(parser.parse_args()))
