param(
    [string]$LogPath = "C:\Users\YOUR_WINDOWS_USER\.openclaw\workspace\scan_v3.log",
    [int]$KeepTailLines = 5000
)

if (-not (Test-Path -LiteralPath $LogPath)) {
    Write-Host "Log tidak ditemukan: $LogPath"
    exit 0
}

$dir = Split-Path -Parent $LogPath
$name = Split-Path -Leaf $LogPath
$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$archive = Join-Path $dir "$name.$stamp.bak"

Move-Item -LiteralPath $LogPath -Destination $archive

try {
    Get-Content -LiteralPath $archive -Tail $KeepTailLines | Set-Content -LiteralPath $LogPath -Encoding UTF8
    Write-Host "Log lama dipindah ke: $archive"
    Write-Host "Log aktif dibuat ulang dengan $KeepTailLines baris terakhir: $LogPath"
}
catch {
    New-Item -ItemType File -Path $LogPath -Force | Out-Null
    Write-Host "Log lama dipindah ke: $archive"
    Write-Host "Log aktif dibuat kosong karena tail gagal dibaca."
}
