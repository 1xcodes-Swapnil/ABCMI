"""
MUCS 2021 Dataset Adapter.
MUCS (Multilingual and Code-Switching ASR Challenges for Low Resource Indian Languages)
was an INTERSPEECH 2021 challenge covering Hindi, Marathi, and code-switched (Hindi-English,
Bengali-English) speech.
Official challenge: http://www.leap.iisc.ac.in/mucs2021/
Data hosted at: https://navana-tech.github.io/MUCS2021/data.html
License: Research / non-commercial use (challenge participant agreement).
Evaluates: WER, CER on multilingual and code-switched speech.
"""

import json
import os
from typing import Any, Dict, List, Optional

from app.benchmarks.datasets.base import BaseDatasetAdapter, BenchmarkSample
from app.benchmarks.exceptions import (
    AccessRequiredError,
    DatasetNotFoundError,
    MissingAnnotationsError,
    MissingAudioError,
)


# MUCS 2021 sub-tasks and their language codes
MUCS_SUBTASKS: Dict[str, str] = {
    "hindi": "hi",
    "marathi": "mr",
    "hindi_english": "hi",      # code-switched Hindi-English
    "bengali_english": "bn",    # code-switched Bengali-English
}


class MUCSDatasetAdapter(BaseDatasetAdapter):
    """
    Adapter for the MUCS 2021 multilingual and code-switching ASR challenge dataset.

    Expected local directory structure (set via MUCS_DATASET_ROOT env var or default):
      <root>/
        <subtask>/            # hindi | marathi | hindi_english | bengali_english
          audio/
            <split>/          # train / dev / test
              <sample_id>.wav
          transcription/
            <split>.txt       # tab-separated: <sample_id>\\t<transcription>
          OR flat:
            <split>_transcript.txt

    Note: MUCS dataset requires participants to sign a data access agreement.
    Contact: navana-tech.github.io/MUCS2021/data.html for access.
    """

    @property
    def name(self) -> str:
        return "MUCS"

    @property
    def version(self) -> str:
        return "MUCS-2021"

    @property
    def license_notice(self) -> str:
        return (
            "MUCS 2021 Challenge Data Use Agreement — Non-commercial research use only. "
            "Contact challenge organizers at navana-tech.github.io/MUCS2021/data.html for access."
        )

    @property
    def description(self) -> str:
        return (
            "Multilingual and Code-Switching ASR Challenges 2021 (INTERSPEECH). "
            "Covers Hindi, Marathi, and code-switched (Hindi-English, Bengali-English) speech. "
            "~1200 hours total audio across four sub-tasks."
        )

    @property
    def expected_audio_format(self) -> str:
        return "WAV 16kHz mono"

    @property
    def supported_tasks(self) -> List[str]:
        return ["ASR", "WER", "CER", "CODE_SWITCHING"]

    @property
    def requires_auth(self) -> bool:
        return True

    @property
    def auth_instructions(self) -> str:
        return (
            "MUCS 2021 requires signing a data access agreement. "
            "Visit: https://navana-tech.github.io/MUCS2021/data.html "
            "Complete the registration form to receive download credentials. "
            "Set MUCS_DATASET_ROOT to the local dataset directory after download."
        )

    @property
    def recommended_sample_size(self) -> int:
        return 50

    def _resolve_root(self, target_dir: str) -> str:
        return os.path.abspath(
            os.getenv("MUCS_DATASET_ROOT") or os.path.join(target_dir, "mucs")
        )

    def _parse_transcript_file(self, transcript_path: str) -> Dict[str, str]:
        """Parse MUCS transcript file. Format: <id>\\t<text> or <id> <text> per line."""
        records: Dict[str, str] = {}
        if not os.path.exists(transcript_path):
            return records
        with open(transcript_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                if "\t" in line:
                    parts = line.split("\t", 1)
                else:
                    parts = line.split(" ", 1)
                if len(parts) == 2:
                    records[parts[0].strip()] = parts[1].strip()
        return records

    def locate_or_download_samples(
        self,
        target_dir: str,
        max_samples: int = 50,
        language: str = "hindi",
        split: str = "dev",
    ) -> List[BenchmarkSample]:
        """
        Locate locally downloaded MUCS 2021 samples for the given subtask and split.
        Does NOT auto-download (requires signed data access agreement).
        Raises AccessRequiredError if data is absent and auth is required.
        """
        root = self._resolve_root(target_dir)
        subtask_dir = os.path.join(root, language)

        if not os.path.isdir(subtask_dir):
            raise AccessRequiredError(
                dataset_name="MUCS",
                publisher="Navana Tech / LEAP IISc",
                license_url="https://navana-tech.github.io/MUCS2021/data.html",
                instructions=(
                    f"MUCS 2021 requires a data access agreement before download. "
                    f"After obtaining access, place files in {subtask_dir}/audio/{split}/ "
                    f"and transcripts in {subtask_dir}/transcription/{split}.txt"
                ),
            )

        # Try structured layout first
        audio_dir = os.path.join(subtask_dir, "audio", split)
        transcript_path = os.path.join(subtask_dir, "transcription", f"{split}.txt")

        if not os.path.isdir(audio_dir):
            # Flat layout fallback
            audio_dir = os.path.join(subtask_dir, split)
            transcript_path = os.path.join(subtask_dir, f"{split}_transcript.txt")

        if not os.path.isdir(audio_dir):
            raise MissingAudioError(
                dataset_name="MUCS",
                sample_id=language,
                expected_path=audio_dir,
            )

        transcripts = self._parse_transcript_file(transcript_path)

        wav_files = sorted(
            f for f in os.listdir(audio_dir)
            if f.endswith(".wav") or f.endswith(".flac")
        )[:max_samples]

        if not wav_files:
            raise MissingAudioError(
                dataset_name="MUCS",
                sample_id=language,
                expected_path=audio_dir,
            )

        lang_code = MUCS_SUBTASKS.get(language, "hi")
        samples: List[BenchmarkSample] = []

        for fname in wav_files:
            sample_id = os.path.splitext(fname)[0]
            audio_path = os.path.join(audio_dir, fname)
            transcript = transcripts.get(sample_id) or transcripts.get(fname)

            duration = self._get_wav_duration(audio_path)
            sample = BenchmarkSample(
                sample_id=f"mucs_{language}_{sample_id}",
                dataset_name=self.name,
                dataset_version=self.version,
                audio_path=audio_path,
                audio_format="wav",
                duration_seconds=duration,
                language=lang_code,
                reference_transcript=transcript,
                ground_truth_status="ground_truth_available" if transcript else "ground_truth_unavailable",
                metadata={
                    "subtask": language,
                    "split": split,
                    "is_code_switched": "english" in language.lower(),
                },
            )
            sample.compute_sha256()
            samples.append(sample)

        return samples

    def _get_wav_duration(self, path: str) -> float:
        try:
            import wave as wv
            with wv.open(path) as wf:
                return wf.getnframes() / wf.getframerate()
        except Exception:
            try:
                size = os.path.getsize(path)
                return max(1.0, (size - 44) / (16000 * 2))
            except Exception:
                return 0.0

    def list_available_subtasks(self) -> List[str]:
        """Return all supported MUCS subtask names."""
        return list(MUCS_SUBTASKS.keys())
