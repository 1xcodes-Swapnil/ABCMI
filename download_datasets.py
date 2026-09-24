#!/usr/bin/env python3
"""
ABCI-MI Benchmark Dataset Downloader
Downloads all 7 benchmark datasets into data/benchmarks/<dataset>/
using the HF_TOKEN from backend/.env.

Datasets handled:
  1. AMI Meeting Corpus          — audio already in data/audio/raw/; downloads RTTM annotations
  2. AISHELL-1                   — Mandarin ASR (OpenSLR direct download)
  3. VoxConverse                 — Speaker diarization (diarizers-community/voxconverse via HF)
  4. FLEURS                      — Multilingual ASR (google/fleurs via HF, 10 Indian + EN configs)
  5. IndicSUPERB / Kathbath      — Indian ASR (ai4bharat/Kathbath via HF, 12 languages)
  6. MUCS 2021                   — Skipped: requires signed data access agreement
  7. DIHARD III                  — Skipped: requires LDC license purchase

Run from repo root:
  python download_datasets.py

Set env vars to override default directories:
  AMI_DATASET_ROOT, AISHELL_DATASET_ROOT, VOXCONVERSE_DATASET_ROOT,
  FLEURS_DATASET_ROOT, INDIC_DATASET_ROOT
"""

import os
import sys
import time
import urllib.request
import zipfile
import tarfile
import shutil
from pathlib import Path
from typing import List, Optional

# ── Load .env first ──────────────────────────────────────────────────────────
_env_path = Path(__file__).parent / "backend" / ".env"
if _env_path.exists():
    from dotenv import load_dotenv
    load_dotenv(_env_path)

# Suppress symlink warning on Windows (no symlink support; files will duplicate but work)
os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"

HF_TOKEN: str = os.environ.get("HF_TOKEN", "")
REPO_ROOT = Path(__file__).parent
BENCH_ROOT = REPO_ROOT / "data" / "benchmarks"
AMI_AUDIO_ROOT = REPO_ROOT / "data" / "audio" / "raw"

# ── Helpers ──────────────────────────────────────────────────────────────────

def _log(msg: str, level: str = "INFO") -> None:
    tag = {"INFO": "\033[36mINFO\033[0m", "OK": "\033[32m OK \033[0m",
           "WARN": "\033[33mWARN\033[0m", "ERR": "\033[31m ERR\033[0m",
           "SKIP": "\033[35mSKIP\033[0m", "HEAD": "\033[1m----\033[0m"}.get(level, level)
    print(f"[{tag}] {msg}", flush=True)


def _size_str(path: Path) -> str:
    try:
        total = sum(f.stat().st_size for f in path.rglob("*") if f.is_file())
        return f"{total / 1e9:.2f} GB" if total > 1e9 else f"{total / 1e6:.1f} MB"
    except Exception:
        return "?"


def _free_gb(path: Path) -> float:
    try:
        import shutil as _sh
        return _sh.disk_usage(path).free / 1e9
    except Exception:
        return 999.0


def _http_download(url: str, dest: Path, label: str) -> bool:
    """Download url → dest with progress display. Returns True on success."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() and dest.stat().st_size > 1000:
        _log(f"{label}: already present ({dest.stat().st_size/1e6:.1f} MB), skipping.", "SKIP")
        return True
    try:
        req = urllib.request.Request(
            url, headers={"User-Agent": "Mozilla/5.0 (ABCI-MI-Downloader/1.0)"}
        )
        _log(f"Downloading {label} …", "INFO")
        t0 = time.time()
        with urllib.request.urlopen(req, timeout=120) as resp, open(dest, "wb") as f:
            total = int(resp.headers.get("Content-Length", 0))
            downloaded = 0
            chunk = 524288  # 512 KB
            while True:
                data = resp.read(chunk)
                if not data:
                    break
                f.write(data)
                downloaded += len(data)
                if total:
                    pct = downloaded * 100 // total
                    mb = downloaded / 1e6
                    print(f"\r    {mb:.1f} MB / {total/1e6:.1f} MB  ({pct}%)  ", end="", flush=True)
        print()
        elapsed = time.time() - t0
        _log(f"{label}: downloaded {downloaded/1e6:.1f} MB in {elapsed:.0f}s", "OK")
        return True
    except Exception as e:
        _log(f"{label}: download failed — {e}", "ERR")
        if dest.exists() and dest.stat().st_size < 1000:
            dest.unlink(missing_ok=True)
        return False


# ── 1. AMI RTTM Annotations ──────────────────────────────────────────────────

def download_ami_annotations() -> None:
    _log("", "HEAD")
    _log("1 / 6  AMI Meeting Corpus — RTTM Annotations", "HEAD")
    _log("", "HEAD")

    ami_root = Path(os.environ.get("AMI_DATASET_ROOT", str(AMI_AUDIO_ROOT)))
    ann_url = (
        "https://groups.inf.ed.ac.uk/ami/AMICorpusAnnotations/ami_public_manual_1.6.2.zip"
    )
    zip_path = BENCH_ROOT / "ami" / "ami_public_manual_1.6.2.zip"
    rttm_dest = ami_root

    # Check if RTTMs already exist
    existing_rttm = list(ami_root.glob("*.rttm"))
    if len(existing_rttm) >= 5:
        _log(f"AMI: {len(existing_rttm)} RTTM files already present in {ami_root}", "SKIP")
        return

    (BENCH_ROOT / "ami").mkdir(parents=True, exist_ok=True)
    ok = _http_download(ann_url, zip_path, "AMI annotations zip")
    if not ok:
        return

    # Extract .rttm files only
    _log("Extracting AMI RTTM files …", "INFO")
    try:
        extracted = 0
        with zipfile.ZipFile(zip_path, "r") as zf:
            for name in zf.namelist():
                if name.endswith(".rttm"):
                    meeting_id = Path(name).stem  # e.g. ES2002a
                    dest_rttm = rttm_dest / f"{meeting_id}.rttm"
                    if not dest_rttm.exists():
                        with zf.open(name) as src, open(dest_rttm, "wb") as dst:
                            dst.write(src.read())
                        extracted += 1
        _log(f"AMI: extracted {extracted} RTTM files → {rttm_dest}", "OK")
    except Exception as e:
        _log(f"AMI: RTTM extraction failed — {e}", "ERR")


# ── 2. AISHELL-1 ─────────────────────────────────────────────────────────────

def download_aishell() -> None:
    _log("", "HEAD")
    _log("2 / 6  AISHELL-1 — Mandarin ASR", "HEAD")
    _log("", "HEAD")

    aishell_root = Path(
        os.environ.get("AISHELL_DATASET_ROOT", str(BENCH_ROOT / "aishell"))
    )
    aishell_root.mkdir(parents=True, exist_ok=True)

    # Check if already extracted
    test_dir = aishell_root / "data_aishell" / "wav" / "test"
    transcript_file = aishell_root / "data_aishell" / "transcript" / "aishell_transcript_v0.8.txt"
    if test_dir.is_dir() and transcript_file.exists():
        count = sum(1 for _ in test_dir.rglob("*.wav"))
        _log(f"AISHELL-1: already extracted — {count} test WAV files in {aishell_root}", "SKIP")
        return

    tgz_url = "https://www.openslr.org/resources/33/data_aishell.tgz"
    tgz_path = aishell_root / "data_aishell.tgz"
    _log(f"AISHELL-1: ~15 GB download. Free: {_free_gb(aishell_root):.1f} GB", "INFO")

    ok = _http_download(tgz_url, tgz_path, "AISHELL-1 tgz")
    if not ok:
        return

    _log("Extracting AISHELL-1 (this may take several minutes) …", "INFO")
    try:
        with tarfile.open(tgz_path, "r:gz") as tf:
            members = tf.getmembers()
            total = len(members)
            for i, member in enumerate(members, 1):
                tf.extract(member, path=aishell_root)
                if i % 5000 == 0:
                    print(f"\r    {i}/{total} files …", end="", flush=True)
        print()
        _log(f"AISHELL-1: extracted → {aishell_root}", "OK")
        # Remove tgz to save space
        tgz_path.unlink(missing_ok=True)
    except Exception as e:
        _log(f"AISHELL-1: extraction failed — {e}", "ERR")


# ── 3. VoxConverse ───────────────────────────────────────────────────────────

def download_voxconverse() -> None:
    _log("", "HEAD")
    _log("3 / 6  VoxConverse — Speaker Diarization", "HEAD")
    _log("", "HEAD")

    vc_root = Path(
        os.environ.get("VOXCONVERSE_DATASET_ROOT", str(BENCH_ROOT / "voxconverse"))
    )
    vc_root.mkdir(parents=True, exist_ok=True)

    audio_dir = vc_root / "audio" / "test"
    rttm_dir = vc_root / "rttm"

    existing_audio = list(audio_dir.glob("*.wav")) if audio_dir.exists() else []
    existing_rttm  = list(rttm_dir.glob("*.rttm")) if rttm_dir.exists() else []

    if len(existing_audio) >= 100 and len(existing_rttm) >= 100:
        _log(f"VoxConverse: {len(existing_audio)} audio + {len(existing_rttm)} RTTM already present.", "SKIP")
        return

    if not HF_TOKEN:
        _log("VoxConverse: HF_TOKEN not set — skipping HF download.", "WARN")
        return

    _log("VoxConverse: downloading via HuggingFace datasets (diarizers-community/voxconverse)…", "INFO")
    _log(f"  Estimated size: ~8 GB audio + 2 MB RTTM. Free: {_free_gb(vc_root):.1f} GB", "INFO")

    try:
        import datasets as hf_datasets
        hf_datasets.disable_progress_bar()  # use our own progress

        _log("  Loading test split (audio + annotations) …", "INFO")
        ds = hf_datasets.load_dataset(
            "diarizers-community/voxconverse",
            "default",
            split="test",
            token=HF_TOKEN,
            cache_dir=str(vc_root / ".hf_cache"),
            trust_remote_code=False,
        )
        _log(f"  Loaded {len(ds)} samples. Writing WAV + RTTM files …", "INFO")

        audio_dir.mkdir(parents=True, exist_ok=True)
        rttm_dir.mkdir(parents=True, exist_ok=True)

        import soundfile as sf
        import numpy as np

        for i, sample in enumerate(ds):
            sid = sample.get("audio_id") or sample.get("id") or f"vox_{i:05d}"
            audio = sample.get("audio")
            annotations = sample.get("speakers") or sample.get("annotations") or []

            # Write WAV
            wav_path = audio_dir / f"{sid}.wav"
            if not wav_path.exists() and audio:
                arr = np.array(audio["array"], dtype=np.float32)
                sr = audio["sampling_rate"]
                sf.write(str(wav_path), arr, sr)

            # Write RTTM
            rttm_path = rttm_dir / f"{sid}.rttm"
            if not rttm_path.exists() and annotations:
                with open(rttm_path, "w") as rf:
                    for turn in annotations:
                        spk = turn.get("speaker", f"SPK{i}")
                        start = float(turn.get("start", 0.0))
                        dur = float(turn.get("end", 0.0)) - start
                        rf.write(
                            f"SPEAKER {sid} 1 {start:.3f} {dur:.3f} <NA> <NA> {spk} <NA> <NA>\n"
                        )

            if (i + 1) % 50 == 0:
                print(f"\r    {i+1}/{len(ds)} samples …", end="", flush=True)

        print()
        _log(f"VoxConverse: {len(ds)} samples saved → {vc_root}", "OK")

        # Remove HF cache to reclaim space
        hf_cache = vc_root / ".hf_cache"
        if hf_cache.exists():
            shutil.rmtree(hf_cache, ignore_errors=True)

    except Exception as e:
        _log(f"VoxConverse: HF download failed — {e}", "ERR")
        import traceback; traceback.print_exc()


# ── 4. FLEURS ────────────────────────────────────────────────────────────────

def download_fleurs() -> None:
    _log("", "HEAD")
    _log("4 / 6  FLEURS — Multilingual ASR (Google)", "HEAD")
    _log("", "HEAD")

    fleurs_root = Path(
        os.environ.get("FLEURS_DATASET_ROOT", str(BENCH_ROOT / "fleurs"))
    )

    if not HF_TOKEN:
        _log("FLEURS: HF_TOKEN not set — skipping.", "WARN")
        return

    # Download these language configs (all Indian languages + English)
    configs = [
        "en_us",
        "hi_in", "ta_in", "te_in", "kn_in", "ml_in",
        "bn_in", "mr_in", "gu_in", "pa_in", "ur_pk",
    ]

    import datasets as hf_datasets
    import soundfile as sf
    import numpy as np

    for lang in configs:
        lang_dir = fleurs_root / lang
        audio_dir = lang_dir / "audio" / "test"
        tsv_path = lang_dir / "test.tsv"

        existing = list(audio_dir.glob("*.wav")) if audio_dir.exists() else []
        if len(existing) >= 100 and tsv_path.exists():
            _log(f"  FLEURS/{lang}: {len(existing)} test WAVs already present — skip.", "SKIP")
            continue

        _log(f"  FLEURS/{lang}: downloading test split …", "INFO")
        try:
            hf_datasets.disable_progress_bar()
            ds = hf_datasets.load_dataset(
                "google/fleurs",
                lang,
                split="test",
                token=HF_TOKEN,
                cache_dir=str(fleurs_root / ".hf_cache"),
                trust_remote_code=False,
            )
            audio_dir.mkdir(parents=True, exist_ok=True)

            tsv_lines = ["id\traw_transcription\ttranscription\tnum_samples\tpath"]
            for i, sample in enumerate(ds):
                sid = str(sample.get("id", i))
                raw_tx = sample.get("raw_transcription", "")
                norm_tx = sample.get("transcription", raw_tx)
                audio = sample.get("audio")
                wav_path = audio_dir / f"{sid}.wav"
                if not wav_path.exists() and audio:
                    arr = np.array(audio["array"], dtype=np.float32)
                    sr = audio["sampling_rate"]
                    sf.write(str(wav_path), arr, sr)
                num_samples = len(audio["array"]) if audio else 0
                tsv_lines.append(f"{sid}\t{raw_tx}\t{norm_tx}\t{num_samples}\t{sid}.wav")

            with open(tsv_path, "w", encoding="utf-8") as f:
                f.write("\n".join(tsv_lines))

            _log(f"  FLEURS/{lang}: {len(ds)} samples → {lang_dir}", "OK")

        except Exception as e:
            _log(f"  FLEURS/{lang}: failed — {e}", "ERR")

    # Clean HF cache
    hf_cache = fleurs_root / ".hf_cache"
    if hf_cache.exists():
        shutil.rmtree(hf_cache, ignore_errors=True)

    total_size = _size_str(fleurs_root)
    _log(f"FLEURS total size on disk: {total_size}", "OK")


# ── 5. IndicSUPERB / Kathbath ────────────────────────────────────────────────

def download_kathbath() -> None:
    _log("", "HEAD")
    _log("5 / 6  IndicSUPERB / Kathbath — Indian ASR (ai4bharat)", "HEAD")
    _log("", "HEAD")

    indic_root = Path(
        os.environ.get("INDIC_DATASET_ROOT",
                       os.environ.get("KATHBATH_DATASET_ROOT", str(BENCH_ROOT / "indicsuperb")))
    )

    if not HF_TOKEN:
        _log("Kathbath: HF_TOKEN not set — skipping.", "WARN")
        return

    # Kathbath language configs on HF
    configs = [
        "bengali", "gujarati", "hindi", "kannada",
        "malayalam", "marathi", "odia", "punjabi",
        "tamil", "telugu", "urdu",
    ]
    # Map HF config name → ISO 639-1
    lang_map = {
        "bengali": "bn", "gujarati": "gu", "hindi": "hi", "kannada": "kn",
        "malayalam": "ml", "marathi": "mr", "odia": "or", "punjabi": "pa",
        "tamil": "ta", "telugu": "te", "urdu": "ur",
    }

    import datasets as hf_datasets
    import soundfile as sf
    import numpy as np

    for config in configs:
        iso = lang_map[config]
        lang_dir = indic_root / iso
        audio_dir = lang_dir / "known" / "audio"
        transcript_path = lang_dir / "known" / "transcript.txt"

        existing = list(audio_dir.glob("*.wav")) if audio_dir.exists() else []
        if len(existing) >= 100 and transcript_path.exists():
            _log(f"  Kathbath/{config}: {len(existing)} WAVs already present — skip.", "SKIP")
            continue

        _log(f"  Kathbath/{config}: downloading valid split …", "INFO")
        try:
            hf_datasets.disable_progress_bar()
            ds = hf_datasets.load_dataset(
                "ai4bharat/Kathbath",
                config,
                split="valid",
                token=HF_TOKEN,
                cache_dir=str(indic_root / ".hf_cache"),
                trust_remote_code=False,
            )
            audio_dir.mkdir(parents=True, exist_ok=True)

            transcript_lines = []
            for i, sample in enumerate(ds):
                # Discover available keys
                if i == 0:
                    _log(f"    Sample keys: {list(sample.keys())}", "INFO")

                # ID — try common field names
                sid = (sample.get("id") or sample.get("audio_id")
                       or sample.get("file_id") or f"{config}_{i:06d}")
                sid = str(sid).replace("/", "_").replace("\\", "_")

                # Transcript — try common field names
                text = (sample.get("text") or sample.get("transcription")
                        or sample.get("sentence") or sample.get("normalized_text", ""))

                # Audio
                audio = sample.get("audio") or sample.get("speech")
                wav_path = audio_dir / f"{sid}.wav"
                if not wav_path.exists() and audio:
                    try:
                        arr = np.array(audio["array"], dtype=np.float32)
                        sr = audio["sampling_rate"]
                        sf.write(str(wav_path), arr, sr)
                    except Exception as we:
                        _log(f"    WAV write failed for {sid}: {we}", "WARN")

                if text:
                    transcript_lines.append(f"{sid}\t{text}")

                if (i + 1) % 200 == 0:
                    print(f"\r    {i+1}/{len(ds)} samples …", end="", flush=True)

            print()
            with open(transcript_path, "w", encoding="utf-8") as f:
                f.write("\n".join(transcript_lines))

            _log(f"  Kathbath/{config}: {len(ds)} samples → {lang_dir}", "OK")

        except Exception as e:
            _log(f"  Kathbath/{config}: failed — {e}", "ERR")
            import traceback; traceback.print_exc()

    # Clean HF cache
    hf_cache = indic_root / ".hf_cache"
    if hf_cache.exists():
        shutil.rmtree(hf_cache, ignore_errors=True)

    total_size = _size_str(indic_root)
    _log(f"Kathbath total size on disk: {total_size}", "OK")


# ── 6. Skipped datasets ──────────────────────────────────────────────────────

def print_skipped() -> None:
    _log("", "HEAD")
    _log("6 / 6  Skipped datasets (manual access required)", "HEAD")
    _log("", "HEAD")
    _log("DIHARD III: requires LDC license purchase.", "SKIP")
    _log("  → https://catalog.ldc.upenn.edu/LDC2020E12  (dev)", "SKIP")
    _log("  → https://catalog.ldc.upenn.edu/LDC2021E02  (eval)", "SKIP")
    _log("  Set DIHARD_DATASET_ROOT after obtaining LDC access.", "SKIP")
    _log("", "SKIP")
    _log("MUCS 2021: requires signed data access agreement.", "SKIP")
    _log("  → https://navana-tech.github.io/MUCS2021/data.html", "SKIP")
    _log("  Set MUCS_DATASET_ROOT after obtaining access.", "SKIP")


# ── Summary ───────────────────────────────────────────────────────────────────

def print_summary() -> None:
    _log("", "HEAD")
    _log("=== DOWNLOAD SUMMARY ===", "HEAD")
    _log("", "HEAD")

    checks = {
        "AMI audio":       list(AMI_AUDIO_ROOT.glob("ES*.wav")),
        "AMI RTTM":        list(AMI_AUDIO_ROOT.glob("*.rttm")),
        "AISHELL test":    list((BENCH_ROOT / "aishell" / "data_aishell" / "wav" / "test").rglob("*.wav")) if (BENCH_ROOT / "aishell" / "data_aishell" / "wav" / "test").exists() else [],
        "VoxConverse audio": list((BENCH_ROOT / "voxconverse" / "audio" / "test").glob("*.wav")) if (BENCH_ROOT / "voxconverse" / "audio" / "test").exists() else [],
        "VoxConverse RTTM":  list((BENCH_ROOT / "voxconverse" / "rttm").glob("*.rttm")) if (BENCH_ROOT / "voxconverse" / "rttm").exists() else [],
        "FLEURS en_us":    list((BENCH_ROOT / "fleurs" / "en_us" / "audio" / "test").glob("*.wav")) if (BENCH_ROOT / "fleurs" / "en_us" / "audio" / "test").exists() else [],
        "FLEURS hi_in":    list((BENCH_ROOT / "fleurs" / "hi_in" / "audio" / "test").glob("*.wav")) if (BENCH_ROOT / "fleurs" / "hi_in" / "audio" / "test").exists() else [],
        "Kathbath hindi":  list((BENCH_ROOT / "indicsuperb" / "hi" / "known" / "audio").glob("*.wav")) if (BENCH_ROOT / "indicsuperb" / "hi" / "known" / "audio").exists() else [],
        "Kathbath tamil":  list((BENCH_ROOT / "indicsuperb" / "ta" / "known" / "audio").glob("*.wav")) if (BENCH_ROOT / "indicsuperb" / "ta" / "known" / "audio").exists() else [],
    }

    for label, files in checks.items():
        status = "OK " if files else "---"
        count = len(files)
        tag = "\033[32m OK \033[0m" if files else "\033[33m---\033[0m"
        print(f"  [{tag}] {label:<28} {count} files")

    total_bench_size = _size_str(BENCH_ROOT)
    _log(f"Total benchmark data directory size: {total_bench_size}", "OK")
    _log("", "HEAD")
    _log("Next step: set EXECUTION_MODE=REAL in backend/.env then run:", "INFO")
    _log("  cd backend && python benchmark_cli.py run --dataset ami --samples 1 --device cuda --model OpenMOSS-Team/MOSS-Transcribe-Diarize", "INFO")


# ── Main ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="ABCI-MI benchmark dataset downloader")
    parser.add_argument("--only", nargs="+",
                        choices=["ami", "aishell", "voxconverse", "fleurs", "kathbath", "all"],
                        default=["all"],
                        help="Which datasets to download (default: all)")
    parser.add_argument("--skip-aishell", action="store_true",
                        help="Skip AISHELL-1 (15 GB download)")
    args = parser.parse_args()

    download_all = "all" in args.only

    print()
    _log("ABCI-MI Benchmark Dataset Downloader", "HEAD")
    _log(f"Benchmark root: {BENCH_ROOT}", "INFO")
    _log(f"F: drive free:  {_free_gb(BENCH_ROOT):.1f} GB", "INFO")
    _log(f"HF_TOKEN:       {'SET (' + HF_TOKEN[:10] + '...)' if HF_TOKEN else 'NOT SET — HF datasets will be skipped'}", "INFO")
    print()

    BENCH_ROOT.mkdir(parents=True, exist_ok=True)

    if download_all or "ami" in args.only:
        download_ami_annotations()

    if (download_all or "aishell" in args.only) and not args.skip_aishell:
        download_aishell()
    elif args.skip_aishell:
        _log("AISHELL-1: skipped (--skip-aishell flag).", "SKIP")

    if download_all or "voxconverse" in args.only:
        download_voxconverse()

    if download_all or "fleurs" in args.only:
        download_fleurs()

    if download_all or "kathbath" in args.only:
        download_kathbath()

    print_skipped()
    print_summary()
