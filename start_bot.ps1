param(
    [ValidateSet("menu", "simulate", "real")]
    [string]$Mode = "menu",
    [int]$RunInterval = 15,
    [int]$MaxWorkers = 8
)

$ErrorActionPreference = "Stop"
$ProjectDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ConfigPath = Join-Path $ProjectDir "config.json"
$SimScript = Join-Path $ProjectDir "run_simulate.ps1"
$RealScript = Join-Path $ProjectDir "run_real.ps1"
$SetupScript = Join-Path $ProjectDir "setup_config.ps1"

Set-Location $ProjectDir

function Show-Header {
    Clear-Host
    Write-Host "KT Auto Trading Bot" -ForegroundColor Cyan
    Write-Host "===================" -ForegroundColor Cyan
    Write-Host ""
}

function Test-ConfigReady {
    if (-not (Test-Path $ConfigPath)) {
        return $false
    }

    $cfg = Get-Content -Raw -LiteralPath $ConfigPath | ConvertFrom-Json
    return (
        -not [string]::IsNullOrWhiteSpace($cfg.telegram.bot_token) -and
        -not [string]::IsNullOrWhiteSpace($cfg.telegram.chat_id) -and
        -not [string]::IsNullOrWhiteSpace($cfg.binance.api_key) -and
        -not [string]::IsNullOrWhiteSpace($cfg.binance.api_secret)
    )
}

function Start-Simulate {
    & $SimScript -RunInterval $RunInterval -MaxWorkers $MaxWorkers
}

function Start-Real {
    if (-not (Test-ConfigReady)) {
        Write-Host ""
        Write-Host "config.json belum lengkap. Jalankan setup dulu." -ForegroundColor Yellow
        Write-Host ""
        & $SetupScript
        if (-not (Test-ConfigReady)) {
            Write-Host "Config masih belum lengkap. Real mode dibatalkan." -ForegroundColor Red
            exit 1
        }
    }

    Write-Host ""
    Write-Host "PERINGATAN: Real mode akan mengirim order ke Binance Futures." -ForegroundColor Yellow
    $confirm = Read-Host "Ketik REAL untuk lanjut"
    if ($confirm -ne "REAL") {
        Write-Host "Real mode dibatalkan."
        exit 0
    }

    & $RealScript -RunInterval $RunInterval -MaxWorkers $MaxWorkers
}

if ($Mode -eq "simulate") {
    Start-Simulate
    exit $LASTEXITCODE
}

if ($Mode -eq "real") {
    Start-Real
    exit $LASTEXITCODE
}

while ($true) {
    Show-Header
    Write-Host "1. Run SIMULATE / dry-run"
    Write-Host "2. Run REAL trading"
    Write-Host "3. Setup / update config.json"
    Write-Host "4. Buka folder project"
    Write-Host "5. Keluar"
    Write-Host ""
    $choice = Read-Host "Pilih menu"

    switch ($choice) {
        "1" { Start-Simulate; break }
        "2" { Start-Real; break }
        "3" { & $SetupScript -Force; Read-Host "Tekan Enter untuk kembali ke menu" }
        "4" { Invoke-Item $ProjectDir }
        "5" { exit 0 }
        default {
            Write-Host "Pilihan tidak dikenal." -ForegroundColor Yellow
            Start-Sleep -Seconds 1
        }
    }
}
