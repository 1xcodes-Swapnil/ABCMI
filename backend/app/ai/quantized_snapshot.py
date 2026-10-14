"""Verify derived local NF4 artifacts before using actual cached model weights."""
from functools import lru_cache
import hashlib
from importlib.metadata import version
import json
from pathlib import Path


@lru_cache(maxsize=2)
def verified_sarvam_snapshot(path):
    root = Path(path).resolve()
    manifest = json.loads((root / "abci_quantized_manifest.json").read_text(encoding="utf-8"))
    if manifest.get("source_repository") != "sarvamai/sarvam-1" or manifest.get("precision") != "nf4":
        raise RuntimeError("Derived Sarvam snapshot has invalid provenance/precision")
    for package, expected in manifest["packages"].items():
        if version(package) != expected:
            raise RuntimeError("Derived Sarvam snapshot runtime versions differ; explicit revalidation required")
    weights = manifest.get("weight_sha256", {})
    if not weights:
        raise RuntimeError("Derived Sarvam snapshot contains no verified weights")
    for name, expected in weights.items():
        file = root / name
        if file.parent != root or file.suffix != ".safetensors":
            raise RuntimeError("Invalid derived weight filename")
        h = hashlib.sha256()
        with file.open("rb") as source:
            for block in iter(lambda: source.read(1024*1024), b""):
                h.update(block)
        if h.hexdigest() != expected:
            raise RuntimeError("Derived Sarvam weight hash differs; refusing model fallback")
    config = json.loads((root / "config.json").read_text(encoding="utf-8"))
    if config.get("quantization_config", {}).get("bnb_4bit_quant_type") != "nf4":
        raise RuntimeError("Derived Sarvam config is not NF4")
    return str(root)
