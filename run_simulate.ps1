param(
    [int]$RunInterval = 15,
    [int]$MaxWorkers = 8
)

$ErrorActionPreference = "Stop"
$ProjectDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$BotScript = Join-Path $ProjectDir "v3_swing_bot_fixed.py"
$BundledPython = Join-Path $env:USERPROFILE ".cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"

if (Test-Path $BundledPython) {
    $PythonExe = $BundledPython
} else {
    $PythonExe = "python"
}

Set-Location $ProjectDir
& $PythonExe $BotScript --simulate --run-interval $RunInterval --max-workers $MaxWorkers
