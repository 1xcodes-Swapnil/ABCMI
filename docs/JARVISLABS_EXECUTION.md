# JarvisLabs execution of the existing application

## Resume the existing instance and reopen localhost — start here

Updated **20 October 2026**. These instructions describe the existing installation,
not a fresh installation. **Do not reinstall dependencies, reclone over the current
source, replace `.env`, redownload models, or upload the same audio again.**

The last confirmed address was `217.18.55.36`. It can change after resume. Copy
the **current SSH address from your JarvisLabs instance page** each time.

### 1. Resume the same instance

1. In JarvisLabs, resume the instance containing your existing `/home` files.
2. Wait until it shows **Running** and copy its current SSH command/address.
3. Use that address below. Creating another instance does not restore the old
   instance's source, environment, models, uploads or chunk checkpoints.

### 2. Connect from Windows PowerShell

Run locally on the laptop:

```powershell
Set-Location -LiteralPath 'F:\abci-mi-backend-&-application (6)'
$JarvisHost = Read-Host 'Current JarvisLabs IPv4 address only, without root@'
ssh -o StrictHostKeyChecking=accept-new -o UserKnownHostsFile=.runtime/ssh/jarvislabs_known_hosts -i .runtime/ssh/jarvislabs_ed25519 "root@$JarvisHost"
```

If asked for a **key passphrase**, enter the passphrase you chose when creating
the SSH key. This is different from the app sign-in password. Do not paste either
into chat. If your key is already unlocked in `ssh-agent`, no passphrase is needed.

If SSH says **REMOTE HOST IDENTIFICATION HAS CHANGED**, do not disable checking.
Confirm the address in your instance page. Where available, compare the presented
fingerprint with this command in the trusted JarvisLabs browser terminal:

```bash
ssh-keygen -lf /etc/ssh/ssh_host_ed25519_key.pub
```

Only after confirming the expected instance/key, remove the **one outdated entry**
in local PowerShell and reconnect:

```powershell
ssh-keygen -R $JarvisHost -f .runtime/ssh/jarvislabs_known_hosts
```

If the fingerprint cannot be confirmed, stop and resolve it through JarvisLabs.
Do not clear all known hosts or replace private keys.

### 3. Start the remote app services

**Paste the next block in the remote SSH terminal, not local PowerShell.** It
starts missing services only, retains sign-in and existing configuration, appends
logs, and detaches processes so they survive closing SSH or this chat. It does not
load models, download anything or submit an audio test. The worker can process
already queued jobs; do not submit duplicate attempts.

```bash
/home/abci-runtime/venv/bin/python - <<'PY'
import json, os, socket, subprocess
from pathlib import Path

root = Path('/home/abci-mi')
runtime = Path('/home/abci-runtime')
python = runtime / 'venv/bin/python'
node = runtime / 'node-v22.23.3-linux-x64/bin/node'
for required in (root/'backend/.env', python, node, root/'node_modules/vite/bin/vite.js'):
    if not required.exists():
        raise SystemExit('Existing installation is incomplete: ' + str(required))

def listening(port):
    with socket.socket() as connection:
        connection.settimeout(0.3)
        return connection.connect_ex(('127.0.0.1', port)) == 0

def worker_pids():
    found = []
    for entry in Path('/proc').iterdir():
        if not entry.name.isdigit():
            continue
        try:
            argv = (entry/'cmdline').read_bytes().split(b'\0')
            if argv[1:3] == [b'-m', b'app.services.live_inference_worker']:
                found.append(int(entry.name))
        except (FileNotFoundError, PermissionError, ProcessLookupError):
            pass
    return found

logs = runtime / 'logs'
logs.mkdir(parents=True, exist_ok=True)
environment = os.environ.copy()
environment.update(HF_HUB_OFFLINE='1', TRANSFORMERS_OFFLINE='1',
                   PYTHONUNBUFFERED='1', VITE_PROXY_TARGET='http://127.0.0.1:8000')
environment['PATH'] = str(node.parent) + os.pathsep + environment.get('PATH', '')
services = [
    ('api', [str(python), '-m', 'uvicorn', 'app.main:app', '--host', '127.0.0.1', '--port', '8000'], root/'backend', 8000),
    ('frontend', [str(node), str(root/'node_modules/vite/bin/vite.js'), '--host', '127.0.0.1', '--port', '3000'], root, 3000),
    ('worker', [str(python), '-m', 'app.services.live_inference_worker', '--kind', 'all'], root/'backend', None),
]
result = {}
for name, arguments, cwd, port in services:
    if port and listening(port):
        result[name] = {'status': 'ALREADY LISTENING — verify health below'}
        continue
    existing = worker_pids() if name == 'worker' else []
    if existing:
        result[name] = {'status': 'ALREADY RUNNING', 'pids': existing}
        continue
    with (logs/(name+'.log')).open('ab') as log:
        process = subprocess.Popen(arguments, cwd=cwd, env=environment,
            stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT,
            start_new_session=True)
    result[name] = {'status': 'STARTED — readiness not yet checked', 'pid': process.pid}
(runtime/'manual_services.json').write_text(json.dumps(result, indent=2))
print(json.dumps(result, indent=2))
PY
```

Wait briefly, then check **in that remote terminal**:

```bash
curl --fail --silent --show-error http://127.0.0.1:8000/api/v1/health
curl --fail --silent --show-error --output /dev/null --write-out 'Frontend HTTP %{http_code}\n' http://127.0.0.1:3000/
```

The API should respond and the frontend should return HTTP 200. A health check
proves connectivity, not transcript accuracy or completion of an audio job.
If a service fails, inspect its startup log; do not start another duplicate:

```bash
tail -n 60 /home/abci-runtime/logs/api.log
tail -n 60 /home/abci-runtime/logs/worker.log
tail -n 60 /home/abci-runtime/logs/frontend.log
```

Only missing services started by the block write to these log files. If it reused
earlier processes, their logs can be `/home/abci-runtime/api_vad_20261020.log`,
`worker_vad_20261020.log` and `frontend_vad_20261020.log` instead. Do not share raw
configuration or logs containing credentials. Do not kill an active worker to
apply a source change; first inspect its job state.

### 4. Open the localhost tunnel in a SECOND PowerShell window

Keep this new window open while using the app. It is a **local laptop terminal**:

```powershell
Set-Location -LiteralPath 'F:\abci-mi-backend-&-application (6)'
$JarvisHost = Read-Host 'Current JarvisLabs IPv4 address only, without root@'
ssh -N -o ExitOnForwardFailure=yes -o ServerAliveInterval=30 -o ServerAliveCountMax=3 -o StrictHostKeyChecking=accept-new -o UserKnownHostsFile=.runtime/ssh/jarvislabs_known_hosts -i .runtime/ssh/jarvislabs_ed25519 -L 127.0.0.1:3001:127.0.0.1:3000 -L 127.0.0.1:8001:127.0.0.1:8000 "root@$JarvisHost"
```

**A blank terminal after connecting is normal.** `-N` forwards ports without
opening a remote shell. Do not close it; use another window for other commands.
Relative key/known-host paths are intentional: the project directory contains
spaces and `&`, and a previous background launch failed on absolute-path quoting.

### 5. Open and sign in

- Application: **http://127.0.0.1:3001/**
- API health: **http://127.0.0.1:8001/api/v1/health**
- Sign in with your existing app account. This is not the JarvisLabs/SSH password.
- A page left open from an old connection may need a refresh and sign-in again.
- Select the existing meeting to inspect progress/results. Do not upload it again
  merely because the browser disconnected. Retry a failed attempt only after its
  actual failure has been inspected; preserved chunk checkpoints may be reusable.

### Troubleshooting connection failures

| Symptom | Action |
|---|---|
| SSH timeout | Check Running status and the current address; an old address can belong to another instance. |
| `Permission denied (publickey)` | Use the existing private key above and confirm its matching public key is registered in JarvisLabs. Never upload the private key. |
| `Address already in use` / forward failure | Inspect the existing local tunnel below. Reuse it if it targets the current address; do not run competing tunnels. |
| UI opens but says `Failed to fetch` | Verify remote API health and BOTH port forwards; ensure the current frontend proxies to remote API port 8000. |
| Tunnel says `connect failed: Connection refused` | SSH works, but the remote API/frontend is not listening. Return to step 3. |
| Browser cannot open localhost | Keep the tunnel window open; verify local health in another PowerShell window. |
| `code_switch_intelligence` / MOSS error after upload | This is a processing failure, not an SSH problem. Preserve the meeting/attempt IDs and inspect its saved stage error. |

Local diagnostics (PowerShell):

```powershell
Get-NetTCPConnection -State Listen -LocalPort 3001,8001 -ErrorAction SilentlyContinue | Select-Object LocalPort,OwningProcess
Get-Process ssh -ErrorAction SilentlyContinue | Select-Object Id,StartTime
Invoke-WebRequest -Uri 'http://127.0.0.1:8001/api/v1/health' -UseBasicParsing -TimeoutSec 10
```

If you own the old foreground tunnel, press **Ctrl+C in its window**, then repeat
step 4 with the current address. For a background tunnel, identify its recorded
PID and command first; do not stop all `ssh` processes. Recent local records are
under `.runtime/ssh/tunnel*.json` with associated `.log` files.

### What happens when this chat or connection stops?

| Event | Effect |
|---|---|
| Codex reaches a usage limit / chat ends | Detached remote services and submitted jobs do not depend on the chat staying open. Pending fixes are not automatically deployed. |
| Remote SSH shell closes | Services started by step 3 continue while the instance remains running. |
| Local tunnel closes / laptop sleeps | Localhost becomes unavailable; remote uploaded-file processing can continue. Reopen the tunnel. Live microphone capture cannot continue from a sleeping laptop. |
| Instance pauses / loses runtime | Processes stop. After resume, repeat steps 1–5. Stored files/checkpoints are not the same as a running worker; interrupted jobs may need an inspected explicit retry. |
| Instance is deleted / replaced | Do not assume the old files are available on the new machine. Save source, uploads, evidence and checkpoints before deletion. |

### Existing installation locations

| Item | Location |
|---|---|
| Source and frontend | `/home/abci-mi` |
| Python environment | `/home/abci-runtime/venv/bin/python` |
| Node executable | `/home/abci-runtime/node-v22.23.3-linux-x64/bin/node` |
| Private configuration | `/home/abci-mi/backend/.env` — do not print/share |
| Cached models | `/home/hf-cache/hub` |
| Uploads | Existing `AUDIO_STORAGE_PATH` (currently `/home/abci-data/audio`) |
| Audio checkpoints | Existing `AUDIO_CHUNK_STATE_DIR` (currently `/home/abci-data/chunk-state`) |
| Worker attempt journals | `AUDIO_STORAGE_PATH/live-results` |
| Validation evidence | `/home/abci-mi/e2e_validation` |
| Saved benchmark/run results | `/home/abci-mi/benchmark results` |
| Laptop copies/results | `F:\abci-mi-backend-&-application (6)\benchmark results` |

## Fresh installation / deployment reference — not the resume procedure

Deployment preparation is not proof of remote execution or long-audio accuracy.
Actual short checks were performed on the existing L4 installation; GPU capacity
does not establish accuracy. Keep existing files under the configured `/home`
paths; after a pause we have reused these files, but restarted the processes.
Keep sign-in. This installation uses existing reachable PostgreSQL/Redis/Qdrant;
the resume procedure does not create replacement services or depend on Docker.
Official references: https://docs.jarvislabs.ai/ and https://docs.jarvislabs.ai/ssh

## Source and dependencies

Transfer the current release archive and unpack it under `/home/abci-mi`.
The archive includes local fixes absent from HEAD, with a source SHA-256 manifest.
It excludes credentials, recordings, caches, previous evidence and logs.
Run `bash backend/scripts/setup_jarvislabs.sh` from this source directory.
The installer constrains torch/torchaudio to the template's CUDA versions, installs
the existing adapter pins, and applies the existing version-checked PyAnnote patch.
It does not start inference, provision models, run migrations or create infrastructure.
Dependency downloads and Linux compatibility must be checked on the instance.

## Private configuration

Create `backend/.env` privately on the instance using the existing configured credentials
and an existing authorized identity. Never upload the laptop `.env` unchanged:
Windows paths and laptop localhost service addresses are invalid on the instance.

For a fresh installation only, the most recent experimental remote profile used
these non-secret values. **Do not overwrite an existing `.env` from this block.**
The 20s/4s profile has short-run evidence, not long-audio accuracy acceptance.

```dotenv
EXECUTION_MODE=REAL
ENVIRONMENT=production
DEBUG=false
ALLOW_TEST_TOKENS=false
ABCI_RUNTIME_ROOT=/home/abci-runtime
AUDIO_STORAGE_PATH=/home/abci-data/audio
AUDIO_CHUNK_STATE_DIR=/home/abci-data/chunk-state
OPENMOSS_DEVICE=cuda
OPENMOSS_PRECISION=bf16
OPENMOSS_MAX_NEW_TOKENS=1024
OPENMOSS_MODEL_ID=OpenMOSS-Team/MOSS-Transcribe-Diarize
OPENMOSS_CACHE_DIR=/home/hf-cache/hub
HF_HOME=/home/hf-cache
HUGGINGFACE_HUB_CACHE=/home/hf-cache/hub
AUDIO_CHUNK_DURATION_SECONDS=20
AUDIO_CHUNK_OVERLAP_SECONDS=4
AUDIO_CHUNK_THRESHOLD_SECONDS=20
AUDIO_CHUNK_CONCURRENCY=1
PYANNOTE_WINDOW_SECONDS=30
PYANNOTE_WINDOW_OVERLAP_SECONDS=5
TEXT_AI_PROVIDER=gemini
```

Supply privately: `HF_TOKEN`, `DATABASE_URL_ASYNC`, `DATABASE_URL_SYNC`,
`REDIS_URL`, `QDRANT_URL`, the required service API key, `GEMINI_API_KEY`, and
the existing JWT signing secret. Preserve the configured Gemini model. Set
`ABCI_USER_ID` and `ABCI_TENANT_ID` for the validation CLI in its environment.
Use reachable existing PostgreSQL/Redis/Qdrant services; no duplicate services,
fixture identities, SQLite, fake vectors or authentication bypass.

Transfer only the complete required model snapshots and corresponding refs from
the existing F: cache: MOSS, Sarvam, PyAnnote diarization/segmentation/speaker
embedding, and MiniLM semantic embedding. Dereference snapshot symlinks when
transferring, or include their referenced blobs. Do not transfer HF token files.
Check cache inventory before any inference; missing files are a blocker.
Keep HF_HUB_OFFLINE=1 and TRANSFORMERS_OFFLINE=1 after transfer.
The laptop's 8s/3s NF4 profile is separate from this experimental remote profile.
Neither is a guarantee for arbitrary recordings. Longer chunks require an actual capacity probe; do not bypass the
resource admission gate or advertise real-time throughput without measuring it.

## Required instance gates

1. Verify CUDA, dependency imports, persistent paths, disk, model inventory and
   all existing services using `backend/scripts/kaggle_real_runner.py` diagnostics
   and services stages with a new evidence directory under `/home`.
2. Perform one short REAL provider/production check to catch driver/model/API
   failures before committing paid compute to a long recording. Do not repeat
   prior local recordings as an accuracy claim.
3. Start the API bound to 127.0.0.1:8000 and the existing worker, then the UI with
   VITE_PROXY_TARGET=http://127.0.0.1:8000. Use an SSH tunnel for UI port 3000;
   no public anonymous backend is required. Use the account-protected template
   interface or the SSH tunnel, retaining ABCMI sign-in.
4. Sign in, upload the actual long recording to a new meeting, then Process
   uploaded audio. Files larger than the configured 500 MiB upload ceiling must
   receive a measured size-specific configuration change, not silent truncation.
5. Save chunks, generation evidence, reconciliation, timestamps, dedup decisions,
   PostgreSQL commit/fresh readback and actual job state. Stop on the first failed
   gate; resume the existing job/chunk state instead of resubmitting completed work.

Bounded text extraction now processes complete source turns sequentially and
validates citations independently per window. Window summaries are explicitly
scoped; they are not a verified whole-meeting synthesis. An oversized individual
turn or provider failure still fails explicitly, while the transcript recovery
path preserves successful audio output. Fresh multi-window Gemini generation,
long speaker accuracy, all UI features and 150/180-minute completion remain
unverified until executed. Pause the instance to stop compute billing; storage
billing continues. Download results before deleting the instance.
