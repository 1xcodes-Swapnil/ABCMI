param([string]$Python, [switch]$WithWorker)
$ErrorActionPreference = 'Stop'
$backendRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$repositoryRoot = (Resolve-Path (Join-Path $backendRoot '..')).Path
. (Join-Path $PSScriptRoot 'workspace_storage.ps1')
if (-not $Python -and $env:ABCI_PYTHON) { $Python = $env:ABCI_PYTHON }
if (-not $Python) {
    $configured = Get-Content -LiteralPath (Join-Path $repositoryRoot '.venv\pyvenv.cfg') | Where-Object { $_ -like 'executable = *' } | Select-Object -First 1
    if ($configured) { $Python = $configured.Substring('executable = '.Length) }
}
if (-not $Python -or -not (Test-Path -LiteralPath $Python)) { throw 'Pass -Python with the existing provisioned Python interpreter.' }
$env:EXECUTION_MODE = 'REAL'
$env:DEBUG = 'false'
$env:LOG_LEVEL = 'WARNING'
$env:HF_HUB_OFFLINE = '1'
$evidenceRoot = Join-Path $repositoryRoot ('e2e_validation\runs\workspace_runtime_' + [DateTime]::UtcNow.ToString('yyyyMMddTHHmmssZ'))
New-Item -ItemType Directory -Path $evidenceRoot -Force | Out-Null
$processes = @()
foreach ($service in @(@{Name='api'; Port=8000}, @{Name='frontend'; Port=3000})) {
    $listener = Get-NetTCPConnection -LocalPort $service.Port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($listener) { $processes += @{service=$service.Name; pid=$listener.OwningProcess; status='existing listener; not replaced'}; continue }
    if ($service.Name -eq 'api') {
        $started = Start-Process -FilePath $Python -ArgumentList @('-m','uvicorn','app.main:app','--host','127.0.0.1','--port','8000') -WorkingDirectory $backendRoot -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $evidenceRoot 'api.stdout.log') -RedirectStandardError (Join-Path $evidenceRoot 'api.stderr.log')
    } else {
        $node = Join-Path $repositoryRoot '.runtime/node.exe'
        if (-not (Test-Path -LiteralPath $node)) { $node = (Get-Command node -ErrorAction Stop).Source }
        $vite = '"' + (Join-Path $repositoryRoot 'node_modules\vite\bin\vite.js') + '"'
        $started = Start-Process -FilePath $node -ArgumentList @($vite,'--host','127.0.0.1','--port','3000','--strictPort') -WorkingDirectory $repositoryRoot -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $evidenceRoot 'frontend.stdout.log') -RedirectStandardError (Join-Path $evidenceRoot 'frontend.stderr.log')
    }
    $processes += @{service=$service.Name; pid=$started.Id; status='started; readiness not yet checked'}
}
if ($WithWorker) {
    $existingWorker = Get-CimInstance Win32_Process | Where-Object { $_.Name -match '^python' -and $_.CommandLine -like '*app.services.live_inference_worker*' } | Select-Object -First 1
    if ($existingWorker) { $processes += @{service='worker';pid=$existingWorker.ProcessId;status='existing worker; not duplicated'} }
    else {
        $started = Start-Process -FilePath $Python -ArgumentList @('-m','app.services.live_inference_worker','--kind','all','--warmup') -WorkingDirectory $backendRoot -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $evidenceRoot 'worker.stdout.log') -RedirectStandardError (Join-Path $evidenceRoot 'worker.stderr.log')
        $processes += @{service='worker';pid=$started.Id;status='started; readiness not yet checked'}
    }
}
$processes | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $evidenceRoot 'processes.json') -Encoding utf8
$processes | ConvertTo-Json
