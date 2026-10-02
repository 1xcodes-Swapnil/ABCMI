"""Observe existing REAL production CLI; persist evidence without replacing inference."""
import argparse
import asyncio
import contextlib
import hashlib
import json
import logging
import os
from pathlib import Path
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "backend"))
os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["TRANSFORMERS_OFFLINE"] = "1"
from app.core.config import get_settings

def now():
    return datetime.now(timezone.utc).isoformat()

def save(path, value):
    path.write_text(json.dumps(value, indent=2, default=str), encoding="utf-8")

def append_log(text):
    with (REPO / "e2e_validation/execution_log.md").open("a", encoding="utf-8") as f:
        f.write(text + "\n")

def prepare():
    import soundfile as sf
    settings = get_settings()
    if settings.EXECUTION_MODE.upper() != "REAL":
        raise RuntimeError("Phase 1 requires REAL mode")
    if not settings.OPENMOSS_DEVICE.startswith("cuda"):
        raise RuntimeError("Phase 1 requires configured CUDA; CPU fallback forbidden")
    duration = settings.AUDIO_CHUNK_DURATION_SECONDS
    overlap = settings.AUDIO_CHUNK_OVERLAP_SECONDS
    threshold = settings.AUDIO_CHUNK_THRESHOLD_SECONDS
    if not 0 < overlap < duration:
        raise RuntimeError("Invalid configured overlap")
    base = REPO / "e2e_validation"
    for folder in ("runs", "artifacts", "diagnostics"):
        (base / folder).mkdir(parents=True, exist_ok=True)
    checkpoint = base / "CHECKPOINT.md"
    if not checkpoint.exists():
        checkpoint.write_text("# Execution checkpoint\n\nPrior evidence: real_local/CHECKPOINT.md and real_local/FINAL_REPORT.md.\n", encoding="utf-8")
    if not (base / "execution_log.md").exists():
        (base / "execution_log.md").write_text("# Execution log\n\nPrevious evidence remains under real_local and local_real_20260930.\n", encoding="utf-8")
    candidates = []
    for audio in (REPO / "data/audio/raw").rglob("*"):
        if audio.suffix.lower() in (".wav", ".mp3", ".flac", ".m4a") and audio.is_file():
            info = sf.info(audio)
            if info.duration > max(duration, threshold):
                candidates.append((info.duration, audio, info))
    if not candidates:
        raise RuntimeError("No existing authorized audio produces multiple chunks under current settings")
    _, audio, info = min(candidates, key=lambda item: (item[0], item[1].stat().st_size))
    run_id = "phase1_" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ_") + uuid.uuid4().hex[:12]
    run = base / "runs" / run_id
    run.mkdir()
    digest = hashlib.sha256()
    with audio.open("rb") as f:
        for data in iter(lambda: f.read(1024*1024), b""):
            digest.update(data)
    coverage = []
    start = 0.0
    while start < info.duration:
        end = min(start+duration, info.duration)
        coverage.append([start, end])
        if end == info.duration:
            break
        start += duration-overlap
    preflight = {"run_id": run_id, "timestamp": now(), "phase": 1,
        "status": "PREPARED", "execution_mode": "REAL", "audio_path": str(audio),
        "audio_filename": audio.name, "audio_sha256": digest.hexdigest(),
        "audio_size": audio.stat().st_size, "audio_duration": info.duration,
        "sample_rate": info.samplerate, "channels": info.channels,
        "chunk_duration": duration, "overlap": overlap, "step": duration-overlap,
        "threshold": threshold, "concurrency": settings.AUDIO_CHUNK_CONCURRENCY,
        "coverage": coverage, "coverage_has_gaps": any(b[0]>a[1] for a,b in zip(coverage,coverage[1:])),
        "git_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO, text=True).strip()}
    save(run / "preflight.json", preflight)
    append_log(f"\n## {now()} — {run_id} — Phase 1 prepared\n- Audio: {audio.name}, {info.duration} s; SHA-256 {digest.hexdigest()}.\n- Current chunk settings: {duration}/{overlap}, step {duration-overlap}; coverage {coverage}.\n- Evidence: runs/{run_id}/preflight.json. No inference yet.")
    print(json.dumps(preflight, indent=2))
    return 0

def telemetry():
    result = {"timestamp": now()}
    try:
        import psutil
        result.update(cpu_rss_bytes=psutil.Process().memory_info().rss, ram_available_bytes=psutil.virtual_memory().available)
    except ImportError:
        result["cpu_rss_bytes"] = "NOT AVAILABLE"
    try:
        import torch
        result.update(cuda_available=torch.cuda.is_available(), gpu_allocated_bytes=torch.cuda.memory_allocated(),
                      gpu_peak_allocated_bytes=torch.cuda.max_memory_allocated())
    except Exception as exc:
        result["gpu"] = type(exc).__name__
    return result

def execute(run):
    from app import cli
    from app.ai.multilingual_asr import OpenMOSSProvider
    from app.ai.long_audio_processor import LongAudioProcessor
    from app.ai.speaker_diarization import SpeakerDiarizationEngine
    from app.events.redis_bus import RedisEventBus
    from app.services.meeting_service import MeetingService
    from app.ai.code_switch_intelligence import CodeSwitchIntelligenceEngine
    run = run.resolve()
    preflight = json.loads((run / "preflight.json").read_text())
    if (run / "execution.json").exists():
        raise RuntimeError("Run already attempted; evidence must not be overwritten")
    trace = {**preflight, "status": "RUNNING", "execution_started": now(), "telemetry": [telemetry()]}
    save(run / "execution.json", trace)
    boards, planned = [], []
    events, provider_calls = [], []
    factory = cli.get_cli_ace_orchestrator
    def observed_factory(*a, **kw):
        obj = factory(*a, **kw)
        boards.append(obj)
        return obj
    cli.get_cli_ace_orchestrator = observed_factory
    create_meeting = MeetingService.create_meeting
    async def observed_create(self, *a, **kw):
        result = await create_meeting(self, *a, **kw)
        trace.update(meeting_id=str(result.id), project_id=str(getattr(result,"project_id",None) or "NOT AVAILABLE"))
        save(run / "execution.json", trace)
        return result
    MeetingService.create_meeting = observed_create
    process = MeetingService.process_meeting
    async def observed_process(self, meeting_id, req, *a, **kw):
        trace["processing_request"] = req.model_dump(mode="json")
        trace["correlation_id"] = str(req.correlation_id or "NOT AVAILABLE")
        save(run / "execution.json", trace)
        return await process(self, meeting_id, req, *a, **kw)
    MeetingService.process_meeting = observed_process
    plan = LongAudioProcessor.plan_chunks
    def observed_plan(self, *a, **kw):
        result = plan(self, *a, **kw)
        planned.extend(result)
        save(run / "chunks.json", [c.model_dump(mode="json") for c in planned])
        return result
    LongAudioProcessor.plan_chunks = observed_plan
    transcribe = OpenMOSSProvider.transcribe
    async def observed_moss(self, path, options=None):
        index = len(provider_calls)
        entry = {"call_index": index, "timestamp": now(), "status": "RUNNING"}
        provider_calls.append(entry)
        chunk = (options or {}).get("chunk_meta")
        if chunk:
            entry["chunk"] = chunk.model_dump(mode="json")
        save(run / "moss_calls.json", provider_calls)
        self.last_raw_output, self.last_inference = None, {}
        started = time.perf_counter()
        try:
            result = await transcribe(self, path, options)
            entry.update(status="COMPLETED", segments=[s.model_dump(mode="json") for s in result])
            return result
        except Exception as exc:
            entry.update(status="FAILED", error=cli.sanitize_error_text(str(exc)))
            raise
        finally:
            entry.update(elapsed_seconds=time.perf_counter()-started, diagnostics=self.last_inference,
                         raw_output=self.last_raw_output if self.last_raw_output is not None else "NOT AVAILABLE")
            trace["telemetry"].append(telemetry())
            save(run / "moss_calls.json", provider_calls)
            save(run / "execution.json", trace)
    OpenMOSSProvider.transcribe = observed_moss
    diarize = SpeakerDiarizationEngine.diarize_audio
    async def observed_diarize(self, *a, **kw):
        started = time.perf_counter()
        try:
            result = await diarize(self, *a, **kw)
            save(run / "pyannote.json", {"status":"COMPLETED", "elapsed_seconds":time.perf_counter()-started,
                                         "output":result.model_dump(mode="json")})
            return result
        except Exception as exc:
            save(run / "pyannote.json", {"status":"FAILED", "elapsed_seconds":time.perf_counter()-started,
                                         "error":cli.sanitize_error_text(str(exc))})
            raise
    SpeakerDiarizationEngine.diarize_audio = observed_diarize
    normalize = CodeSwitchIntelligenceEngine.map_to_canonical
    normalizations = []
    async def observed_normalize(self, text):
        started = time.perf_counter()
        record = {"input_text": text, "timestamp": now()}
        normalizations.append(record)
        try:
            output = await normalize(self, text)
            record.update(status="COMPLETED", output=output,
                raw_completion=getattr(self, "last_raw_completion", None),
                inference=dict(getattr(self, "last_inference", {})))
            return output
        except Exception as exc:
            record.update(status="FAILED", error=cli.sanitize_error_text(str(exc)))
            raise
        finally:
            record["elapsed_seconds"] = time.perf_counter() - started
            save(run / "sarvam_calls.json", normalizations)
    CodeSwitchIntelligenceEngine.map_to_canonical = observed_normalize
    reconcile = LongAudioProcessor.reconcile_speakers_across_chunks
    def observed_reconcile(self, chunk_results, *a, **kw):
        result = reconcile(self, chunk_results, *a, **kw)
        save(run / "speaker_reconciliation.json", {"inputs":[{"chunk":m.model_dump(mode="json"),
             "global_segments":[s.model_dump(mode="json") for s in ss]} for m,ss in chunk_results],
             "mapping":result[1], "output":[[s.model_dump(mode="json") for s in ss] for ss in result[0]]})
        return result
    LongAudioProcessor.reconcile_speakers_across_chunks = observed_reconcile
    dedup = LongAudioProcessor.merge_and_deduplicate_chunks
    def observed_dedup(self, chunk_metas, reconciled_chunks):
        result = dedup(self, chunk_metas, reconciled_chunks)
        kept = {str(s.segment_id) for s in result[0]}
        save(run / "deduplication.json", {"explicit_duplicate_removals":result[1],
            "decisions":[{"segment":s.model_dump(mode="json"), "retained":str(s.segment_id) in kept}
                         for ss in reconciled_chunks for s in ss],
            "final_segments":[s.model_dump(mode="json") for s in result[0]]})
        return result
    LongAudioProcessor.merge_and_deduplicate_chunks = observed_dedup
    publish = RedisEventBus.publish_with_status
    async def observed_publish(self, channel, event):
        result = await publish(self, channel, event)
        data = event.model_dump(mode="json") if hasattr(event,"model_dump") else event
        events.append({"timestamp":now(), "channel":channel, "delivery_status":result.value, "event":data})
        save(run / "redis_events.json", events)
        return result
    RedisEventBus.publish_with_status = observed_publish
    pipeline = cli.execute_cli_pipeline
    async def observed_pipeline(*a, **kw):
        result = await pipeline(*a, **kw)
        save(run / "cli_result.json", result)
        trace.update(cli_status=result["status"], final_segment_count=result["transcript_count"])
        return result
    cli.execute_cli_pipeline = observed_pipeline
    settings = get_settings()
    secrets = [v for k,v in settings.model_dump().items() if isinstance(v,str) and v and
               any(x in k for x in ("TOKEN","PASSWORD","SECRET","URL","API_KEY"))]
    class SafeLog:
        def __init__(self, file): self.file=file
        def write(self, text):
            for secret in secrets: text=text.replace(secret,"[REDACTED]")
            self.file.write(cli.sanitize_error_text(text)); self.file.flush()
        def flush(self): self.file.flush()
        def isatty(self): return False
    started = time.perf_counter()
    streams=[]
    with (run / "cli.log").open("w",encoding="utf-8") as f:
        log=SafeLog(f)
        for logger in [logging.getLogger(), *[x for x in logging.Logger.manager.loggerDict.values() if isinstance(x,logging.Logger)]]:
            for handler in logger.handlers:
                if isinstance(handler,logging.StreamHandler) and not isinstance(handler,logging.FileHandler):
                    try:
                        prior_stream=handler.stream
                        handler.setStream(log)
                    except AttributeError:
                        # Python's _StderrHandler follows redirected sys.stderr
                        # and exposes a read-only stream property.
                        continue
                    streams.append((handler,prior_stream))
        sys.argv=["abcimi","--title",preflight.get("title","Phase 1 REAL multi-chunk production")]
        if preflight.get("resume_meeting_id"):
            sys.argv += ["--meeting-id",preflight["resume_meeting_id"]]
        else:
            sys.argv += ["--file",preflight["audio_path"]]
        if preflight.get("cli_user_id"):
            sys.argv += ["--user-id",preflight["cli_user_id"]]
        if preflight.get("cli_tenant_id"):
            sys.argv += ["--tenant-id",preflight["cli_tenant_id"]]
        try:
            with contextlib.redirect_stdout(log), contextlib.redirect_stderr(log):
                try:
                    cli.main(); trace["cli_exit_code"]=0
                except SystemExit as exc:
                    trace["cli_exit_code"]=exc.code
                    if exc.code: raise RuntimeError(f"Existing CLI exited {exc.code}")
            trace["status"]="PRODUCTION_COMPLETED" if trace.get("final_segment_count",0)>0 else "NOT VERIFIED"
        except Exception as exc:
            trace.update(status="NOT VERIFIED", error=cli.sanitize_error_text(str(exc)))
        finally:
            for handler,stream in streams: handler.setStream(stream)
            trace.update(processing_seconds=time.perf_counter()-started, execution_finished=now())
            trace["telemetry"].append(telemetry())
            tasks=[]
            for orchestrator in boards:
                for board in orchestrator.blackboards.values():
                    trace["blackboard_execution_state"]=board.execution_state
                    for task in board.list_tasks():
                        tasks.append(task.model_dump(mode="json"))
            first_failed=next((task for task in tasks if task.get("status")=="FAILED"),None)
            if first_failed:
                trace["first_failed_capability"]=first_failed.get("required_capability")
                trace["first_failure"]=first_failed.get("metadata",{}).get("error_message")
            save(run / "blackboard_tasks.json", tasks)
            save(run / "chunks.json", [c.model_dump(mode="json") for c in planned])
            save(run / "execution.json", trace)
    append_log(f"\n## {now()} — {preflight['run_id']} — Phase 1 execution\n- State: {trace['status']}; CLI exit {trace.get('cli_exit_code','NOT AVAILABLE')}.\n- Meeting: {trace.get('meeting_id','NOT AVAILABLE')}; correlation: {trace.get('correlation_id','NOT AVAILABLE')}.\n- Duration: {trace['processing_seconds']} s. Evidence: runs/{preflight['run_id']}/execution.json and associated artifacts. Fresh-process read-back pending.")
    print(json.dumps({k:v for k,v in trace.items() if k not in ("blackboard_execution_state","processing_request")},indent=2))
    return 0 if trace["status"]=="PRODUCTION_COMPLETED" else 1

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--prepare",action="store_true")
    parser.add_argument("--run",type=Path)
    parser.add_argument("--retry-from",type=Path)
    parser.add_argument("--failure",default="Evidence recorder AttributeError before CLI/model execution; fixed factory reference")
    args=parser.parse_args()
    if args.retry_from:
        prior=json.loads((args.retry_from/"preflight.json").read_text())
        previous=json.loads((args.retry_from/"execution.json").read_text())
        previous.update(status="BLOCKED",error=args.failure,execution_finished=now())
        save(args.retry_from/"execution.json",previous)
        append_log(f"\n## {now()} — {prior['run_id']} — recorder failure\n- No production CLI or inference ran. {args.failure}. Evidence retained.\n")
        run_id="phase1_"+datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ_")+uuid.uuid4().hex[:12]
        run=REPO/"e2e_validation/runs"/run_id
        run.mkdir()
        prior.update(run_id=run_id,timestamp=now(),retry_of=previous['run_id'])
        save(run/"preflight.json",prior)
        print(str(run))
        return 0
    return prepare() if args.prepare else execute(args.run)

if __name__=="__main__":
    sys.exit(main())
