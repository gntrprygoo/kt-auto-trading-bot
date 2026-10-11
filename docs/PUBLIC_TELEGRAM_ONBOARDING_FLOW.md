# Public Telegram Onboarding Flow

Dokumen ini menjelaskan rancangan onboarding publik melalui Telegram.

## Bisa Dibuat?

Bisa. Telegram bot bisa memandu user dari `/start` sampai siap menjalankan bot.

Namun, API secret sebaiknya tidak dikirim lewat chat Telegram biasa. Untuk public product, gunakan salah satu:

- Setup lokal melalui `config.json`.
- Setup assisted oleh admin.
- Dashboard/form terenkripsi di fase berikutnya.
- License system yang hanya mengaktifkan user, bukan menyimpan secret di chat.

## Flow Aman Versi Telegram

### `/start`

Bot menjelaskan:

- Apa itu KT Auto Trading Bot.
- Risiko futures.
- Tahapan setup.
- Command penting.

### `/onboarding`

Bot mengirim checklist:

1. Baca risk disclosure.
2. Setup Binance Futures.
3. Buat API key.
4. Jalankan setup config lokal.
5. Kirim `/health`.
6. Jalankan simulate.
7. Real mode kecil.

### `/setup_binance`

Bot memberi instruksi pembuatan API key:

- Read ON.
- Futures trading ON.
- Withdrawal OFF.
- IP whitelist jika tersedia.

### `/setup_bot`

Bot memberi instruksi:

```text
Double-click START_BOT.bat
Pilih menu 3 Setup / update config.json
Isi token/chat ID/API key/API secret di perangkat sendiri
```

### `/health`

Bot memvalidasi kesiapan teknis.

### `/risk_accept`

Untuk fase lanjutan, command ini bisa dipakai mencatat bahwa user sudah membaca disclaimer.

## Yang Jangan Dilakukan

- Jangan minta user mengirim API secret ke chat group.
- Jangan mengaktifkan withdrawal permission.
- Jangan menjanjikan profit.
- Jangan langsung real mode besar.
- Jangan public release tanpa support workflow.

## Fase Lanjutan

Jika ingin public-ready:

- Tambahkan license key.
- Tambahkan admin-only command.
- Tambahkan user registry.
- Tambahkan expiry subscription.
- Tambahkan onboarding state per Telegram ID.
- Tambahkan dashboard atau encrypted setup form.
