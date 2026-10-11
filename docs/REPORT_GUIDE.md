# Panduan Membaca Report

Report bot dikirim melalui Telegram dan bisa diminta manual dengan:

```text
/report
/weekly
/monthly
/alltime
```

## Field Utama

### Total trade

Jumlah semua trade yang masuk ke periode report.

### Closed

Jumlah trade yang sudah selesai dan punya hasil R.

### Win/Loss/BE

Ringkasan hasil trade:

- Win: trade profit.
- Loss: trade rugi.
- BE: breakeven atau mendekati nol.

### Winrate

Persentase closed trade yang berakhir win.

Winrate tinggi tidak selalu berarti sistem bagus. Tetap lihat Avg R, Total R, dan Profit Factor.

### Avg R

Rata-rata hasil trade dalam satuan R.

Contoh:

- `+0.25R`: rata-rata trade menghasilkan seperempat risiko awal.
- `-0.10R`: rata-rata trade masih negatif.

### Total R

Akumulasi hasil dalam satuan R.

Ini membantu membaca performa tanpa terlalu dipengaruhi ukuran modal.

### Max DD

Maximum drawdown dalam satuan R, dihitung dari kurva akumulasi R trade yang sudah closed.

Contoh:

- `-2.50R`: dari puncak performa terakhir, sistem sempat turun 2.5R.
- Semakin kecil drawdown relatif terhadap Total R, semakin sehat performanya.

### Realized P&L

P&L dollar yang diprioritaskan dari data `realized_pnl` Binance jika tersedia.

Jika data Binance belum ada untuk trade tertentu, bot memakai estimasi berbasis R dan risk trade.

### Profit Factor

Rasio gross profit dibanding gross loss.

Interpretasi sederhana:

- Di bawah 1.0: belum profitable.
- Di atas 1.0: profit lebih besar dari loss.
- Di atas 1.5: mulai menarik, tetapi perlu sample besar.

### Best Pair dan Worst Pair

Pair dengan kontribusi Total R terbaik dan terburuk pada periode report.

Gunakan ini untuk evaluasi, bukan untuk langsung menghapus pair hanya karena 1-2 loss.

### Entry Path

Performa jalur entry:

- `A`: entry langsung di support/resistance.
- `B`: breakout-retest.
- `UNKNOWN`: trade lama atau data journal yang belum punya label jalur.

Metrik ini membantu membandingkan jalur mana yang lebih cocok dengan kondisi market.

## Command Terkait

### `/status`

Melihat mode bot, entry aktif/pause, jumlah pair, posisi, dan risk snapshot.

### `/positions`

Melihat posisi live Binance atau posisi aktif dari journal.

### `/orders`

Melihat open order Binance, termasuk SL/TP conditional order.

### `/risk`

Melihat setting notional, leverage, daily loss limit, dan audit.

### `/weekly`

Melihat performa minggu berjalan berdasarkan timezone WIB.

### `/monthly`

Melihat performa bulan berjalan berdasarkan timezone WIB.

## Cara Membaca Dengan Sehat

Jangan menilai bot dari 1-5 trade. Evaluasi minimal dari:

- 30 hari testing.
- Jumlah trade cukup.
- Kondisi market berbeda.
- Drawdown dan loss streak.
- Konsistensi SL/TP dan sync journal.
