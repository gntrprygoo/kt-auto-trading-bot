param(
    [Parameter(Mandatory=$true)]
    [ValidateSet("create", "start", "stop", "status")]
    [string]$Action,

    [Parameter(Mandatory=$true)]
    [string]$ChatId,

    [string]$ApiKey = "",
    [string]$ApiSecret = "",
    [string]$TelegramToken = "",
    [double]$Notional = 50,
    [int]$Leverage = 3,
    [int]$MaxConcurrent = 3,
    [double]$DailyLossLimitR = -3,
    [int]$RunInterval = 15,
    [int]$MaxWorkers = 8,
    [switch]$Simulate,
    [switch]$Force
)

$ErrorActionPreference = "Stop"
$ProjectDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$Manager = Join-Path $ProjectDir "tools\worker_manager.py"
$BundledPython = Join-Path $env:USERPROFILE ".cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"

if (Test-Path $BundledPython) {
    $PythonExe = $BundledPython
} else {
    $PythonExe = "python"
}

Set-Location $ProjectDir

$argsList = @($Manager, $Action, "--chat-id", $ChatId)

if ($Action -eq "create") {
    if (-not $ApiKey -or -not $ApiSecret) {
        throw "Action create membutuhkan -ApiKey dan -ApiSecret."
    }
    $argsList += @(
        "--api-key", $ApiKey,
        "--api-secret", $ApiSecret,
        "--notional", $Notional,
        "--leverage", $Leverage,
        "--max-concurrent", $MaxConcurrent,
        "--daily-loss-limit-r", $DailyLossLimitR
    )
    if ($TelegramToken) {
        $argsList += @("--telegram-token", $TelegramToken)
    }
    if ($Force) {
        $argsList += "--force"
    }
}

if ($Action -eq "start") {
    $argsList += @(
        "--run-interval", $RunInterval,
        "--max-workers", $MaxWorkers
    )
    if ($Simulate) {
        $argsList += "--simulate"
    }
}

& $PythonExe @argsList
