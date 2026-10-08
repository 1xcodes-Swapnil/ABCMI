"""Run the authorized ten-sample language groups sequentially; stop on first failure."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
os.environ.update(EXECUTION_MODE="REAL", DEBUG="false", LOG_LEVEL="CRITICAL", HF_HUB_OFFLINE="1",
    AMI_AUDIO_ROOT=str(ROOT / "data/audio/raw"))

def save(path, record):
    with path.open("x", encoding="utf-8") as handle: json.dump(record, handle, indent=2)

def main(args):
    root = args.output.resolve()
    root.mkdir(parents=True, exist_ok=True)
    groups = [("fleurs", "en_us")]
    groups += [("fleurs", p.name) for p in sorted((ROOT / "data/benchmarks/fleurs").iterdir()) if p.is_dir() and p.name != "en_us"]
    groups += [("indicsuperb", p.name) for p in sorted((ROOT / "data/benchmarks/indicsuperb").iterdir()) if p.is_dir()]
    groups += [("voxconverse", "en"), ("ami", "en")]
    save(root / "suite_plan.json", {"timestamp": datetime.now(timezone.utc).isoformat(), "pid": os.getpid(),
        "samples_per_group": 10, "groups": groups, "mode": "REAL",
        "execution": "Sequential application upload/process/persist/fresh-readback; stop on first failure",
        "AMI": "10 full existing meetings with official XML references; user authorized full meetings",
        "selection": "ASR groups first sorted local files; VoxConverse and AMI shortest full recordings; not dataset-wide estimates"})
    for dataset, language in groups:
        group = root / (dataset + "_" + language)
        group.mkdir(exist_ok=True)
        execution = args.english_run.resolve() if dataset == "fleurs" and language == "en_us" else group
        command = [sys.executable, str(ROOT / "backend/scripts/benchmark_production.py"), "--dataset", dataset,
            "--language", language, "--samples", "10", "--run", str(execution)]
        if execution == args.english_run.resolve(): command += ["--retry-failed"]
        started = datetime.now(timezone.utc).isoformat()
        save(group / "started.json", {"timestamp": started, "dataset": dataset, "language": language,
            "evidence_folder": str(execution.relative_to(ROOT)), "status": "RUNNING"})
        print("RUNNING", dataset, language, flush=True)
        with (group / "launcher.log").open("x", encoding="utf-8") as log:
            process = subprocess.Popen(command, cwd=ROOT, stdout=log, stderr=log, text=True)
            save(group / "process.json", {"pid": process.pid, "timestamp": datetime.now(timezone.utc).isoformat()})
            code = process.wait()
        if execution != group:
            for path in execution.rglob("*.json"):
                target = group / path.relative_to(execution)
                target.parent.mkdir(parents=True, exist_ok=True)
                if not target.exists(): shutil.copy2(path, target)
        record = {"timestamp": datetime.now(timezone.utc).isoformat(), "dataset": dataset, "language": language,
            "exit_code": code, "status": "COMPLETED GROUP" if code == 0 else "BLOCKED",
            "evidence_folder": str(execution.relative_to(ROOT)), "results_folder": str(group.relative_to(ROOT))}
        save(group / "finished.json", record)
        for name in ("e2e_validation/execution_log.md", "DEVELOPMENT_LOG_BOOK.md", "docs/DEVELOPMENT_LOG_BOOK.md"):
            with (ROOT / name).open("a", encoding="utf-8") as log:
                log.write("\n- Local benchmark group " + json.dumps(record) + "\n")
        print(json.dumps(record), flush=True)
        if code: return 1
    save(root / "completed.json", {"timestamp": datetime.now(timezone.utc).isoformat(), "status": "ALL REQUESTED GROUPS EXECUTED",
        "groups": len(groups), "note": "Read each measured result; no cross-language accuracy aggregate"})
    return 0

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--english-run", type=Path, required=True)
    raise SystemExit(main(parser.parse_args()))
