"""Read structural metadata only from existing local benchmark caches."""
import json
from pathlib import Path
import pyarrow.parquet as pq

result = {}
for name, folder in {
    "Kathbath": "datasets--ai4bharat--Kathbath",
    "VoxConverse": "datasets--diarizers-community--voxconverse",
    "AISHELL": "datasets--AISHELL--AISHELL-1",
}.items():
    root = Path("F:/hf-cache/hub") / folder
    shard = next(root.glob("snapshots/**/*.parquet"), None)
    if shard is None:
        result[name] = {"status": "BLOCKED", "reason": "No cached snapshot/audio shards"}
        continue
    reader = pq.ParquetFile(shard)
    row = next(reader.iter_batches(batch_size=1)).to_pylist()[0]
    audio = row.get("audio") or row.get("audio_filepath") or {}
    result[name] = {
        "snapshot_exists": True, "shard_readable": True,
        "schema": str(reader.schema_arrow), "row_fields": list(row),
        "audio_bytes_present": bool(audio.get("bytes")),
        "split": shard.name.split("-")[0],
        "annotation_types": {k: type(v).__name__ for k, v in row.items() if k != "audio"},
    }
path = Path("e2e_validation/real_local/benchmark/cache_inventory.json")
path.write_text(json.dumps(result, indent=2))
print(json.dumps(result, indent=2))
