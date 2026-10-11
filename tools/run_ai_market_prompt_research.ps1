[CmdletBinding()]
param(
    [string]$Model = "gpt-5.6-luna",
    [ValidateRange(1, 4)]
    [int]$Workers = 2,
    [ValidateRange(100, 2000)]
    [int]$DevelopmentSnapshots = 240,
    [ValidateRange(100, 2000)]
    [int]$ValidationSnapshots = 240,
    [string]$PythonPath = ""
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$Audit = Join-Path $Root ".audit\2026-08-05-ai-market-scanner"
$MarketCache = Join-Path $Root ".audit\2026-08-04-strategy-f\market_cache_official"
$Builder = Join-Path $Root "tools\build_ai_market_dataset.py"
$Replay = Join-Path $Root "tools\replay_ai_market_prompts.py"
$Selector = Join-Path $Root "tools\select_ai_market_prompt.py"

if (-not $PythonPath) {
    $BundledPython = Join-Path $env:USERPROFILE ".cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
    if (Test-Path -LiteralPath $BundledPython) {
        $PythonPath = $BundledPython
    } else {
        $PythonPath = (Get-Command python -ErrorAction Stop).Source
    }
}

if ([string]::IsNullOrWhiteSpace([Environment]::GetEnvironmentVariable("OPENAI_API_KEY", "Process"))) {
    throw "OPENAI_API_KEY belum tersedia pada process environment PowerShell."
}

New-Item -ItemType Directory -Force -Path $Audit | Out-Null
$DevelopmentDataset = Join-Path $Audit "market_development.json"
$ValidationDataset = Join-Path $Audit "market_validation.json"
$Cache = Join-Path $Audit "openai_market_prompt_cache.jsonl"
$Smoke = Join-Path $Audit "openai_market_prompt_v2_smoke.json"
$Development = Join-Path $Audit "openai_market_prompt_v2_development.json"
$DevelopmentGate = Join-Path $Audit "development_prompt_v2_gate.json"
$Validation = Join-Path $Audit "openai_market_prompt_v2_validation.json"
$FinalGate = Join-Path $Audit "ai_market_prompt_v2_gate.json"
$Prompts = @("P4_LONG_REGIME_PULLBACK", "P5_BALANCED_TREND_CONTINUATION", "P6_RANGE_ABSORPTION_REVERSAL")

Write-Host "[1/7] Building outcome-independent development snapshots"
& $PythonPath $Builder `
    --market-cache $MarketCache `
    --output $DevelopmentDataset `
    --stage development `
    --start 2021-07-01 `
    --end 2023-12-31 `
    --interval-hours 1 `
    --max-snapshots $DevelopmentSnapshots
if ($LASTEXITCODE -ne 0) { throw "Development dataset build failed." }

Write-Host "[2/7] Building sealed unseen-validation snapshots"
& $PythonPath $Builder `
    --market-cache $MarketCache `
    --output $ValidationDataset `
    --stage validation `
    --start 2024-01-01 `
    --end 2024-10-31 `
    --interval-hours 1 `
    --max-snapshots $ValidationSnapshots
if ($LASTEXITCODE -ne 0) { throw "Validation dataset build failed." }

Write-Host "[3/7] One-snapshot API/schema/quota smoke; fail-fast after first fatal error"
& $PythonPath $Replay `
    --dataset $DevelopmentDataset `
    --output $Smoke `
    --cache $Cache `
    --stage development `
    --prompts $Prompts `
    --model $Model `
    --workers 1 `
    --max-output-tokens 1200 `
    --min-confidence 0.60 `
    --min-quality 60 `
    --max-snapshots 1
if ($LASTEXITCODE -ne 0) {
    throw "OpenAI smoke failed. Tournament stopped before bulk API spend. Inspect $Smoke"
}

Write-Host "[4/7] Development prompt tournament"
& $PythonPath $Replay `
    --dataset $DevelopmentDataset `
    --output $Development `
    --cache $Cache `
    --stage development `
    --prompts $Prompts `
    --model $Model `
    --workers $Workers `
    --max-output-tokens 1200 `
    --min-confidence 0.60 `
    --min-quality 60
if ($LASTEXITCODE -ne 0) { throw "Development replay failed. Inspect $Development" }

Write-Host "[5/7] Selecting a development winner without forcing one"
& $PythonPath $Selector --development $Development --output $DevelopmentGate
if ($LASTEXITCODE -ne 0) {
    Write-Host "No development prompt passed. Validation remains sealed; AI_SIGNAL stays disabled."
    exit 2
}
$Gate = Get-Content -Raw -LiteralPath $DevelopmentGate | ConvertFrom-Json
$Winner = [string]$Gate.winner.prompt_id

Write-Host "[6/7] Frozen-winner unseen validation: $Winner"
& $PythonPath $Replay `
    --dataset $ValidationDataset `
    --output $Validation `
    --cache $Cache `
    --stage validation `
    --prompts $Winner `
    --model $Model `
    --workers $Workers `
    --max-output-tokens 1200 `
    --min-confidence 0.60 `
    --min-quality 60
if ($LASTEXITCODE -ne 0) { throw "Validation replay failed. AI_SIGNAL stays disabled." }

Write-Host "[7/7] Building historical eligibility artifact"
& $PythonPath $Selector `
    --development $Development `
    --validation $Validation `
    --output $FinalGate
exit $LASTEXITCODE
