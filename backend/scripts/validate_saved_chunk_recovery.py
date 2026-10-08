"""Replay actual saved chunk journals; fail if any new inference is attempted."""
import asyncio
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

async def main():
    from app.ai.long_audio_processor import LongAudioProcessor, ChunkProcessingState
    from app.core.config import get_settings
    meeting = uuid.UUID("40560ee3-9d8e-45c1-b2b4-eaa0f1f9bbdb")
    history = Path(get_settings().AUDIO_CHUNK_STATE_DIR) / str(meeting)
    before = {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in history.glob("*.json")}
    state = ChunkProcessingState.model_validate_json((history / "state_00000001.json").read_text(encoding="utf-8"))
    calls = 0
    async def never_infer(*args):
        nonlocal calls
        calls += 1
        raise RuntimeError("Saved actual journals must be restored without inference")
    result = await LongAudioProcessor().process_long_audio(state.audio_file_path, meeting, never_infer, initial_state=state)
    preserved = all(hashlib.sha256(p.read_bytes()).hexdigest() == digest for p, digest in before.items())
    assert calls == 0 and result.completed_chunks == 2 and len(result.asr_result.segments) == 4 and preserved
    assert all(0 <= s.start_time <= s.end_time <= 10 for s in result.asr_result.segments)
    output = {"timestamp": datetime.now(timezone.utc).isoformat(), "status": "VERIFIED",
        "check": "Recover actual journals from oldest pending manifest without repeating inference",
        "meeting_id": str(meeting), "provider_calls": calls, "completed_chunks": result.completed_chunks,
        "final_segments": len(result.asr_result.segments), "previous_evidence_preserved": preserved,
        "inference_executed": False, "three_hour_inference": "NOT VERIFIED"}
    target = ROOT / "e2e_validation/runs/bounded_batch_20261008T112512Z" / ("crash_recovery_" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + ".json")
    with target.open("x", encoding="utf-8") as handle:
        json.dump(output, handle, indent=2)
    print(json.dumps(output))

if __name__ == "__main__":
    asyncio.run(main())
