"""Run one explicitly identified production job and save measured telemetry."""
import argparse
import asyncio
import contextlib
import io
import json
import os
from pathlib import Path
import sys
import threading
import time
import uuid

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
os.environ.update(EXECUTION_MODE="REAL", DEBUG="false", LOG_LEVEL="CRITICAL", HF_HUB_OFFLINE="1")


async def main(args):
    import psutil
    from app.services.live_inference_worker import LiveInferenceWorker
    from app.infrastructure.database import close_database_connections
    from app.cli import sanitize_error_text
    folder = args.run.resolve()
    if not folder.is_dir():
        raise RuntimeError("Use an existing evidence directory")
    # Exclusive files prevent an accidental repeated invocation overwriting evidence.
    with (folder / "targeted_worker.json").open("x", encoding="utf-8") as output:
        captured, stop = io.StringIO(), threading.Event()
        process, sampled_peak = psutil.Process(), [0]
        def sample():
            while not stop.is_set():
                sampled_peak[0] = max(sampled_peak[0], process.memory_info().rss)
                stop.wait(0.2)
        monitor = threading.Thread(target=sample, daemon=True)
        monitor.start()
        started = time.perf_counter()
        worker, report = None, {"job_id": str(args.job), "status": "NOT VERIFIED"}
        try:
            with contextlib.redirect_stdout(captured), contextlib.redirect_stderr(captured):
                worker = LiveInferenceWorker()
                result = await worker.run_once("batch", job_id=args.job)
                report.update(result=result, status=result["status"] if result else "IDLE")
        except Exception as exc:
            report.update(status="FAILED", error_type=type(exc).__name__, error=sanitize_error_text(str(exc)))
        finally:
            stop.set()
            monitor.join()
            report.update(elapsed_seconds=time.perf_counter()-started,
                          sampled_peak_process_rss_bytes=sampled_peak[0], rss_sample_interval_seconds=0.2)
            torch = sys.modules.get("torch")
            if torch is not None and torch.cuda.is_initialized():
                report.update(peak_cuda_allocated_bytes=torch.cuda.max_memory_allocated(),
                              peak_cuda_reserved_bytes=torch.cuda.max_memory_reserved(),
                              cuda_peak_scope="this process; allocator metrics exclude other processes")
            json.dump(report, output, indent=2, default=str)
            (folder / "targeted_worker.log").write_text(sanitize_error_text(captured.getvalue()), encoding="utf-8")
            if worker is not None:
                worker.release_models()
            await close_database_connections()
    print(json.dumps({k: report.get(k) for k in ("status", "job_id", "elapsed_seconds", "sampled_peak_process_rss_bytes", "peak_cuda_allocated_bytes", "peak_cuda_reserved_bytes")}), flush=True)
    return 0 if report["status"] == "completed" else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--job", type=uuid.UUID, required=True)
    raise SystemExit(asyncio.run(main(parser.parse_args())))
