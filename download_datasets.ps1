# ==============================================================================
# ABCI-MI Benchmark Dataset Downloader (PowerShell for Windows)
# ==============================================================================
[CmdletBinding()]
param(
    [string]$Dataset = "all",
    [int]$Samples = 5,
    [string]$OutputDir = "$PSScriptRoot\data\benchmarks",
    [switch]$VerifyOnly,
    [switch]$Offline,
    [switch]$Force
)

$ErrorActionPreference = "Stop"

Write-Host "==================================================================" -ForegroundColor Cyan
Write-Host " ABCI-MI: Benchmark Datasets Setup & Local Cache Provisioning" -ForegroundColor Cyan
Write-Host "==================================================================" -ForegroundColor Cyan

$ScriptPath = Join-Path $PSScriptRoot "backend\scripts\download_benchmark_datasets.py"

$ArgsList = @(
    $ScriptPath,
    "--dataset", $Dataset,
    "--samples", $Samples,
    "--output-dir", $OutputDir
)

if ($VerifyOnly) {
    $ArgsList += "--verify-only"
}
if ($Offline) {
    $ArgsList += "--offline"
}
if ($Force) {
    $ArgsList += "--force"
}

python @ArgsList

Write-Host ""
Write-Host "Datasets ready at: $OutputDir" -ForegroundColor Green
Write-Host "Run benchmarks with:" -ForegroundColor Yellow
Write-Host "  python backend\cli.py benchmark run ami --samples 3" -ForegroundColor Yellow
Write-Host "  python backend\cli.py benchmark run-all" -ForegroundColor Yellow
Write-Host "==================================================================" -ForegroundColor Cyan
