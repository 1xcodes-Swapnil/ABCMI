#!/usr/bin/env python3
"""
ABCI-MI Dataset Preparation Script
Handles: AMI RTTM generation, VoxConverse extraction, FLEURS, Kathbath, AISHELL

Run:  python prepare_datasets.py
      python prepare_datasets.py --only ami voxconverse
      python prepare_datasets.py --only fleurs kathbath
      python prepare_datasets.py --only aishell
"""

import os, sys, time, shutil, traceback, urllib.request, tarfile, zipfile, argparse
from pathlib import Path

# ── env ------------------------------------------------------------------
_env = Path(__file__).parent / "backend" / ".env"
if _env.exists():
    from dotenv import load_dotenv
    load_dotenv(_env)
os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"
# Redirect ALL HF caches to F: drive if set (avoids filling C: system drive).
# HF_HUB_CACHE  = model/dataset parquet blobs
# HF_DATASETS_CACHE = Arrow build cache (can be very large: 30+ GB)
_hf_hub = os.environ.get("HF_HUB_CACHE", "")
if _hf_hub:
    os.environ["HF_HUB_CACHE"] = _hf_hub
    os.environ["HUGGINGFACE_HUB_CACHE"] = _hf_hub
_hf_ds = os.environ.get("HF_DATASETS_CACHE", "")
if _hf_ds:
    os.environ["HF_DATASETS_CACHE"] = _hf_ds

HF_TOKEN   = os.environ.get("HF_TOKEN", "")
REPO_ROOT  = Path(__file__).parent
BENCH_ROOT = REPO_ROOT / "data" / "benchmarks"
AMI_WAV    = REPO_ROOT / "data" / "audio" / "raw"
AMI_ANN    = BENCH_ROOT / "ami" / "ami_public_manual_1.6.2"

def _p(msg, lv="I"):
    c = {"I":"\033[36m", "O":"\033[32m", "W":"\033[33m", "E":"\033[31m", "S":"\033[35m", "H":"\033[1m"}.get(lv,"")
    r = "\033[0m"
    labels = {"I":"INFO","O":" OK ","W":"WARN","E":" ERR","S":"SKIP","H":"----"}
    print(f"[{c}{labels.get(lv,lv)}{r}] {msg}", flush=True)

def _free(p: Path):
    try: return shutil.disk_usage(p).free / 1e9
    except: return 999.0

def _sz(p: Path):
    try:
        t = sum(f.stat().st_size for f in p.rglob("*") if f.is_file())
        return f"{t/1e9:.2f} GB" if t > 1e9 else f"{t/1e6:.1f} MB"
    except: return "?"

# ────────────────────────────────────────────────────────────────────────────
# 1. AMI -- generate RTTM from extracted XML segments
# ────────────────────────────────────────────────────────────────────────────
def prepare_ami():
    _p("", "H"); _p("1/5  AMI -- RTTM from XML segments", "H"); _p("", "H")

    # Check if already done
    existing = list(AMI_WAV.glob("*.rttm"))
    if len(existing) >= 10:
        _p(f"AMI: {len(existing)} RTTM files already in {AMI_WAV}", "S"); return

    if not AMI_ANN.exists():
        _p(f"AMI annotations dir not found: {AMI_ANN}", "E")
        _p("Re-run download_datasets.py --only ami first", "E"); return

    seg_dir = AMI_ANN / "segments"
    words_dir = AMI_ANN / "words"
    if not seg_dir.exists():
        _p(f"segments dir missing: {seg_dir}", "E"); return

    import xml.etree.ElementTree as ET

    # Collect all meeting IDs from segment filenames (e.g. ES2004a.A.segments.xml -> ES2004a)
    meeting_ids = sorted({f.stem.split(".")[0] for f in seg_dir.glob("*.xml")})
    _p(f"AMI: found {len(meeting_ids)} meetings in annotations", "I")

    generated = 0
    for mid in meeting_ids:
        rttm_path = AMI_WAV / f"{mid}.rttm"
        if rttm_path.exists():
            continue

        lines = []
        # Each speaker has a letter (A/B/C/D) -> one XML file per speaker
        for seg_xml in sorted(seg_dir.glob(f"{mid}.*.segments.xml")):
            # Extract speaker letter from filename: ES2004a.A.segments.xml -> A
            parts = seg_xml.stem.split(".")   # ['ES2004a', 'A', 'segments']
            speaker = parts[1] if len(parts) >= 2 else "UNK"
            spk_id  = f"{mid}_{speaker}"

            try:
                tree = ET.parse(seg_xml)
                root = tree.getroot()
                for seg in root:
                    start = float(seg.attrib.get("transcriber_start", 0.0))
                    end   = float(seg.attrib.get("transcriber_end", 0.0))
                    dur   = end - start
                    if dur <= 0:
                        continue
                    # RTTM format: SPEAKER <file> <channel> <start> <dur> <NA> <NA> <speaker> <NA> <NA>
                    lines.append(
                        f"SPEAKER {mid} 1 {start:.3f} {dur:.3f} <NA> <NA> {spk_id} <NA> <NA>"
                    )
            except Exception as e:
                _p(f"  {mid} speaker {speaker}: parse error -- {e}", "W")

        if lines:
            # Sort by start time
            lines.sort(key=lambda x: float(x.split()[3]))
            rttm_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
            generated += 1

    _p(f"AMI: generated {generated} RTTM files -> {AMI_WAV}", "O")

    # Also generate word-level transcript manifests from words XML
    _p("AMI: generating word transcripts from words XML ...", "I")
    transcript_dir = BENCH_ROOT / "ami" / "transcripts"
    transcript_dir.mkdir(parents=True, exist_ok=True)
    gen_txt = 0
    for mid in meeting_ids:
        txt_path = transcript_dir / f"{mid}.txt"
        if txt_path.exists():
            continue
        all_words = []
        for wxml in sorted(words_dir.glob(f"{mid}.*.words.xml")):
            parts = wxml.stem.split(".")
            speaker = parts[1] if len(parts) >= 2 else "UNK"
            try:
                tree = ET.parse(wxml)
                root = tree.getroot()
                for w in root:
                    st = float(w.attrib.get("starttime", 0.0))
                    word = (w.text or "").strip()
                    if word:
                        all_words.append((st, speaker, word))
            except: pass
        if all_words:
            all_words.sort(key=lambda x: x[0])
            txt_path.write_text(
                "\n".join(f"{st:.3f}\t{sp}\t{wrd}" for st, sp, wrd in all_words),
                encoding="utf-8"
            )
            gen_txt += 1
    _p(f"AMI: generated {gen_txt} word transcript files -> {transcript_dir}", "O")


# ────────────────────────────────────────────────────────────────────────────
# 2. VoxConverse -- write WAV + RTTM from HF arrow cache
# ────────────────────────────────────────────────────────────────────────────
def prepare_voxconverse():
    _p("", "H"); _p("2/5  VoxConverse -- extract WAV + RTTM from cache", "H"); _p("", "H")

    vc_root   = Path(os.environ.get("VOXCONVERSE_DATASET_ROOT", str(BENCH_ROOT / "voxconverse")))
    audio_dir = vc_root / "audio" / "test"
    rttm_dir  = vc_root / "rttm"

    existing_wav  = list(audio_dir.glob("*.wav")) if audio_dir.exists() else []
    existing_rttm = list(rttm_dir.glob("*.rttm")) if rttm_dir.exists() else []
    if len(existing_wav) >= 100 and len(existing_rttm) >= 100:
        _p(f"VoxConverse: {len(existing_wav)} WAV + {len(existing_rttm)} RTTM already present", "S")
        return
    _p(f"VoxConverse: {len(existing_wav)} WAV + {len(existing_rttm)} RTTM so far", "I")

    if not HF_TOKEN:
        _p("VoxConverse: HF_TOKEN not set -- skipping", "W"); return

    _p(f"Free disk: {_free(vc_root):.1f} GB", "I")
    try:
        import datasets as hfd
        import soundfile as sf
        import numpy as np
        import io
        from datasets import Audio as HFAudio

        hfd.disable_progress_bar()
        cache = str(vc_root / ".hf_cache")

        # Load with audio decoding DISABLED to bypass broken torchcodec on Windows
        _p("Loading voxconverse (audio decode=False to avoid torchcodec) ...", "I")
        ds = hfd.load_dataset(
            "diarizers-community/voxconverse", "default",
            split="test", token=HF_TOKEN, cache_dir=cache, trust_remote_code=False,
        ).cast_column("audio", HFAudio(decode=False))

        _p(f"  {len(ds)} samples", "I")
        # Print non-audio keys safely
        row0 = {k: v for k, v in ds[0].items() if k != "audio"}
        _p(f"  Non-audio keys: {list(row0.keys())}", "I")

        audio_dir.mkdir(parents=True, exist_ok=True)
        rttm_dir.mkdir(parents=True, exist_ok=True)

        wrote_wav = wrote_rttm = 0
        for i, sample in enumerate(ds):
            sid = (sample.get("audio_id") or sample.get("id") or f"vox_{i:05d}")
            sid = str(sid).replace("/", "_")

            # Audio field is now {"path": ..., "bytes": ...} -- no torchcodec needed
            audio_field = sample.get("audio") or sample.get("speech")
            wav_path = audio_dir / f"{sid}.wav"
            if not wav_path.exists() and audio_field:
                try:
                    raw = audio_field.get("bytes")
                    src = audio_field.get("path")
                    if raw:
                        arr, sr = sf.read(io.BytesIO(raw))
                    elif src and Path(src).exists():
                        arr, sr = sf.read(src)
                    else:
                        arr, sr = None, None
                    if arr is not None:
                        arr = np.array(arr, dtype=np.float32)
                        if arr.ndim > 1:
                            arr = arr.mean(axis=1)
                        sf.write(str(wav_path), arr, int(sr))
                        wrote_wav += 1
                except Exception as e:
                    _p(f"  WAV {sid}: {e}", "W")

            # diarizers-community/voxconverse schema:
            #   speakers:          list[str]   — speaker label per turn
            #   timestamps_start:  list[float] — turn start times (seconds)
            #   timestamps_end:    list[float] — turn end times (seconds)
            speakers   = sample.get("speakers") or []
            ts_start   = sample.get("timestamps_start") or []
            ts_end     = sample.get("timestamps_end")   or []
            rttm_path  = rttm_dir / f"{sid}.rttm"
            if not rttm_path.exists() and speakers and ts_start:
                try:
                    with open(rttm_path, "w") as rf:
                        for spk, t0, t1 in zip(speakers, ts_start, ts_end if ts_end else [None]*len(speakers)):
                            start = float(t0)
                            end   = float(t1) if t1 is not None else start + 1.0
                            dur   = max(0.001, end - start)
                            rf.write(f"SPEAKER {sid} 1 {start:.3f} {dur:.3f} <NA> <NA> {spk} <NA> <NA>\n")
                    wrote_rttm += 1
                except Exception as e:
                    _p(f"  RTTM {sid}: {e}", "W")

            if (i+1) % 50 == 0:
                print(f"\r    {i+1}/{len(ds)} ...", end="", flush=True)
        print()
        _p(f"VoxConverse: {wrote_wav} WAV + {wrote_rttm} RTTM -> {vc_root}", "O")

        cache_path = Path(cache)
        if cache_path.exists():
            shutil.rmtree(cache_path, ignore_errors=True)
            _p("VoxConverse: HF cache cleaned", "O")

    except Exception as e:
        _p(f"VoxConverse failed: {e}", "E"); traceback.print_exc()


# ────────────────────────────────────────────────────────────────────────────
# 3. FLEURS -- test splits for EN + 10 Indian languages
# ────────────────────────────────────────────────────────────────────────────
def prepare_fleurs():
    _p("", "H"); _p("3/5  FLEURS -- multilingual ASR (google/fleurs)", "H"); _p("", "H")

    if not HF_TOKEN:
        _p("FLEURS: HF_TOKEN not set -- skipping", "W"); return

    fleurs_root = Path(os.environ.get("FLEURS_DATASET_ROOT", str(BENCH_ROOT / "fleurs")))
    configs = ["en_us","hi_in","ta_in","te_in","kn_in","ml_in","bn_in","mr_in","gu_in","pa_in","ur_pk"]

    try:
        import datasets as hfd, soundfile as sf, numpy as np, io
        from datasets import Audio as HFAudio
        hfd.disable_progress_bar()
        # Use None so HF uses the global cache (~/.cache/huggingface/hub) which
        # already has all parquet data from the previous download run.
        cache = None

        for lang in configs:
            lang_dir  = fleurs_root / lang
            audio_dir = lang_dir / "audio" / "test"
            tsv_path  = lang_dir / "test.tsv"

            existing = list(audio_dir.glob("*.wav")) if audio_dir.exists() else []
            tsv_lines = (sum(1 for _ in tsv_path.open(encoding="utf-8")) - 1) if tsv_path.exists() else 0
            # Only skip if WAV count matches TSV data rows (complete extraction)
            if len(existing) >= 100 and tsv_path.exists() and len(existing) >= tsv_lines - 5:
                _p(f"  FLEURS/{lang}: {len(existing)} WAVs complete -- skip", "S"); continue

            _p(f"  FLEURS/{lang}: loading test split ...", "I")
            try:
                ds = hfd.load_dataset(
                    "google/fleurs", lang, split="test",
                    token=HF_TOKEN, cache_dir=cache, trust_remote_code=False,
                ).cast_column("audio", HFAudio(decode=False))
                audio_dir.mkdir(parents=True, exist_ok=True)
                # Use index-based filename to avoid ID collision (FLEURS IDs are not unique per split)
                tsv = ["idx\tid\traw_transcription\ttranscription\tnum_samples\tpath"]

                for i, s in enumerate(ds):
                    utterance_id = str(s.get("id", i))
                    fname   = f"{lang}_{i:05d}"          # unique per index
                    raw_tx  = s.get("raw_transcription", "")
                    norm_tx = s.get("transcription", raw_tx)
                    af      = s.get("audio") or {}
                    wav_p   = audio_dir / f"{fname}.wav"
                    nsamp   = 0
                    if not wav_p.exists():
                        raw = af.get("bytes")
                        src = af.get("path")
                        try:
                            if raw:
                                arr, sr = sf.read(io.BytesIO(raw))
                            elif src and Path(src).exists():
                                arr, sr = sf.read(src)
                            else:
                                arr, sr = None, 16000
                            if arr is not None:
                                arr = np.array(arr, dtype=np.float32)
                                if arr.ndim > 1:
                                    arr = arr.mean(axis=1)
                                nsamp = len(arr)
                                sf.write(str(wav_p), arr, int(sr))
                        except Exception as ae:
                            _p(f"    audio {fname}: {ae}", "W")
                    tsv.append(f"{i}\t{utterance_id}\t{raw_tx}\t{norm_tx}\t{nsamp}\t{fname}.wav")
                    if (i+1) % 100 == 0:
                        print(f"\r    {i+1}/{len(ds)} ...", end="", flush=True)
                print()
                tsv_path.write_text("\n".join(tsv), encoding="utf-8")
                _p(f"  FLEURS/{lang}: {len(ds)} samples written -> {lang_dir}", "O")
            except Exception as e:
                _p(f"  FLEURS/{lang}: {e}", "E")

        _p(f"FLEURS total: {_sz(fleurs_root)}", "O")

    except Exception as e:
        _p(f"FLEURS failed: {e}", "E"); traceback.print_exc()


# ────────────────────────────────────────────────────────────────────────────
# 4. Kathbath / IndicSUPERB -- valid splits for 11 Indian languages
# ────────────────────────────────────────────────────────────────────────────
def prepare_kathbath():
    _p("", "H"); _p("4/5  Kathbath / IndicSUPERB (ai4bharat/Kathbath)", "H"); _p("", "H")

    if not HF_TOKEN:
        _p("Kathbath: HF_TOKEN not set -- skipping", "W"); return

    indic_root = Path(os.environ.get("INDIC_DATASET_ROOT",
                      os.environ.get("KATHBATH_DATASET_ROOT", str(BENCH_ROOT / "indicsuperb"))))

    lang_map = {
        "bengali":"bn","gujarati":"gu","hindi":"hi","kannada":"kn",
        "malayalam":"ml","marathi":"mr","odia":"or","punjabi":"pa",
        "tamil":"ta","telugu":"te","urdu":"ur",
    }

    try:
        import pyarrow.parquet as pq, soundfile as sf, numpy as np, io
        import huggingface_hub as hfh

        for config, iso in lang_map.items():
            lang_dir  = indic_root / iso
            audio_dir = lang_dir / "known" / "audio"
            tx_path   = lang_dir / "known" / "transcript.txt"

            existing = list(audio_dir.glob("*.wav")) if audio_dir.exists() else []
            tx_lines = (sum(1 for _ in tx_path.open(encoding="utf-8"))) if tx_path.exists() else 0
            if len(existing) >= 100 and tx_path.exists() and len(existing) >= tx_lines - 5:
                _p(f"  Kathbath/{config}: {len(existing)} WAVs complete -- skip", "S"); continue

            _p(f"  Kathbath/{config}: reading parquet directly (bypasses torchcodec) ...", "I")
            try:
                # List parquet files for the valid split from HF hub (no Arrow build)
                api = hfh.HfApi()
                files = api.list_repo_files(
                    "ai4bharat/Kathbath", repo_type="dataset", token=HF_TOKEN
                )
                parquet_files = [
                    f for f in files
                    if f.startswith(f"{config}/valid") and f.endswith(".parquet")
                ]
                if not parquet_files:
                    # Fallback: try data/<config>/valid-*.parquet pattern
                    parquet_files = [
                        f for f in files
                        if config in f and "valid" in f and f.endswith(".parquet")
                    ]
                _p(f"    Found {len(parquet_files)} parquet file(s) for {config}/valid", "I")
                if not parquet_files:
                    _p(f"  Kathbath/{config}: no parquet files found", "W"); continue

                audio_dir.mkdir(parents=True, exist_ok=True)
                txlines = []
                i = 0
                for pf in sorted(parquet_files):
                    local = hfh.hf_hub_download(
                        "ai4bharat/Kathbath", pf, repo_type="dataset", token=HF_TOKEN
                    )
                    tbl = pq.read_table(local)
                    col_names = tbl.schema.names
                    # Find audio column -- Kathbath uses "audio_filepath" with bytes dict
                    audio_col = next(
                        (c for c in col_names if c in ("audio","speech","audio_filepath")), None
                    )
                    text_cols = [c for c in col_names if c in ("text","transcription","sentence","normalized_text")]

                    for row in tbl.to_pylist():
                        fname = f"{iso}_{i:06d}"
                        text  = next((row.get(c,"") for c in text_cols if row.get(c)), "")
                        af    = row.get(audio_col) if audio_col else None
                        wav_p = audio_dir / f"{fname}.wav"
                        if not wav_p.exists() and af is not None:
                            raw = af.get("bytes") if isinstance(af, dict) else (af if isinstance(af, bytes) else None)
                            src = af.get("path")  if isinstance(af, dict) else None
                            try:
                                if raw and len(raw) > 0:
                                    arr, sr = sf.read(io.BytesIO(raw))
                                elif src and Path(src).exists():
                                    arr, sr = sf.read(src)
                                else:
                                    arr, sr = None, 16000
                                if arr is not None:
                                    arr = np.array(arr, dtype=np.float32)
                                    if arr.ndim > 1: arr = arr.mean(axis=1)
                                    sf.write(str(wav_p), arr, int(sr))
                            except Exception as ae:
                                _p(f"    WAV {fname}: {ae}", "W")
                        if text:
                            txlines.append(f"{fname}\t{text}")
                        i += 1
                        if i % 200 == 0:
                            print(f"\r    {i} ...", end="", flush=True)
                print()
                tx_path.write_text("\n".join(txlines), encoding="utf-8")
                n_wav = len(list(audio_dir.glob("*.wav")))
                _p(f"  Kathbath/{config}: {i} rows, {n_wav} WAVs -> {lang_dir}", "O")
            except Exception as e:
                _p(f"  Kathbath/{config}: {e}", "E")
                import traceback; traceback.print_exc()

        _p(f"Kathbath total: {_sz(indic_root)}", "O")

    except Exception as e:
        _p(f"Kathbath failed: {e}", "E"); traceback.print_exc()


# ────────────────────────────────────────────────────────────────────────────
# 5. AISHELL-1 -- direct OpenSLR download (15 GB)
# ────────────────────────────────────────────────────────────────────────────
def prepare_aishell():
    _p("", "H"); _p("5/5  AISHELL-1 -- Mandarin ASR (OpenSLR)", "H"); _p("", "H")

    aishell_root = Path(os.environ.get("AISHELL_DATASET_ROOT", str(BENCH_ROOT / "aishell")))
    test_dir  = aishell_root / "data_aishell" / "wav" / "test"
    tx_file   = aishell_root / "data_aishell" / "transcript" / "aishell_transcript_v0.8.txt"

    if test_dir.is_dir() and tx_file.exists():
        n = sum(1 for _ in test_dir.rglob("*.wav"))
        _p(f"AISHELL-1: already extracted -- {n} test WAVs", "S"); return

    _p(f"AISHELL-1: ~15 GB download. Free: {_free(aishell_root):.1f} GB", "I")
    if _free(aishell_root) < 17:
        _p("AISHELL-1: insufficient disk space (need ≥17 GB free)", "E"); return

    aishell_root.mkdir(parents=True, exist_ok=True)
    url  = "https://www.openslr.org/resources/33/data_aishell.tgz"
    tgz  = aishell_root / "data_aishell.tgz"

    if not (tgz.exists() and tgz.stat().st_size > 1e9):
        _p("Downloading AISHELL-1 tgz ...", "I")
        try:
            req = urllib.request.Request(url, headers={"User-Agent":"Mozilla/5.0"})
            t0 = time.time()
            with urllib.request.urlopen(req, timeout=600) as resp, open(tgz,"wb") as f:
                total = int(resp.headers.get("Content-Length",0))
                done  = 0
                while True:
                    chunk = resp.read(1048576)
                    if not chunk: break
                    f.write(chunk); done += len(chunk)
                    if total:
                        print(f"\r    {done/1e9:.2f}/{total/1e9:.2f} GB ({done*100//total}%)  ", end="", flush=True)
            print()
            _p(f"Downloaded in {time.time()-t0:.0f}s", "O")
        except Exception as e:
            _p(f"Download failed: {e}", "E"); return

    _p("Extracting AISHELL-1 ...", "I")
    try:
        with tarfile.open(tgz, "r:gz") as tf:
            members = tf.getmembers()
            for i, m in enumerate(members, 1):
                tf.extract(m, path=aishell_root)
                if i % 10000 == 0:
                    print(f"\r    {i}/{len(members)} ...", end="", flush=True)
        print()
        tgz.unlink(missing_ok=True)
        n = sum(1 for _ in test_dir.rglob("*.wav")) if test_dir.exists() else 0
        _p(f"AISHELL-1: extracted, {n} test WAVs -> {aishell_root}", "O")
    except Exception as e:
        _p(f"Extraction failed: {e}", "E")


# ────────────────────────────────────────────────────────────────────────────
# Summary
# ────────────────────────────────────────────────────────────────────────────
def summary():
    _p("", "H"); _p("=== DATASET STATUS ===", "H"); _p("", "H")
    checks = [
        ("AMI audio (WAV)",         list(AMI_WAV.glob("ES*.wav"))),
        ("AMI RTTM",                list(AMI_WAV.glob("*.rttm"))),
        ("AMI transcripts",         list((BENCH_ROOT/"ami"/"transcripts").glob("*.txt")) if (BENCH_ROOT/"ami"/"transcripts").exists() else []),
        ("VoxConverse WAV",         list((BENCH_ROOT/"voxconverse"/"audio"/"test").glob("*.wav")) if (BENCH_ROOT/"voxconverse"/"audio"/"test").exists() else []),
        ("VoxConverse RTTM",        list((BENCH_ROOT/"voxconverse"/"rttm").glob("*.rttm")) if (BENCH_ROOT/"voxconverse"/"rttm").exists() else []),
        ("FLEURS en_us",            list((BENCH_ROOT/"fleurs"/"en_us"/"audio"/"test").glob("*.wav")) if (BENCH_ROOT/"fleurs"/"en_us"/"audio"/"test").exists() else []),
        ("FLEURS hi_in",            list((BENCH_ROOT/"fleurs"/"hi_in"/"audio"/"test").glob("*.wav")) if (BENCH_ROOT/"fleurs"/"hi_in"/"audio"/"test").exists() else []),
        ("Kathbath hindi",          list((BENCH_ROOT/"indicsuperb"/"hi"/"known"/"audio").glob("*.wav")) if (BENCH_ROOT/"indicsuperb"/"hi"/"known"/"audio").exists() else []),
        ("Kathbath tamil",          list((BENCH_ROOT/"indicsuperb"/"ta"/"known"/"audio").glob("*.wav")) if (BENCH_ROOT/"indicsuperb"/"ta"/"known"/"audio").exists() else []),
        ("AISHELL test WAV",        list((BENCH_ROOT/"aishell"/"data_aishell"/"wav"/"test").rglob("*.wav")) if (BENCH_ROOT/"aishell"/"data_aishell"/"wav"/"test").exists() else []),
    ]
    for label, files in checks:
        ok  = "\033[32m OK \033[0m" if files else "\033[33m --- \033[0m"
        print(f"  [{ok}] {label:<30} {len(files)} files")
    _p(f"Benchmark root total: {_sz(BENCH_ROOT)}", "O")
    _p("", "H")
    _p("To run benchmark: set EXECUTION_MODE=REAL in backend/.env then:", "I")
    _p("  cd backend && python benchmark_cli.py run --dataset ami --samples 1 --device cuda --model OpenMOSS-Team/MOSS-Transcribe-Diarize", "I")


# ────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--only", nargs="+",
                        choices=["ami","voxconverse","fleurs","kathbath","aishell","all"],
                        default=["all"])
    args = parser.parse_args()
    run_all = "all" in args.only

    _p("ABCI-MI Dataset Preparation", "H")
    _p(f"Bench root : {BENCH_ROOT}", "I")
    _p(f"Disk free  : {_free(BENCH_ROOT):.1f} GB", "I")
    _p(f"HF_TOKEN   : {'SET (' + HF_TOKEN[:10] + '...)' if HF_TOKEN else 'NOT SET'}", "I")
    print()

    BENCH_ROOT.mkdir(parents=True, exist_ok=True)

    if run_all or "ami"         in args.only: prepare_ami()
    if run_all or "voxconverse" in args.only: prepare_voxconverse()
    if run_all or "fleurs"      in args.only: prepare_fleurs()
    if run_all or "kathbath"    in args.only: prepare_kathbath()
    if run_all or "aishell"     in args.only: prepare_aishell()

    summary()
