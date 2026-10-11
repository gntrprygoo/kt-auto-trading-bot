# Setup Binance API

Panduan ini untuk menjalankan KT Auto Trading Bot dengan Binance Futures.

## 1. Buat API Key

1. Login ke Binance.
2. Buka menu API Management.
3. Buat API key baru khusus untuk bot ini.
4. Simpan API key dan secret di tempat aman.

## 2. Permission Yang Dibutuhkan

Aktifkan permission yang diperlukan untuk Futures trading:

- Read.
- Futures trading.

Jangan aktifkan withdrawal permission.

## 3. IP Restriction

Jika bot berjalan di VPS dengan IP tetap, aktifkan IP whitelist. Ini lebih aman.

Jika masih testing di laptop dengan koneksi internet rumahan, IP bisa berubah. Untuk fase awal, pastikan perangkat aman dan jangan bagikan API key.

## 4. Buat Config

Copy `config.example.json` menjadi `config.json`, lalu isi bagian ini:

```json
"telegram": {
  "bot_token": "ISI_TOKEN_BOT",
  "chat_id": "ISI_CHAT_ID"
},
"binance": {
  "base_url": "https://fapi.binance.com",
  "api_key": "ISI_BINANCE_API_KEY",
  "api_secret": "ISI_BINANCE_API_SECRET"
}
```

`config.json` sudah masuk `.gitignore`, jadi tidak ikut tersimpan ke git.

## 5. Test Simulate Mode

Jalankan:

```powershell
.\run_simulate.ps1
```

Bot akan memakai data live untuk scanning dan report, tetapi tidak mengirim order real.

## 6. Jalankan Real Mode

Mulai dari notional kecil. Pastikan Telegram command dan audit sudah jalan.

```powershell
.\run_real.ps1
```

## Checklist Sebelum Real Mode

- API key benar.
- Telegram command `/status` dibalas.
- Binance Futures account aktif.
- Tidak ada posisi manual tanpa SL.
- Orphan order lama sudah dicek.
- Notional masih kecil untuk fase awal.
