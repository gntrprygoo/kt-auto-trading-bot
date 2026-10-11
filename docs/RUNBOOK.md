# Runbook Operasional

Dokumen ini berisi langkah praktis menjalankan dan memantau KT Auto Trading Bot.

## Start Simulate Mode

Cara paling mudah:

```text
Double-click START_BOT.bat
```

Lalu pilih menu simulate.

Atau dari PowerShell:

```powershell
cd "C:\Users\YOUR_WINDOWS_USER\OneDrive\Dokumen\KT Auto trading bot"
.\run_simulate.ps1
```

## Start Real Mode

Pastikan `config.json` sudah berisi Telegram token, chat ID, Binance API key, dan Binance API secret.

Cara paling mudah:

```text
Double-click START_BOT.bat
```

Lalu pilih menu real trading.

Atau dari PowerShell:

```powershell
cd "C:\Users\YOUR_WINDOWS_USER\OneDrive\Dokumen\KT Auto trading bot"
.\run_real.ps1
```

## Stop Bot

Di terminal tempat bot berjalan, tekan:

```text
Ctrl + C
```

Tunggu sampai muncul pesan bot stopped.

## Command Telegram Harian

Gunakan:

```text
/status
/positions
/orders
/report
/risk
```

Jika ingin menghentikan entry baru tanpa mematikan bot:

```text
/pause
```

Untuk mengaktifkan lagi:

```text
/resume
```

## Jika Ada Alert Posisi Tanpa SL

1. Buka Binance Futures.
2. Cek pair yang disebutkan.
3. Pastikan posisi punya SL aktif.
4. Jika tidak punya SL, pasang SL manual atau close posisi sesuai keputusan risiko.
5. Jangan tunggu cycle bot berikutnya untuk posisi yang berisiko.

## Jika Ada Alert Orphan Order

1. Buka Binance Futures.
2. Cek Open Orders atau Conditional Orders.
3. Cocokkan dengan posisi live.
4. Jika order tidak terkait posisi mana pun, cancel manual.
5. Jika masih terkait posisi, jangan cancel.

## Backup Journal

Bot membuat backup journal sebelum sync besar ke folder:

```text
C:\Users\YOUR_WINDOWS_USER\.openclaw\workspace\backups
```

Gunakan backup ini jika perlu audit atau recovery manual.
