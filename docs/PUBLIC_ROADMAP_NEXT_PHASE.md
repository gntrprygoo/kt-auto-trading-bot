# Public Roadmap Next Phase

Update: 2026-07-06

## Tujuan Fase Berikut

Mengubah KT Auto Trading Bot dari bot single-user/local script menjadi produk yang bisa dipakai calon client mobile-only melalui Telegram.

## Keputusan Produk

Target user publik:

- Punya Binance account.
- Punya Telegram.
- Mungkin tidak punya laptop.
- Ingin setup praktis.
- Ingin kontrol dan report dari Telegram.

Konsekuensi:

- Bot perlu backend/server.
- Perlu user registry.
- Perlu license/subscription.
- Perlu penyimpanan credential yang aman.
- Perlu onboarding flow.
- Perlu admin/support workflow.

## Milestone 1: User Registry

Status: implemented as local JSON registry foundation.

Fitur:

- Daftar Telegram ID user.
- Status user: pending, active, paused, expired, banned.
- Admin ID.
- Admin command untuk approve/revoke.

Command awal:

```text
/register
/myaccount
/admin_users
/admin_approve
/admin_revoke
```

## Milestone 2: License System

Status: basic license/trial metadata implemented in local registry.

Fitur:

- License key per user.
- Expiry date.
- Trial period.
- Subscription status.

Command:

```text
/license
/activate
/expiry
```

## Milestone 3: Per-User Config dan Journal

Saat ini bot memakai satu config dan satu journal.

Untuk publik, perlu:

- `users/<telegram_id>/config.json`
- `users/<telegram_id>/journal.json`
- `users/<telegram_id>/logs`
- worker per user atau scheduler multi-user.

## Milestone 4: Secure API Setup

Pilihan awal:

- Assisted setup oleh admin.
- Config dibuat per user di server.

Pilihan lanjut:

- Secure web form.
- Telegram Web App.
- Encrypted credential vault.

## Milestone 5: Managed Worker

Fitur:

- Start/stop worker per user.
- Restart otomatis jika crash.
- Health monitor.
- Alert admin jika worker error.

## Milestone 6: Public Onboarding

Flow:

1. User `/start`.
2. User baca disclaimer.
3. User `/register`.
4. Admin approve.
5. User setup Binance API.
6. Admin/user input credential via flow aman.
7. `/health`.
8. Trial/simulate.
9. Real mode kecil.

## Prioritas Sekarang

Langkah coding berikut yang paling masuk akal:

1. Tambah user registry lokal.
2. Tambah admin-only command.
3. Tambah license/trial metadata.
4. Pisahkan journal/config per user.

Ini adalah fondasi sebelum API setup publik dan SaaS penuh.
