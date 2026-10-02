"""Local-only inventory of the official models used by the existing REAL adapters."""
from dataclasses import dataclass
import json
import os
from pathlib import Path


@dataclass(frozen=True)
class ModelSpec:
    name: str
    repository: str
    purpose: str
    required_by: str
    required_files: tuple[str, ...]
    requires_weights: bool = True
    required: bool = True
    weight_files: tuple[str, ...] = ()


MODELS = (
    ModelSpec("MOSS", "OpenMOSS-Team/MOSS-Transcribe-Diarize", "ASR and speaker turns", "OpenMOSSProvider",
              ("config.json", "tokenizer_config.json", "tokenizer.json", "processor_config.json",
               "preprocessor_config.json", "chat_template.jinja", "configuration_moss_transcribe_diarize.py",
               "modeling_moss_transcribe_diarize.py", "processing_moss_transcribe_diarize.py")),
    ModelSpec("Sarvam", "sarvamai/sarvam-1", "Text normalization (not audio ASR)", "CodeSwitchIntelligenceEngine",
              ("config.json", "tokenizer_config.json", "tokenizer.json", "tokenizer.model")),
    ModelSpec("PyAnnote diarization", "pyannote/speaker-diarization-3.1", "Diarization pipeline", "SpeakerDiarizationEngine",
              ("config.yaml",), False),
    ModelSpec("PyAnnote segmentation", "pyannote/segmentation-3.0", "Speech segmentation", "speaker-diarization-3.1",
              ("pytorch_model.bin",)),
    ModelSpec("Speaker embedding model", "pyannote/wespeaker-voxceleb-resnet34-LM", "256 dimensional speaker embeddings",
              "speaker-diarization-3.1", ("pytorch_model.bin",)),
    ModelSpec("Whisper/WhisperX", "openai/whisper-large-v3", "Optional separate ASR model", "Not used by current MOSS REAL route",
              ("config.json", "preprocessor_config.json", "tokenizer.json"), required=False),
    ModelSpec("Semantic embedding", "sentence-transformers/all-MiniLM-L6-v2", "Learned 384-dimensional text embeddings",
              "SemanticIndexer", ("config.json", "tokenizer_config.json", "tokenizer.json", "model.safetensors"),
              weight_files=("model.safetensors",)),
)


def cache_directory() -> Path:
    from app.core.config import get_settings
    settings = get_settings()
    explicit = (os.environ.get("HF_HUB_CACHE") or os.environ.get("HUGGINGFACE_HUB_CACHE")
                or settings.HUGGINGFACE_HUB_CACHE)
    if explicit:
        return Path(explicit).expanduser().resolve()
    home = os.environ.get("HF_HOME") or settings.HF_HOME
    if home:
        return Path(home).expanduser().resolve() / "hub"
    return Path.home() / ".cache" / "huggingface" / "hub"


def configure_cache() -> Path:
    """Set before importing Hugging Face so every provider uses the same cache."""
    cache = cache_directory()
    os.environ.setdefault("HF_HOME", str(cache.parent))
    os.environ.setdefault("HF_HUB_CACHE", str(cache))
    os.environ.setdefault("HUGGINGFACE_HUB_CACHE", str(cache))
    return cache


def snapshot_for(repository: str, cache: Path) -> Path | None:
    root = cache / ("models--" + repository.replace("/", "--"))
    main = root / "refs" / "main"
    if main.is_file():
        candidate = root / "snapshots" / main.read_text().strip()
        if candidate.is_dir():
            return candidate
    snapshots = root / "snapshots"
    if snapshots.is_dir():
        candidates = sorted((p for p in snapshots.iterdir() if p.is_dir()), key=lambda p: p.stat().st_mtime, reverse=True)
        if candidates:
            return candidates[0]
    return None


def inspect_snapshot(spec: ModelSpec, snapshot: Path | None) -> dict:
    missing = list(spec.required_files)
    weights = []
    missing_shards = []
    if snapshot is not None:
        missing = [name for name in spec.required_files if not (snapshot / name).is_file() or (snapshot / name).stat().st_size == 0]
        weights = sorted(p for p in snapshot.glob("*") if p.is_file() and p.suffix in {".safetensors", ".bin"} and p.stat().st_size > 0)
        for index in snapshot.glob("*.index.json"):
            try:
                shards = set(json.loads(index.read_text())["weight_map"].values())
            except (KeyError, ValueError, TypeError):
                missing_shards.append(index.name + ":invalid_index")
                continue
            missing_shards.extend(name for name in sorted(shards) if not (snapshot / name).is_file() or (snapshot / name).stat().st_size == 0)
    complete = not missing and not missing_shards and (bool(weights) or not spec.requires_weights)
    return {"model": spec.name, "repository": spec.repository, "purpose": spec.purpose,
            "required_by": spec.required_by, "required": spec.required,
            "status": "COMPLETE" if complete else "INCOMPLETE", "revision": snapshot.name if snapshot else None,
            "cache_location": str(snapshot) if snapshot else None, "weight_file_count": len(weights),
            "total_weight_bytes": sum(p.stat().st_size for p in weights), "missing_files": missing,
            "missing_shards": missing_shards, "weights_present": bool(weights),
            "load_test": "NOT_VERIFIED", "real_verification": "NOT_VERIFIED"}


def inventory() -> list[dict]:
    cache = configure_cache()
    return [inspect_snapshot(spec, snapshot_for(spec.repository, cache)) for spec in MODELS]
