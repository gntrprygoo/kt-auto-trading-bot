# Beta Tester Onboarding

Dokumen ini untuk membantu tester memahami cara memakai KT Auto Trading Bot dengan aman.

## Positioning Produk

KT Auto Trading Bot adalah trading automation assistant berbasis Telegram dan rule-based risk control.

Bot ini:

- Membantu eksekusi strategi secara disiplin.
- Memberikan notifikasi posisi dan report.
- Memiliki kontrol pause/resume.
- Memiliki audit safety untuk SL dan orphan order.

Bot ini tidak:

- Menjamin profit.
- Menghilangkan risiko loss.
- Menggantikan tanggung jawab user.
- Menjadi nasihat keuangan.

## Setup Awal Tester

1. Buat Telegram bot atau gunakan bot yang disediakan admin.
2. Buat Binance API key khusus bot.
3. Jangan aktifkan withdrawal permission.
4. Jalankan `START_BOT.bat`.
5. Pilih setup config.
6. Jalankan simulate mode.
7. Cek `/health`.

## Command Yang Wajib Diketahui

```text
/health
/status
/positions
/orders
/report
/pause
/resume
/risk
/help
```

## Aturan Beta

- Mulai dari simulate mode.
- Jangan menaikkan notional tanpa izin/admin review.
- Jangan mengabaikan alert safety.
- Jangan cancel order tanpa cek posisi live.
- Laporkan bug dengan screenshot/log.
- Gunakan `/pause` jika ada kondisi tidak jelas.

## Emergency Action

Jika ada posisi bermasalah:

1. Kirim `/pause`.
2. Buka Binance Futures.
3. Cek posisi dan order aktif.
4. Pasang SL manual atau close posisi jika perlu.
5. Kirim bug report ke admin.

## Data Yang Perlu Dilaporkan Tester

Setiap bug idealnya berisi:

- Waktu kejadian.
- Pair.
- Command atau action yang dilakukan.
- Screenshot Telegram.
- Screenshot Binance jika terkait posisi/order.
- Potongan log jika tersedia.
- Apakah posisi real atau simulate.
