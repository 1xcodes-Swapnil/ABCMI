"""Replay actual saved chunk journals; fail if any new inference is attempted."""
import asyncio
import argparse
import faulthandler
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
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--meeting", required=True, type=uuid.UUID)
    parser.add_argument("--run", required=True, type=Path)
    parser.add_argument("--chunks", required=True, type=int)
    parser.add_argument("--segments", required=True, type=int)
    args = parser.parse_args()
    meeting = args.meeting
    history = Path(get_settings().AUDIO_CHUNK_STATE_DIR) / str(meeting)
    before = {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in history.glob("*.json")}
    state = ChunkProcessingState.model_validate_json(sorted(history.glob("state_*.json"))[0].read_text(encoding="utf-8"))
    calls = 0
    async def never_infer(*args):
        nonlocal calls
        calls += 1
        raise RuntimeError("Saved actual journals must be restored without inference")
    from app.infrastructure.redis import close_redis_client
    try:
        result = await asyncio.wait_for(LongAudioProcessor().process_long_audio(
            state.audio_file_path, meeting, never_infer, initial_state=state), timeout=60)
    finally:
        await close_redis_client()
    preserved = all(hashlib.sha256(p.read_bytes()).hexdigest() == digest for p, digest in before.items())
    assert calls == 0 and result.completed_chunks == args.chunks and len(result.asr_result.segments) == args.segments and preserved
    assert all(0 <= s.start_time <= s.end_time <= state.total_duration_seconds for s in result.asr_result.segments)
    output = {"timestamp": datetime.now(timezone.utc).isoformat(), "status": "VERIFIED",
        "check": "Recover actual journals from oldest pending manifest without repeating inference",
        "meeting_id": str(meeting), "provider_calls": calls, "completed_chunks": result.completed_chunks,
        "final_segments": len(result.asr_result.segments), "previous_evidence_preserved": preserved,
        "inference_executed": False, "three_hour_inference": "NOT VERIFIED"}
    target = args.run / ("crash_recovery_" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ") + ".json")
    with target.open("x", encoding="utf-8") as handle:
        json.dump(output, handle, indent=2)
    print(json.dumps(output))

if __name__ == "__main__":
    faulthandler.dump_traceback_later(45, exit=True)
    asyncio.run(main())
    faulthandler.cancel_dump_traceback_later()
