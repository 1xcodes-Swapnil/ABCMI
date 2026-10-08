# Dot-source before launching Python/Node so temporary files also stay on the project drive.
$workspaceRoot = (Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
$runtimeRoot = Join-Path $workspaceRoot '.runtime'
$paths = @{
    TEMP = 'tmp'; TMP = 'tmp'; TMPDIR = 'tmp'
    XDG_CACHE_HOME = 'cache'; TORCH_HOME = 'cache/torch'
    NUMBA_CACHE_DIR = 'cache/numba'; MPLCONFIGDIR = 'cache/matplotlib'
    PIP_CACHE_DIR = 'cache/pip'; npm_config_cache = 'cache/npm'
    CUDA_CACHE_PATH = 'cache/cuda'; HF_MODULES_CACHE = 'cache/huggingface/modules'
}
foreach ($key in $paths.Keys) {
    $directory = Join-Path $runtimeRoot $paths[$key]
    New-Item -ItemType Directory -Path $directory -Force | Out-Null
    [Environment]::SetEnvironmentVariable($key, $directory, 'Process')
}
$env:ABCI_RUNTIME_ROOT = $runtimeRoot
$env:PYTHONNOUSERSITE = '1'
$localPython = Join-Path $runtimeRoot 'python/python.exe'
if (Test-Path -LiteralPath $localPython) { $env:ABCI_PYTHON = $localPython }
