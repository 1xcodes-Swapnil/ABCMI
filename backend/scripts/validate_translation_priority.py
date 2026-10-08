"""One real Hindi translation of the existing short transcript; no audio processing."""
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
os.environ.update(EXECUTION_MODE="REAL", DEBUG="false", LOG_LEVEL="CRITICAL")


async def main():
    from httpx import AsyncClient, ASGITransport
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import async_sessionmaker
    from app.infrastructure.database import init_database, close_database_connections
    from app.models.meeting import Meeting
    from app.models.user import User
    from app.models.translation import DerivedTranslation
    from app.core.security import create_access_token
    from app.main import app
    meeting_id = uuid.UUID("2126caea-4e13-4902-a02f-12a8260db0bd")
    folder = ROOT / "e2e_validation/runs" / ("translation_priority_" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"))
    folder.mkdir(parents=True, exist_ok=False)
    result = {"run_id": folder.name, "meeting_id": str(meeting_id), "audio_inference_executed": False,
              "timestamp": datetime.now(timezone.utc).isoformat(), "status": "NOT VERIFIED"}
    sessions = async_sessionmaker(init_database(), expire_on_commit=False)
    try:
        async with sessions() as db:
            meeting = await db.get(Meeting, meeting_id)
            user = await db.get(User, meeting.host_id)
            token = create_access_token({"sub": str(user.id), "role": user.role, "tenant_id": meeting.tenant_id})
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://abci.local",
                               headers={"Authorization": f"Bearer {token}"}) as client:
            started = time.perf_counter()
            response = await client.post(f"/api/v1/meetings/{meeting_id}/translations",
                json={"target_language": "hi", "representation_types": ["transcript"]})
            result.update(http_status=response.status_code, body=response.json(), elapsed_seconds=time.perf_counter()-started)
            if response.status_code not in (200, 201):
                raise RuntimeError("Translation API failed")
            async with sessions() as db:
                rows = (await db.execute(select(DerivedTranslation).where(DerivedTranslation.meeting_id == meeting_id,
                    DerivedTranslation.target_language == "hi", DerivedTranslation.representation_type == "transcript"))).scalars().all()
                result["fresh_readback"] = [{"id": str(r.id), "source_segment_id": str(r.source_segment_id),
                    "text": r.translated_text, "confidence": r.confidence, "provenance": r.provenance,
                    "correlation_id": r.correlation_id} for r in rows]
                if len(rows) == 3 and all(r.translated_text.strip() and r.confidence is None and
                        (r.provenance or {}).get("lineage", {}).get("is_fixture") is False for r in rows):
                    result["status"] = "VERIFIED"
    except Exception as exc:
        result.update(status="BLOCKED", error_type=type(exc).__name__)
    finally:
        with (folder / "result.json").open("x", encoding="utf-8") as file:
            json.dump(result, file, indent=2, default=str)
        await close_database_connections()
    print(json.dumps({k:result.get(k) for k in ("run_id", "status", "http_status", "elapsed_seconds", "error_type")}, indent=2))
    if result["status"] != "VERIFIED":
        raise SystemExit(1)


if __name__ == "__main__":
    asyncio.run(main())
