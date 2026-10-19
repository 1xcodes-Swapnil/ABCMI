"""Check bounded text planning against saved REAL transcript evidence, no generation."""
import argparse
import asyncio
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
from app.ai.grounded_meeting_text import plan_text_batches, EXTRACTION_VERSION


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--limit", type=int, default=1000)
    parser.add_argument("--generate", action="store_true", help="Call the configured REAL Gemini provider on these saved turns")
    args = parser.parse_args()
    raw = args.source.read_bytes()
    saved = json.loads(raw)
    turns = [{"segment_id": s["segment_id"], "text": s["original_text"],
              "start_ms": s["start_time_ms"], "end_ms": s["end_time_ms"]}
             for s in saved["database_segments"] if s["original_text"].strip()]
    batches = plan_text_batches(turns, args.limit)
    assert [t for batch in batches for t in batch] == turns
    assert len(batches) > 1, "This focused check requires actual multiple windows"
    sizes = [len(json.dumps({"turns": batch}, ensure_ascii=False)) for batch in batches]
    assert all(size <= args.limit for size in sizes)
    # An actual existing turn too large for its budget must fail before any call.
    from fastapi import HTTPException
    try:
        plan_text_batches([turns[0]], len(json.dumps({"turns": [turns[0]]}, ensure_ascii=False))-1)
    except HTTPException as exc:
        assert exc.status_code == 422
    else:
        raise AssertionError("Oversized complete turn was not rejected")
    report = {"status": "VERIFIED", "scope": "REAL saved-source planning only",
              "timestamp": datetime.now(timezone.utc).isoformat(),
              "source_sha256": hashlib.sha256(raw).hexdigest(),
              "meeting_id": saved["meeting_id"], "canonical_transcript_id": saved["canonical_transcript_id"],
              "extraction_version": EXTRACTION_VERSION, "source_turn_count": len(turns),
              "batch_count": len(batches), "input_limit": args.limit, "json_characters": sizes,
              "source_segment_ids": [[t["segment_id"] for t in batch] for batch in batches],
              "complete_ordered_coverage": True, "oversized_turn_rejected": True,
              "generation_executed": False, "bounded_generation": "NOT VERIFIED"}
    if args.generate:
        os.environ["GEMINI_MAX_INPUT_CHARACTERS"] = str(args.limit)
        from app.ai.grounded_meeting_text import extract_meeting_items
        from app.core.config import get_settings
        get_settings.cache_clear()
        if get_settings().EXECUTION_MODE != "REAL":
            raise RuntimeError("REAL mode required")
        items, generation = asyncio.run(extract_meeting_items(turns))
        assert generation["batch_count"] == len(batches)
        assert len([i for i in items if i["object_type"] == "summary"]) >= len(batches)
        assert all(i["source_segments"] for i in items)
        assert all(i["generation_metadata"]["text_window"]["whole_meeting_summary"] is False for i in items)
        report.update(scope="REAL saved-source bounded generation", generation_executed=True,
                      bounded_generation="VERIFIED", items=items, generation=generation,
                      persistence="NOT EXECUTED; existing results unchanged")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as output:
        json.dump(report, output, indent=2)
    print(json.dumps({k: report[k] for k in ("status", "source_turn_count", "batch_count", "generation_executed")}))


if __name__ == "__main__":
    main()
