"""
IndicSUPERB / Kathbath Dataset Adapter.
IndicSUPERB is a speech understanding benchmark for 12 Indian languages.
Kathbath is the underlying speech corpus providing read-speech utterances recorded
across diverse Indian speakers and recording conditions.
Official Publisher: AI4Bharat (IIT Madras).
Official GitHub: https://github.com/AI4Bharat/IndicSUPERB
Kathbath Paper: https://arxiv.org/abs/2211.16177
Download: https://huggingface.co/datasets/ai4bharat/kathbath
License: CC BY 4.0
Evaluates: WER, CER for 12 Indian languages.
"""

import json
import os
from typing import Any, Dict, List, Optional

from app.benchmarks.datasets.base import BaseDatasetAdapter, BenchmarkSample
from app.benchmarks.exceptions import (
    DatasetNotFoundError,
    MissingAnnotationsError,
    MissingAudioError,
)


# Supported Indian language codes (ISO 639-1 / BCP-47)
KATHBATH_LANGUAGES: Dict[str, str] = {
    "hi": "Hindi",
    "ta": "Tamil",
    "te": "Telugu",
    "kn": "Kannada",
    "ml": "Malayalam",
    "bn": "Bengali",
    "mr": "Marathi",
    "gu": "Gujarati",
    "pa": "Punjabi",
    "or": "Odia",
    "as": "Assamese",
    "ur": "Urdu",
}


class IndicSUPERBDatasetAdapter(BaseDatasetAdapter):
    """
    Adapter for the IndicSUPERB / Kathbath Indian-language ASR benchmark.

    Expected local directory structure (set via INDIC_DATASET_ROOT env var or default):
      <root>/
        <lang_code>/          # e.g. hi, ta, te, kn, ml, ...
          known/              # known-speaker split
            audio/
              <sample_id>.wav
            transcript.txt    # one line per utterance: <sample_id>\\t<text>
          unknown/            # unknown-speaker split (optional)
            audio/
              <sample_id>.wav
            transcript.txt

    Alternatively supports the flat HuggingFace download layout where transcript is
    embedded in a TSV/JSONL manifest alongside audio paths.
    """

    @property
    def name(self) -> str:
        return "IndicSUPERB"

    @property
    def version(self) -> str:
        return "kathbath-1.0"

    @property
    def license_notice(self) -> str:
        return (
            "Creative Commons Attribution 4.0 International (CC BY 4.0) — "
            "AI4Bharat / IIT Madras."
        )

    @property
    def description(self) -> str:
        return (
            "IndicSUPERB is a multilingual speech benchmark covering 12 Indian languages. "
            "Kathbath corpus provides read-speech utterances from diverse speakers across India."
        )

    @property
    def expected_audio_format(self) -> str:
        return "WAV 16kHz mono"

    @property
    def supported_tasks(self) -> List[str]:
        return ["ASR", "CER", "WER"]

    @property
    def requires_auth(self) -> bool:
        return False

    @property
    def auth_instructions(self) -> str:
        return (
            "IndicSUPERB / Kathbath is publicly available under CC BY 4.0. "
            "Download via: huggingface-cli download ai4bharat/kathbath --repo-type dataset "
            "or from https://github.com/AI4Bharat/IndicSUPERB. "
            "Set INDIC_DATASET_ROOT to the local mirror directory."
        )

    @property
    def recommended_sample_size(self) -> int:
        return 50

    def _resolve_root(self, target_dir: str) -> str:
        return os.path.abspath(
            os.getenv("INDIC_DATASET_ROOT")
            or os.getenv("KATHBATH_DATASET_ROOT")
            or os.path.join(target_dir, "indicsuperb")
        )

    def _parse_transcript_file(self, transcript_path: str) -> Dict[str, str]:
        """Parse transcript.txt file. Supports: '<id>\\t<text>' or '<id> <text>' per line."""
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

    def _parse_jsonl_manifest(self, jsonl_path: str) -> Dict[str, Dict[str, Any]]:
        """Parse JSONL manifest (HuggingFace download format)."""
        records: Dict[str, Dict[str, Any]] = {}
        if not os.path.exists(jsonl_path):
            return records
        with open(jsonl_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                    uid = obj.get("id") or obj.get("audio_id") or os.path.splitext(
                        os.path.basename(obj.get("audio", {}).get("path", ""))
                    )[0]
                    if uid:
                        records[uid] = obj
                except json.JSONDecodeError:
                    continue
        return records

    def locate_or_download_samples(
        self,
        target_dir: str,
        max_samples: int = 50,
        language: str = "hi",
        split: str = "known",
    ) -> List[BenchmarkSample]:
        """
        Locate locally mirrored IndicSUPERB/Kathbath samples for the given language and split.
        Supports 'known' and 'unknown' speaker splits.
        Raises DatasetNotFoundError if the language directory does not exist.
        """
        root = self._resolve_root(target_dir)
        lang_dir = os.path.join(root, language)

        if not os.path.isdir(lang_dir):
            raise DatasetNotFoundError(
                dataset_name="IndicSUPERB",
                path=lang_dir,
                instructions=(
                    f"IndicSUPERB language directory for '{language}' not found. "
                    f"Download with: huggingface-cli download ai4bharat/kathbath --repo-type dataset "
                    f"and place files under {lang_dir}/{split}/audio/"
                ),
            )

        # Try split subdirectory first, then fallback to flat layout
        audio_dir = os.path.join(lang_dir, split, "audio")
        transcript_path = os.path.join(lang_dir, split, "transcript.txt")
        jsonl_manifest = os.path.join(lang_dir, split, "manifest.jsonl")

        if not os.path.isdir(audio_dir):
            # Flat layout: audio directly in lang_dir
            audio_dir = os.path.join(lang_dir, "audio")
            transcript_path = os.path.join(lang_dir, "transcript.txt")
            jsonl_manifest = os.path.join(lang_dir, "manifest.jsonl")

        if not os.path.isdir(audio_dir):
            raise MissingAudioError(
                dataset_name="IndicSUPERB",
                sample_id=language,
                expected_path=audio_dir,
            )

        # Parse ground truth
        transcripts = self._parse_transcript_file(transcript_path)
        if not transcripts:
            jsonl_records = self._parse_jsonl_manifest(jsonl_manifest)
            for uid, obj in jsonl_records.items():
                text = obj.get("transcription") or obj.get("text") or obj.get("sentence", "")
                if text:
                    transcripts[uid] = text

        # Enumerate audio files
        wav_files = sorted(
            f for f in os.listdir(audio_dir)
            if f.endswith(".wav") or f.endswith(".flac")
        )[:max_samples]

        if not wav_files:
            raise MissingAudioError(
                dataset_name="IndicSUPERB",
                sample_id=language,
                expected_path=audio_dir,
            )

        lang_name = KATHBATH_LANGUAGES.get(language, language)
        samples: List[BenchmarkSample] = []

        for fname in wav_files:
            sample_id = os.path.splitext(fname)[0]
            audio_path = os.path.join(audio_dir, fname)
            transcript = transcripts.get(sample_id) or transcripts.get(fname)

            duration = self._get_wav_duration(audio_path)
            sample = BenchmarkSample(
                sample_id=f"indicsuperb_{language}_{sample_id}",
                dataset_name=self.name,
                dataset_version=self.version,
                audio_path=audio_path,
                audio_format="wav",
                duration_seconds=duration,
                language=language,
                reference_transcript=transcript,
                ground_truth_status="ground_truth_available" if transcript else "ground_truth_unavailable",
                metadata={
                    "language_name": lang_name,
                    "split": split,
                    "corpus": "kathbath",
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

    def list_available_languages(self) -> List[str]:
        """Return all supported Indian language codes."""
        return list(KATHBATH_LANGUAGES.keys())
