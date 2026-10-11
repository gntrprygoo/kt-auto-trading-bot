# KT Auto Trading Bot

Telegram-based Binance Futures trading assistant with rule-based risk control.

Bot ini ditujukan sebagai alat bantu otomasi trading berbasis rule, bukan jaminan profit dan bukan nasihat keuangan. Fokus utama produk adalah disiplin eksekusi, kontrol risiko, transparansi posisi, dan report performa melalui Telegram.

## Status Project

Versi kerja saat ini:

- Core bot: `v3_swing_bot_fixed.py`
- Strategy base: V7.4 Swing Bot
- Sizing: fixed notional per trade
- Trade management: TP1 1R, TP2 2R, breakeven setelah TP1
- Interface: Telegram command dan notification
- Exchange: Binance Futures

## Fitur Utama

- Dynamic pair universe berdasarkan volume Binance Futures.
- Fixed notional sizing agar ukuran posisi konsisten.
- Dual TP: TP1 untuk booking profit, TP2 untuk target lanjut.
- Breakeven SL otomatis setelah TP1.
- Daily report dan all-time report.
- Startup reconciliation dengan Binance.
- Audit posisi live tanpa SL.
- Audit orphan SL/TP order.
- Journal backup otomatis sebelum sync.
- Telegram command:
  - `/register`
  - `/myaccount`
  - `/license`
  - `/onboarding`
  - `/status`
  - `/health`
  - `/positions`
  - `/orders`
  - `/report`
  - `/weekly`
  - `/monthly`
  - `/alltime`
  - `/pause`
  - `/resume`
  - `/risk`
  - `/ai_status`
  - `/ai_market` (admin, live shadow only)
  - `/ai_pending`
  - `/ai_mode shadow|approval|live` (admin)
  - `/ai_approve ID` dan `/ai_reject ID` (admin)
  - `/help`
  - admin-only registry commands

## Cara Paling Mudah Menjalankan

Double-click:

```text
START_BOT.bat
```

Lalu pilih menu:

1. Simulate / dry-run.
2. Real trading.
3. Setup config.

Alternatif dari PowerShell:

```powershell
.\start_bot.ps1
```

## Setup Awal

1. Buat `config.json` dari `config.example.json`.
2. Isi:
   - Telegram bot token.
   - Telegram chat ID.
   - Binance API key.
   - Binance API secret.
3. Cara termudah membuat config:

```powershell
.\setup_config.ps1
```

4. Jalankan simulate mode terlebih dahulu:

```powershell
.\run_simulate.ps1
```

5. Jika sudah yakin, jalankan real mode:

```powershell
.\run_real.ps1
```

## File Penting

- `v3_swing_bot_fixed.py`: script utama bot.
- `config.example.json`: contoh konfigurasi.
- `start_bot.ps1`: menu launcher utama.
- `START_BOT.bat`: launcher double-click.
- `setup_config.ps1`: wizard sederhana untuk membuat `config.json`.
- `run_simulate.ps1`: launcher dry-run/simulate.
- `run_real.ps1`: launcher real trading.
- `docs\SETUP_BINANCE_API.md`: panduan setup API Binance.
- `docs\REPORT_GUIDE.md`: panduan membaca report.
- `docs\RISK_DISCLOSURE.md`: disclaimer dan risiko.
- `docs\BETA_READINESS_CHECKLIST.md`: checklist kesiapan private beta.
- `docs\BETA_TESTER_ONBOARDING.md`: onboarding beta tester.
- `docs\CLIENT_ONBOARDING_PACKAGE.md`: paket onboarding calon client.
- `docs\PUBLIC_TELEGRAM_ONBOARDING_FLOW.md`: flow onboarding Telegram publik yang aman.
- `docs\MOBILE_ONLY_PUBLIC_PRODUCT_ARCHITECTURE.md`: arsitektur produk untuk user mobile-only.
- `docs\PUBLIC_ROADMAP_NEXT_PHASE.md`: roadmap fase publik berikutnya.
- `docs\SEMI_SAAS_ADMIN_COMMANDS.md`: command registry/license/admin Semi-SaaS.
- `docs\MANAGED_WORKER_RUNBOOK.md`: cara membuat dan menjalankan worker per user.
- `docs\BUG_REPORT_TEMPLATE.md`: template laporan bug.
- `docs\ROADMAP_STATUS.md`: status roadmap profesional.
- `docs\HYBRID_AI_TRADING_ENGINE_SPEC_2026-08-05.md`: kontrak dan safety gate Hybrid AI.
- `docs\HYBRID_AI_RUNBOOK.md`: replay, deployment, dan operasi Hybrid AI.
- `docs\AI_MARKET_SCANNER_RESEARCH_RUNBOOK.md`: riset prompt scanner pasar
  independen, dataset, biaya, dan promotion gate.
- `docs\AI_MARKET_SCANNER_PROMPT_RESEARCH_RESULT_2026-08-06.md`: hasil final
  turnamen prompt-only V1/V2 dan keputusan penolakan.
- `docs\LIVE_AI_MARKET_SHADOW.md`: operasi analyzer OpenAI pada data Binance
  live, batas credential, biaya cadence, deployment, dan command Telegram.
- `hybrid_ai_engine.py`: reviewer AI, state proposal, risk gateway, dan live lock.
- `ai_market_scanner.py`: client scanner pasar OpenAI dengan output JSON ketat.
- `ai_range_setup.py`: kontrak P6, schema setup lengkap, dan validator level/R:R.
- `range_setup_shadow.py`: lifecycle setup P6 berbasis candle terkonfirmasi.
- `live_ai_market.py`: snapshot Binance live, setup P6, dan state shadow-only.
- `tools\historical_ai_replay.py`: replay AI tanpa look-ahead dan tanpa order.
- `tools\run_ai_market_prompt_research.ps1`: runner turnamen prompt direct scanner.
- `CHANGELOG.md`: catatan perubahan versi.

## Rekomendasi Penggunaan

- Selalu mulai dengan simulate mode.
- Gunakan notional kecil pada real mode awal.
- Jangan matikan audit SL.
- Jangan cancel orphan order tanpa cek posisi Binance lebih dulu.
- Simpan config dan API key hanya di mesin pribadi/VPS yang aman.

## Disclaimer

Trading futures memiliki risiko tinggi dan bisa menyebabkan kerugian modal. Bot ini tidak menjamin profit. Semua keputusan dan risiko penggunaan menjadi tanggung jawab pengguna.
