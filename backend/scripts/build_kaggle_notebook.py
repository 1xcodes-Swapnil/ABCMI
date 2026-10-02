"""Build one self-contained Kaggle notebook around the existing backend CLI."""
import ast
import base64
import hashlib
import io
import json
from pathlib import Path
import re
import subprocess
import textwrap
import uuid
import zipfile

ROOT=Path(__file__).resolve().parents[2]
OUTPUT=ROOT/'notebooks/ABCI_MI_Full_Application_Kaggle_REAL.ipynb'
cells=[]
def markdown(text):
    cells.append({'cell_type':'markdown','id':uuid.uuid4().hex[:8],'metadata':{},'source':textwrap.dedent(text).strip().splitlines(keepends=True)})
def code(text,hidden=False):
    source=textwrap.dedent(text).strip()+'\n'
    ast.parse(source)
    cells.append({'cell_type':'code','id':uuid.uuid4().hex[:8],'metadata':{'collapsed':hidden},'execution_count':None,'outputs':[],
                  'source':source.splitlines(keepends=True)})

files=list((ROOT/'backend/app').rglob('*.py'))
files += [ROOT/'backend'/name for name in ('__init__.py','cli.py','requirements.txt','requirements-real.txt')]
files += [ROOT/'backend/scripts'/name for name in ('kaggle_real_runner.py','validate_phase1.py',
    'readback_phase1.py','provision_real_models.py','patch_pyannote_407.py')]
commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
manifest={}
buffer=io.BytesIO()
with zipfile.ZipFile(buffer,'w',zipfile.ZIP_DEFLATED) as archive:
    for path in sorted(set(files)):
        if not path.exists() or '__pycache__' in path.parts: continue
        data=path.read_bytes()
        if re.search(rb'hf_[A-Za-z0-9]{20,}|sk-[A-Za-z0-9]{25,}',data):
            raise RuntimeError('Secret-like literal detected in source; refusing to embed '+str(path.relative_to(ROOT)))
        relative=path.relative_to(ROOT).as_posix()
        manifest[relative]=hashlib.sha256(data).hexdigest()
        entry=zipfile.ZipInfo(relative,date_time=(2026,10,2,0,0,0))
        entry.compress_type=zipfile.ZIP_DEFLATED
        archive.writestr(entry,data)
bundle=buffer.getvalue()
bundle_hash=hashlib.sha256(bundle).hexdigest()

markdown('''
# ABCI-MI — Full-Application Kaggle REAL Execution

This notebook runs the **existing backend production CLI**: meeting service →
LongAudioProcessor/MOSS → PyAnnote/Sarvam → reconstruction → ACE/Blackboard →
SKW/PostgreSQL/Redis/Qdrant. Notebook code only configures, launches and observes
the repository. The embedded source snapshot contains current uncommitted fixes;
its archive/file SHA-256 manifest identifies the code actually executed.

**Before Run All:** enable a Kaggle GPU and Internet, attach the actual full audio
as an input, and configure Secrets `HF_TOKEN`, `DATABASE_URL_ASYNC`, `REDIS_URL`,
`QDRANT_URL` (plus `QDRANT_API_KEY`/`ABCI_USER_ID`/`ABCI_TENANT_ID` if needed).
The database must already have this repository's schema and the authorized CLI
user. PostgreSQL/Qdrant must be reachable from Kaggle. A Windows localhost URL
does not reach the laptop from Kaggle. Redis's existing fallback is reported
explicitly; it prevents a distributed-path VERIFIED classification.

Optional environment/Secret `ABCI_AUDIO_PATH` selects an existing mounted file;
otherwise ES2002a.Mix-Headset.wav is preferred, or the sole attached audio file.
Attach existing HF model caches to avoid duplicate model downloads. HF gated
model access must already be granted. Missing files alone are provisioned using
the repository's official model provisioning script. No datasets are downloaded.

No cell edits are required. Run All records BLOCKED rather than fabricating
results when prerequisites fail. The notebook is **not executed** in this saved
deliverable. Reference `sucess1.ipynb` is short Kaggle evidence, not full-application
or local validation. No tokens, original reference outputs or local .env files
are embedded. Raw real transcript evidence is saved privately under working output;
review it before sharing an executed notebook/output dataset.
''')
markdown('## 1–2. Environment and repository setup\nThe backend snapshot is embedded to preserve actual current changes. No Git credentials or local configuration are included.')
code('''
import base64, hashlib, io, json, os, re, shutil, subprocess, sys, time, uuid, zipfile
from pathlib import Path
from datetime import datetime, timezone
RUN_ID = "kaggle_real_" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ_") + uuid.uuid4().hex[:12]
WORK = Path("/kaggle/working") / RUN_ID
WORK.mkdir(parents=True, exist_ok=False)
REPO = WORK / "application"
EVIDENCE = WORK / "evidence"
EVIDENCE.mkdir()
STAGES = {}
BLOCKERS = []
def save(path, value):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    candidate = path
    version = 1
    while candidate.exists():
        candidate = path.with_name(f"{path.stem}_{version:03d}{path.suffix}")
        version += 1
    with candidate.open("x", encoding="utf-8") as f: json.dump(value, f, indent=2, default=str)
    return candidate
def redact(value):
    text = str(value)
    for key, secret in os.environ.items():
        if secret and any(x in key for x in ("TOKEN", "PASSWORD", "SECRET", "URL", "API_KEY")):
            text = text.replace(secret, "[REDACTED]")
    text = re.sub(r"hf_[A-Za-z0-9]{12,}", "[REDACTED]", text)
    return re.sub(r"(://)[^/@\\s]+:[^/@\\s]+@", r"\\1[REDACTED]@", text)
def gated(name, function, depends=()):
    if any(STAGES.get(dep, {}).get("status") != "VERIFIED" for dep in depends):
        result = {"status": "BLOCKED", "reason": "Prerequisite gate did not pass", "dependencies": list(depends)}
    else:
        try: result = function() or {"status": "VERIFIED"}
        except Exception as exc: result = {"status": "BLOCKED", "error_type": type(exc).__name__, "reason": redact(exc)}
    STAGES[name] = result
    save(EVIDENCE / f"{name}.json", result)
    if result["status"] == "BLOCKED": BLOCKERS.append({"stage": name, **result})
    print(name, result["status"])
    return result
''')
code(f'''
SOURCE_COMMIT = {commit!r}
SOURCE_ARCHIVE_SHA256 = {bundle_hash!r}
SOURCE_MANIFEST = {manifest!r}
BACKEND_SOURCE_ZIP_B64 = {base64.b64encode(bundle).decode()!r}
archive_bytes = base64.b64decode(BACKEND_SOURCE_ZIP_B64)
assert hashlib.sha256(archive_bytes).hexdigest() == SOURCE_ARCHIVE_SHA256
REPO.mkdir()
with zipfile.ZipFile(io.BytesIO(archive_bytes)) as z:
    for member in z.infolist():
        target = (REPO / member.filename).resolve()
        if not target.is_relative_to(REPO.resolve()): raise RuntimeError("Unsafe archive member")
        z.extract(member, REPO)
for relative, digest in SOURCE_MANIFEST.items():
    assert hashlib.sha256((REPO / relative).read_bytes()).hexdigest() == digest
for folder in ("runs", "artifacts", "diagnostics"):
    (REPO / "e2e_validation" / folder).mkdir(parents=True, exist_ok=True)
(REPO / "e2e_validation/execution_log.md").write_text("# Kaggle execution log\\n", encoding="utf-8")
(REPO / "e2e_validation/CHECKPOINT.md").write_text("# Kaggle checkpoint\\n", encoding="utf-8")
save(EVIDENCE / "source_manifest.json", {{"git_commit": SOURCE_COMMIT, "working_tree_snapshot": True,
    "archive_sha256": SOURCE_ARCHIVE_SHA256, "files": SOURCE_MANIFEST}})
os.environ["ABCI_SOURCE_COMMIT"] = SOURCE_COMMIT
os.environ["ABCI_SOURCE_ARCHIVE_SHA256"] = SOURCE_ARCHIVE_SHA256
print("Backend source verified:", len(SOURCE_MANIFEST), "files; commit", SOURCE_COMMIT)
''',hidden=True)
markdown('## 3. Configuration and credentials\nSecrets are retrieved at runtime. Original 600/30/1 settings remain in force until an actual OOM is recorded.')
code('''
def configure():
    try:
        from kaggle_secrets import UserSecretsClient
        secret_client = UserSecretsClient()
    except ImportError: secret_client = None
    labels = ("HF_TOKEN", "DATABASE_URL_ASYNC", "DATABASE_URL_SYNC", "REDIS_URL", "QDRANT_URL",
              "QDRANT_API_KEY", "ABCI_USER_ID", "ABCI_TENANT_ID", "ABCI_AUDIO_PATH")
    for label in labels:
        if not os.environ.get(label) and secret_client:
            try: os.environ[label] = secret_client.get_secret(label)
            except Exception: pass
    cache = WORK / "hf-cache/hub"
    cache.mkdir(parents=True, exist_ok=True)
    os.environ.update(EXECUTION_MODE="REAL", OPENMOSS_MODEL_ID="OpenMOSS-Team/MOSS-Transcribe-Diarize",
        OPENMOSS_DEVICE="cuda", OPENMOSS_CACHE_DIR=str(cache), HF_HOME=str(cache.parent),
        HF_HUB_CACHE=str(cache), HUGGINGFACE_HUB_CACHE=str(cache),
        AUDIO_CHUNK_DURATION_SECONDS="600", AUDIO_CHUNK_OVERLAP_SECONDS="30",
        AUDIO_CHUNK_THRESHOLD_SECONDS="600", AUDIO_CHUNK_CONCURRENCY="1", OPENMOSS_MAX_NEW_TOKENS="28800",
        AUDIO_CHUNK_STATE_DIR=str(WORK / "chunk-state"), AUDIO_STORAGE_PATH=str(WORK / "audio-storage"),
        DEBUG="false", ENVIRONMENT="production", LOG_LEVEL="INFO")
    os.environ.pop("TESTING", None); os.environ.pop("PYTEST_CURRENT_TEST", None)
    status = {label: "present" if os.environ.get(label) else "missing" for label in labels}
    save(EVIDENCE / "configuration_details.json", {"execution_mode": "REAL", "device": "cuda", "chunk_duration": 600,
        "overlap": 30, "concurrency": 1, "secret_presence": status})
    for label in ("HF_TOKEN", "DATABASE_URL_ASYNC", "QDRANT_URL"):
        if not os.environ.get(label): raise RuntimeError(label + " missing from environment/Kaggle Secrets")
    return {"status": "VERIFIED", "secrets": status}
gated("configuration", configure)
''')
markdown('## 4. Hardware and compatible dependency setup\nKeep Kaggle’s existing CUDA torch/torchaudio pair. A conflicting environment is BLOCKED instead of downloading replacement torch wheels. Adapter dependencies are installed into a run-specific environment; the kernel need not restart.')
code('''
def dependencies():
    import torch, importlib.metadata as md
    if not torch.cuda.is_available(): raise RuntimeError("Kaggle CUDA GPU unavailable; enable a GPU accelerator")
    gpu = torch.cuda.get_device_properties(0)
    torch_version = md.version("torch"); audio_version = md.version("torchaudio")
    if torch_version.split("+")[0] != audio_version.split("+")[0]:
        raise RuntimeError("Existing torch/torchaudio versions differ; use a compatible Kaggle runtime")
    save(EVIDENCE / "hardware.json", {"gpu": gpu.name, "vram_bytes": gpu.total_memory,
        "cuda": torch.version.cuda, "torch": torch_version, "torchaudio": audio_version,
        "python": sys.version.split()[0]})
    venv = WORK / "venv"
    proc = subprocess.run([sys.executable, "-m", "venv", "--system-site-packages", "--without-pip", str(venv)], text=True, capture_output=True)
    if proc.returncode: raise RuntimeError(redact(proc.stdout + proc.stderr))
    python = venv / "bin/python"
    proc = subprocess.run([sys.executable, "-m", "pip", "--python", str(python),
        "install", "--disable-pip-version-check", "pip", "wrapt"], text=True, capture_output=True)
    save(EVIDENCE / "venv_bootstrap.json", {"exit_code": proc.returncode,
        "stdout": redact(proc.stdout), "stderr": redact(proc.stderr)})
    if proc.returncode: raise RuntimeError("Pip bootstrap failed: " + redact(proc.stdout + proc.stderr))
    constraints = WORK / "torch-constraints.txt"
    constraints.write_text(f"torch=={torch_version}\\ntorchaudio=={audio_version}\\n")
    requirements = ["transformers==5.16.1", "accelerate==1.14.0", "safetensors==0.8.0",
        "bitsandbytes==0.50.2", "pyannote.audio==4.0.7", "av==17.1.0", "librosa>=0.11,<0.12",
        "soundfile>=0.13,<0.15", "soxr>=1,<2"]
    commands = [[str(python), "-m", "pip", "install", "--disable-pip-version-check", "-c", str(constraints),
                 "-r", str(REPO / "backend/requirements.txt"), *requirements],
                [str(python), "-m", "pip", "install", "--no-deps", "--disable-pip-version-check",
                 "moss-transcribe-diarize @ git+https://github.com/OpenMOSS/MOSS-Transcribe-Diarize.git@61bc29cd4120be7b5d3b761b64cd5dff57263642"]]
    for index, command in enumerate(commands):
        proc = subprocess.run(command, text=True, capture_output=True)
        (EVIDENCE / f"dependency_{index}.log").write_text(redact(proc.stdout + proc.stderr))
        if proc.returncode: raise RuntimeError("Compatible dependency installation failed; see saved dependency log (torch unchanged)")
    # Isolate the reproducible PyAnnote package patch inside this run's venv.
    overlay_script = """from importlib.metadata import distribution
from pathlib import Path
import shutil,sysconfig
d=distribution('pyannote.audio'); site=Path(sysconfig.get_paths()['purelib'])
for file in d.files:
 p=Path(str(file))
 if p.parts[0]=='pyannote' and len(p.parts)>1 and p.parts[1]=='audio' or p.parts[0].endswith('.dist-info'):
  src=Path(d.locate_file(file)); dst=site/p
  if src.is_file() and src.resolve()!=dst.resolve():
   dst.parent.mkdir(parents=True,exist_ok=True); shutil.copy2(src,dst)
"""
    proc = subprocess.run([str(python), "-c", overlay_script], capture_output=True, text=True)
    if proc.returncode: raise RuntimeError("Could not isolate PyAnnote compatibility package")
    proc = subprocess.run([str(python), str(REPO / "backend/scripts/patch_pyannote_407.py")], capture_output=True, text=True)
    (EVIDENCE / "pyannote_compatibility.log").write_text(redact(proc.stdout + proc.stderr))
    if proc.returncode: raise RuntimeError("Version-checked PyAnnote compatibility patch failed")
    os.environ["ABCI_PYTHON"] = str(python)
    return {"status": "VERIFIED", "torch_reused": True, "gpu": gpu.name}
gated("dependencies", dependencies, ("configuration",))
''')
markdown('## 5. Service connectivity\nUse the existing PostgreSQL, Redis, Qdrant and authorized SKW paths. No fake services, SQLite fallback or in-memory Qdrant. Database migrations are an external prerequisite; this notebook never performs destructive schema operations.')
code('''
def worker(stage, folder, extra=()):
    folder = Path(folder); folder.mkdir(parents=True, exist_ok=True)
    existing = folder / f"{stage}_stage.json"
    if existing.exists(): return json.loads(existing.read_text())
    cmd = [os.environ["ABCI_PYTHON"], str(REPO / "backend/scripts/kaggle_real_runner.py"),
           stage, "--run", str(folder), *map(str, extra)]
    started = time.perf_counter()
    proc = subprocess.run(cmd, cwd=REPO, text=True, capture_output=True)
    save(folder / f"{stage}_process.json", {"exit_code": proc.returncode, "elapsed_seconds": time.perf_counter()-started})
    (folder / f"{stage}_launcher.log").write_text(redact(proc.stdout + proc.stderr))
    if existing.exists(): return json.loads(existing.read_text())
    return {"status": "BLOCKED", "reason": "Worker failed before a structured result; see saved launcher log"}
gated("diagnostics", lambda: worker("diagnostics", EVIDENCE / "diagnostics"), ("dependencies",))
gated("services", lambda: worker("services", EVIDENCE / "services"), ("diagnostics",))
''')
markdown('## 6. Local model cache reuse and complete weight provisioning\nOnly required incomplete model repositories are provisioned. Cached snapshots are linked into a writable overlay; existing complete weights are never fetched again. HF gate failures remain BLOCKED.')
code('''
def models():
    cache = Path(os.environ["HF_HUB_CACHE"])
    mounted = Path("/kaggle/input")
    for source in mounted.rglob("models--*"):
        if not source.is_dir() or source.parent.name != "hub": continue
        for item in source.rglob("*"):
            if not item.is_file() or ".locks" in item.parts: continue
            target = cache / source.name / item.relative_to(source)
            if not target.exists():
                target.parent.mkdir(parents=True, exist_ok=True)
                target.symlink_to(item.resolve())
    check_code = "import sys,json;sys.path.insert(0,'backend');from app.ai.model_inventory import inventory;print(json.dumps(inventory()))"
    proc = subprocess.run([os.environ["ABCI_PYTHON"], "-c", check_code], cwd=REPO, capture_output=True, text=True)
    if proc.returncode: raise RuntimeError("Local model inventory failed")
    inventory = json.loads(proc.stdout)
    save(EVIDENCE / "model_inventory_before.json", inventory)
    missing = [row["model"] for row in inventory if row["required"] and row["status"] != "COMPLETE"]
    if missing:
        cmd = [os.environ["ABCI_PYTHON"], str(REPO / "backend/scripts/provision_real_models.py"),
               "--models", *missing, "--report", str(EVIDENCE / "model_provisioning.json")]
        plan_cmd = cmd + ["--dry-run"]
        # Use distinct report paths so the plan is retained.
        plan_cmd[plan_cmd.index("--report")+1] = str(EVIDENCE / "model_provisioning_plan.json")
        proc = subprocess.run(plan_cmd, cwd=REPO, text=True, capture_output=True)
        (EVIDENCE / "model_plan.log").write_text(redact(proc.stdout + proc.stderr))
        if proc.returncode: raise RuntimeError("Official cache provisioning plan blocked; check HF access and Internet")
        plan = json.loads((EVIDENCE / "model_provisioning_plan.json").read_text())
        print("Missing required model repositories:", missing)
        print("Missing artifacts only; complete cached equivalents are reused:")
        for entry in plan["models"]:
            print(json.dumps({"model": entry["model"], "download_bytes": entry["download_bytes"],
                "reuse_bytes": entry["reuse_bytes"], "destination": plan["cache"],
                "reason": "Required local snapshot incomplete"}))
        print("Download size/destination/reuse plan saved:", str(EVIDENCE / "model_provisioning_plan.json"))
        proc = subprocess.run(cmd, cwd=REPO, text=True, capture_output=True)
        (EVIDENCE / "model_provisioning.log").write_text(redact(proc.stdout + proc.stderr))
        if proc.returncode: raise RuntimeError("Required weights unavailable; see provisioning evidence; no substituted models")
    proc = subprocess.run([os.environ["ABCI_PYTHON"], "-c", check_code], cwd=REPO, capture_output=True, text=True)
    if proc.returncode: raise RuntimeError("Post-provisioning inventory failed")
    complete = json.loads(proc.stdout); save(EVIDENCE / "model_status.json", complete)
    if any(row["required"] and row["status"]!="COMPLETE" for row in complete):
        raise RuntimeError("Required model weights/shards incomplete")
    os.environ["HF_HUB_OFFLINE"] = "1"; os.environ["TRANSFORMERS_OFFLINE"] = "1"
    return {"status": "VERIFIED", "artifacts_complete": True, "inference": "NOT VERIFIED"}
gated("models", models, ("services",))
''')
markdown('## 7–8. Actual audio selection and small REAL inference\nThe smoke uses a genuine interval; it is never the final result. Audio metadata/hash are measured from the complete input file.')
code('''
AUDIO = None
def select_audio():
    global AUDIO
    explicit = os.environ.get("ABCI_AUDIO_PATH")
    paths = [Path(explicit)] if explicit else sorted(p for p in Path("/kaggle/input").rglob("*")
        if p.is_file() and p.suffix.lower() in (".wav", ".mp3", ".flac", ".m4a") and not any(x.startswith("models--") for x in p.parts))
    preferred = [p for p in paths if p.name == "ES2002a.Mix-Headset.wav"]
    if preferred: paths = preferred
    if len(paths)!=1 or not paths[0].is_file():
        raise RuntimeError("Attach one actual full audio file or set ABCI_AUDIO_PATH to the intended mounted input")
    AUDIO = paths[0].resolve()
    return {"status": "VERIFIED", "audio_filename": AUDIO.name}
gated("audio", select_audio, ("models",))
def smoke():
    start = 71 if AUDIO.name == "ES2014a.Mix-Headset.wav" else 0
    result = worker("probe", EVIDENCE / "real_smoke", ("--audio", AUDIO, "--duration", 10, "--start", start, "--all-models"))
    result["scope"] = "10-second actual provider smoke, not full production"
    return result
gated("real_smoke", smoke, ("audio",))
''')
markdown('''
## 9. Evidence-based configured chunk probe / OOM handling

First attempt the configured 600-second interval through the existing MOSS
provider. An actual CUDA OOM permits distinct smaller candidates; each executes
in a fresh process to release failed CUDA allocations. No identical failed size
is retried. Non-OOM failures stop the gate. Full audio is never truncated.
Working overlap is 30 s when valid, otherwise one fifth of chunk duration.
Both original/working settings and the reason are recorded.
''')
code('''
def choose_chunks():
    attempts = []
    for duration in (600, 300, 120, 60, 30, 15, 10):
        os.environ["OPENMOSS_MAX_NEW_TOKENS"] = str(max(5120, duration * 48))
        folder = EVIDENCE / f"chunk_probe_{duration}"
        result = worker("probe", folder, ("--audio", AUDIO, "--duration", duration))
        attempts.append({"duration": duration, "result": result, "evidence": str(folder)})
        if result["status"] == "VERIFIED":
            overlap = 30 if duration>30 else duration/5
            os.environ.update(AUDIO_CHUNK_DURATION_SECONDS=str(duration), AUDIO_CHUNK_OVERLAP_SECONDS=str(overlap),
                              AUDIO_CHUNK_THRESHOLD_SECONDS=str(duration), AUDIO_CHUNK_CONCURRENCY="1")
            choice = {"status": "VERIFIED", "configured_duration": 600, "configured_overlap": 30,
                "working_duration": duration, "working_overlap": overlap, "step": duration-overlap,
                "reason": "Configured size passed" if duration==600 else "Smaller distinct interval passed after recorded CUDA OOM",
                "attempts": attempts}
            save(EVIDENCE / "chunk_configuration.json", choice)
            print("Working chunk configuration:", duration, "seconds; overlap", overlap)
            return choice
        probe_file = folder / "probe_result.json"
        probe = json.loads(probe_file.read_text()) if probe_file.exists() else {}
        if not probe.get("oom"):
            save(EVIDENCE / "chunk_configuration.json", {"status":"BLOCKED", "attempts":attempts})
            return {"status": "BLOCKED", "reason": "Non-OOM inference failure; no configuration workaround or fallback"}
    save(EVIDENCE / "chunk_configuration.json", {"status":"BLOCKED", "attempts":attempts})
    return {"status":"BLOCKED", "reason":"No tested chunk size completed real MOSS generation"}
gated("working_chunks", choose_chunks, ("real_smoke",))
''')
markdown('''
## 10–14. Full REAL production and independent persistence read-back

The **entire original input** is passed to the existing CLI. LongAudioProcessor
plans and processes all chunks. Actual MOSS, PyAnnote, Sarvam, ACE, Blackboard,
SKW, PostgreSQL, Redis and Qdrant evidence is captured by the repository recorder.
PyAnnote retains its existing full-file pipeline; its actual observed global turns
are additionally grouped into production chunk windows, not relabelled as separate
chunk inference. Original ASR text remains canonical; normalization accuracy is unknown.

State journals retain actual completed global chunk segments, SHA-256/model/config
identity and IDs. A later explicit `ABCI_RESUME_MEETING_ID` may select the same
committed meeting via CLI; this notebook does not automatically exercise resume
or claim it verified. Existing overlap source separation remains unconfigured:
if the actual module blocks on overlapping speech, the run is BLOCKED and saved.
No fake separation/semantic output is inserted.
''')
code('''
FULL_RUN = REPO / "e2e_validation/runs" / RUN_ID
def full_production():
    extra = ["--audio", AUDIO]
    resume = os.environ.get("ABCI_RESUME_MEETING_ID")
    if resume: extra += ["--resume-meeting-id", resume]
    return worker("production", FULL_RUN, extra)
gated("full_production", full_production, ("working_chunks",))
def persistence_readback():
    if not (FULL_RUN / "execution.json").exists():
        return {"status":"BLOCKED", "reason":"No production meeting execution to read back"}
    return worker("readback", FULL_RUN)
# Read back actual storage even after a failed production attempt; do not hide absence.
gated("fresh_process_readback", persistence_readback, ("dependencies", "services"))
''')
markdown('## 15–17. Measured performance, evidence and final verification\nVERIFIED requires the entire supplied file to have actual successful chunk inference, valid reconstruction, committed canonical text, fresh-process matching read-back and existing CLI success. No ground-truth accuracy metrics are invented.')
code('''
def final_verification():
    if not (FULL_RUN / "execution.json").exists():
        return {"status":"BLOCKED", "reason":"Full production never executed"}
    return worker("report", FULL_RUN)
gated("final_verification", final_verification, ("dependencies",))
actual_path = FULL_RUN / "final_verification.json"
actual = json.loads(actual_path.read_text()) if actual_path.exists() else {}
hardware_path = EVIDENCE / "hardware.json"
hardware = json.loads(hardware_path.read_text()) if hardware_path.exists() else {}
ids = actual.get("IDS", {})
status = actual.get("STATUS", "BLOCKED")
if not actual.get("gates", {}).get("entire_audio_coverage", False): status = "BLOCKED"
final = {
    "STATUS": status, "GPU / VRAM": hardware,
    "AUDIO FILE": str(AUDIO) if AUDIO else "NOT AVAILABLE", "AUDIO DURATION": actual.get("AUDIO", {}).get("audio_duration", "NOT AVAILABLE"),
    "CHUNK CONFIGURATION": STAGES.get("working_chunks", "NOT VERIFIED"), "CHUNK COUNT": len(actual.get("CHUNKS", [])),
    "COVERAGE": actual.get("gates", {}).get("entire_audio_coverage", False), "GAPS": "See measured chunk plan; no lossless claim",
    "MOSS": actual.get("MOSS", "NOT VERIFIED"), "SARVAM": actual.get("SARVAM", "NOT VERIFIED"),
    "PYANNOTE": actual.get("PYANNOTE", "NOT VERIFIED"),
    "SPEAKER RECONCILIATION": actual.get("gates", {}).get("speaker_reconciliation", False),
    "TIMESTAMP RECONSTRUCTION": actual.get("gates", {}).get("timestamps", False),
    "DEDUPLICATION": actual.get("gates", {}).get("deduplication_executed", False),
    "ACE": actual.get("gates", {}).get("ace", False), "BLACKBOARD": "Actual saved task/event artifacts; no synthetic status",
    "SKW": "See actual committed object and Qdrant read-back artifacts" if actual else "NOT VERIFIED",
    "POSTGRESQL": actual.get("POSTGRESQL", "NOT VERIFIED"), "FRESH READ-BACK": actual.get("FRESH_READ_BACK", "NOT VERIFIED"),
    "REDIS": actual.get("REDIS", "NOT VERIFIED"), "QDRANT": actual.get("QDRANT", "NOT VERIFIED"),
    "CLI": actual.get("gates", {}).get("cli", False), "PROCESSING TIME": actual.get("PROCESSING_TIME", "NOT AVAILABLE"),
    "RTF": actual.get("RTF", "NOT AVAILABLE"), "MEETING ID": ids.get("meeting_id", "NOT AVAILABLE"),
    "TRANSCRIPT ID": ids.get("transcript_id", "NOT AVAILABLE"), "PROJECT ID": ids.get("project_id", "NOT AVAILABLE"),
    "CORRELATION ID": ids.get("correlation_ids", "NOT AVAILABLE"), "ARTIFACTS": str(WORK),
    "FAILURES": actual.get("FAILURES", BLOCKERS), "RETRIES": actual.get("RETRIES", "NOT AVAILABLE"),
    "REMAINING GAPS": actual.get("REMAINING_GAPS", ["Full production did not complete"]),
    "Resume/retry verification": "NOT VERIFIED unless actually exercised",
    "Semantic retrieval accuracy": "NOT VERIFIED", "ASR/speaker accuracy": "NOT VERIFIED without ground truth",
    "SOURCE COMMIT": SOURCE_COMMIT, "SOURCE SNAPSHOT SHA-256": SOURCE_ARCHIVE_SHA256,
}
save(EVIDENCE / "final_report.json", final)
save(EVIDENCE / "run_metadata.json", {"run_id": RUN_ID, "timestamp": datetime.now(timezone.utc).isoformat(),
    "git_commit": SOURCE_COMMIT, "source_archive_sha256": SOURCE_ARCHIVE_SHA256, "stages": STAGES})
with (REPO / "e2e_validation/execution_log.md").open("a", encoding="utf-8") as log:
    log.write("\\n## Notebook final report\\n```json\\n" + json.dumps(final, indent=2) + "\\n```\\n")
with (REPO / "e2e_validation/CHECKPOINT.md").open("a", encoding="utf-8") as checkpoint:
    checkpoint.write(f"\\nRun {RUN_ID}: {status}. Evidence: {EVIDENCE}. No accuracy or resume claim.\\n")
for name in ("execution_log.md", "CHECKPOINT.md"):
    shutil.copy2(REPO / "e2e_validation" / name, EVIDENCE / name)
shutil.make_archive(str(WORK / "execution_evidence"), "zip", root_dir=WORK,
    base_dir="evidence")
if FULL_RUN.exists(): shutil.make_archive(str(WORK / "production_evidence"), "zip", root_dir=FULL_RUN)
if (WORK / "chunk-state").exists(): shutil.make_archive(str(WORK / "chunk_state"), "zip", root_dir=WORK / "chunk-state")
# Display structural evidence only; raw transcript/model/SQL payloads stay in artifacts.
display({key: value for key, value in final.items() if key not in ("FAILURES", "CHUNK CONFIGURATION")})
print("Overall:", status)
print("Evidence directory:", WORK)
''')
markdown('''
### Interpretation and references

- A model inventory, successful import, HTTP 200 or empty artifact is not inference success.
- Timeline coverage refers to processing all real audio chunks, not proof that every word was transcribed correctly.
- Speaker mappings and overlap dedup decisions are observed algorithm outputs, not ground-truth accuracy.
- The current source-separation gate, unavailable services, gated model access, dependency conflicts,
  token-limit failures or model OOMs are recorded as actual blockers.
- Do not publish credentials or private transcript evidence with notebook output. Source code contains
  no local environment file; executed artifacts contain actual user audio/transcript data.
- Official sources: [OpenMOSS inference/API](https://github.com/OpenMOSS/MOSS-Transcribe-Diarize),
  [Kaggle Secrets](https://github.com/Kaggle/kaggle-cli/blob/main/docs/kernels.md),
  [Sarvam base model](https://huggingface.co/sarvamai/sarvam-1).
''')
notebook={'nbformat':4,'nbformat_minor':5,'metadata':{'kernelspec':{'display_name':'Python 3','language':'python','name':'python3'},
    'language_info':{'name':'python'},'abci_mi':{'source_commit':commit,'archive_sha256':bundle_hash,
    'reference_notebook':'sucess1.ipynb','execution_status':'NOT EXECUTED','full_audio_required':True}},'cells':cells}
OUTPUT.parent.mkdir(parents=True,exist_ok=True)
OUTPUT.write_text(json.dumps(notebook,indent=1),encoding='utf-8')
print(json.dumps({'notebook':str(OUTPUT),'cells':len(cells),'embedded_source_files':len(manifest),
    'source_archive_bytes':len(bundle),'source_archive_sha256':bundle_hash,'status':'BUILT; NOT EXECUTED'},indent=2))
