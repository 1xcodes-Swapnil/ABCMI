[CmdletBinding()]
param(
    [string]$OutputDir = (Join-Path (Resolve-Path (Join-Path $PSScriptRoot "..\..")) "data\audio\raw")
)

$ErrorActionPreference = "Stop"
$BaseUrl = "https://groups.inf.ed.ac.uk/ami/AMICorpusMirror/amicorpus/HeadsetAudio"

# AMI meeting IDs you want.
# Add/remove meetings as needed.
$Meetings = @(
    "ES2002a","ES2002b","ES2002c","ES2002d",
    "ES2003a",
    "ES2004a","ES2004b","ES2004c","ES2004d",
    "ES2014a","ES2014b","ES2014c","ES2014d"
)

New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null

foreach ($Meeting in $Meetings) {

    $FileName = "$Meeting.Mix-Headset.wav"
    $Url = "$BaseUrl/$FileName"
    $Destination = Join-Path $OutputDir $FileName

    if (Test-Path $Destination) {
        Write-Host "[SKIP] $FileName already exists"
        continue
    }

    Write-Host "[DOWNLOAD] $FileName"

    try {
        Invoke-WebRequest `
            -Uri $Url `
            -OutFile $Destination `
            -UseBasicParsing

        Write-Host "[OK] $FileName"
    }
    catch {
        Write-Host "[FAILED] $FileName"
        Write-Host $_.Exception.Message
    }
}