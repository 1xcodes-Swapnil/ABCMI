"""Observe real PyAnnote generation and cancellation at its next window boundary."""
import asyncio
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sys
import time
import uuid

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
os.environ.update(EXECUTION_MODE="REAL", HF_HUB_OFFLINE="1", DEBUG="false", LOG_LEVEL="CRITICAL")


async def main():
    import soundfile as sf
    from app.ai.speaker_diarization import SpeakerDiarizationEngine
    from app.core.config import get_settings
    from app.infrastructure.redis import close_redis_client

    settings = get_settings()
    audio = ROOT / "data/audio/raw/real_35s_pyannote_20261011.wav"
    info = sf.info(str(audio))
    assert settings.EXECUTION_MODE == "REAL" and settings.OPENMOSS_DEVICE.startswith("cuda")
    assert info.duration > settings.PYANNOTE_WINDOW_SECONDS
    run_id = "pyannote_cancel_" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    folder = ROOT / "e2e_validation/diagnostics" / run_id
    folder.mkdir(exist_ok=False)
    # Diagnostic-only identity; no meeting row is created or cancelled.
    diagnostic_id = uuid.uuid4()
    original = SpeakerDiarizationEngine._bounded_inference
    calls = []

    def observe(pipeline, path, profile, speakers, cancel_check=None):
        def real_pipeline(*args, **kwargs):
            started = time.perf_counter()
            output = pipeline(*args, **kwargs)
            annotation = getattr(output, "speaker_diarization", output)
            turns = [{"start": float(t.start), "end": float(t.end), "speaker": str(label)}
                     for t, _, label in annotation.itertracks(yield_label=True)]
            calls.append({"window_index": len(calls), "inference_seconds": time.perf_counter()-started,
                          "raw_output_type": type(output).__name__, "turns": turns,
                          "speaker_labels": annotation.labels()})
            with (folder / f"window_{len(calls)-1}.json").open("x", encoding="utf-8") as handle:
                json.dump(calls[-1], handle, indent=2)
            return output
        return original(real_pipeline, path, profile, speakers, cancel_check)

    SpeakerDiarizationEngine._bounded_inference = staticmethod(observe)
    started = time.perf_counter()
    result = {"run_id": run_id, "diagnostic_id": str(diagnostic_id), "meeting_id": "NOT AVAILABLE",
              "execution_mode": settings.EXECUTION_MODE, "device": settings.OPENMOSS_DEVICE,
              "audio": audio.name, "sha256": hashlib.sha256(audio.read_bytes()).hexdigest(),
              "duration": info.duration, "sample_rate": info.samplerate, "channels": info.channels,
              "scope": "real component inference; cancellation signal after first completed window",
              "timestamp": datetime.now(timezone.utc).isoformat()}
    try:
        await SpeakerDiarizationEngine().diarize_audio(
            b"", diagnostic_id, audio_file_path=str(audio), cancel_check=lambda: bool(calls))
        result.update(status="NOT VERIFIED", reason="Cancellation failed to stop next window")
    except RuntimeError as exc:
        cancelled = "cancelled at PyAnnote window boundary" in str(exc)
        passed = cancelled and len(calls) == 1 and bool(calls[0]["turns"])
        result.update(status="VERIFIED" if passed else "NOT VERIFIED", reason=str(exc),
                      completed_windows=len(calls), cancellation_observed=cancelled,
                      actual_turns=sum(len(c["turns"]) for c in calls),
                      next_window_inferred=False if passed else "NOT VERIFIED")
    finally:
        SpeakerDiarizationEngine._bounded_inference = staticmethod(original)
        await close_redis_client()
    result["elapsed_seconds"] = time.perf_counter()-started
    with (folder / "result.json").open("x", encoding="utf-8") as handle:
        json.dump(result, handle, indent=2)
    print(json.dumps(result))
    return 0 if result["status"] == "VERIFIED" else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
