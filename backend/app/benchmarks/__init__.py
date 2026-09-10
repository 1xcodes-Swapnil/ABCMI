"""
ABCI-MI Benchmark and Real-Data Evaluation Subsystem
Provides rigorous, reproducible, real-data benchmarking across public conversational
speech datasets (AMI, VoxConverse, DIHARD, AISHELL, Mozilla Common Voice).
"""

from app.benchmarks.config import BenchmarkConfig, get_benchmark_config
from app.benchmarks.dataset_registry import DatasetRegistry, get_dataset_registry
from app.benchmarks.metrics import (
    BenchmarkMetrics,
    calculate_wer,
    calculate_cer,
    calculate_der,
    calculate_timestamp_boundary_error,
    calculate_rtf,
)
from app.benchmarks.runner import BenchmarkRunner
from app.benchmarks.storage import BenchmarkStorage

__all__ = [
    "BenchmarkConfig",
    "get_benchmark_config",
    "DatasetRegistry",
    "get_dataset_registry",
    "BenchmarkMetrics",
    "calculate_wer",
    "calculate_cer",
    "calculate_der",
    "calculate_timestamp_boundary_error",
    "calculate_rtf",
    "BenchmarkRunner",
    "BenchmarkStorage",
]
