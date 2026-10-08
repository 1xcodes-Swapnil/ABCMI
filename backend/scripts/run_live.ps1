param(
    [ValidateSet('api', 'worker')][string]$Role = 'api',
    [string]$Python,
    [ValidateSet('all', 'chunk', 'finalize', 'batch')][string]$Kind = 'all'
)
$ErrorActionPreference = 'Stop'
$backendRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$repoRoot = (Resolve-Path (Join-Path $backendRoot '..')).Path
. (Join-Path $PSScriptRoot 'workspace_storage.ps1')
$candidates = @()
if ($Python) { $candidates += $Python }
else {
    if ($env:ABCI_PYTHON) { $candidates += $env:ABCI_PYTHON }
    $candidates += Join-Path $repoRoot '.venv\Scripts\python.exe'
    $venvConfig = Join-Path $repoRoot '.venv\pyvenv.cfg'
    if (Test-Path -LiteralPath $venvConfig) {
        $configured = Get-Content -LiteralPath $venvConfig | Where-Object { $_ -like 'executable = *' } | Select-Object -First 1
        if ($configured) { $candidates += $configured.Substring('executable = '.Length) }
    }
}
$probe = "import importlib.util; names=['fastapi','uvicorn','asyncpg','sqlalchemy','soundfile']; assert all(importlib.util.find_spec(n) for n in names)"
if ($Role -eq 'worker') {
    $probe = "import importlib.util; names=['torch','librosa','transformers','moss_transcribe_diarize','pyannote.audio','asyncpg','psycopg2','soundfile']; assert all(importlib.util.find_spec(n) for n in names)"
}
$selectedPython = $null
foreach ($candidate in $candidates | Select-Object -Unique) {
    if (Test-Path -LiteralPath $candidate) {
        & $candidate -c $probe 2>$null
        if ($LASTEXITCODE -eq 0) { $selectedPython = $candidate; break }
    }
}
if (-not $selectedPython) { throw 'No existing compatible Python found. Pass -Python with the provisioned interpreter; nothing was installed.' }
$env:EXECUTION_MODE = 'REAL'
$env:DEBUG = 'false'
$env:LOG_LEVEL = 'WARNING'
$env:HF_HUB_OFFLINE = '1'
Push-Location -LiteralPath $backendRoot
try {
    if ($Role -eq 'api') {
        & $selectedPython -m uvicorn app.main:app --host 127.0.0.1 --port 8000
    } else {
        & $selectedPython -m app.services.live_inference_worker --kind $Kind --warmup
    }
    $workerExit = $LASTEXITCODE
} finally { Pop-Location }
exit $workerExit
