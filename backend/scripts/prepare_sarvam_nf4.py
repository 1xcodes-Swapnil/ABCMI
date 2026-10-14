"""Serialize the existing REAL CUDA NF4 model locally; never download weights."""
import faulthandler
import hashlib
import json
import os
from pathlib import Path
import sys
import threading
import time
from datetime import datetime, timezone
from importlib.metadata import version

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
os.environ.update(EXECUTION_MODE="REAL", DEBUG="false", LOG_LEVEL="CRITICAL", HF_HUB_OFFLINE="1")


def digest(path):
    h = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024*1024), b""):
            h.update(block)
    return h.hexdigest()


def main():
    import psutil
    from app.core.config import get_settings
    from app.ai.model_inventory import configure_cache, snapshot_for
    settings = get_settings()
    if not settings.OPENMOSS_DEVICE.startswith("cuda"):
        raise RuntimeError("Explicit CUDA required")
    source = snapshot_for("sarvamai/sarvam-1", configure_cache())
    if source is None:
        raise RuntimeError("Existing local Sarvam snapshot required")
    target = ROOT / ".runtime/cache/sarvam-1-nf4"
    if target.exists():
        raise RuntimeError("Derived snapshot already exists; inspect it instead of overwriting")
    folder = ROOT / "e2e_validation/diagnostics/low_resource_20261012"
    folder.mkdir(parents=True, exist_ok=True)
    partial = target.with_name(target.name + ".incomplete")
    partial.mkdir(parents=True, exist_ok=False)
    stop, peak = threading.Event(), [0, 0]
    process = psutil.Process()
    def sample():
        while not stop.is_set():
            info = process.memory_info()
            peak[0] = max(peak[0], info.rss)
            peak[1] = max(peak[1], getattr(info, "private", 0))
            if psutil.virtual_memory().available < 256*2**20:
                (folder / "sarvam_provision_resource_stop.json").write_text(json.dumps({
                    "status": "BLOCKED", "reason": "Available RAM below 256MiB during isolated provisioning",
                    "sampled_peak_rss_bytes": peak[0], "sampled_peak_private_bytes": peak[1]}), encoding="utf-8")
                os._exit(3)
            stop.wait(.1)
    monitor = threading.Thread(target=sample, daemon=True)
    monitor.start()
    started = time.perf_counter()
    try:
        from app.ai.code_switch_intelligence import CodeSwitchIntelligenceEngine
        engine = CodeSwitchIntelligenceEngine()
        print("Loading existing cached CUDA Sarvam NF4", flush=True)
        engine._load_sarvam_model()
        if not getattr(engine.model, "is_loaded_in_4bit", False):
            raise RuntimeError("Actual model is not NF4; refusing derived snapshot")
        load_seconds = time.perf_counter()-started
        engine.model.save_pretrained(partial, safe_serialization=True, max_shard_size="256MB")
        engine.tokenizer.save_pretrained(partial)
        manifest = {"source_repository": "sarvamai/sarvam-1", "source_revision": source.name,
            "precision": "nf4", "created_at": datetime.now(timezone.utc).isoformat(),
            "packages": {p: version(p) for p in ("torch", "transformers", "bitsandbytes", "safetensors")},
            "weight_sha256": {p.name: digest(p) for p in partial.glob("*.safetensors")}}
        (partial / "abci_quantized_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        partial.rename(target)
        report = {"status": "CREATED; fresh reload NOT VERIFIED", "actual_model_loaded": True,
            "audio_inference_executed": False, "text_generation_executed": False,
            "source_revision": source.name, "load_seconds": load_seconds,
            "total_seconds": time.perf_counter()-started, "sampled_peak_rss_bytes": peak[0],
            "sampled_peak_private_bytes": peak[1], "sample_interval_seconds": .1,
            "derived_weight_bytes": sum(p.stat().st_size for p in target.glob("*.safetensors")),
            "artifact": str(target.relative_to(ROOT)), "original_cache_modified": False}
        with (folder / "sarvam_nf4_provision.json").open("x", encoding="utf-8") as output:
            json.dump(report, output, indent=2)
        print(json.dumps(report), flush=True)
    finally:
        stop.set()
        monitor.join()


if __name__ == "__main__":
    faulthandler.dump_traceback_later(120, exit=True)
    main()
    faulthandler.cancel_dump_traceback_later()
