"""
FLEURS Dataset Adapter.
FLEURS (Few-shot Learning Evaluation of Universal Representations of Speech) is a multilingual
ASR benchmark covering 102 languages, built on FLoRes-101 translated text.
Official Publisher: Google Research.
Official HuggingFace: https://huggingface.co/datasets/google/fleurs
Evaluates: WER, CER across 102 languages.
License: CC BY 4.0
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


# Representative FLEURS language codes with their full names (ISO 639-1 / BCP-47)
FLEURS_LANGUAGES: Dict[str, str] = {
    "en_us": "English (US)",
    "hi_in": "Hindi",
    "ta_in": "Tamil",
    "te_in": "Telugu",
    "kn_in": "Kannada",
    "ml_in": "Malayalam",
    "bn_in": "Bengali",
    "mr_in": "Marathi",
    "gu_in": "Gujarati",
    "pa_in": "Punjabi",
    "zh_cn": "Chinese (Simplified)",
    "zh_tw": "Chinese (Traditional)",
    "ja_jp": "Japanese",
    "fr_fr": "French",
    "es_419": "Spanish (Latin America)",
    "de_de": "German",
    "ru_ru": "Russian",
    "ar_eg": "Arabic (Egypt)",
    "sw_ke": "Swahili",
    "ur_pk": "Urdu",
}


class FLEURSDatasetAdapter(BaseDatasetAdapter):
    """
    Adapter for the FLEURS multilingual ASR benchmark dataset.

    Expected local directory structure (set via FLEURS_DATASET_ROOT env var or default):
      <root>/
        <lang_code>/
          audio/
            <split>/         # train / dev / test
              <sample_id>.wav
          <split>.tsv        # tab-separated: id \\t raw_transcription \\t transcription \\t ...
    
    The TSV columns follow the official FLEURS format:
      id, raw_transcription, transcription, num_samples, path, gender, lang_id, language, ...
    
    Ground truth is the 'transcription' (normalised) or 'raw_transcription' column.
    """

    @property
    def name(self) -> str:
        return "FLEURS"

    @property
    def version(self) -> str:
        return "1.0"

    @property
    def license_notice(self) -> str:
        return "Creative Commons Attribution 4.0 International (CC BY 4.0) — Google Research."

    @property
    def description(self) -> str:
        return (
            "Few-shot Learning Evaluation of Universal Representations of Speech. "
            "Multilingual ASR benchmark covering 102 languages, built on FLoRes-101 translated text."
        )

    @property
    def expected_audio_format(self) -> str:
        return "WAV 16kHz mono"

    @property
    def supported_tasks(self) -> List[str]:
        return ["ASR", "LANGUAGE_IDENTIFICATION"]

    @property
    def requires_auth(self) -> bool:
        return False

    @property
    def auth_instructions(self) -> str:
        return (
            "FLEURS is publicly available on Hugging Face (google/fleurs) under CC BY 4.0. "
            "Download via: huggingface-cli download google/fleurs --repo-type dataset "
            "or use the datasets library: datasets.load_dataset('google/fleurs', '<lang_code>'). "
            "Set FLEURS_DATASET_ROOT to the local mirror directory."
        )

    @property
    def recommended_sample_size(self) -> int:
        return 50

    def _resolve_root(self, target_dir: str) -> str:
        return os.path.abspath(
            os.getenv("FLEURS_DATASET_ROOT") or os.path.join(target_dir, "fleurs")
        )

    def _parse_tsv(self, tsv_path: str) -> Dict[str, Dict[str, Any]]:
        """Parse official FLEURS TSV file. Returns dict keyed by sample id."""
        records: Dict[str, Dict[str, Any]] = {}
        if not os.path.exists(tsv_path):
            return records
        with open(tsv_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("id\t"):
                    continue
                parts = line.split("\t")
                if len(parts) < 3:
                    continue
                # columns: id, raw_transcription, transcription[, num_samples, path, gender, ...]
                sample_id = parts[0].strip()
                raw_transcript = parts[1].strip()
                normalised_transcript = parts[2].strip() if len(parts) > 2 else raw_transcript
                records[sample_id] = {
                    "raw_transcription": raw_transcript,
                    "transcription": normalised_transcript,
                    "path": parts[4].strip() if len(parts) > 4 else f"{sample_id}.wav",
                }
        return records

    def locate_or_download_samples(
        self,
        target_dir: str,
        max_samples: int = 50,
        language: str = "en_us",
        split: str = "test",
    ) -> List[BenchmarkSample]:
        """
        Locate locally mirrored FLEURS samples for the given language and split.
        Does NOT auto-download from HuggingFace (dataset is large; controlled download is required).
        Raises DatasetNotFoundError if the language directory does not exist.
        """
        root = self._resolve_root(target_dir)
        lang_dir = os.path.join(root, language)

        if not os.path.isdir(lang_dir):
            raise DatasetNotFoundError(
                dataset_name="FLEURS",
                path=lang_dir,
                instructions=(
                    f"FLEURS language directory for '{language}' not found. "
                    f"Download with: huggingface-cli download google/fleurs --repo-type dataset "
                    f"or place audio files in {lang_dir}/audio/{split}/ "
                    f"and TSV file at {lang_dir}/{split}.tsv"
                ),
            )

        audio_dir = os.path.join(lang_dir, "audio", split)
        tsv_path = os.path.join(lang_dir, f"{split}.tsv")

        if not os.path.isdir(audio_dir):
            raise MissingAudioError(
                dataset_name="FLEURS",
                sample_id=language,
                expected_path=audio_dir,
            )

        # Parse ground truth TSV
        ground_truth = self._parse_tsv(tsv_path)

        # Enumerate WAV files
        wav_files = sorted(
            f for f in os.listdir(audio_dir)
            if f.endswith(".wav") or f.endswith(".flac")
        )[:max_samples]

        if not wav_files:
            raise MissingAudioError(
                dataset_name="FLEURS",
                sample_id=language,
                expected_path=audio_dir,
            )

        # Map language code to ISO 639-1 for ABCI-MI
        lang_map = {
            "en_us": "en", "hi_in": "hi", "ta_in": "ta", "te_in": "te",
            "kn_in": "kn", "ml_in": "ml", "bn_in": "bn", "mr_in": "mr",
            "gu_in": "gu", "pa_in": "pa", "zh_cn": "zh", "zh_tw": "zh",
            "ja_jp": "ja", "fr_fr": "fr", "es_419": "es", "de_de": "de",
            "ru_ru": "ru", "ar_eg": "ar", "sw_ke": "sw", "ur_pk": "ur",
        }
        lang_code = lang_map.get(language, language.split("_")[0])

        samples: List[BenchmarkSample] = []
        for fname in wav_files:
            sample_id = os.path.splitext(fname)[0]
            audio_path = os.path.join(audio_dir, fname)
            gt = ground_truth.get(sample_id, {})
            transcript = gt.get("transcription") or gt.get("raw_transcription")

            duration = self._get_wav_duration(audio_path)
            sample = BenchmarkSample(
                sample_id=f"fleurs_{language}_{sample_id}",
                dataset_name=self.name,
                dataset_version=self.version,
                audio_path=audio_path,
                audio_format="wav",
                duration_seconds=duration,
                language=lang_code,
                reference_transcript=transcript,
                ground_truth_status="ground_truth_available" if transcript else "ground_truth_unavailable",
                metadata={
                    "fleurs_language_code": language,
                    "split": split,
                    "language_name": FLEURS_LANGUAGES.get(language, language),
                },
            )
            sample.compute_sha256()
            samples.append(sample)

        return samples

    def _get_wav_duration(self, path: str) -> float:
        """Return audio duration in seconds without heavy dependencies."""
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
        """Return all FLEURS language codes supported by this adapter."""
        return list(FLEURS_LANGUAGES.keys())
