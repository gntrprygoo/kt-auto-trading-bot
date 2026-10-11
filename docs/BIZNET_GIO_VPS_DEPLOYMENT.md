# Biznet Gio VPS Deployment

## VPS

- Provider: Biznet Gio
- Product: NEO Lite SS 2.1
- OS: Ubuntu 22.04
- IP: 203.0.113.10
- App user: `kulitrader`
- App directory: `/opt/kt-auto-trading-bot`

## Login SSH Dari Windows

```powershell
ssh kulitrader@203.0.113.10
```

Jika login pertama kali bertanya fingerprint, ketik:

```text
yes
```

## Upload Project Dari Windows

Jalankan dari PowerShell di laptop:

```powershell
cd "C:\Users\YOUR_WINDOWS_USER\OneDrive\Dokumen\KT Auto trading bot"
scp -r .\v3_swing_bot_fixed.py .\config.json .\deploy .\tools .\docs kulitrader@203.0.113.10:/tmp/kt-bot-upload
```

Lalu login SSH dan pindahkan ke folder production:

```bash
sudo mkdir -p /opt/kt-auto-trading-bot
sudo chown -R kulitrader:kulitrader /opt/kt-auto-trading-bot
rsync -av /tmp/kt-bot-upload/ /opt/kt-auto-trading-bot/
```

## Sesuaikan Path Linux Di Config

Di VPS, edit:

```bash
nano /opt/kt-auto-trading-bot/config.json
```

Ganti semua path Windows menjadi path Linux:

```json
"paths": {
  "journal_path": "/opt/kt-auto-trading-bot/data/journal_v3.json",
  "log_path": "/opt/kt-auto-trading-bot/logs/scan_v3.log",
  "log_max_bytes": 10485760,
  "log_rotate_keep": 2,
  "report_state_path": "/opt/kt-auto-trading-bot/data/daily_report_state_v3.json",
  "heartbeat_path": "/opt/kt-auto-trading-bot/data/heartbeat_v3.txt",
  "user_registry_path": "/opt/kt-auto-trading-bot/data/user_registry_v1.json",
  "breakout_state_path": "/opt/kt-auto-trading-bot/data/breakout_state_v3.json",
  "shadow_trades_path": "/opt/kt-auto-trading-bot/data/shadow_trades_v3.json",
  "journal_backup_dir": "/opt/kt-auto-trading-bot/data/backups"
}
```

## Install Service

```bash
cd /opt/kt-auto-trading-bot
bash deploy/install_ubuntu.sh
```

## Start Bot

```bash
sudo systemctl start kt-auto-trading-bot
sudo systemctl status kt-auto-trading-bot
```

Live log:

```bash
journalctl -u kt-auto-trading-bot -f
```

Stop bot:

```bash
sudo systemctl stop kt-auto-trading-bot
```

Restart bot:

```bash
sudo systemctl restart kt-auto-trading-bot
```

## Telegram Check

Setelah service jalan, cek dari Telegram:

```text
/health
/status
/positions
/shadow
```

## Binance API

Setelah bot sudah stabil di VPS, update whitelist Binance API ke IP VPS:

```text
203.0.113.10
```

Withdrawal permission harus tetap OFF.
