"""Cheap routing checks using recorded REAL outputs; not end-to-end evidence."""
import argparse
import asyncio
import json
from pathlib import Path
import sys
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.core.config import get_settings
from app.orchestration.module_runner import AIModuleRunner
from app.cli import sanitize_error_text


async def run(args):
    if get_settings().EXECUTION_MODE.upper() != "REAL":
        raise RuntimeError("REAL mode required")
    root = args.evidence
    segments = json.loads((root / "moss_segments.json").read_text())
    diarization = json.loads((root / "pyannote_result.json").read_text())
    audio = json.loads((root / "moss.json").read_text())
    assert audio["status"] == "passed" and segments
    upstream = {
        "audio_intelligence": {"duration_seconds": audio["audio_duration"]},
        "multilingual_asr": {"segments": segments, "transcript": " ".join(s["transcript"] for s in segments)},
        "speaker_representation": {"speaker_turns": diarization["speaker_turns"]},
    }
    runner = AIModuleRunner()
    trace = {"scope": "engineering_replay_of_actual_provider_outputs", "end_to_end": "NOT_VERIFIED", "gates": []}
    for capability in ["timestamp_intelligence", "transcript_intelligence", "confidence_fusion", "context_intelligence",
                       "verification_engine", "meeting_understanding", "meeting_analytics", "knowledge_memory"]:
        try:
            result = await runner.execute_task(capability, uuid.uuid4(), uuid.uuid4(), uuid.uuid4(),
                                               {"upstream_results": upstream})
            upstream[capability] = result["result_data"]
            trace["gates"].append({"capability": capability, "status": "passed", "result_keys": list(result["result_data"])})
        except Exception as exc:
            trace["gates"].append({"capability": capability, "status": "BLOCKED", "error": sanitize_error_text(str(exc))})
            break
    (root / "downstream_routing.json").write_text(json.dumps(trace, indent=2))
    print(json.dumps(trace, indent=2))
    return 0 if len(trace["gates"]) == 8 and trace["gates"][-1]["status"] == "passed" else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence", type=Path, required=True)
    sys.exit(asyncio.run(run(parser.parse_args())))
