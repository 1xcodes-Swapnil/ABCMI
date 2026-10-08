"""Instrument the existing CLI, without substituting providers or pipeline results."""
import argparse
import contextlib
import io
import json
import logging
import os
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ["HF_HUB_OFFLINE"] = "1"
from app import cli
from app.core.config import get_settings


def safe(text):
    for name, value in get_settings().model_dump().items():
        if isinstance(value, str) and value and any(key in name for key in ("TOKEN", "SECRET", "PASSWORD", "URL", "API_KEY")):
            text = text.replace(value, "[REDACTED]")
    return cli.sanitize_error_text(text)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence", type=Path, required=True)
    args = parser.parse_args()
    root = args.evidence.resolve()
    for gate in ("moss", "pyannote", "sarvam", "reconcile"):
        if json.loads((root / (gate + ".json")).read_text())["status"] != "passed":
            raise RuntimeError(f"REAL meeting requires passed {gate}")
    if get_settings().EXECUTION_MODE.upper() != "REAL":
        raise RuntimeError("REAL mode required")
    excerpt = root / "real_excerpt.wav"
    trace = {"stage": "existing production CLI", "status": "started", "execution_mode": "REAL"}
    orchestrators = []
    factory = cli.get_cli_ace_orchestrator
    def observed_factory(db):
        orchestrator = factory(db)
        orchestrators.append(orchestrator)
        return orchestrator
    cli.get_cli_ace_orchestrator = observed_factory
    pipeline = cli.execute_cli_pipeline
    async def observed_pipeline(*a, **kw):
        result = await pipeline(*a, **kw)
        (root / "production_cli_result.json").write_text(json.dumps(result, indent=2, default=str))
        trace.update(meeting_id=result["meeting_id"], transcript_count=result["transcript_count"], cli_status=result["status"])
        return result
    cli.execute_cli_pipeline = observed_pipeline
    log = io.StringIO()
    streams = []
    for logger in [logging.getLogger(), *[l for l in logging.Logger.manager.loggerDict.values() if isinstance(l, logging.Logger)]]:
        for handler in logger.handlers:
            if isinstance(handler, logging.StreamHandler) and not isinstance(handler, logging.FileHandler):
                streams.append((handler, handler.stream))
                handler.setStream(log)
    sys.argv = ["abcimi", "--file", str(excerpt), "--title", "REAL local short meeting validation"]
    started = time.perf_counter()
    try:
        with contextlib.redirect_stdout(log), contextlib.redirect_stderr(log):
            try:
                cli.main()
                trace["cli_exit_code"] = 0
            except SystemExit as exc:
                trace["cli_exit_code"] = exc.code
                if exc.code:
                    raise RuntimeError(f"Existing CLI returned exit {exc.code}")
        if trace.get("transcript_count", 0) == 0:
            raise RuntimeError("Existing CLI returned no persisted transcript")
        trace["status"] = "passed"
    except Exception as exc:
        trace.update(status="BLOCKED", error=safe(str(exc)))
    finally:
        trace["processing_seconds"] = time.perf_counter()-started
        for handler, stream in streams:
            handler.setStream(stream)
        (root / "production_cli.log").write_text(safe(log.getvalue()), encoding="utf-8")
        boards = [board for orchestrator in orchestrators for board in orchestrator.blackboards.values()]
        tasks = []
        for board in boards:
            trace["meeting_id"] = str(board.meeting_id)
            trace["persistence"] = board.execution_state.get("transcript_persistence")
            for task in board.list_tasks():
                tasks.append({"capability": task.required_capability,
                              "status": getattr(task.status, "value", task.status), "metadata": task.metadata})
        (root / "production_blackboard.json").write_text(json.dumps(tasks, indent=2, default=str))
        trace["tasks"] = [{"capability": t["capability"], "status": t["status"]} for t in tasks]
        failed = next((t for t in tasks if t["status"] == "FAILED"), None)
        if failed:
            trace["first_failed_capability"] = failed["capability"]
            trace["first_failure"] = safe(str(failed["metadata"].get("error_message")))
        (root / "production_meeting.json").write_text(json.dumps(trace, indent=2))
    print(json.dumps(trace, indent=2))
    return 0 if trace["status"] == "passed" else 1


if __name__ == "__main__":
    sys.exit(main())
