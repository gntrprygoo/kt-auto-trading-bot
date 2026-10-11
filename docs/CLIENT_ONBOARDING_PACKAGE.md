# Client Onboarding Package

Dokumen ini adalah paket onboarding calon client KT Auto Trading Bot.

## Tujuan Onboarding

Membuat client bisa:

- Memahami fungsi bot.
- Setup Binance Futures dengan benar.
- Membuat API key yang aman.
- Menjalankan bot dengan config yang benar.
- Menggunakan Telegram command.
- Memahami risiko futures.
- Tahu apa yang harus dilakukan saat alert/error.

## Prinsip Keamanan API

Untuk versi publik, jangan meminta user mengirim API secret lewat chat Telegram biasa.

Alur yang lebih aman:

1. Telegram bot memberi instruksi.
2. User membuat API key di Binance.
3. User memasukkan API key ke `config.json` lokal/VPS, atau dibantu admin via sesi setup yang aman.
4. Bot melakukan `/health` untuk validasi.
5. Jika valid, bot boleh masuk simulate/real mode.

Permission API:

- Read: ON.
- Futures trading: ON.
- Withdrawal: OFF.
- IP whitelist: ON jika VPS punya IP tetap.

## Alur Onboarding Client

### Step 1: Edukasi Singkat

Kirim pesan:

```text
KT Auto Trading Bot adalah alat bantu otomasi trading berbasis rule dan risk control.
Bot tidak menjamin profit. Futures tetap berisiko tinggi.
```

### Step 2: Persetujuan Risiko

Client wajib membaca:

- `docs/RISK_DISCLOSURE.md`
- `docs/REPORT_GUIDE.md`

### Step 3: Setup Binance

Client mengikuti:

- `docs/SETUP_BINANCE_API.md`

### Step 4: Setup Bot

Client menjalankan:

```text
START_BOT.bat
```

Lalu pilih:

```text
3. Setup / update config.json
```

### Step 5: Health Check

Client kirim command:

```text
/health
```

Syarat lanjut:

- Tidak ada `FAIL`.
- Telegram token terbaca.
- Binance account OK.
- Open positions dan open orders bisa dibaca.

Jika client sudah memakai managed worker, command berikut membaca data worker pribadi client:

```text
/status
/positions
/orders
/report
/weekly
/monthly
/alltime
/risk
```

### Step 6: Simulate Mode

Jalankan simulate mode minimal 24 jam untuk client baru.

### Step 7: Real Mode Kecil

Mulai real mode dengan notional kecil. Naikkan hanya setelah user paham command dan risiko.

## Command Yang Diajarkan Ke Client

```text
/health
/status
/positions
/orders
/report
/weekly
/monthly
/alltime
/pause
/resume
/risk
/help
```

## Pesan Siap Pakai Untuk Client

```text
Selamat datang di KT Auto Trading Bot.

Sebelum real mode, kita akan lakukan:
1. Setup Binance Futures.
2. Buat API key tanpa withdrawal permission.
3. Setup config bot.
4. Cek /health.
5. Jalankan simulate mode.
6. Baru real mode kecil jika semua aman.

Bot ini bukan jaminan profit. Semua risiko trading tetap menjadi tanggung jawab pengguna.
```

## Checklist Admin Sebelum Aktivasi

- Client memahami risiko.
- API withdrawal OFF.
- Config sudah lengkap.
- `/health` OK.
- `/status` OK.
- `/positions` bisa dibaca.
- `/orders` bisa dibaca.
- Client tahu cara `/pause`.
- Client tahu emergency manual di Binance.

## Model Distribusi Awal

Rekomendasi fase awal:

- Slot terbatas.
- Setup dibantu admin.
- Subscription bulanan, bukan lifetime.
- Support via Telegram group/private.
- Track record weekly/monthly dipublikasikan transparan.
