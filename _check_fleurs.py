"""Quick check of FLEURS audio field structure."""
import os, sys
os.environ["HF_HUB_CACHE"] = "F:/hf-cache/hub"
os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"
from pathlib import Path
from dotenv import load_dotenv
load_dotenv("backend/.env")

import datasets as hfd
from datasets import Audio as HFAudio
import soundfile as sf, io, numpy as np

token = os.environ.get("HF_TOKEN", "")
print(f"HF_TOKEN set: {'YES' if token else 'NO'}")

ds = hfd.load_dataset(
    "google/fleurs", "kn_in", split="test",
    token=token, trust_remote_code=False
).cast_column("audio", HFAudio(decode=False))

print(f"Dataset size: {len(ds)}")
print(f"Keys: {list(ds[0].keys())}")

raw_count = 0
path_count = 0
none_count = 0
read_ok = 0
read_fail = 0

for i in range(min(20, len(ds))):
    s = ds[i]
    af = s.get("audio") or {}
    raw = af.get("bytes")
    path = af.get("path")
    if raw and len(raw) > 0:
        raw_count += 1
        try:
            arr, sr = sf.read(io.BytesIO(raw))
            read_ok += 1
            if i < 3:
                print(f"  [{i}] bytes={len(raw)} sr={sr} samples={len(arr)}")
        except Exception as e:
            read_fail += 1
            print(f"  [{i}] READ FAIL: {e}")
    elif path:
        path_count += 1
        p = Path(path)
        if i < 3:
            print(f"  [{i}] path={p} exists={p.exists()}")
        if p.exists():
            read_ok += 1
    else:
        none_count += 1
        if i < 3:
            print(f"  [{i}] NEITHER bytes nor path")

print(f"\nFirst 20 samples: raw_bytes={raw_count} path_only={path_count} none={none_count}")
print(f"Read OK={read_ok} FAIL={read_fail}")
