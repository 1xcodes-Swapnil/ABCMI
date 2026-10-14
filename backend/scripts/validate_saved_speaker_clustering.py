"""Validate global clustering on retained REAL PyAnnote windows, without inference."""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main():
    import numpy as np
    import yaml
    from pyannote.audio.pipelines.clustering import AgglomerativeClustering
    from app.ai.speaker_diarization import SpeakerDiarizationEngine

    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("config", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    saved = json.loads((args.source / "result.json").read_text())
    if saved.get("execution_mode") != "REAL" or saved.get("status") != "VERIFIED":
        raise RuntimeError("Requires retained successful REAL PyAnnote evidence")
    observations, windows = [], saved["metadata"]["windows"]
    for window in windows:
        index = window["index"]
        meta = json.loads((args.source / f"window_{index}.json").read_text())
        observations.append((index, meta["speakers"], np.load(args.source / f"embeddings_{index}.npy")))
    params = yaml.safe_load(args.config.read_text())["params"]["clustering"]
    clustering = AgglomerativeClustering(metric="cosine")
    clustering.instantiate(params)
    mapping, centroids, evidence = SpeakerDiarizationEngine._cluster_window_speakers(clustering, observations)
    reconstructed, old_intervals = [], []
    for window, (index, labels, _) in zip(windows, observations):
        # Distinct actual local identities are never merged within one window.
        assert len({mapping[(index, label)] for label in labels}) == len(labels)
        meta = json.loads((args.source / f"window_{index}.json").read_text())
        for turn in meta["turns"]:
            left = max(window["owned_start"], window["start"] + turn["start"])
            right = min(window["owned_end"], window["start"] + turn["end"])
            if right > left:
                old_intervals.append((left, right))
                reconstructed.append({"start_time": left, "end_time": right,
                                      "speaker_id": mapping[(index, turn["speaker"])],
                                      "original_window": index, "original_speaker": turn["speaker"]})
    assert old_intervals == [(t["start_time"], t["end_time"]) for t in reconstructed]
    assert all(np.isfinite(v).all() for v in centroids.values())
    reconstructed.sort(key=lambda t: (t["start_time"], t["end_time"]))
    result = {"status": "VERIFIED", "scope": "offline REAL-output reconciliation; no audio/model generation or database changes",
              "meeting_id": saved["meeting_id"], "source_run_id": saved["run_id"], "configuration": params,
              "windows": len(windows), "usable_embeddings": len(evidence),
              "distinct_labels": len({t["speaker_id"] for t in reconstructed}),
              "collision_rows": sum(row["status"] == "UNRESOLVED_COLLISION" for row in evidence),
              "within_window_identity_preserved": True, "timestamps_unchanged": True,
              "accuracy": "NOT VERIFIED", "speaker_turns": reconstructed, "assignments": evidence}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as handle:
        json.dump(result, handle, indent=2)
    print(json.dumps({k: v for k, v in result.items() if k not in ("speaker_turns", "assignments", "configuration")}))


if __name__ == "__main__":
    main()
