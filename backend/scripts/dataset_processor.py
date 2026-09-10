"""
ABCI-MI Dataset Processing & Manifest Preparation Tool.
Supports 4 core benchmarking & fine-tuning datasets:
1. AISHELL-1 (Mandarin Speech Recognition)
2. VoxConverse (Speaker Diarization)
3. AMI Meeting Corpus (Multi-talker Meeting ASR & Alignment)
4. YODAS2 - Sidon (Indic Multilingual & Code-Switched Speech)
"""

import argparse
import glob
import json
import logging
import os
import re
import shutil
import sys
from pathlib import Path
from typing import Any, Dict, Generator, List, Optional

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("DatasetProcessor")


class AIShellProcessor:
    """Processor for AISHELL-1 Mandarin speech corpus."""

    def __init__(self, data_dir: str):
        self.data_dir = Path(data_dir)
        self.transcript_file = self._find_transcript()

    def _find_transcript(self) -> Path:
        candidates = [
            self.data_dir / "transcript" / "aishell_transcript_v0.8.txt",
            self.data_dir / "data_aishell" / "transcript" / "aishell_transcript_v0.8.txt",
            self.data_dir / "aishell_transcript_v0.8.txt",
        ]
        for c in candidates:
            if c.exists():
                return c
        raise FileNotFoundError(
            f"AISHELL transcript file not found in {self.data_dir}. "
            "Expected 'transcript/aishell_transcript_v0.8.txt'"
        )

    def load_transcripts(self) -> Dict[str, str]:
        transcripts: Dict[str, str] = {}
        with open(self.transcript_file, "r", encoding="utf-8") as f:
            for line in f:
                parts = line.strip().split(maxsplit=1)
                if len(parts) == 2:
                    utt_id, text = parts
                    # Remove spaces between Chinese characters
                    clean_text = re.sub(r"\s+", "", text)
                    transcripts[utt_id] = clean_text
        logger.info(f"[AISHELL-1] Loaded {len(transcripts)} ground-truth utterances.")
        return transcripts

    def export_to_jsonl(self, split: str, output_jsonl: str, max_samples: Optional[int] = None) -> int:
        transcripts = self.load_transcripts()
        wav_dirs = [
            self.data_dir / "wav" / split,
            self.data_dir / "data_aishell" / "wav" / split,
        ]
        target_wav_dir = None
        for d in wav_dirs:
            if d.exists():
                target_wav_dir = d
                break

        if not target_wav_dir:
            raise FileNotFoundError(f"AISHELL '{split}' audio directory not found in {self.data_dir}")

        out_path = Path(output_jsonl)
        out_path.parent.mkdir(parents=True, exist_ok=True)

        samples: List[Dict[str, Any]] = []
        count = 0

        # Scan all speaker folders: wav/<split>/<speaker_id>/<sample_id>.wav
        wav_files = glob.glob(str(target_wav_dir / "**" / "*.wav"), recursive=True)
        logger.info(f"[AISHELL-1] Found {len(wav_files)} audio files for split '{split}'.")

        with open(out_path, "w", encoding="utf-8") as f_out:
            for wav_path in wav_files:
                sample_id = Path(wav_path).stem
                if sample_id in transcripts:
                    record = {
                        "id": sample_id,
                        "audio_path": os.path.abspath(wav_path),
                        "text": transcripts[sample_id],
                        "language": "zh",
                        "dataset": "AISHELL-1",
                        "split": split,
                    }
                    f_out.write(json.dumps(record, ensure_ascii=False) + "\n")
                    count += 1
                    if max_samples and count >= max_samples:
                        break

        logger.info(f"[AISHELL-1] Exported {count} samples to {out_path}")
        return count


class VoxConverseProcessor:
    """Processor for VoxConverse multi-speaker conversational audio and RTTM diarization files."""

    def __init__(self, audio_dir: str, rttm_dir: str):
        self.audio_dir = Path(audio_dir)
        self.rttm_dir = Path(rttm_dir)

    def parse_rttm_file(self, rttm_path: Path) -> List[Dict[str, Any]]:
        """Parses standard NIST RTTM file into speech turn intervals."""
        turns: List[Dict[str, Any]] = []
        with open(rttm_path, "r", encoding="utf-8") as f:
            for line in f:
                parts = line.strip().split()
                if len(parts) >= 8 and parts[0] == "SPEAKER":
                    session_id = parts[1]
                    start_sec = float(parts[3])
                    duration_sec = float(parts[4])
                    speaker_id = parts[7]
                    turns.append({
                        "session_id": session_id,
                        "start_sec": start_sec,
                        "end_sec": round(start_sec + duration_sec, 3),
                        "duration_sec": duration_sec,
                        "speaker_id": speaker_id,
                    })
        return turns

    def export_diarization_manifest(self, output_json: str) -> int:
        out_path = Path(output_json)
        out_path.parent.mkdir(parents=True, exist_ok=True)

        rttm_files = list(self.rttm_dir.glob("*.rttm"))
        manifest: List[Dict[str, Any]] = []

        for rttm in rttm_files:
            session_id = rttm.stem
            # Check corresponding audio file
            audio_candidates = [
                self.audio_dir / f"{session_id}.wav",
                self.audio_dir / f"{session_id}.mp3",
            ]
            audio_path = None
            for cand in audio_candidates:
                if cand.exists():
                    audio_path = cand
                    break

            turns = self.parse_rttm_file(rttm)
            speakers = list(set(t["speaker_id"] for t in turns))

            manifest.append({
                "session_id": session_id,
                "audio_path": str(audio_path.resolve()) if audio_path else None,
                "rttm_path": str(rttm.resolve()),
                "num_speakers": len(speakers),
                "speakers": speakers,
                "turns_count": len(turns),
                "turns": turns,
                "dataset": "VoxConverse",
            })

        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=2)

        logger.info(f"[VoxConverse] Exported {len(manifest)} meeting sessions to {out_path}")
        return len(manifest)


class AMIProcessor:
    """Processor for AMI Meeting Corpus (Headset IHM and Distant MDM)."""

    def __init__(self, corpus_dir: str):
        self.corpus_dir = Path(corpus_dir)

    def export_manifest(self, output_jsonl: str) -> int:
        out_path = Path(output_jsonl)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        # Search for wav and xml/txt transcripts in corpus_dir
        audio_files = list(self.corpus_dir.glob("**/*.wav"))
        logger.info(f"[AMI] Discovered {len(audio_files)} audio tracks in {self.corpus_dir}")

        count = 0
        with open(out_path, "w", encoding="utf-8") as f_out:
            for audio in audio_files:
                meeting_id = audio.stem.split(".")[0]
                record = {
                    "meeting_id": meeting_id,
                    "audio_path": str(audio.resolve()),
                    "mic_type": "IHM" if "Headset" in str(audio) or "Array" not in str(audio) else "MDM",
                    "dataset": "AMI",
                    "language": "en",
                }
                f_out.write(json.dumps(record, ensure_ascii=False) + "\n")
                count += 1

        logger.info(f"[AMI] Exported {count} meeting tracks to {out_path}")
        return count


class YODAS2SidonProcessor:
    """Processor for YODAS2 - Sidon Indic speech dataset streaming from Hugging Face."""

    def __init__(self, dataset_name: str = "sarulab-speech/yodas2_sidon"):
        self.dataset_name = dataset_name

    def stream_and_export(
        self,
        output_jsonl: str,
        language: str = "hi",
        max_samples: int = 5000,
        hf_token: Optional[str] = None,
    ) -> int:
        try:
            from datasets import load_dataset
        except ImportError:
            raise ImportError("Please install `datasets` via `pip install datasets` to stream YODAS2-Sidon.")

        token = hf_token or os.getenv("HUGGINGFACE_HUB_TOKEN")
        logger.info(f"[YODAS2 Sidon] Connecting to Hugging Face dataset '{self.dataset_name}' (lang: {language})...")

        try:
            ds = load_dataset(
                self.dataset_name,
                streaming=True,
                token=token,
                trust_remote_code=True,
            )
            train_stream = ds["train"]
        except Exception as e:
            logger.error(f"[YODAS2 Sidon] Error initializing dataset stream: {e}")
            raise e

        out_path = Path(output_jsonl)
        out_path.parent.mkdir(parents=True, exist_ok=True)

        count = 0
        with open(out_path, "w", encoding="utf-8") as f_out:
            for sample in train_stream:
                text = sample.get("text") or sample.get("normalized_text") or ""
                lang = sample.get("lang") or sample.get("language") or language

                if text and len(text.strip()) > 3:
                    audio_info = sample.get("audio", {})
                    audio_path = audio_info.get("path") if isinstance(audio_info, dict) else str(audio_info)

                    record = {
                        "id": sample.get("id", f"yodas2_{count}"),
                        "text": text.strip(),
                        "language": lang,
                        "audio_path": audio_path,
                        "dataset": "YODAS2-Sidon",
                    }
                    f_out.write(json.dumps(record, ensure_ascii=False) + "\n")
                    count += 1

                    if count % 500 == 0:
                        logger.info(f"[YODAS2 Sidon] Processed {count} / {max_samples} samples...")

                    if count >= max_samples:
                        break

        logger.info(f"[YODAS2 Sidon] Successfully exported {count} Indic samples to {out_path}")
        return count


def main():
    parser = argparse.ArgumentParser(description="ABCI-MI Dataset Manifest Preprocessor")
    parser.add_argument("--dataset", required=True, choices=["aishell", "voxconverse", "ami", "yodas2"])
    parser.add_argument("--input", default="./data", help="Input dataset directory or source path")
    parser.add_argument("--rttm_dir", default="", help="RTTM directory for VoxConverse")
    parser.add_argument("--output", required=True, help="Output manifest path (.jsonl or .json)")
    parser.add_argument("--split", default="train", help="Dataset split (train/dev/test)")
    parser.add_argument("--language", default="hi", help="Target language code (e.g. hi, zh, ta, te)")
    parser.add_argument("--max_samples", type=int, default=5000, help="Max samples to process")

    args = parser.parse_args()

    if args.dataset == "aishell":
        proc = AIShellProcessor(args.input)
        proc.export_to_jsonl(split=args.split, output_jsonl=args.output, max_samples=args.max_samples)
    elif args.dataset == "voxconverse":
        rttm_path = args.rttm_dir or os.path.join(args.input, "rttm")
        proc = VoxConverseProcessor(audio_dir=args.input, rttm_dir=rttm_path)
        proc.export_diarization_manifest(output_json=args.output)
    elif args.dataset == "ami":
        proc = AMIProcessor(args.input)
        proc.export_manifest(output_jsonl=args.output)
    elif args.dataset == "yodas2":
        proc = YODAS2SidonProcessor()
        proc.stream_and_export(output_jsonl=args.output, language=args.language, max_samples=args.max_samples)


if __name__ == "__main__":
    main()
