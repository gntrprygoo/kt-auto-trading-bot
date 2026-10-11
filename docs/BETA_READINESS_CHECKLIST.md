# Beta Readiness Checklist

Dokumen ini menentukan apakah KT Auto Trading Bot siap diuji oleh 5-10 beta tester terbatas.

## Keputusan Saat Ini

Status: layak untuk private beta terbatas dengan kontrol ketat.

Bot sudah melewati beberapa syarat teknis utama:

- Config eksternal tersedia.
- Telegram command berjalan.
- Pause/resume entry tersedia.
- P&L report memprioritaskan realized PnL Binance.
- Audit posisi tanpa SL tersedia.
- Audit orphan SL/TP order tersedia.
- Journal backup otomatis tersedia.
- Launcher mudah tersedia.
- Dokumentasi setup dan risiko tersedia.
- Report analytics sudah lebih profesional.

## Syarat Wajib Sebelum Beta Tester Masuk

Setiap akun beta wajib:

- Menjalankan simulate mode minimal 24 jam.
- Menjalankan `/health` dan hasilnya tidak ada FAIL.
- Menjalankan `/status`, `/positions`, `/orders`, `/report`, `/risk`.
- Memahami bahwa bot tidak menjamin profit.
- Menggunakan notional kecil.
- Tidak memakai API key dengan withdrawal permission.
- Memiliki akses manual ke Binance untuk emergency close.
- Menyetujui risk disclosure.

## Parameter Beta Awal

Rekomendasi:

- Jumlah tester: 5-10 orang.
- Durasi minimum: 30 hari.
- Mode awal: simulate 24 jam, lalu real mode kecil.
- Notional awal: 5-50 USDT sesuai toleransi user.
- Leverage: rendah dan konsisten.
- Fokus evaluasi: stabilitas, sync, report, risk control, bukan profit cepat.

## Daily Checklist

Setiap hari tester/admin mengecek:

- `/health`
- `/status`
- `/positions`
- `/orders`
- `/report`
- Apakah ada alert posisi tanpa SL.
- Apakah ada orphan order.
- Apakah Telegram command responsif.
- Apakah journal/report sesuai Binance.

## Exit Criteria Beta

Beta bisa naik level jika selama minimal 30 hari:

- Tidak ada posisi live tanpa SL yang tidak tertangani.
- Tidak ada mismatch besar antara Binance dan journal.
- Close notification konsisten.
- Report P&L sesuai realized PnL Binance.
- Bug kritikal terselesaikan.
- Tester memahami cara pause/resume dan emergency manual.

## Kondisi Harus Pause Beta

Pause beta jika terjadi:

- Bot membuka posisi tanpa SL aktif.
- Sync Binance gagal berulang.
- Journal salah menandai posisi live sebagai closed.
- P&L report berbeda jauh dari Binance.
- Telegram command tidak responsif saat real mode.
- Ada error order yang berulang.

Jika salah satu terjadi, gunakan `/pause`, cek Binance manual, lalu analisis log sebelum lanjut.
