"""
Dataset adapters package for ABCI-MI benchmark evaluation.
Exports adapters for AMI, VoxConverse, DIHARD, AISHELL, and Common Voice.
"""

from app.benchmarks.datasets.base import BaseDatasetAdapter, BenchmarkSample
from app.benchmarks.datasets.ami import AMIDatasetAdapter
from app.benchmarks.datasets.voxconverse import VoxConverseDatasetAdapter
from app.benchmarks.datasets.dihard import DIHARDDatasetAdapter
from app.benchmarks.datasets.aishell import AISHELLDatasetAdapter
from app.benchmarks.datasets.common_voice import CommonVoiceDatasetAdapter

__all__ = [
    "BaseDatasetAdapter",
    "BenchmarkSample",
    "AMIDatasetAdapter",
    "VoxConverseDatasetAdapter",
    "DIHARDDatasetAdapter",
    "AISHELLDatasetAdapter",
    "CommonVoiceDatasetAdapter",
]
