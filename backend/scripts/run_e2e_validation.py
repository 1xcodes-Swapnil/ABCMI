"""Run a single, auditable ABCI-MI REAL-mode end-to-end validation.

This harness keeps runtime overrides out of .env and writes logs only to the
user-selected output directory. It does not fine-tune models automatically:
fine-tuning should follow a measured baseline and dataset-specific evaluation.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any


UUID_RE = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}", re.I)


def run_command(command: list[str], env: dict[str, str], log_path: Path) -> tuple[int, str]:
    started = time.time()
    result = subprocess.run(command, text=True, capture_output=True, env=env)
    output = result.stdout
    if result.stderr:
        output += "\n--- stderr ---\n" + result.stderr
    log_path.write_text(output, encoding="utf-8", errors="replace")
    print(output)
    print(f"Command duration: {time.time() - started:.1f}s")
    return result.returncode, output


def extract_summary(output: str) -> dict[str, Any]:
    summary: dict[str, Any] = {}
    patterns = {
        "meeting_id": r"Meeting ID:\s+([0-9a-f-]{36})",
        "report_id": r"Report generated ID:\s+([0-9a-f-]{36})",
        "status": r"Status:\s+(\w+)",
        "transcript_segments": r"Transcript Segments:\s+(\d+)",
        "speakers": r"Speakers Identified:\s+(\d+)",
    }
    for key, pattern in patterns.items():
        match = re.search(pattern, output, re.I)
        if match:
            value = match.group(1)
            summary[key] = int(value) if value.isdigit() else value
    summary["uuid_count"] = len(UUID_RE.findall(output))
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate ABCI-MI once in strict REAL mode.")
    parser.add_argument("audio", type=Path, help="Input WAV/MP3/FLAC audio file")
    parser.add_argument("--output-dir", type=Path, default=Path("./e2e_validation"))
    parser.add_argument("--chunk-seconds", type=int, default=300)
    parser.add_argument("--overlap-seconds", type=int, default=15)
    args = parser.parse_args()

    if not args.audio.is_file():
        raise FileNotFoundError(args.audio)

    backend_root = Path(__file__).resolve().parents[1]
    args.output_dir.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env.update(
        {
            "EXECUTION_MODE": "REAL",
            "OPENMOSS_DEVICE": "cuda",
            "AUDIO_CHUNK_DURATION_SECONDS": str(args.chunk_seconds),
            "AUDIO_CHUNK_OVERLAP_SECONDS": str(args.overlap_seconds),
            "AUDIO_CHUNK_THRESHOLD_SECONDS": str(args.chunk_seconds),
            "AUDIO_CHUNK_CONCURRENCY": "1",
            "PYTORCH_CUDA_ALLOC_CONF": "expandable_segments:True",
        }
    )

    check_log = args.output_dir / "real_mode_check.log"
    process_log = args.output_dir / "pipeline.log"
    result_json = args.output_dir / "result.json"

    check_code, _ = run_command(
        [sys.executable, "cli.py", "meeting", "check-real-mode"],
        env,
        check_log,
    )
    if check_code != 0:
        result_json.write_text(
            json.dumps({"status": "blocked", "stage": "real_mode_check"}, indent=2),
            encoding="utf-8",
        )
        return check_code

    process_code, process_output = run_command(
        [sys.executable, "cli.py", "meeting", "process-real", str(args.audio)],
        env,
        process_log,
    )
    summary = extract_summary(process_output)
    summary.update(
        {
            "status": "passed" if process_code == 0 and summary.get("status") == "completed" else "failed",
            "exit_code": process_code,
            "audio": str(args.audio.resolve()),
            "logs": {"readiness": str(check_log), "pipeline": str(process_log)},
        }
    )
    result_json.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"Validation result: {result_json.resolve()}")
    return process_code


if __name__ == "__main__":
    raise SystemExit(main())
