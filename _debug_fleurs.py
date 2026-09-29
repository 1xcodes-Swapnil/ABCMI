"""Debug why FLEURS WAV extraction stops at ~350."""
import os
os.environ["HF_HUB_CACHE"] = "F:/hf-cache/hub"
os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"
from pathlib import Path
from dotenv import load_dotenv
load_dotenv("backend/.env")

import datasets as hfd
from datasets import Audio as HFAudio
import soundfile as sf, io, numpy as np

token = os.environ.get("HF_TOKEN", "")
out = Path("data/benchmarks/fleurs/kn_in/audio/test")

ds = hfd.load_dataset(
    "google/fleurs", "kn_in", split="test",
    token=token, trust_remote_code=False
).cast_column("audio", HFAudio(decode=False))

print(f"Dataset size: {len(ds)}")
print(f"Existing WAVs: {len(list(out.glob('*.wav')))}")

# Check samples 340-360 to see where failures start
errors = 0
for i in range(340, 360):
    s = ds[i]
    sid = str(s.get("id", i))
    af = s.get("audio") or {}
    raw = af.get("bytes")
    wav_p = out / f"{sid}.wav"
    exists = wav_p.exists()
    
    if raw and len(raw) > 0:
        try:
            arr, sr = sf.read(io.BytesIO(raw))
            has_data = True
        except Exception as e:
            has_data = False
            errors += 1
            print(f"  [{i}] READ ERROR: {e}")
    else:
        has_data = False
    
    print(f"  [{i}] sid={sid} raw={len(raw) if raw else 0}B has_data={has_data} exists={exists}")

print(f"\nErrors in 340-360: {errors}")

# Check what happens when we try to write sample 350
print("\n--- Attempting write test at index 350 ---")
s = ds[350]
sid = str(s.get("id", 350))
af = s.get("audio") or {}
raw = af.get("bytes")
wav_p = out / f"{sid}.wav"
print(f"Target: {wav_p}")
print(f"Raw bytes: {len(raw) if raw else 0}")
if raw:
    arr, sr = sf.read(io.BytesIO(raw))
    print(f"Audio: sr={sr} samples={len(arr)}")
    try:
        sf.write(str(wav_p), arr.astype(np.float32), int(sr))
        print("WRITE OK")
    except Exception as e:
        print(f"WRITE FAIL: {e}")
