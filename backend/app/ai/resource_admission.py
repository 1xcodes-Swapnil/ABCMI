"""Measured resource admission for the existing single-job REAL CUDA worker."""
from datetime import datetime, timezone
import math
from pathlib import Path
import shutil


def assess_resources(settings, duration_seconds):
    import psutil
    import torch
    if not math.isfinite(duration_seconds) or duration_seconds <= 0:
        raise ValueError("Resource admission requires valid actual audio duration")
    ram = psutil.virtual_memory()
    resident = psutil.Process().memory_info().rss
    disk_free = shutil.disk_usage(Path(settings.AUDIO_STORAGE_PATH).resolve()).free
    baseline_profile = (settings.OPENMOSS_PRECISION == "nf4" and
                        settings.AUDIO_CHUNK_DURATION_SECONDS == 8 and
                        settings.AUDIO_CHUNK_OVERLAP_SECONDS == 3 and
                        settings.AUDIO_CHUNK_CONCURRENCY == 1 and
                        settings.PYANNOTE_WINDOW_SECONDS == 30 and
                        settings.PYANNOTE_WINDOW_OVERLAP_SECONDS == 5 and
                        settings.REAL_WORKER_PEAK_RSS_MB >= (4608 if settings.SARVAM_QUANTIZED_MODEL_PATH else 6400) and
                        settings.REAL_WORKER_PEAK_CUDA_MB >= 2304)
    if settings.SARVAM_QUANTIZED_MODEL_PATH:
        from app.ai.quantized_snapshot import verified_sarvam_snapshot
        verified_sarvam_snapshot(settings.SARVAM_QUANTIZED_MODEL_PATH)
    step = settings.AUDIO_CHUNK_DURATION_SECONDS-settings.AUDIO_CHUNK_OVERLAP_SECONDS
    chunks = max(1, math.ceil((duration_seconds-settings.AUDIO_CHUNK_DURATION_SECONDS)/step)+1)
    # Immutable manifests currently repeat chunk metadata. Reserve conservative
    # space for that quadratic growth and the bounded temporary waveform.
    disk_required = max(512*2**20, 2*chunks*chunks*1024)
    ram_required = max(0, settings.REAL_WORKER_PEAK_RSS_MB*2**20-resident)
    cuda_free, cuda_total, cuda_required = 0, 0, settings.REAL_WORKER_PEAK_CUDA_MB*2**20
    reasons = []
    device = torch.device(settings.OPENMOSS_DEVICE)
    if device.type != "cuda" or not torch.cuda.is_available():
        reasons.append("Requested CUDA unavailable; CPU fallback forbidden")
    else:
        cuda_free, cuda_total = torch.cuda.mem_get_info(device)
        cuda_required = max(0, cuda_required-torch.cuda.memory_reserved(device))
    if not baseline_profile and not settings.REAL_ALLOW_UNVERIFIED_RESOURCE_PROFILE:
        reasons.append("Resource profile differs from measured baseline; explicit experiment opt-in required")
    for name, free, required in (("RAM", ram.available, ram_required),
                                ("CUDA", cuda_free, cuda_required), ("disk", disk_free, disk_required)):
        if free < required:
            reasons.append(f"Insufficient {name} for measured admission estimate")
    headroom = settings.REAL_RESOURCE_HEADROOM_RATIO
    full = baseline_profile and ram.available >= ram_required*headroom and cuda_free >= cuda_required*headroom
    return {"timestamp": datetime.now(timezone.utc).isoformat(), "device": str(device),
            "state": "BLOCKED" if reasons else "FULL" if full else "DEGRADED",
            "reasons": reasons, "baseline_profile": baseline_profile, "planned_chunks": chunks,
            "ram_available_bytes": ram.available, "process_rss_bytes": resident,
            "ram_increment_estimate_bytes": ram_required, "cuda_free_bytes": cuda_free,
            "cuda_total_bytes": cuda_total, "cuda_increment_estimate_bytes": cuda_required,
            "disk_free_bytes": disk_free, "disk_reserve_estimate_bytes": disk_required,
            "estimate_source": ("REAL 10s compressed run bounded_batch_20261012T165943Z with verified local Sarvam NF4; sampled worker RSS peak3.73GiB; long duration unverified"
                                if settings.SARVAM_QUANTIZED_MODEL_PATH else
                                "REAL 35s run bounded_batch_20261011T152633Z; long duration unverified"),
            "performance_support": "EXPERIMENTAL"}
