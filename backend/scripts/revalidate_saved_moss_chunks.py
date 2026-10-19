"""Explicitly revalidate real ASR journals before appending a compatible checkpoint.

No inference is performed. Audio/model/config changes and timestamp-planner changes
are refused. Old checkpoints and transcript journals are never rewritten.
"""
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


def main():
    from app.ai.long_audio_processor import ChunkProcessingState, LongAudioProcessor, execution_identity
    from app.ai.multilingual_asr import ASRSegment, OpenMOSSProvider
    from app.core.config import get_settings
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--meeting", required=True, type=uuid.UUID)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--allow-precision-transition", action="store_true",
                        help="Explicitly retain validated NF4 journals when switching future CUDA chunks to BF16")
    args = parser.parse_args()
    settings = get_settings()
    history = Path(settings.AUDIO_CHUNK_STATE_DIR) / str(args.meeting)
    snapshots = sorted(history.glob("state_*.json"))
    state = ChunkProcessingState.model_validate_json(snapshots[-1].read_text(encoding="utf-8"))
    before = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in history.glob("*.json")}
    current, previous = execution_identity(settings), state.execution_identity
    assert previous, "Legacy producer identity cannot be verified"
    ignored = {"source_sha256"}
    transition = None
    if args.allow_precision_transition:
        assert previous["precision"] == "nf4" and current["precision"] == "bf16", "Unsupported precision transition"
        assert str(current["device"]).startswith("cuda"), "Precision transition requires CUDA"
        ignored.add("precision")
        transition = {"completed_chunk_precision": "nf4", "future_chunk_precision": "bf16",
                      "mixed_precision_run": True}
    assert {k: v for k, v in previous.items() if k not in ignored} == {
        k: v for k, v in current.items() if k not in ignored}, "Model/runtime/config differs"
    changed = {k for k, v in current["source_sha256"].items() if previous["source_sha256"].get(k) != v}
    assert changed <= {"multilingual_asr.py", "speaker_diarization.py"}, "Planner/decoder changes require separate validation"
    assert state.chunk_duration_seconds == settings.AUDIO_CHUNK_DURATION_SECONDS
    assert state.overlap_duration_seconds == settings.AUDIO_CHUNK_OVERLAP_SECONDS
    digest = hashlib.sha256()
    with Path(state.audio_file_path).open("rb") as source:
        for block in iter(lambda: source.read(1024*1024), b""):
            digest.update(block)
    assert digest.hexdigest() == state.audio_sha256, "Actual recording differs"
    provider = OpenMOSSProvider()
    def signature(segment):
        return (segment.start_time, segment.end_time, segment.transcript, segment.speaker_id,
                segment.detected_language, segment.confidence,
                [(w.word, w.start_time, w.end_time, w.confidence, w.language_code) for w in segment.words])
    verified = []
    for chunk in state.chunks:
        if chunk.status != "completed":
            continue
        raw = json.loads((history / f"inference_{chunk.chunk_id}.json").read_text(encoding="utf-8"))
        assert raw["execution_mode"] == "REAL" and raw["chunk_id"] == str(chunk.chunk_id)
        assert raw["start_time"] == chunk.start_time and raw["end_time"] == chunk.end_time
        provider.last_inference = dict(raw)
        actual = provider._normalize_moss_output(raw["raw_moss_output"], chunk.duration, chunk)
        saved = [ASRSegment.model_validate(row) for row in raw["segment_payloads"]]
        assert [signature(s) for s in actual] == [signature(s) for s in saved], "Parsed actual output changed"
        global_saved = [ASRSegment.model_validate(row) for row in json.loads(
            (history / f"segments_{chunk.chunk_id}.json").read_text(encoding="utf-8"))]
        mapped = LongAudioProcessor.offset_segments_to_global_time(saved, chunk.start_time)
        assert [signature(s) for s in mapped] == [signature(s) for s in global_saved], "Global output changed"
        verified.append(str(chunk.chunk_id))
    assert len(verified) == state.completed_chunks_count
    assert OpenMOSSProvider._cached_model is None
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    report = {"status": "VERIFIED", "timestamp": datetime.now(timezone.utc).isoformat(),
              "meeting_id": str(args.meeting), "previous_checkpoint": snapshots[-1].name,
              "previous_identity": previous, "validated_identity": current,
              "changed_sources": sorted(changed), "verified_chunk_ids": verified,
              "precision_transition": transition,
              "verified_completed_chunks": len(verified), "model_generation_executed": False,
              "prior_evidence_sha256": before, "applied": args.apply}
    assert all(hashlib.sha256((history / name).read_bytes()).hexdigest() == sha for name, sha in before.items())
    assert current == execution_identity(settings), "Producer changed during revalidation; rerun the cheap journal check"
    if args.apply:
        state.execution_identity = current
        state.checkpoint_version = max(state.checkpoint_version, int(snapshots[-1].stem.removeprefix("state_"))) + 1
        state.updated_at = datetime.now(timezone.utc)
        target = history / f"state_{state.checkpoint_version:08d}.json"
        temporary = target.with_suffix(".tmp")
        with temporary.open("x", encoding="utf-8") as handle:
            handle.write(state.model_dump_json(indent=2, exclude={"chunk_segments"}))
        temporary.replace(target)
        report["new_checkpoint"] = target.name
    with (history / f"compatibility_{stamp}.json").open("x", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2)
    print(json.dumps({k: report.get(k) for k in ("status", "verified_completed_chunks", "changed_sources", "applied", "new_checkpoint")}))


if __name__ == "__main__":
    main()
