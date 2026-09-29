"""Inspect Kathbath parquet audio_filepath and repo file structure."""
import os, sys
os.environ["HF_HUB_CACHE"] = "F:/hf-cache/hub"
os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"
os.environ["PYTHONIOENCODING"] = "utf-8"
from dotenv import load_dotenv
load_dotenv("backend/.env")
import huggingface_hub as hfh
import pyarrow.parquet as pq

token = os.environ.get("HF_TOKEN", "")
api = hfh.HfApi()

# Download bengali valid parquet and inspect audio_filepath
local = hfh.hf_hub_download(
    "ai4bharat/Kathbath", "bengali/valid-00000-of-00002.parquet",
    repo_type="dataset", token=token
)
tbl = pq.read_table(local)
rows = tbl.to_pylist()

print(f"Rows in file: {len(rows)}", flush=True)
print("Schema:", tbl.schema.names, flush=True)

# Show first 5 rows
for r in rows[:5]:
    fname = r.get("fname", "")
    text  = r.get("text", "")
    apath = r.get("audio_filepath", "")
    dur   = r.get("duration", 0)
    # Encode safely for cp1252 console
    text_safe = text.encode("ascii", "replace").decode("ascii")
    print(f"  fname={fname}  dur={dur:.1f}  path={apath}  text={text_safe[:40]}", flush=True)

# List ALL non-parquet files in repo
print("\nNon-parquet repo files (first 30):", flush=True)
all_files = list(api.list_repo_files("ai4bharat/Kathbath", repo_type="dataset", token=token))
non_pq = [f for f in all_files if not f.endswith(".parquet")]
for f in non_pq[:30]:
    print(" ", f, flush=True)
