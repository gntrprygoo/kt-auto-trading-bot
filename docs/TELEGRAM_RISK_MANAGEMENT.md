# Telegram Risk Management

Update: 2026-07-09

Dokumen ini menjelaskan cara user mengatur risk management KT Auto Trading Bot langsung dari Telegram.

## Prinsip

Risk management dibuat sederhana supaya user baru tidak bingung:

- User bisa memilih preset.
- User bisa mengubah angka utama secara manual.
- Bot membatasi nilai ekstrem dari Telegram.
- Posisi yang sudah terbuka tidak diubah otomatis.
- Perubahan berlaku penuh setelah worker/bot direstart.

## Command Utama

Lihat setting risk:

```text
/risk
```

Lihat panduan:

```text
/risk help
```

## Preset Risk

Preset untuk user baru:

```text
/risk preset conservative
```

Isi:

- Notional: $25/trade
- Leverage: 2x
- Max posisi: 3
- Daily limit: -2R

Preset normal:

```text
/risk preset standard
```

Isi:

- Notional: $50/trade
- Leverage: 3x
- Max posisi: 5
- Daily limit: -3R

Preset growth:

```text
/risk preset growth
```

Isi:

- Notional: $75/trade
- Leverage: 3x
- Max posisi: 7
- Daily limit: -4R

## Ubah Manual

Ubah notional per trade:

```text
/risk set notional 50
```

Ubah leverage:

```text
/risk set leverage 3
```

Ubah maksimal posisi bersamaan:

```text
/risk set max 5
```

Ubah daily loss limit:

```text
/risk set daily -3
```

## Batas Aman Telegram

Bot membatasi perubahan dari Telegram:

- Notional: $10 sampai $500.
- Leverage: 1x sampai 5x.
- Max posisi: 1 sampai 20.
- Daily loss limit: -1R sampai -10R.

Batas ini sengaja konservatif untuk menghindari salah setting dari user baru.

## Penjelasan Untuk User

Notional/trade:

- Besar nilai posisi yang dibuka per trade.
- Semakin besar notional, semakin besar potensi profit dan loss.

Leverage:

- Pengali exposure futures.
- Untuk user baru, gunakan 2x-3x.

Max concurrent:

- Jumlah maksimal posisi yang boleh terbuka bersamaan.
- Semakin tinggi nilainya, semakin besar exposure akun.

Daily loss limit:

- Batas kerugian harian dalam satuan R.
- Contoh -3R berarti bot harus lebih defensif setelah performa hari itu mencapai batas risiko.

## Pesan Aman Untuk Client

```text
Saya sarankan mulai dari /risk preset conservative dulu.
Setelah paham report dan cara kerja bot, baru naik ke standard.
Jangan naikkan notional hanya karena satu-dua trade profit.
```

## Catatan Operasional

Untuk single bot admin:

- `/risk set ...` mengubah config bot utama.
- Perubahan langsung diterapkan ke runtime bot utama.
- Notional, leverage, max posisi, dan daily limit berlaku mulai scan/order berikutnya.
- Restart tidak wajib untuk bot utama VPS.

Untuk managed user:

- `/risk set ...` mengubah config worker user.
- Worker user terpisah perlu reload/restart agar semua perubahan berlaku penuh.
- Tahap berikutnya: worker manager otomatis melakukan restart worker user setelah perubahan risk.
- Posisi lama tidak diubah otomatis.

## Warning

Bot tidak menjamin profit. Futures tetap berisiko tinggi. User wajib paham bahwa menaikkan notional, leverage, dan max posisi dapat memperbesar kerugian.
