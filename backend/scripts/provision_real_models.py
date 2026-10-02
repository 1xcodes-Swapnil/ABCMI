"""Provision official REAL artifacts, reusing complete existing files first.

Run: python backend/scripts/provision_real_models.py --models Sarvam MOSS
No audio is uploaded. Token values and authenticated URLs are never logged.
"""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import sys

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))
from app.ai.model_inventory import MODELS, configure_cache, inspect_snapshot, snapshot_for
from app.core.config import get_settings


def provision(models, *, dry_run=False):
    cache = configure_cache()
    from huggingface_hub import HfApi, hf_hub_download
    token = os.environ.get("HF_TOKEN") or get_settings().HF_TOKEN
    if not token:
        raise RuntimeError("HF_TOKEN is missing; required gated models cannot be provisioned")
    api = HfApi(token=token)
    api.whoami()  # Prove authentication without printing identity or credentials.
    report = {"authentication": "usable", "cache": str(cache), "dry_run": dry_run,
              "started_at": datetime.now(timezone.utc).isoformat(), "models": []}
    source_caches = [cache, BACKEND, Path.home()/".cache/huggingface/hub"]
    for spec in models:
        local = snapshot_for(spec.repository, cache)
        revision = local.name if local else "main"
        info = api.model_info(spec.repository, revision=revision, files_metadata=True)
        revision = info.sha
        model_root = cache / ("models--" + spec.repository.replace("/", "--"))
        destination = model_root / "snapshots" / revision
        artifacts = [s for s in info.siblings if s.rfilename.endswith(
            (".json", ".model", ".txt", ".py", ".jinja", ".yaml", ".safetensors", ".bin"))
            and not s.rfilename.startswith((".", "images/")) and s.rfilename != "README.md"]
        if spec.weight_files:
            artifacts = [s for s in artifacts if not s.rfilename.endswith((".bin", ".safetensors"))
                         or s.rfilename in spec.weight_files]
        entry = {"model": spec.name, "repository": spec.repository, "revision": revision,
                 "files": [], "download_bytes": 0, "reuse_bytes": 0}
        report["models"].append(entry)
        for artifact in artifacts:
            name, expected = artifact.rfilename, artifact.size
            if expected is None or expected <= 0:
                raise RuntimeError(f"Missing size metadata for {spec.repository}/{name}")
            existing = None
            for root in source_caches:
                candidate = root / ("models--" + spec.repository.replace("/", "--")) / "snapshots" / revision / name
                if candidate.is_file() and candidate.stat().st_size == expected:
                    existing = candidate
                    break
            row = {"file": name, "bytes": expected, "action": "reuse" if existing else "download"}
            entry["files"].append(row)
            entry["reuse_bytes" if existing else "download_bytes"] += expected
            if dry_run:
                continue
            target = destination / name
            if existing:
                if existing.resolve() != target.resolve():
                    target.parent.mkdir(parents=True, exist_ok=True)
                    if target.exists():
                        raise RuntimeError(f"Existing incomplete artifact requires inspection: {spec.repository}/{name}")
                    try:
                        os.link(existing.resolve(), target)
                        row["action"] = "hardlink_existing"
                    except OSError:
                        shutil.copy2(existing, target)
                        row["action"] = "copy_existing"
            else:
                print(json.dumps({"model": spec.name, "file": name, "download_bytes": expected}), flush=True)
                target = Path(hf_hub_download(spec.repository, name, revision=revision, cache_dir=cache, token=token))
            if not target.is_file() or target.stat().st_size != expected:
                raise RuntimeError(f"Artifact size verification failed: {spec.repository}/{name}")
        if not dry_run:
            refs = model_root / "refs"
            refs.mkdir(parents=True, exist_ok=True)
            (refs / "main").write_text(revision)
            entry["inventory"] = inspect_snapshot(spec, destination)
            if entry["inventory"]["status"] != "COMPLETE":
                raise RuntimeError(f"Provisioning left {spec.name} incomplete")
        print(json.dumps({"model": spec.name, "download_bytes": entry["download_bytes"],
                          "reuse_bytes": entry["reuse_bytes"], "status": "planned" if dry_run else "COMPLETE"}), flush=True)
    report["status"] = "passed"
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--models", nargs="+", choices=[s.name for s in MODELS], default=[s.name for s in MODELS if s.required])
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--report", type=Path, default=BACKEND.parent / "e2e_validation/local_real_20260930/provisioning.json")
    args = parser.parse_args()
    try:
        report = provision([s for s in MODELS if s.name in args.models], dry_run=args.dry_run)
        code = 0
    except Exception as exc:
        report = {"status": "BLOCKED", "error_type": type(exc).__name__}
        response = getattr(exc, "response", None)
        if response is not None:
            report["http_status"] = response.status_code
        code = 1
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k != "models"}, indent=2))
    raise SystemExit(code)


if __name__ == "__main__":
    main()
