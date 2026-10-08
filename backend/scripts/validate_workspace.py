"""Cheap UI contract checks against real persisted records; no AI inference."""
import asyncio
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
import uuid

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
os.environ.update(EXECUTION_MODE="REAL", DEBUG="false", LOG_LEVEL="CRITICAL", HF_HUB_OFFLINE="1")

async def main():
    from httpx import AsyncClient, ASGITransport
    from sqlalchemy.ext.asyncio import async_sessionmaker
    from app.infrastructure.database import init_database, close_database_connections
    from app.models.meeting import Meeting
    from app.models.user import User
    from app.core.security import create_access_token
    from app.main import app
    meeting_id = uuid.UUID("fd2c1cca-5cd1-403e-90bd-c63c1f5b1874")
    folder = ROOT / "e2e_validation/runs" / ("workspace_" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"))
    folder.mkdir(parents=True, exist_ok=False)
    results = []
    phase = sys.argv[1] if len(sys.argv) > 1 else "reads"
    sessions = async_sessionmaker(init_database(), expire_on_commit=False)
    async with sessions() as db:
        meeting = await db.get(Meeting, meeting_id)
        user = await db.get(User, meeting.host_id)
        token = create_access_token(data={"sub": str(user.id), "role": user.role, "tenant_id": meeting.tenant_id, "email": user.email})
    prefix = f"/meetings/{meeting_id}"
    async with AsyncClient(transport=None if phase == "network" else ASGITransport(app=app, raise_app_exceptions=False),
                           base_url="http://127.0.0.1:3000" if phase == "network" else "http://127.0.0.1:8000",
                           headers={"Authorization": "Bearer " + token}, timeout=45) as client:
        async def check(method, path, payload=None):
            reply = await client.request(method, "/api/v1" + path, **({"json": payload} if payload is not None else {}))
            try: data = reply.json()
            except ValueError: data = {"body": reply.text[:1000]}
            entry = {"method": method, "path": path, "status_code": reply.status_code,
                     "response_type": type(data).__name__}
            if reply.status_code >= 400: entry["error"] = data
            if isinstance(data, list): entry["records"] = len(data)
            if path.endswith('/transcript'): entry["nonempty_transcript"] = bool(data) and all(r.get("original_text") for r in data)
            (folder / f"response_{len(results):02}.json").write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
            results.append(entry)
            print(json.dumps(entry, default=str))
            return data
        if phase == "projects":
            created = await check("POST", "/projects", {"name": "Project workflow priority check", "description": "Temporary validation project; no AI inference."})
            if not created.get("id"):
                raise RuntimeError("Project creation failed; inspect saved response")
            project_path = "/projects/" + str(uuid.UUID(created["id"]))
            try:
                await check("PATCH", project_path, {"description": "Updated through the real API"})
                await check("POST", project_path+"/meetings", {"meeting_id": str(meeting_id)})
                for suffix in ["", "/meetings", "/summary", "/action-items", "/decisions", "/topics/recurring", "/insights", "/historical-context"]:
                    await check("GET", project_path+suffix)
                await check("DELETE", project_path+"/meetings/"+str(meeting_id))
            finally:
                # This exact project was created above solely for this check.
                await check("DELETE", project_path)
        if phase == "reads":
            for path in ["/auth/me", "/meetings?limit=200", prefix, prefix+"/transcript", prefix+"/pipeline",
                         prefix+"/live/status", prefix+"/summary", prefix+"/decisions", prefix+"/action-items",
                         prefix+"/topics", prefix+"/facts", prefix+"/hypotheses", prefix+"/insights", prefix+"/analytics",
                         "/knowledge/meeting/"+str(meeting_id), prefix+"/queries", prefix+"/translations", prefix+"/reports",
                         "/notifications", "/admin/audit", "/admin/users", "/admin/roles", "/benchmarks/runs",
                         "/benchmarks/datasets", "/health/system-metrics", "/openapi.json"]:
                await check("GET", path)
        if phase == "actions":
            await check("POST", prefix+"/translations", {"target_language":"hi", "representation_types":["transcript"]})
            await check("POST", "/queries", {"query":"What was said in the first meeting?", "meeting_id":str(meeting_id), "scope":"meeting", "retrieval_mode":"structured"})
            report = await check("POST", prefix+"/reports", {"format":"markdown", "report_type":"comprehensive"})
            if report.get("id"):
                for fmt in ("json", "markdown", "txt", "pdf"):
                    exported = await check("POST", f"/reports/{report['id']}/export", {"format":fmt})
                    if exported.get("download_url"):
                        reply = await client.get(exported["download_url"])
                        results.append({"download":fmt, "status_code":reply.status_code, "bytes":len(reply.content)})
            await check("POST", "/knowledge/search", {"query":"first meeting", "meeting_id":str(meeting_id)})
            await check("GET", prefix+"/pipeline")
        if phase == "search":
            await check("POST", "/knowledge/search", {"query":"first meeting", "meeting_id":str(meeting_id)})
        if phase == "readback":
            await check("GET", "/queries/3f6886df-8bdf-4b37-94de-d4b8a34647a1")
            await check("GET", "/reports/51422a30-7e64-4220-8e11-cc2f3e707b23")
        if phase == "network":
            for path in ["/auth/me", "/meetings", prefix+"/transcript", prefix+"/pipeline", "/openapi.json"]:
                await check("GET", path)
            from app.models.inference_job import InferenceJob
            from sqlalchemy import select, func
            async with sessions() as db:
                counts = dict((await db.execute(select(InferenceJob.status, func.count()).group_by(InferenceJob.status))).all())
                print(json.dumps({"durable_job_counts":counts}))
                results.append({"durable_job_counts":counts})
        if phase == "intake":
            created = await check("POST", "/meetings", {"title":"Workspace intake verification (no inference)", "language":"en"})
            if not created.get("id"):
                raise RuntimeError("Meeting intake failed")
            path = "/meetings/"+created["id"]
            await check("PUT", path, {"description":"Real upload, queue, cancellation and readback validation; no audio inference."})
            audio_path = ROOT / "data/audio/raw/f01d7854-a29a-47b7-8c0f-741e2d1fad46_real_excerpt.wav"
            content = audio_path.read_bytes()
            reply = await client.post("/api/v1"+path+"/audio", files={"file":(audio_path.name, content, "audio/wav")})
            audio = reply.json()
            results.append({"upload_status":reply.status_code, "meeting_id":created["id"], "audio":audio})
            if reply.status_code != 201:
                raise RuntimeError("Real upload failed")
            playback = await client.get("/api/v1"+path+f"/audio/{audio['id']}/content")
            import hashlib
            results.append({"playback_status":playback.status_code, "sha256_match":hashlib.sha256(playback.content).digest()==hashlib.sha256(content).digest()})
            first = await check("POST", path+"/process-async", {})
            repeated = await check("POST", path+"/process-async", {})
            results.append({"queue_idempotent":first.get("job_id") == repeated.get("job_id")})
            await check("GET", path+"/pipeline")
            await check("POST", path+"/processing/cancel", {})
            await check("DELETE", path)
        if phase == "security":
            await check("POST", "/auth/login", {"email": "admin@example.invalid", "password": "invalid"})
            await check("POST", prefix+"/process-async", {})
            wrong = create_access_token(data={"sub":str(user.id), "role":user.role, "tenant_id":"invalid-tenant"})
            client.headers['Authorization'] = 'Bearer '+wrong
            for path in ["/meetings", prefix+"/pipeline", "/knowledge/meeting/"+str(meeting_id), prefix+"/reports", prefix+"/translations", prefix+"/insights"]:
                await check("GET", path)
    (folder / "checks.json").write_text(json.dumps({"meeting_id":str(meeting_id), "results":results,
        "audio_inference_executed":False, "embedding_search_attempted":phase in {"actions", "search"},
        "timestamp":datetime.now(timezone.utc).isoformat()}, indent=2), encoding="utf-8")
    await close_database_connections()
    print("Evidence:", folder.name)
    if phase == "projects" and any(r.get("status_code", 200) >= 400 for r in results):
        raise SystemExit(1)

if __name__ == "__main__":
    asyncio.run(main())
