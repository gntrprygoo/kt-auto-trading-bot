param(
    [switch]$Force
)

$ErrorActionPreference = "Stop"
$ProjectDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ExamplePath = Join-Path $ProjectDir "config.example.json"
$ConfigPath = Join-Path $ProjectDir "config.json"

if ((Test-Path $ConfigPath) -and -not $Force) {
    Write-Host "config.json sudah ada." -ForegroundColor Yellow
    Write-Host "Gunakan: .\setup_config.ps1 -Force  untuk membuat ulang."
    exit 0
}

if (-not (Test-Path $ExamplePath)) {
    throw "config.example.json tidak ditemukan."
}

$cfg = Get-Content -Raw -LiteralPath $ExamplePath | ConvertFrom-Json

Write-Host ""
Write-Host "KT Auto Trading Bot - Setup Config" -ForegroundColor Cyan
Write-Host "Isi data berikut. Tekan Enter untuk memakai default yang sudah ada."
Write-Host ""

$botToken = Read-Host "Telegram Bot Token"
if ($botToken) {
    $cfg.telegram.bot_token = $botToken
}

$chatId = Read-Host "Telegram Chat ID [$($cfg.telegram.chat_id)]"
if ($chatId) {
    $cfg.telegram.chat_id = $chatId
}

$apiKey = Read-Host "Binance API Key"
if ($apiKey) {
    $cfg.binance.api_key = $apiKey
}

$apiSecret = Read-Host "Binance API Secret"
if ($apiSecret) {
    $cfg.binance.api_secret = $apiSecret
}

$notional = Read-Host "Notional per trade USDT [$($cfg.risk.fixed_notional_usdt)]"
if ($notional) {
    $cfg.risk.fixed_notional_usdt = [double]$notional
}

$leverage = Read-Host "Leverage [$($cfg.risk.leverage)]"
if ($leverage) {
    $cfg.risk.leverage = [int]$leverage
}

$json = $cfg | ConvertTo-Json -Depth 8
$utf8NoBom = [System.Text.UTF8Encoding]::new($false)
[System.IO.File]::WriteAllText($ConfigPath, $json + [Environment]::NewLine, $utf8NoBom)

Write-Host ""
Write-Host "config.json berhasil dibuat:" -ForegroundColor Green
Write-Host $ConfigPath
Write-Host ""
Write-Host "Langkah berikutnya:"
Write-Host "  .\start_bot.ps1"
