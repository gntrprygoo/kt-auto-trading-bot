# Telegram API Setup Flow

Panduan ini untuk fase Semi-SaaS KT Auto Trading Bot, supaya user bisa onboarding dari HP melalui Telegram dengan alur yang tetap rapi dan aman.

## Prinsip Keamanan

- API Binance wajib dibuat tanpa withdrawal permission.
- Permission yang dibutuhkan hanya Read dan Futures.
- API wajib memakai IP whitelist VPS: `203.0.113.10`.
- Telegram bot chat dipakai untuk early access dan kemudahan user, tetapi bukan kanal paling ideal untuk secret jangka panjang.
- Bot mencoba menghapus pesan `/api_key` dan `/api_secret` setelah diterima.
- API Secret hanya disimpan ke config user jika validasi Binance berhasil.

## Alur User

1. User kirim `/register`.
2. User baca panduan dari `/onboarding`.
3. User baca `/api_guide` untuk membuat Binance API:
   - Read: ON
   - Futures: ON
   - Withdrawal: OFF
   - IP whitelist: `203.0.113.10`
4. User kirim `/setup_api`.
5. User kirim `/api_key API_KEY_ANDA`.
6. User kirim `/api_secret API_SECRET_ANDA`.
7. Bot validasi API dari server.
8. Jika valid, bot menyimpan config user dan memberi notifikasi ke admin.
9. User cek dengan `/api_status`.
10. Setelah admin approve/start worker, user cek `/health`.

## Command User

```text
/api_guide
/setup_api
/api_key API_KEY_ANDA
/api_secret API_SECRET_ANDA
/api_status
/delete_api
/cancel_setup
```

## Panduan Membuat API Binance

Di Binance, user masuk ke Account/Profile, lalu buka API Management. Pilih Create API, gunakan System generated API key jika tersedia, beri nama singkat seperti `ktbot`, lalu selesaikan verifikasi email/2FA.

Setelah API dibuat, permission yang dipakai untuk bot:

- Enable Reading: ON
- Enable Futures: ON
- Enable Spot/Margin: OFF jika tidak diperlukan
- Enable Withdrawals: wajib OFF
- Restrict access to trusted IPs only: ON
- Trusted IP: `203.0.113.10`

Jika Binance menampilkan API Secret hanya sekali, user harus langsung copy secret tersebut. Setelah halaman ditutup, secret biasanya tidak bisa dilihat ulang dan API perlu dibuat ulang.

## Alur Admin

Saat API valid, admin menerima notifikasi `API READY`.

Langkah admin:

```text
/admin_approve CHAT_ID
```

Setelah itu worker user dapat dibuat/dijalankan sesuai runbook managed worker.

## Disclaimer Untuk User

Trading futures berisiko tinggi. Bot tidak menjamin profit, tidak menghilangkan risiko likuidasi, dan tidak menggantikan keputusan finansial pribadi. User bertanggung jawab atas akun Binance, API permission, modal, dan risiko trading masing-masing.

Jangan aktifkan withdrawal permission. Jika withdrawal permission aktif, API harus dihapus dan dibuat ulang sebelum digunakan.
