[CmdletBinding()]
param(
    [string]$Model = "gpt-5.6-luna",
    [ValidateRange(1, 8)]
    [int]$Workers = 2,
    [string]$PythonPath = ""
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$Audit = Join-Path $Root ".audit\2026-08-05-hybrid-ai"
$Source = Join-Path $Root ".audit\2026-08-04-strategy-f"
$CacheRoot = Join-Path $Root ".audit\2026-07-22"
$MarketCache = Join-Path $Source "market_cache_official"

if (-not $PythonPath) {
    $BundledPython = Join-Path $env:USERPROFILE ".cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
    if (Test-Path -LiteralPath $BundledPython) {
        $PythonPath = $BundledPython
    } else {
        $PythonPath = (Get-Command python -ErrorAction Stop).Source
    }
}

if (-not $env:OPENAI_API_KEY) {
    throw "OPENAI_API_KEY belum tersedia di environment PowerShell."
}

New-Item -ItemType Directory -Force -Path $Audit | Out-Null
$Replay = Join-Path $Root "tools\historical_ai_replay.py"
$Evaluate = Join-Path $Root "tools\evaluate_hybrid_ai_gate.py"
$Cache = Join-Path $Audit "openai_replay_cache.jsonl"
$Smoke = Join-Path $Audit "openai_smoke.json"
$Development = Join-Path $Audit "openai_development.json"
$Validation = Join-Path $Audit "openai_validation.json"
$Gate = Join-Path $Audit "hybrid_ai_live_gate.json"

Write-Host "[1/4] One-event API/model/schema smoke (no orders)"
& $PythonPath $Replay `
    --input (Join-Path $Source "f2_development.json") `
    --stage development `
    --cache-root $CacheRoot `
    --extra-cache $MarketCache `
    --output $Smoke `
    --cache $Cache `
    --provider openai `
    --model $Model `
    --reasoning-effort low `
    --workers 1 `
    --max-events 1
if ($LASTEXITCODE -ne 0) {
    throw "Smoke OpenAI gagal. Full replay tidak dijalankan; periksa $Smoke."
}

Write-Host "[2/4] Development replay (cache-resumable, no orders)"
& $PythonPath $Replay `
    --input (Join-Path $Source "f2_development.json") `
    --stage development `
    --cache-root $CacheRoot `
    --extra-cache $MarketCache `
    --output $Development `
    --cache $Cache `
    --provider openai `
    --model $Model `
    --reasoning-effort low `
    --workers $Workers `
    --sleep-ms 100
if ($LASTEXITCODE -ne 0) {
    throw "Development replay gagal. Periksa error pada $Development dan cache $Cache."
}

$DevelopmentResult = Get-Content -LiteralPath $Development -Raw | ConvertFrom-Json
if (-not $DevelopmentResult.summary.gate.passed) {
    Write-Host "Development gate FAILED. Validation tetap disegel dan AI_LIVE tetap LOCKED."
    exit 2
}

Write-Host "[3/4] Validation replay (frozen settings)"
& $PythonPath $Replay `
    --input (Join-Path $Source "f2r_validation.json") `
    --stage validation `
    --cache-root $CacheRoot `
    --extra-cache $MarketCache `
    --output $Validation `
    --cache $Cache `
    --provider openai `
    --model $Model `
    --reasoning-effort low `
    --workers $Workers `
    --sleep-ms 100
if ($LASTEXITCODE -ne 0) {
    throw "Validation replay gagal. AI_LIVE tetap LOCKED."
}

Write-Host "[4/4] Building immutable live-gate artifact"
& $PythonPath $Evaluate --development $Development --validation $Validation --output $Gate
$GateExit = $LASTEXITCODE
Write-Host "Gate artifact: $Gate"
exit $GateExit
