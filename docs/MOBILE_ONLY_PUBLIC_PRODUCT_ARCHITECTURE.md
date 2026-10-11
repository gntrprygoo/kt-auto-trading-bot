# Mobile-Only Public Product Architecture

Dokumen ini menjelaskan cara menjadikan KT Auto Trading Bot bisa dipakai user yang hanya punya handphone dan ingin memakai Telegram sebagai pusat onboarding, kontrol, dan report.

## Jawaban Singkat

Bisa dibuat.

Namun, modelnya bukan lagi user menjalankan script Python di laptop. Produk harus berubah menjadi:

```text
Telegram Bot -> Backend Server -> User Config + Encrypted API Vault -> Trading Worker -> Binance Futures
```

Telegram tetap menjadi interface utama, tetapi eksekusi bot berjalan di server yang kita kelola.

## Kenapa Tidak Cukup Script Lokal?

Script lokal cocok untuk:

- Owner/admin.
- Tester teknis.
- User yang punya laptop/VPS.

Untuk public mobile-only user, script lokal tidak cocok karena:

- User tidak punya terminal.
- User tidak mau edit config.
- User tidak paham install Python.
- Bot harus tetap hidup 24 jam.
- API key harus disimpan aman.
- Perlu subscription/license.
- Perlu monitoring multi-user.

## Prinsip Keamanan API

API secret tidak ideal dikirim sebagai chat Telegram biasa.

Untuk produk publik, pilihan yang lebih aman:

1. Telegram bot memberi link setup aman.
2. User mengisi API key di halaman aman / Telegram Web App.
3. Backend mengenkripsi secret sebelum disimpan.
4. Trading worker membaca secret hanya saat perlu request Binance.
5. User bisa revoke/delete API key kapan saja.

Permission API wajib:

- Read: ON.
- Futures trading: ON.
- Withdrawal: OFF.
- IP whitelist: direkomendasikan.

## Arsitektur MVP Publik

### 1. Telegram Bot

Fungsi:

- `/start`
- onboarding
- status user
- subscription status
- report
- pause/resume
- positions/orders
- warning/error

Telegram bot tidak menyimpan strategi. Bot hanya interface.

### 2. Backend API

Fungsi:

- Menyimpan user Telegram ID.
- Menyimpan status onboarding.
- Mengelola subscription/license.
- Menyimpan config user.
- Menerima update dari Telegram.
- Menjadwalkan worker trading.

### 3. Encrypted API Vault

Fungsi:

- Menyimpan Binance API key/secret terenkripsi.
- Secret tidak muncul di log.
- Secret tidak dikirim balik ke Telegram.
- User/admin bisa revoke/delete.

### 4. Trading Worker

Fungsi:

- Menjalankan logic bot per user.
- Sync Binance.
- Scan pair.
- Place order.
- Audit SL/orphan.
- Kirim report ke Telegram.

Model worker bisa:

- Satu process per user.
- Multi-user scheduler.
- Queue-based worker.

Untuk awal, satu process per user lebih sederhana dan lebih aman di-isolasi.

### 5. Database

Menyimpan:

- Telegram user ID.
- License/subscription.
- User config.
- Bot status.
- Journal per user.
- Audit log.
- Error log.
- Encrypted API credential reference.

## Flow User Mobile-Only

### Step 1: User Start

User buka Telegram bot:

```text
/start
```

Bot menjawab:

- Apa itu produk.
- Disclaimer risiko.
- Tombol mulai setup.

### Step 2: Risk Acceptance

User wajib menyetujui:

- Bukan jaminan profit.
- Futures berisiko tinggi.
- User bertanggung jawab atas API dan akun Binance.

### Step 3: Binance Setup Guide

Bot memberi panduan:

- Aktifkan Futures.
- Buat API key.
- Permission Read + Futures Trading.
- Withdrawal OFF.
- IP whitelist jika tersedia.

### Step 4: Secure API Setup

Pilihan aman:

- Telegram Web App.
- Secure web link.
- Assisted setup oleh admin.

User memasukkan API key/secret di tempat aman, bukan di chat biasa.

### Step 5: Health Check

Backend menjalankan:

- API key valid.
- Futures enabled.
- Bisa baca account.
- Bisa baca positions/orders.
- Permission cukup.

### Step 6: Trial / Activate

User masuk:

- Trial.
- Paid subscription.
- Manual approval admin.

### Step 7: Running

User mengontrol lewat Telegram:

```text
/status
/health
/positions
/orders
/report
/weekly
/monthly
/pause
/resume
/risk
```

## Fase Implementasi

### Fase A: Assisted Managed Setup

Cocok untuk awal.

Flow:

- User daftar via Telegram.
- Admin bantu setup VPS/instance.
- API key disimpan di config instance user.
- Telegram user menerima report.

Kelebihan:

- Cepat dibuat.
- Risiko multi-tenant lebih kecil.
- Cocok untuk 5-20 user awal.

Kekurangan:

- Banyak kerja manual admin.
- Scaling terbatas.

### Fase B: Semi-SaaS

Flow:

- Telegram bot punya user registry.
- Admin approve user.
- Worker per user dibuat otomatis/semi otomatis.
- Config dan journal dipisah per user.

Kelebihan:

- Lebih scalable.
- Masih relatif aman.

Kekurangan:

- Butuh backend dan database.

### Fase C: Full SaaS

Flow:

- User daftar sendiri.
- Bayar subscription.
- Isi API lewat secure form/Web App.
- Bot aktif otomatis.
- License dan expiry otomatis.

Kelebihan:

- Siap publik.
- User experience paling mudah.

Kekurangan:

- Butuh security, backend, infra, monitoring, legal, support.

## Rekomendasi Strategis

Jangan langsung lompat ke Full SaaS.

Urutan terbaik:

1. Assisted Managed Setup.
2. Semi-SaaS dengan user registry dan admin approval.
3. Full SaaS setelah proses support dan security matang.

Dengan posisi bot saat ini, fase berikut paling realistis adalah:

```text
Telegram User Registry + License + Admin Approval + Per-user Config/Journal
```

Ini menjadi jembatan dari script single-user menuju produk publik mobile-only.

## Status Implementasi Awal

Fondasi Semi-SaaS awal sudah mulai dibuat:

- `/register`
- `/myaccount`
- `/license`
- `/onboarding`
- `/admin_users`
- `/admin_pending`
- `/admin_approve`
- `/admin_revoke`
- `/admin_extend`

Catatan penting: command trading untuk non-admin belum diarahkan ke worker pribadi. Ini sengaja, agar data akun owner/admin tidak bocor ke calon client. Tahap berikutnya adalah per-user config/journal dan managed worker.
