"""
VoxConverse Dataset Adapter.
VoxConverse is an audio-visual multi-speaker diarization dataset extracted from YouTube videos.
Official Publisher: Visual Geometry Group (VGG), Department of Engineering Science, University of Oxford.
Official Homepage: https://www.robots.ox.ac.uk/~vgg/data/voxconverse/
Official GitHub Repository: https://github.com/joonson/voxconverse
Official RTTMs: https://raw.githubusercontent.com/joonson/voxconverse/master/test/
Evaluates: Diarization Error Rate (DER), Missed Speech, False Alarm, Speaker Confusion.
"""

import json
import os
import urllib.request
from typing import Any, Dict, List, Optional

from app.benchmarks.datasets.base import BaseDatasetAdapter, BenchmarkSample
from app.benchmarks.exceptions import (
    AccessRequiredError,
    DatasetNotFoundError,
    InvalidDatasetStructureError,
    MissingAnnotationsError,
    MissingAudioError,
)


class VoxConverseDatasetAdapter(BaseDatasetAdapter):
    """Adapter for VoxConverse Diarization Benchmark."""

    @property
    def name(self) -> str:
        return "VoxConverse"

    @property
    def version(self) -> str:
        return "v0.0.3"

    @property
    def license_notice(self) -> str:
        return "Creative Commons Attribution 4.0 International (CC BY 4.0) - Visual Geometry Group (VGG), University of Oxford"

    @property
    def description(self) -> str:
        return "Multi-speaker conversational video audio designed for speaker diarization under varied acoustic environments."

    @property
    def expected_audio_format(self) -> str:
        return "WAV 16kHz mono / FLAC"

    @property
    def supported_tasks(self) -> List[str]:
        return ["DIARIZATION", "ALIGNMENT"]

    @property
    def requires_auth(self) -> bool:
        return False

    @property
    def auth_instructions(self) -> str:
        return (
            "VoxConverse ground truth RTTMs are automatically retrieved from the official Oxford VGG "
            "GitHub repository (https://github.com/joonson/voxconverse). Place matching audio WAV files "
            "in $VOXCONVERSE_DATASET_ROOT or ./data/benchmarks/voxconverse/ (e.g., 'aepyx.wav', 'bcuqu.wav')."
        )

    @property
    def recommended_sample_size(self) -> int:
        return 5

    # Official VoxConverse test/dev sample catalog
    OFFICIAL_SAMPLES: Dict[str, Dict[str, Any]] = {
        "aepyx": {
            "split": "test",
            "duration": 182.4,
            "rttm_url": "https://raw.githubusercontent.com/joonson/voxconverse/master/test/aepyx.rttm",
            "num_speakers": 3,
        },
        "bcuqu": {
            "split": "test",
            "duration": 210.0,
            "rttm_url": "https://raw.githubusercontent.com/joonson/voxconverse/master/test/bcuqu.rttm",
            "num_speakers": 2,
        },
        "cljsh": {
            "split": "test",
            "duration": 145.8,
            "rttm_url": "https://raw.githubusercontent.com/joonson/voxconverse/master/test/cljsh.rttm",
            "num_speakers": 4,
        },
        "dcsrt": {
            "split": "test",
            "duration": 234.2,
            "rttm_url": "https://raw.githubusercontent.com/joonson/voxconverse/master/test/dcsrt.rttm",
            "num_speakers": 3,
        },
        "edjyo": {
            "split": "test",
            "duration": 198.5,
            "rttm_url": "https://raw.githubusercontent.com/joonson/voxconverse/master/test/edjyo.rttm",
            "num_speakers": 2,
        },
    }

    def _parse_rttm_file(self, rttm_path: str) -> List[Dict[str, Any]]:
        """Parse standard NIST RTTM file into speaker turns."""
        turns = []
        if not os.path.exists(rttm_path):
            return turns
        with open(rttm_path, "r", encoding="utf-8") as f:
            for line in f:
                parts = line.strip().split()
                if len(parts) >= 8 and parts[0] == "SPEAKER":
                    start_s = float(parts[3])
                    dur_s = float(parts[4])
                    spk = parts[7]
                    turns.append({
                        "speaker": spk,
                        "start_time": start_s,
                        "end_time": round(start_s + dur_s, 3),
                        "duration": dur_s,
                    })
        return turns

    def locate_or_download_samples(
        self,
        target_dir: str,
        max_samples: int = 5,
        language: str = "en",
        split: str = "test",
    ) -> List[BenchmarkSample]:
        """Load VoxConverse evaluation samples and fetch official RTTMs from Oxford VGG."""
        vox_dir = os.getenv("VOXCONVERSE_DATASET_ROOT") or os.path.join(target_dir, "voxconverse")
        os.makedirs(vox_dir, exist_ok=True)
        samples: List[BenchmarkSample] = []

        sample_keys = list(self.OFFICIAL_SAMPLES.keys())[:max_samples]
        for s_key in sample_keys:
            meta = self.OFFICIAL_SAMPLES[s_key]
            audio_path = os.path.join(vox_dir, f"{s_key}.wav")
            rttm_path = os.path.join(vox_dir, f"{s_key}.rttm")

            # 1. Fetch official RTTM ground truth from Oxford VGG GitHub
            if not os.path.exists(rttm_path):
                try:
                    req = urllib.request.Request(
                        meta["rttm_url"],
                        headers={"User-Agent": "Mozilla/5.0 (ABCI-MI Benchmark Framework/1.0)"},
                    )
                    with urllib.request.urlopen(req, timeout=15) as resp, open(rttm_path, "wb") as out_f:
                        out_f.write(resp.read())
                except Exception as dl_err:
                    pass

            # 2. Check audio existence
            if not os.path.exists(audio_path) or os.path.getsize(audio_path) == 0:
                # If audio is missing, raise explicit MissingAudioError with guidance
                raise MissingAudioError(
                    dataset_name="VoxConverse",
                    sample_id=s_key,
                    expected_path=audio_path,
                )

            # 3. Parse ground truth RTTM
            turns = self._parse_rttm_file(rttm_path)
            if not turns:
                raise MissingAnnotationsError(
                    dataset_name="VoxConverse",
                    sample_id=s_key,
                    expected_file=rttm_path,
                )

            duration = meta["duration"]
            if os.path.exists(audio_path):
                info = self.inspect_audio_file(audio_path)
                if info.get("is_valid_wave") and info.get("duration_seconds", 0) > 0:
                    duration = info["duration_seconds"]

            sample = BenchmarkSample(
                sample_id=s_key,
                dataset_name=self.name,
                dataset_version=self.version,
                audio_path=audio_path,
                audio_format="wav",
                duration_seconds=duration,
                language="en",
                reference_transcript=None,  # VoxConverse is diarization-focused
                reference_speaker_turns=turns,
                reference_segments=[
                    {"start_time": t["start_time"], "end_time": t["end_time"], "speaker": t["speaker"]}
                    for t in turns
                ],
                ground_truth_status="ground_truth_available",
                metadata={"num_speakers": meta["num_speakers"], "split": meta["split"]},
            )
            sample.compute_sha256()
            samples.append(sample)

        return samples
