"""
Base dataset adapter and sample model for ABCI-MI benchmark evaluation.
Defines contracts for downloading, parsing, validating, and extracting ground truth.
"""

import abc
import hashlib
import os
import wave
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple


@dataclass
class BenchmarkSample:
    """Represents a validated benchmark sample with audio and ground truth."""
    sample_id: str
    dataset_name: str
    dataset_version: str
    audio_path: str
    audio_format: str
    duration_seconds: float
    language: str
    reference_transcript: Optional[str] = None
    reference_speaker_turns: List[Dict[str, Any]] = field(default_factory=list)
    reference_segments: List[Dict[str, Any]] = field(default_factory=list)
    reference_topics: List[str] = field(default_factory=list)
    reference_decisions: List[str] = field(default_factory=list)
    reference_summary: Optional[str] = None
    ground_truth_status: str = "ground_truth_available"  # ground_truth_available | ground_truth_unavailable
    metadata: Dict[str, Any] = field(default_factory=dict)
    audio_sha256: Optional[str] = None

    def compute_sha256(self) -> str:
        """Calculate SHA256 of the audio file for integrity check."""
        if not os.path.exists(self.audio_path):
            return ""
        hasher = hashlib.sha256()
        with open(self.audio_path, "rb") as f:
            while chunk := f.read(65536):
                hasher.update(chunk)
        self.audio_sha256 = hasher.hexdigest()
        return self.audio_sha256


class BaseDatasetAdapter(abc.ABC):
    """Abstract Base Class for all benchmark dataset adapters."""

    @property
    @abc.abstractmethod
    def name(self) -> str:
        """Unique dataset identifier."""
        pass

    @property
    @abc.abstractmethod
    def version(self) -> str:
        """Dataset version or release string."""
        pass

    @property
    @abc.abstractmethod
    def license_notice(self) -> str:
        """License and citation requirements."""
        pass

    @property
    @abc.abstractmethod
    def description(self) -> str:
        """Human readable description of the dataset."""
        pass

    @property
    @abc.abstractmethod
    def expected_audio_format(self) -> str:
        """Expected audio format (e.g. 'wav 16kHz mono')."""
        pass

    @property
    @abc.abstractmethod
    def supported_tasks(self) -> List[str]:
        """Supported evaluation tasks: ASR, DIARIZATION, ALIGNMENT, MEETING_UNDERSTANDING."""
        pass

    @property
    @abc.abstractmethod
    def requires_auth(self) -> bool:
        """Whether dataset download requires commercial agreement or user API token."""
        pass

    @property
    def auth_instructions(self) -> str:
        """Instructions if authentication or agreement is required."""
        return "No special authentication required."

    @property
    def recommended_sample_size(self) -> int:
        """Recommended default sample size for practical evaluation."""
        return 5

    @abc.abstractmethod
    def locate_or_download_samples(
        self,
        target_dir: str,
        max_samples: int = 5,
        language: str = "en",
        split: str = "test",
    ) -> List[BenchmarkSample]:
        """
        Locate local cached samples or download real audio and annotations.
        Must raise ClearConfigurationError if required authentication or files are missing.
        """
        pass

    def inspect_audio_file(self, audio_path: str) -> Dict[str, Any]:
        """Inspect real wave audio file metadata (channels, framerate, duration)."""
        if not os.path.exists(audio_path):
            raise FileNotFoundError(f"Audio file does not exist: {audio_path}")

        try:
            with wave.open(audio_path, "rb") as w:
                n_channels = w.getnchannels()
                sample_width = w.getsampwidth()
                frame_rate = w.getframerate()
                n_frames = w.getnframes()
                duration = n_frames / float(frame_rate) if frame_rate > 0 else 0.0
                return {
                    "channels": n_channels,
                    "sample_width_bytes": sample_width,
                    "frame_rate_hz": frame_rate,
                    "frames_count": n_frames,
                    "duration_seconds": duration,
                    "is_valid_wave": True,
                }
        except Exception as ex:
            file_size = os.path.getsize(audio_path)
            return {
                "file_size_bytes": file_size,
                "is_valid_wave": False,
                "error": str(ex),
                "duration_seconds": 0.0,
            }
