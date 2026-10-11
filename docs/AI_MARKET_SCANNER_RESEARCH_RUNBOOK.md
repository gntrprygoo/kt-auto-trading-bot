# AI Market Scanner Prompt Research Runbook

Date: 2026-08-05

Status: `DEVELOPMENT_REJECTED_NO_WINNER`

## Tujuan

Pipeline ini menguji apakah model OpenAI dapat menemukan keputusan market yang
lebih berguna daripada strategi kandidat lama. Model membaca snapshot pasar
Binance yang sudah diambil aplikasi, lalu memilih paling banyak satu pair dan
satu arah, atau memilih `NO_TRADE`.

Pipeline ini tidak menjanjikan profit. Prompt hanya dinyatakan memiliki bukti
awal jika lolos development dan validation unseen setelah biaya transaksi.

## Batas tanggung jawab

Model boleh menentukan:

- `TRADE` atau `NO_TRADE`;
- pair dari universe yang tersedia;
- `LONG` atau `SHORT`;
- regime, confidence, setup quality, thesis, dan risk flags.

Model tidak boleh menentukan:

- quantity atau leverage;
- risiko akun;
- harga entry, SL, atau TP;
- kredensial Binance;
- pengiriman order.

Entry, stop, target, biaya, sizing, dan semua hard risk limit tetap dihitung
oleh kode deterministik. OpenAI tidak menerima Binance API key, Telegram token,
saldo, atau identitas akun.

## Data yang dikunci

Universe:

```text
BTCUSDT ETHUSDT SOLUSDT ADAUSDT DOGEUSDT XRPUSDT
```

Feature set: `OHLCV_TAKER_CROSS_MARKET_V1`

- sumber candle 15 menit;
- keputusan hanya setelah candle satu jam terkonfirmasi;
- return 1h, 4h, 12h, dan 24h;
- EMA alignment dan spread;
- ATR percent dan posisi dalam range;
- relative strength terhadap BTC;
- volume ratio dan taker buy/sell flow;
- urutan delapan jam terakhir;
- tanpa OI, funding, dan order book historis karena datanya belum tersedia.

Outcome masa depan disimpan terpisah dari snapshot model. Hash kontrak fitur
diverifikasi lagi sebelum request API dan saat pembuatan gate.

## Tiga prompt kandidat

`P1_REGIME_STRUCTURE`

Fokus pada BTC regime, struktur, trend, relative strength, dan lokasi harga.

`P2_LIQUIDITY_FLOW`

Fokus pada auction, persistence taker flow, volume, absorption, dan acceptance.

`P3_CONSERVATIVE_CONFLUENCE`

Fokus pada keselarasan regime, trend, lokasi, flow, dan volatility. Prompt ini
lebih selektif dan harus memilih `NO_TRADE` saat bukti bercampur.

## Protokol pengujian

1. Build 240 snapshot development dari 2021-07 sampai 2023-12.
2. Build 240 snapshot validation unseen dari 2024-01 sampai 2024-10.
3. Kirim satu request smoke. Error key, model, schema, rate limit, atau kredit
   langsung menghentikan semua request berikutnya.
4. Uji ketiga prompt hanya pada development.
5. Pilih pemenang hanya jika gate development lulus. Tidak ada pemenang paksa.
6. Bekukan model, prompt hash, threshold, feature hash, dan execution model.
7. Jalankan hanya pemenang pada validation unseen.
8. Hasil validation gagal tetap mengunci seluruh integrasi.

Model eksekusi:

- entry pada open candle 15 menit berikutnya;
- stop `max(0.75%, 1.5 ATR)` dengan batas maksimum 3%;
- target 2R;
- maksimum holding 12 jam;
- jika SL dan TP tersentuh dalam candle yang sama, SL dihitung lebih dahulu;
- maksimum satu posisi bersamaan;
- baseline cost 0.14%;
- stress cost 0.20%.

## Promotion gate

Development memerlukan paling sedikit 100 keputusan valid dan 25 trade,
coverage 98%, total R positif pada baseline dan stress, PF baseline minimal
1.15, PF stress minimal 1.05, drawdown baseline dan stress maksimum 10R, serta
konsentrasi satu pair maksimum 70%.

Validation memerlukan paling sedikit 100 keputusan valid dan 20 trade, total R
positif pada baseline dan stress, PF baseline minimal 1.10, PF stress minimal
1.00, drawdown baseline dan stress maksimum 8R, serta konsentrasi satu pair
maksimum 70%.

Lulus historis hanya membuat kandidat layak untuk `AI_SIGNAL`. `AI_APPROVAL`
dan `AI_LIVE` tetap terkunci sampai ada bukti forward dan pemeriksaan operasi.

## Menjalankan riset

OpenAI API billing terpisah dari langganan ChatGPT. Tambahkan kredit melalui
akun OpenAI Platform milik sendiri dan jangan mengirim API key melalui Telegram,
chat, screenshot, atau source code.

Set key hanya untuk PowerShell saat ini:

```powershell
$env:OPENAI_API_KEY = "YOUR_OPENAI_API_KEY"
```

Jalankan dari folder project:

```powershell
.\tools\run_ai_market_prompt_research.ps1
```

Runner menggunakan cache JSONL. Request yang sudah sukses tidak diulang.
Default concurrency adalah dua request dan dapat diturunkan menjadi satu:

```powershell
.\tools\run_ai_market_prompt_research.ps1 -Workers 1
```

## Biaya terkontrol

Rencana penuh memakai maksimum 720 request development dan, hanya bila ada
pemenang, 240 request validation. Script mencatat input token, output token,
dan estimasi biaya aktual dari usage API. Sebelum menjalankan, cek kembali harga
model pada dokumentasi resmi karena harga dapat berubah.

Kredit API kemudian diaktifkan dan dua turnamen development diselesaikan pada
2026-08-06. Seluruh prompt V1 dan V2 gagal pada development. Validation tidak
dibuka, tidak ada prompt pemenang, dan direct scanner tetap terkunci. Jangan
menjalankan ulang prompt yang sama karena hasil sukses sudah ada di cache.

Hasil lengkap:

```text
docs/AI_MARKET_SCANNER_PROMPT_RESEARCH_RESULT_2026-08-06.md
```

## Artefak

```text
.audit/2026-08-05-ai-market-scanner/market_development.json
.audit/2026-08-05-ai-market-scanner/market_validation.json
.audit/2026-08-05-ai-market-scanner/openai_market_prompt_cache.jsonl
.audit/2026-08-05-ai-market-scanner/openai_market_prompt_development.json
.audit/2026-08-05-ai-market-scanner/openai_market_prompt_validation.json
.audit/2026-08-05-ai-market-scanner/ai_market_prompt_gate.json
```

Exit code `2` berarti riset belum lengkap atau gate gagal. Itu bukan izin untuk
menyetel prompt memakai validation atau mengaktifkan order.

## Kondisi produksi saat ini

- Bot live di VPS tidak diubah oleh pipeline ini.
- Tidak ada scanner AI direct yang mengirim order.
- Hybrid AI reviewer lama tetap terpisah dan tetap dalam mode aman.
- `AI_APPROVAL` dan `AI_LIVE` untuk scanner direct belum tersedia.
- `AI_SIGNAL` juga tetap terkunci karena tidak ada prompt yang lolos.
