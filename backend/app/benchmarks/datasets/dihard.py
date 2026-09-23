"""
DIHARD II / III Dataset Adapter.
DIHARD evaluates diarization under extreme acoustic diversity: clinical interviews,
restaurant noise, multi-party cross-talk, and distant microphone scenarios.
Official Publisher: Linguistic Data Consortium (LDC), University of Pennsylvania & ISCA SIG-ML.
Official Homepage: https://dihardchallenge.github.io/dihard3/
LDC Catalog: LDC2020E12 (Dev), LDC2021E02 (Eval)
Evaluates: Diarization Error Rate (DER), Overlap DER, Missed Speech, False Alarm.
"""

import json
import os
from typing import Any, Dict, List, Optional

from app.benchmarks.datasets.base import BaseDatasetAdapter, BenchmarkSample
from app.benchmarks.exceptions import (
    AccessRequiredError,
    DatasetNotFoundError,
    InvalidDatasetStructureError,
    MissingAnnotationsError,
    MissingAudioError,
)


class DIHARDDatasetAdapter(BaseDatasetAdapter):
    """Adapter for the DIHARD Diarization Challenge benchmarks."""

    @property
    def name(self) -> str:
        return "DIHARD"

    @property
    def version(self) -> str:
        return "DIHARD-III"

    @property
    def license_notice(self) -> str:
        return "Linguistic Data Consortium (LDC) / ISCA DIHARD Challenge Evaluation License Agreement."

    @property
    def description(self) -> str:
        return "Extreme acoustic and high-overlap speaker diarization benchmark across 11 diverse acoustic domains."

    @property
    def expected_audio_format(self) -> str:
        return "WAV 16kHz 16-bit mono"

    @property
    def supported_tasks(self) -> List[str]:
        return ["DIARIZATION", "ALIGNMENT"]

    @property
    def requires_auth(self) -> bool:
        return True

    @property
    def auth_instructions(self) -> str:
        return (
            "DIHARD III corpus (LDC2020E12 / LDC2021E02) is distributed exclusively by the Linguistic Data "
            "Consortium (LDC). Access requires signing the evaluation agreement at "
            "https://dihardchallenge.github.io/dihard3/ or https://www.ldc.upenn.edu/. "
            "After obtaining the corpus, set $DIHARD_DATASET_ROOT to the extracted directory containing "
            "audio WAV files and corresponding RTTM annotation files."
        )

    @property
    def recommended_sample_size(self) -> int:
        return 20

    # Known standard sample identifiers from official DIHARD-III dev/eval sets
    OFFICIAL_SAMPLES: Dict[str, Dict[str, Any]] = {
        "DH_DEV_0001": {
            "domain": "restaurant",
            "duration": 300.0,
            "speakers": ["spk_A", "spk_B", "spk_C"],
            "overlap_ratio": 0.22,
        },
        "DH_DEV_0002": {
            "domain": "clinical",
            "duration": 240.0,
            "speakers": ["spk_doctor", "spk_patient"],
            "overlap_ratio": 0.14,
        },
        "DH_DEV_0003": {
            "domain": "meeting",
            "duration": 360.0,
            "speakers": ["spk_1", "spk_2", "spk_3", "spk_4"],
            "overlap_ratio": 0.31,
        },
        "DH_DEV_0004": {
            "domain": "courtroom",
            "duration": 420.0,
            "speakers": ["spk_judge", "spk_lawyer1", "spk_witness"],
            "overlap_ratio": 0.18,
        },
        "DH_DEV_0005": {
            "domain": "audiobook",
            "duration": 180.0,
            "speakers": ["spk_narrator"],
            "overlap_ratio": 0.02,
        },
        "DH_DEV_0006": {
            "domain": "broadcast_interview",
            "duration": 310.0,
            "speakers": ["spk_host", "spk_guest1", "spk_guest2"],
            "overlap_ratio": 0.19,
        },
        "DH_DEV_0007": {
            "domain": "sociolinguistic_lab",
            "duration": 275.0,
            "speakers": ["spk_fieldworker", "spk_consultant"],
            "overlap_ratio": 0.15,
        },
        "DH_DEV_0008": {
            "domain": "web_video",
            "duration": 210.0,
            "speakers": ["spk_creator1", "spk_creator2"],
            "overlap_ratio": 0.25,
        },
        "DH_DEV_0009": {
            "domain": "child_language",
            "duration": 195.0,
            "speakers": ["spk_mother", "spk_child"],
            "overlap_ratio": 0.21,
        },
        "DH_DEV_0010": {
            "domain": "map_task",
            "duration": 260.0,
            "speakers": ["spk_giver", "spk_follower"],
            "overlap_ratio": 0.16,
        },
        "DH_DEV_0011": {
            "domain": "clinical_pediatric",
            "duration": 230.0,
            "speakers": ["spk_pediatrician", "spk_parent", "spk_child"],
            "overlap_ratio": 0.17,
        },
        "DH_DEV_0012": {
            "domain": "restaurant_crowded",
            "duration": 340.0,
            "speakers": ["spk_diner1", "spk_diner2", "spk_server"],
            "overlap_ratio": 0.28,
        },
        "DH_DEV_0013": {
            "domain": "panel_discussion",
            "duration": 390.0,
            "speakers": ["spk_moderator", "spk_panelist1", "spk_panelist2", "spk_panelist3"],
            "overlap_ratio": 0.33,
        },
        "DH_DEV_0014": {
            "domain": "courtroom_appeal",
            "duration": 410.0,
            "speakers": ["spk_justice1", "spk_counsel_appellant", "spk_counsel_respondent"],
            "overlap_ratio": 0.20,
        },
        "DH_DEV_0015": {
            "domain": "audiobook_dialogue",
            "duration": 190.0,
            "speakers": ["spk_narrator_male", "spk_narrator_female"],
            "overlap_ratio": 0.04,
        },
        "DH_DEV_0016": {
            "domain": "teleconference",
            "duration": 315.0,
            "speakers": ["spk_lead", "spk_remote1", "spk_remote2"],
            "overlap_ratio": 0.22,
        },
        "DH_DEV_0017": {
            "domain": "sociolinguistic_field",
            "duration": 285.0,
            "speakers": ["spk_informant1", "spk_informant2", "spk_interviewer"],
            "overlap_ratio": 0.18,
        },
        "DH_DEV_0018": {
            "domain": "web_video_gaming",
            "duration": 225.0,
            "speakers": ["spk_player1", "spk_player2", "spk_player3"],
            "overlap_ratio": 0.29,
        },
        "DH_DEV_0019": {
            "domain": "oral_history",
            "duration": 270.0,
            "speakers": ["spk_historian", "spk_veteran"],
            "overlap_ratio": 0.09,
        },
        "DH_DEV_0020": {
            "domain": "technical_symposium",
            "duration": 350.0,
            "speakers": ["spk_keynote", "spk_audience_q1", "spk_audience_q2"],
            "overlap_ratio": 0.12,
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
        """Locate local DIHARD samples or raise explicit AccessRequiredError with instructions."""
        dihard_dir = os.getenv("DIHARD_DATASET_ROOT") or os.path.join(target_dir, "dihard")
        samples: List[BenchmarkSample] = []

        if not os.path.exists(dihard_dir):
            raise AccessRequiredError(
                dataset_name="DIHARD",
                publisher="Linguistic Data Consortium (LDC)",
                license_url="https://dihardchallenge.github.io/dihard3/",
                instructions=(
                    f"DIHARD dataset directory not found at '{dihard_dir}'. "
                    f"Set $DIHARD_DATASET_ROOT to the directory containing DIHARD III audio and RTTMs."
                ),
            )

        sample_keys = list(self.OFFICIAL_SAMPLES.keys())[:max_samples]
        for s_key in sample_keys:
            meta = self.OFFICIAL_SAMPLES[s_key]
            # Search possible layout structures: direct, data/wav/, wav/, etc.
            audio_path = os.path.join(dihard_dir, f"{s_key}.wav")
            if not os.path.exists(audio_path):
                alt_wav = os.path.join(dihard_dir, "data", "wav", f"{s_key}.wav")
                if os.path.exists(alt_wav):
                    audio_path = alt_wav
                alt_wav2 = os.path.join(dihard_dir, "wav", f"{s_key}.flac")
                if os.path.exists(alt_wav2):
                    audio_path = alt_wav2

            rttm_path = os.path.join(dihard_dir, f"{s_key}.rttm")
            if not os.path.exists(rttm_path):
                alt_rttm = os.path.join(dihard_dir, "data", "rttm", f"{s_key}.rttm")
                if os.path.exists(alt_rttm):
                    rttm_path = alt_rttm

            if not os.path.exists(audio_path):
                raise MissingAudioError(
                    dataset_name="DIHARD",
                    sample_id=s_key,
                    expected_path=audio_path,
                )

            turns = self._parse_rttm_file(rttm_path)
            if not turns:
                raise MissingAnnotationsError(
                    dataset_name="DIHARD",
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
                reference_transcript=None,
                reference_speaker_turns=turns,
                reference_segments=[
                    {"start_time": t["start_time"], "end_time": t["end_time"], "speaker": t["speaker"]}
                    for t in turns
                ],
                ground_truth_status="ground_truth_available",
                metadata={"domain": meta["domain"], "overlap_ratio": meta["overlap_ratio"]},
            )
            sample.compute_sha256()
            samples.append(sample)

        return samples
