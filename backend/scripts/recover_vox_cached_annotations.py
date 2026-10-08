"""Recover real VoxConverse annotations only after exact decoded-waveform matching."""
from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path
import pyarrow.parquet as pq
import soundfile as sf

ROOT = Path(__file__).resolve().parents[2]
local = ROOT / "data/benchmarks/voxconverse"
cache = Path("F:/hf-cache/hub/datasets--diarizers-community--voxconverse")
files = sorted(local.glob("audio/test/*.wav"), key=lambda p: (sf.info(p).duration, p.name))[:10]
targets = {}
for path in files:
    info = sf.info(path)
    waveform, rate = sf.read(path, dtype="float32", always_2d=True)
    targets[path.name] = {"path": path, "info": info, "waveform_sha256": hashlib.sha256(waveform.tobytes()).hexdigest()}
output = local / "rttm_recovered"
output.mkdir(exist_ok=True)
recovered = []
for shard in sorted(cache.glob("snapshots/**/test-*.parquet")):
    for index, batch in enumerate(pq.ParquetFile(shard).iter_batches(batch_size=1)):
        row = batch.to_pylist()[0]
        payload = row["audio"]["bytes"]
        info = sf.info(io.BytesIO(payload))
        candidates = [t for t in targets.values() if t["info"].samplerate == info.samplerate
            and t["info"].frames == info.frames and t["info"].channels == info.channels]
        if not candidates: continue
        waveform, rate = sf.read(io.BytesIO(payload), dtype="float32", always_2d=True)
        digest = hashlib.sha256(waveform.tobytes()).hexdigest()
        for target in candidates:
            if digest != target["waveform_sha256"]: continue
            starts, ends, speakers = row["timestamps_start"], row["timestamps_end"], row["speakers"]
            if not starts or not len(starts) == len(ends) == len(speakers):
                raise RuntimeError("Matched cached sample has invalid annotation arrays")
            if any(not 0 <= start <= end <= info.duration + 0.02 for start, end in zip(starts, ends)):
                raise RuntimeError("Cached annotation exceeds matched audio")
            path = target["path"]
            rttm = output / (path.stem + ".rttm")
            text = "".join(f"SPEAKER {path.stem} 1 {start:.6f} {end-start:.6f} <NA> <NA> {speaker} <NA> <NA>\n"
                for start, end, speaker in zip(starts, ends, speakers))
            if rttm.exists():
                if rttm.read_text() != text: raise RuntimeError("Existing recovered annotation differs")
            else:
                with rttm.open("x", encoding="utf-8") as handle: handle.write(text)
            recovered.append({"local_audio": str(path.relative_to(ROOT)), "duration": info.duration,
                "sample_rate": rate, "waveform_sha256": digest, "cache_shard": str(shard), "cache_row": index,
                "cached_audio_path": row["audio"].get("path"), "annotation_turns": len(starts),
                "rttm": str(rttm.relative_to(ROOT)), "rttm_sha256": hashlib.sha256(text.encode()).hexdigest()})
            del targets[path.name]
    if not targets: break
evidence = ROOT / "e2e_validation/diagnostics" / ("vox_annotation_recovery_" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + ".json")
record = {"timestamp": datetime.now(timezone.utc).isoformat(), "status": "VERIFIED" if not targets else "PARTIAL",
    "recovered": recovered, "unmatched": list(targets), "downloads": False, "inference": False,
    "original_empty_rttm_preserved": True, "selection": "10 shortest measured existing test recordings"}
with evidence.open("x", encoding="utf-8") as handle: json.dump(record, handle, indent=2)
print(json.dumps({"status": record["status"], "recovered": len(recovered), "unmatched": len(targets), "artifact": str(evidence.relative_to(ROOT))}))
