"""Prepare one small existing real upload for the changed long-audio batch path."""
import asyncio
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sys
import uuid

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
os.environ.update(EXECUTION_MODE="REAL", DEBUG="false", LOG_LEVEL="CRITICAL", HF_HUB_OFFLINE="1")


async def main(audio_path=None, max_audio_seconds=60):
    import httpx
    import mimetypes
    from types import SimpleNamespace
    from app.ai.multilingual_asr import validate_audio
    from sqlalchemy.ext.asyncio import async_sessionmaker
    from app.infrastructure.database import init_database, close_database_connections
    from app.models.meeting import Meeting
    from app.models.user import User
    from app.core.config import get_settings
    from app.core.security import create_access_token
    from app.ai.long_audio_processor import LongAudioProcessor

    audio = (audio_path or ROOT / "data/audio/raw/f01d7854-a29a-47b7-8c0f-741e2d1fad46_real_excerpt.wav").resolve()
    if not audio.is_relative_to((ROOT / "data/audio/raw").resolve()) or not audio.is_file():
        raise RuntimeError("Small REAL validation requires an existing authorized raw recording")
    metadata = validate_audio(str(audio))
    info = SimpleNamespace(duration=metadata["duration"], samplerate=metadata["sample_rate"], channels=metadata["channels"])
    if not 0 < info.duration <= max_audio_seconds <= 600:
        raise RuntimeError("Validation audio exceeds the explicitly selected gate (maximum 600 seconds)")
    settings = get_settings()
    assert settings.EXECUTION_MODE == "REAL"
    planner = LongAudioProcessor()
    chunks = planner.plan_chunks(info.duration)
    if len(chunks) < 2:
        raise RuntimeError("Small validation must exercise multiple actual MOSS chunks")
    async with async_sessionmaker(init_database())() as db:
        existing = await db.get(Meeting, uuid.UUID("88f69541-dff5-48a9-8901-5460be8a5d97"))
        user = await db.get(User, existing.host_id)
        if not user.is_active:
            raise RuntimeError("Existing host unavailable")
        token = create_access_token({"sub": str(user.id), "role": user.role, "tenant_id": existing.tenant_id})
    folder = ROOT / "e2e_validation/runs" / ("bounded_batch_" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"))
    folder.mkdir()
    record = {"run_id": folder.name, "timestamp": datetime.now(timezone.utc).isoformat(),
              "audio": audio.name, "sha256": hashlib.sha256(audio.read_bytes()).hexdigest(),
              "duration_seconds": info.duration, "sample_rate": info.samplerate, "channels": info.channels,
              "size_bytes": audio.stat().st_size, "execution_mode": settings.EXECUTION_MODE,
              "chunk_duration": planner.chunk_duration, "overlap": planner.overlap_duration,
              "step": planner.chunk_duration-planner.overlap_duration,
              "planned_chunks": [c.model_dump(mode="json", exclude={"chunk_id"}) for c in chunks],
              "inference_executed": False}
    # Planner-only IDs are excluded: production will create its own actual IDs.
    try:
        async with httpx.AsyncClient(base_url="http://127.0.0.1:3000/api/v1", timeout=45,
                headers={"Authorization": "Bearer " + token}) as client:
            response = await client.get("/health")
            response.raise_for_status()
            if response.json()["status"] != "healthy":
                raise RuntimeError("Required services are unhealthy")
            response = await client.post("/meetings", json={"title": f"REAL bounded batch validation — {info.duration:g} seconds", "language": "en"})
            response.raise_for_status()
            meeting = response.json()
            record["meeting_id"] = meeting["id"]
            with (folder / "created.json").open("x", encoding="utf-8") as handle:
                json.dump(record, handle, indent=2)
            with audio.open("rb") as source:
                response = await client.post(f"/meetings/{meeting['id']}/audio",
                    files={"file": (audio.name, source, mimetypes.guess_type(audio.name)[0] or "application/octet-stream")},
                    data={"format": audio.suffix.lower().lstrip(".")})
            record["upload"] = {"http_status": response.status_code, "body": response.json()}
            response.raise_for_status()
            stored = Path(response.json()["file_path"])
            record["upload_sha256_matches"] = hashlib.sha256(stored.read_bytes()).hexdigest() == record["sha256"]
            if not record["upload_sha256_matches"]:
                raise RuntimeError("Stored upload differs from actual input")
            record["status"] = "PREPARED; inference not yet executed"
    except Exception as exc:
        record.update(status="BLOCKED", error_type=type(exc).__name__)
    finally:
        with (folder / "input.json").open("x", encoding="utf-8") as handle:
            json.dump(record, handle, indent=2, default=str)
        await close_database_connections()
    print(json.dumps({k: record.get(k) for k in ("run_id", "meeting_id", "status", "upload_sha256_matches", "error_type")}))
    if record["status"] == "BLOCKED":
        raise SystemExit(1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--audio", type=Path)
    parser.add_argument("--max-audio-seconds", type=float, default=60,
                        help="Explicit progressive validation limit, at most 600 seconds; default remains 60")
    args = parser.parse_args()
    asyncio.run(main(args.audio, args.max_audio_seconds))
