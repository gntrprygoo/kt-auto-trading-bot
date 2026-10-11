# Managed Worker Runbook

Dokumen ini menjelaskan cara menjalankan worker per user untuk fase Semi-SaaS.

## Konsep

Setiap client memiliki:

- `users/<chat_id>/config.json`
- `users/<chat_id>/data/journal_v3.json`
- `users/<chat_id>/logs/scan_v3.log`
- `users/<chat_id>/worker.pid`
- proses bot sendiri

Worker client memakai config sendiri dan mengirim notifikasi ke chat ID client.

## Kenapa Command Telegram Dimatikan Di Worker?

Satu Telegram bot token tidak boleh dipolling oleh banyak proses sekaligus.

Karena itu:

- proses admin/registry boleh polling command Telegram,
- worker client hanya mengirim notifikasi/report,
- command client publik nanti diarahkan melalui backend/registry layer.

## Create Config User

```powershell
.\managed_worker.ps1 create `
  -ChatId 123456789 `
  -ApiKey "BINANCE_API_KEY" `
  -ApiSecret "BINANCE_API_SECRET" `
  -Notional 50 `
  -Leverage 3 `
  -MaxConcurrent 3
```

Jika ingin overwrite:

```powershell
.\managed_worker.ps1 create -ChatId 123456789 -ApiKey "..." -ApiSecret "..." -Force
```

## Start Worker Simulate

```powershell
.\managed_worker.ps1 start -ChatId 123456789 -Simulate
```

Setelah worker simulate aktif, user bisa cek dari Telegram:

```text
/status
/health
/positions
/report
/weekly
/monthly
/alltime
/risk
```

## Start Worker Real

```powershell
.\managed_worker.ps1 start -ChatId 123456789
```

## Check Status

```powershell
.\managed_worker.ps1 status -ChatId 123456789
```

## Stop Worker

```powershell
.\managed_worker.ps1 stop -ChatId 123456789
```

## Double-Click Wrapper

Untuk menjalankan dari CMD/batch:

```text
MANAGED_WORKER.bat status -ChatId 123456789
```

## Batasan Fase Ini

Sudah:

- Config per user.
- Journal per user.
- Log per user.
- Worker process per user.
- PID file.
- Start/stop/status worker.
- Telegram command polling disabled di worker.

Belum:

- Pause/resume worker pribadi langsung dari Telegram client.
- Secure API vault.
- Auto worker provisioning dari `/admin_approve`.
- Payment/subscription otomatis.

## Praktik Aman

- Mulai setiap user dengan `-Simulate`.
- Gunakan notional kecil.
- Jangan aktifkan withdrawal permission.
- Jangan jalankan terlalu banyak worker di laptop pribadi.
- Untuk publik serius, pindahkan worker ke VPS/server.
