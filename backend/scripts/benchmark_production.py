"""Sequential local-dataset benchmark through the REAL persisted application path."""
import argparse
import asyncio
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import uuid

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
os.environ.update(EXECUTION_MODE="REAL", DEBUG="false", LOG_LEVEL="CRITICAL", HF_HUB_OFFLINE="1")

def save(path, value):
    with path.open("x", encoding="utf-8") as handle:
        json.dump(value, handle, indent=2, default=str)

async def prepare(sample, folder, run_id):
    import httpx
    import soundfile as sf
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import async_sessionmaker
    from app.infrastructure.database import init_database, close_database_connections
    from app.models.meeting import Meeting
    from app.models.user import User
    from app.core.security import create_access_token
    from app.core.config import get_settings
    info = sf.info(sample.audio_path)
    settings = get_settings()
    assert settings.EXECUTION_MODE == "REAL" and settings.OPENMOSS_DEVICE == "cuda"
    async with async_sessionmaker(init_database())() as db:
        if (await db.execute(text("SELECT count(*) FROM inference_jobs WHERE status IN ('queued','running')"))).scalar_one():
            raise RuntimeError("Wait for existing application work; benchmark will not compete with active jobs")
        existing = await db.get(Meeting, uuid.UUID("40560ee3-9d8e-45c1-b2b4-eaa0f1f9bbdb"))
        user = await db.get(User, existing.host_id)
        if not user or not user.is_active:
            raise RuntimeError("Existing authorized host unavailable")
        token = create_access_token({"sub": str(user.id), "role": user.role, "tenant_id": existing.tenant_id})
    await close_database_connections()
    record = {"benchmark_run_id": run_id, "benchmark_sample_id": sample.sample_id,
        "timestamp": datetime.now(timezone.utc).isoformat(), "sample": asdict(sample),
        "audio_filename": Path(sample.audio_path).name, "duration_seconds": info.duration,
        "sample_rate": info.samplerate, "channels": info.channels,
        "size_bytes": Path(sample.audio_path).stat().st_size, "sha256": sample.audio_sha256,
        "device": settings.OPENMOSS_DEVICE, "model": settings.OPENMOSS_MODEL_ID,
        "chunk_duration": settings.AUDIO_CHUNK_DURATION_SECONDS,
        "chunk_overlap": settings.AUDIO_CHUNK_OVERLAP_SECONDS,
        "chunk_threshold": settings.AUDIO_CHUNK_THRESHOLD_SECONDS,
        "selection": "first locally sorted files; bounded pilot is not a dataset-wide estimate"}
    async with httpx.AsyncClient(base_url="http://127.0.0.1:3000/api/v1", timeout=120,
        headers={"Authorization": "Bearer " + token}) as client:
        response = await client.get("/health")
        response.raise_for_status()
        if response.json()["status"] != "healthy":
            raise RuntimeError("Required application services are unhealthy")
        response = await client.post("/meetings", json={"title": "REAL benchmark " + sample.sample_id, "language": sample.language})
        response.raise_for_status()
        record["meeting_id"] = response.json()["id"]
        save(folder / "created.json", record)
        with open(sample.audio_path, "rb") as source:
            response = await client.post(f"/meetings/{record['meeting_id']}/audio",
                files={"file": (Path(sample.audio_path).name, source, "audio/wav")}, data={"format": "wav"})
        response.raise_for_status()
        record["upload"] = response.json()
        hasher = hashlib.sha256()
        with open(record["upload"]["file_path"], "rb") as source:
            for block in iter(lambda: source.read(1048576), b""): hasher.update(block)
        if hasher.hexdigest() != sample.audio_sha256: raise RuntimeError("Stored audio hash mismatch")
        save(folder / "input.json", record)
    return record

async def main(args):
    from app.benchmarks.dataset_registry import get_dataset_registry
    from app.benchmarks.metrics import calculate_wer, calculate_cer, calculate_rtf, calculate_der
    import resume_uploaded_meeting
    adapter = get_dataset_registry().get_adapter(args.dataset)
    samples = adapter.locate_or_download_samples(str(ROOT / "data/benchmarks"), max_samples=args.samples, language=args.language)
    if any(not s.reference_transcript and not s.reference_speaker_turns for s in samples):
        raise RuntimeError("Accuracy benchmark requires actual matched text or speaker ground truth")
    folder = args.run or ROOT / "benchmark results" / ("benchmark_" + args.dataset + "_" + args.language + "_" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"))
    folder.mkdir(parents=True, exist_ok=True)
    plan = folder / "plan.json"
    if not plan.exists():
        save(plan, {"benchmark_run_id": folder.name, "dataset": args.dataset, "language": args.language,
            "samples": [asdict(s) for s in samples], "execution_mode": "REAL", "scope": "production API upload, worker, persistence, fresh readback",
            "git_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()})
    else:
        previous = json.loads(plan.read_text())
        if previous["dataset"] != args.dataset or previous["language"] != args.language or previous["samples"] != [asdict(s) for s in samples]:
            raise RuntimeError("Resume plan differs; use the same dataset, language and sample count")
    results = []
    print("Benchmark evidence:", str(folder.relative_to(ROOT)), flush=True)
    for sample in samples:
        sample_folder = folder / sample.sample_id
        sample_folder.mkdir(exist_ok=True)
        if (sample_folder / "metrics.json").exists():
            results.append(json.loads((sample_folder / "metrics.json").read_text()))
            continue
        metrics_target = sample_folder / "metrics.json"
        if (sample_folder / "created.json").exists():
            evidence = sorted(sample_folder.glob("processing_result_*.json"))
            failed = json.loads(evidence[-1].read_text(encoding="utf-8")) if evidence else {}
            if not args.retry_failed or failed.get("pipeline", {}).get("status") != "failed":
                raise RuntimeError("Existing unfinished meeting: inspect its job/evidence before resuming; do not resubmit")
            sample_folder = sample_folder / ("attempt_" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"))
            sample_folder.mkdir()
        print("Processing", sample.sample_id, sample.duration_seconds, "seconds", flush=True)
        record = await prepare(sample, sample_folder, folder.name)
        code = await resume_uploaded_meeting.run(argparse.Namespace(run=sample_folder,
            meeting=uuid.UUID(record["meeting_id"]), observation_seconds=86400))
        if code: raise RuntimeError("Production processing failed; inspect saved first failure before continuing")
        command = [sys.executable, str(ROOT / "backend/scripts/capture_workspace_run.py"), "--run", str(sample_folder), "--meeting", record["meeting_id"]]
        proc = await asyncio.to_thread(subprocess.run, command, cwd=ROOT, capture_output=True, text=True)
        save(sample_folder / "fresh_process.json", {"exit_code": proc.returncode})
        if proc.returncode: raise RuntimeError("Fresh-process readback failed")
        readback = json.loads(sorted(sample_folder.glob("readback_*.json"))[-1].read_text())
        if not readback["fresh_readback_matches_api"] or not readback["database_segments"]:
            raise RuntimeError("Actual non-empty persisted transcript not verified")
        if not readback["qdrant_ids_match"]:
            raise RuntimeError("Qdrant fresh readback differs from persisted knowledge")
        text_out = " ".join(s["original_text"] for s in readback["database_segments"])
        job = readback["pipeline"]["body"]["jobs"][-1]
        elapsed = job["result"]["elapsed_seconds"]
        tasks = job["result"].get("ace_tasks", [])
        asr_metadata = next(((t.get("output") or {}).get("metadata", {}) for t in tasks
            if t.get("capability") == "multilingual_asr"), {})
        inference = asr_metadata.get("inference", [])
        inference = [inference] if isinstance(inference, dict) else inference
        moss_times = [v["generation_seconds"] for v in inference if "generation_seconds" in v]
        pyannote_times = [(t.get("output") or {}).get("metadata", {}).get("inference_seconds") for t in tasks]
        pyannote_times = [v for v in pyannote_times if v is not None]
        metrics = {"benchmark_run_id": folder.name, "benchmark_sample_id": sample.sample_id,
            "meeting_id": record["meeting_id"], "job_id": job["id"],
            "canonical_transcript_id": readback["canonical_transcript_id"], "dataset": args.dataset,
            "language": sample.language, "duration_seconds": record["duration_seconds"],
            "sample_rate": record["sample_rate"], "sha256": record["sha256"],
            "model": record["model"], "device": record["device"], "chunk_duration": record["chunk_duration"],
            "chunk_overlap": record["chunk_overlap"], "processing_seconds": elapsed,
            "RTF": calculate_rtf(elapsed, record["duration_seconds"]),
            "WER": calculate_wer(sample.reference_transcript, text_out) if sample.reference_transcript else None,
            "CER": calculate_cer(sample.reference_transcript, text_out) if sample.reference_transcript else None,
            "DER": calculate_der(sample.reference_speaker_turns,
                [{"speaker": s["speaker_label"], "start_time": s["start_time_ms"]/1000,
                  "end_time": s["end_time_ms"]/1000} for s in readback["database_segments"]],
                collar_seconds=0.25) if sample.reference_speaker_turns else None,
            "DER_protocol": {"implementation": "ABCI-MI 10ms discretized Hungarian matching",
                "collar_half_width_seconds": 0.25, "skip_overlap": False} if sample.reference_speaker_turns else None,
            "JER": None, "timestamp_error": None,
            "unverified_metrics_reason": "Metrics without matched ground truth remain null; JER not implemented; timestamp metric not validated",
            "reference_transcript": sample.reference_transcript, "predicted_transcript": text_out,
            "final_segments": len(readback["database_segments"]), "fresh_readback": True,
            "qdrant_readback": readback["qdrant_ids_match"], "status": "VERIFIED SAMPLE; NOT DATASET-WIDE",
            "evidence_folder": str(sample_folder.relative_to(ROOT)),
            "gpu_readback_snapshot": readback.get("gpu_after_readback"),
            "correlation_id": readback["pipeline"]["body"].get("provenance", {}).get("correlation_id"),
            "event_id": job["result"].get("event_id"), "ace_status": job["result"].get("ace_status")}
        metrics.update(moss_generation_seconds=sum(moss_times) if moss_times else None,
            pyannote_inference_seconds=sum(pyannote_times) if pyannote_times else None,
            chunk_count=asr_metadata.get("chunk_count"), cpu_peak_memory="NOT AVAILABLE")
        save(sample_folder / "metrics.json", metrics)
        if metrics_target != sample_folder / "metrics.json":
            metrics["successful_attempt_artifact"] = str(sample_folder.relative_to(ROOT))
            save(metrics_target, metrics)
        results.append(metrics)
        report = ROOT / "benchmark results" / folder.name / sample.sample_id
        report.mkdir(parents=True, exist_ok=True)
        if report / "metrics.json" != metrics_target and not (report / "metrics.json").exists():
            save(report / "metrics.json", metrics)
        with (ROOT / "e2e_validation/execution_log.md").open("a", encoding="utf-8") as log:
            log.write(f"\n- REAL benchmark {folder.name}/{sample.sample_id}: meeting {record['meeting_id']}, canonical {readback['canonical_transcript_id']}, job {job['id']}; {metrics['final_segments']} segments; fresh PostgreSQL/API/Qdrant readback passed. WER={metrics['WER']}, CER={metrics['CER']}, DER={metrics['DER']}, RTF={metrics['RTF']}. Evidence: {metrics['evidence_folder']}.\n")
        print(json.dumps({k: metrics[k] for k in ("benchmark_sample_id", "status", "RTF", "WER", "CER")}), flush=True)
    aggregates = {}
    for name, count_key in (("WER", "ref_word_count"), ("CER", "ref_char_count")):
        values = [r[name] for r in results if r.get(name)]
        denominator = sum(v[count_key] for v in values)
        errors = sum(v["substitutions"] + v["deletions"] + v["insertions"] for v in values)
        aggregates["micro_" + name] = errors / denominator if denominator else None
    total_duration = sum(r["duration_seconds"] for r in results)
    aggregates["overall_RTF"] = sum(r["processing_seconds"] for r in results)/total_duration if total_duration else None
    save(folder / ("summary_" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + ".json"),
        {"benchmark_run_id": folder.name, "dataset": args.dataset, "language": args.language, "completed_samples": len(results),
         "scope": "Per-language local pilot; samples not statistically representative", "aggregates": aggregates, "results": results})

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", choices=["fleurs", "indicsuperb", "voxconverse", "ami"], required=True)
    parser.add_argument("--language", required=True)
    parser.add_argument("--samples", type=int, default=10)
    parser.add_argument("--run", type=Path)
    parser.add_argument("--retry-failed", action="store_true", help="New attempt only for a saved explicitly failed sample; preserve earlier evidence")
    args = parser.parse_args()
    if not 1 <= args.samples <= 50: parser.error("Bounded evaluation supports 1–50 samples per group")
    asyncio.run(main(args))
