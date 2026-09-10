"""
Benchmark configuration and environment settings for ABCI-MI evaluation framework.
"""

import os
import platform
import sys
from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class BenchmarkConfig:
    """Configuration container for benchmark runs."""
    results_dir: str = field(
        default_factory=lambda: os.path.abspath(
            os.getenv("BENCHMARK_RESULTS_DIR", "./benchmark_results")
        )
    )
    data_cache_dir: str = field(
        default_factory=lambda: os.path.abspath(
            os.getenv("BENCHMARK_DATA_DIR", os.getenv("DATASET_ROOT", "./data/benchmarks"))
        )
    )
    db_path: str = field(
        default_factory=lambda: os.path.abspath(
            os.getenv("BENCHMARK_DB_PATH", "./benchmark_results/benchmark_runs.db")
        )
    )
    # Specific dataset root overrides
    ami_root: Optional[str] = os.getenv("AMI_DATASET_ROOT")
    voxconverse_root: Optional[str] = os.getenv("VOXCONVERSE_DATASET_ROOT")
    dihard_root: Optional[str] = os.getenv("DIHARD_DATASET_ROOT")
    aishell_root: Optional[str] = os.getenv("AISHELL_DATASET_ROOT")
    common_voice_root: Optional[str] = os.getenv("COMMON_VOICE_DATASET_ROOT")

    default_device: str = os.getenv("BENCHMARK_DEVICE", "cpu")
    default_model: str = os.getenv("BENCHMARK_MODEL", "openai/whisper-large-v3")
    default_collar_seconds: float = float(os.getenv("BENCHMARK_COLLAR_SECONDS", "0.25"))
    sample_timeout_seconds: int = int(os.getenv("BENCHMARK_SAMPLE_TIMEOUT", "600"))
    save_raw_predictions: bool = True
    save_audio_spectrograms: bool = False
    supported_languages: List[str] = field(
        default_factory=lambda: [
            "en", "hi", "ta", "te", "kn", "ml", "bn", "mr",
            "gu", "pa", "zh", "ja", "fr", "es", "de", "ru", "ar"
        ]
    )

    def get_dataset_root(self, dataset_name: str) -> str:
        """Resolve specific root directory for a given dataset."""
        key = dataset_name.lower().replace("-", "_").replace(" ", "_")
        if key == "ami" and self.ami_root:
            return os.path.abspath(self.ami_root)
        if key == "voxconverse" and self.voxconverse_root:
            return os.path.abspath(self.voxconverse_root)
        if key == "dihard" and self.dihard_root:
            return os.path.abspath(self.dihard_root)
        if key == "aishell" and self.aishell_root:
            return os.path.abspath(self.aishell_root)
        if key == "common_voice" and self.common_voice_root:
            return os.path.abspath(self.common_voice_root)
        return os.path.join(self.data_cache_dir, key)

    def ensure_directories(self) -> None:
        """Create necessary result and cache directories."""
        os.makedirs(self.results_dir, exist_ok=True)
        os.makedirs(os.path.join(self.results_dir, "runs"), exist_ok=True)
        os.makedirs(os.path.join(self.results_dir, "latest"), exist_ok=True)
        os.makedirs(self.data_cache_dir, exist_ok=True)


def get_hardware_info() -> Dict[str, str]:
    """Inspect and return current host hardware and runtime environment metadata."""
    cuda_available = False
    gpu_name = "None"
    gpu_count = 0
    try:
        import torch  # type: ignore
        cuda_available = torch.cuda.is_available()
        if cuda_available:
            gpu_count = torch.cuda.device_count()
            gpu_name = torch.cuda.get_device_name(0)
    except Exception:
        pass

    return {
        "platform": platform.platform(),
        "processor": platform.processor() or platform.machine(),
        "python_version": sys.version.split()[0],
        "cuda_available": str(cuda_available),
        "gpu_count": str(gpu_count),
        "gpu_name": gpu_name,
        "os_name": platform.system(),
    }


def get_benchmark_config() -> BenchmarkConfig:
    """Retrieve benchmark configuration singleton."""
    cfg = BenchmarkConfig()
    cfg.ensure_directories()
    return cfg
