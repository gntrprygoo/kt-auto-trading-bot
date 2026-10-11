# Smart Money Entry 3 Proposal

## Tujuan

Menambahkan Jalur C sebagai strategi entry ketiga untuk KT Auto Trading Bot.

Fokus Jalur C:

- menangkap reversal setelah stop/liquidity sweep
- tetap rule-based dan bisa diuji
- tidak mengganti Jalur A dan Jalur B
- tetap memakai risk engine, SL/TP, dual TP, dan breakeven yang sudah ada

## Prinsip Strategi

Smart Money Concepts yang layak dipakai bot perlu diterjemahkan menjadi sinyal objektif. Istilah seperti order block, fair value gap, liquidity sweep, dan CHOCH sering dipakai secara subjektif. Untuk bot, semua harus dihitung dari candle, volume, dan struktur harga.

Jalur C yang disarankan:

Liquidity Sweep + Market Structure Shift + FVG/Order Block Retest.

## Setup LONG

1. Trend besar tidak bearish ekstrem.
2. Harga menyapu swing low/liquidity low 4H atau 15m.
3. Candle sweep menutup kembali di atas level yang disapu.
4. Ada rejection wick bawah yang jelas.
5. Volume sweep naik di atas rata-rata.
6. Setelah sweep, harga membuat market structure shift:
   - break minor high terakhir, atau
   - close kembali di atas micro resistance.
7. Entry saat harga retest area:
   - fair value gap bullish, atau
   - candle impulse/order block terakhir sebelum break.
8. SL di bawah low sweep + buffer.
9. TP tetap memakai sistem existing:
   - TP1 1R
   - TP2 2R
   - BE 1% dan BE setelah TP1 tetap aktif

## Setup SHORT

1. Trend besar tidak bullish ekstrem.
2. Harga menyapu swing high/liquidity high 4H atau 15m.
3. Candle sweep menutup kembali di bawah level yang disapu.
4. Ada rejection wick atas yang jelas.
5. Volume sweep naik di atas rata-rata.
6. Setelah sweep, harga membuat market structure shift:
   - break minor low terakhir, atau
   - close kembali di bawah micro support.
7. Entry saat harga retest area:
   - fair value gap bearish, atau
   - candle impulse/order block terakhir sebelum break.
8. SL di atas high sweep + buffer.
9. TP tetap memakai sistem existing.

## Filter Wajib

- Minimum volume pair tetap dipakai.
- Funding extreme tetap dihindari.
- Spread max tetap dipakai.
- Jangan entry jika sudah ada posisi pair yang sama.
- Jangan entry jika RR ke TP2 kurang dari threshold existing.
- Jangan entry saat candle sweep terlalu kecil atau volume tidak signifikan.

## Parameter Awal

- Sweep lookback 15m: 20 candle
- Sweep lookback 4H: 20 candle
- Sweep buffer: 0.10%-0.20%
- Minimum wick ratio: 0.38
- Minimum sweep volume ratio: 1.5x avg20
- MSS confirmation window: 1-6 candle 15m
- Retest tolerance: 0.15%-0.35%
- Entry expiry: 8 candle 15m

## Kenapa Cocok Untuk Bot Ini

Jalur A sudah fokus entry langsung di S/R.
Jalur B sudah fokus breakout-retest.
Jalur C akan mengisi kategori berbeda: false breakout/liquidity sweep reversal.

Dengan begitu, tiga jalur tidak saling tumpang tindih secara berlebihan:

- Jalur A: support/resistance rejection
- Jalur B: breakout lalu retest
- Jalur C: liquidity sweep lalu reversal confirmation

## Risiko

- Banyak konsep SMC subjektif jika tidak dibuat objektif.
- Sweep palsu bisa berubah menjadi breakdown/breakout asli.
- Entry terlalu cepat sebelum MSS akan sering kena SL.
- Entry terlalu lambat setelah MSS bisa RR buruk.

Karena itu Jalur C sebaiknya dibuat sebagai shadow tracking dulu sebelum real order.

## Rekomendasi Implementasi

Tahap 1:

- Tambahkan detector sweep.
- Tambahkan detector market structure shift.
- Tambahkan detector fair value gap sederhana.
- Catat shadow signal Jalur C tanpa entry real.

Tahap 2:

- Evaluasi winrate, avg R, max losing streak, dan pair terbaik.
- Bandingkan Jalur C vs Jalur A/B.

Tahap 3:

- Aktifkan real entry Jalur C jika hasil shadow layak.

