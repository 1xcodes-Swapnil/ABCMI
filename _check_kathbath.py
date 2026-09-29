"""Verify Kathbath parquet layout and audio field structure."""
import os, io
os.environ["HF_HUB_CACHE"] = "F:/hf-cache/hub"
os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"
from dotenv import load_dotenv
load_dotenv("backend/.env")
import huggingface_hub as hfh
import pyarrow.parquet as pq
import soundfile as sf
import numpy as np

token = os.environ.get("HF_TOKEN", "")
api = hfh.HfApi()

print("Listing repo files for ai4bharat/Kathbath ...")
all_files = list(api.list_repo_files("ai4bharat/Kathbath", repo_type="dataset", token=token))
parquet_files = [f for f in all_files if f.endswith(".parquet")]
print(f"Total parquet files: {len(parquet_files)}")

# Show file structure
configs_seen = {}
for f in parquet_files[:40]:
    parts = f.split("/")
    key = "/".join(parts[:2])
    if key not in configs_seen:
        configs_seen[key] = []
    configs_seen[key].append(f)

for k, v in list(configs_seen.items())[:12]:
    print(f"  {k}: {len(v)} files -> {v[0]}")

# Test: download and inspect one bengali valid parquet
bengali_valid = [f for f in parquet_files if "bengali" in f and "valid" in f]
print(f"\nbengali valid parquets: {bengali_valid[:3]}")

if bengali_valid:
    print(f"\nDownloading {bengali_valid[0]} ...")
    local = hfh.hf_hub_download("ai4bharat/Kathbath", bengali_valid[0], repo_type="dataset", token=token)
    tbl = pq.read_table(local)
    print(f"Schema: {tbl.schema.names}")
    print(f"Rows: {len(tbl)}")
    row = tbl.to_pylist()[0]
    print(f"Keys: {list(row.keys())}")
    
    # Check audio field
    af = row.get("audio") or row.get("speech")
    print(f"Audio type: {type(af)}")
    if isinstance(af, dict):
        print(f"Audio keys: {list(af.keys())}")
        raw = af.get("bytes")
        print(f"Bytes len: {len(raw) if raw else 0}")
        if raw and len(raw) > 0:
            arr, sr = sf.read(io.BytesIO(raw))
            print(f"READABLE: sr={sr} samples={len(arr)}")
    elif isinstance(af, bytes):
        print(f"Direct bytes: {len(af)}")
        arr, sr = sf.read(io.BytesIO(af))
        print(f"READABLE: sr={sr} samples={len(arr)}")
    
    text = row.get("text") or row.get("transcription") or row.get("sentence") or ""
    print(f"Text: {text[:80]}")
