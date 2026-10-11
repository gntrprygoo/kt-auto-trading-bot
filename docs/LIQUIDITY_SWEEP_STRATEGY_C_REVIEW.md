# Strategy C Liquidity Sweep Review

Update: 2026-07-15

Implementation status: Strategy C v2 sudah diterapkan pada 2026-07-15 dalam
mode shadow-only. Data lama tetap diberi label `Jalur C v1 (legacy)` dan semua
sinyal baru memakai label `Jalur C v2 Liquidity Sweep` agar evaluasi tidak
tercampur.

Dokumen ini mengevaluasi ulang Strategy C setelah shadow signal menunjukkan performa buruk.

## Ringkasan Data Shadow VPS

Snapshot dari `shadow_trades_v3.json`:

- Total shadow data: 183
- Closed shadow trade: 152
- Win: 61
- Loss: 91
- Winrate total: 40.13%
- Avg R total: -0.305R
- Total R: -46.37R

Per reason:

- `smart_money_c`: 13 closed, winrate 15.38%, avgR -0.581R, total -7.55R
- `vol_too_high`: 139 closed, winrate 42.45%, avgR -0.279R, total -38.82R

Kesimpulan: Strategy C murni belum layak real entry. Sampelnya masih kecil, tetapi kualitas awalnya buruk dan perlu revisi definisi.

## Apa Itu Liquidity Sweep Yang Layak Ditadingkan

Liquidity sweep bukan sekadar harga menembus high/low lalu balik.

Versi yang lebih layak dipakai bot:

1. Ada level likuiditas yang jelas:
   - equal high/equal low,
   - swing high/low yang sudah diuji,
   - high/low sesi sebelumnya,
   - 4H liquidity pool,
   - area range high/range low.
2. Harga menyapu level tersebut.
3. Candle sweep gagal mempertahankan breakout/breakdown.
4. Ada rejection wick yang jelas.
5. Ada displacement balik yang kuat.
6. Ada market structure shift setelah sweep.
7. Entry hanya saat retest area yang sempit, bukan area terlalu lebar.
8. SL berada di luar extreme sweep.
9. TP diarahkan ke liquidity pool lawan atau minimal struktur yang realistis.

Jika hanya menembus high/low lokal lalu close balik, itu masih false break biasa. Belum tentu ada edge.

## Masalah Pada Strategy C Sekarang

### 1. Sweep hanya berbasis 15m lookback

Code saat ini mencari sweep dari 20 candle 15m. Ini terlalu lokal.

Akibat:

- Banyak sweep kecil yang tidak signifikan.
- Noise intraday dianggap liquidity event.
- Sinyal muncul di tengah struktur, bukan di area high-value liquidity.

Revisi:

- Wajib ada konfirmasi 4H location.
- LONG hanya valid jika sweep terjadi dekat 4H support/range low.
- SHORT hanya valid jika sweep terjadi dekat 4H resistance/range high.

### 2. MSS terlalu berat dan kadang salah lokasi

MSS saat ini memakai high/low dari candle sebelum sweep. Untuk reversal yang sehat, break minor structure sebaiknya diukur dari struktur setelah sweep, bukan seluruh pre-sweep high/low yang terlalu jauh.

Akibat:

- Jika level MSS terlalu jauh, entry terlambat dan RR memburuk.
- Jika level kurang relevan, MSS palsu lolos.

Revisi:

- Setelah sweep, cari displacement candle.
- MSS valid jika close menembus minor pivot setelah sweep.
- Tambahkan syarat body candle displacement minimal.

### 3. Retest area terlalu lebar

Area retest sekarang menggabungkan order block, sweep level, dan MSS level. Ini bisa terlalu lebar.

Akibat:

- Entry terjadi di area yang tidak presisi.
- Bot masuk saat harga belum benar-benar retest zone yang bagus.
- Banyak entry reversal tanpa timing yang tajam.

Revisi:

- Gunakan zone sempit:
  - 50%-100% body candle displacement, atau
  - last opposite candle sebelum displacement,
  - maksimal lebar zone 0.35%-0.60% tergantung volatilitas.

### 4. RR check tidak bermakna

TP Strategy C sekarang dihitung dari entry + 2R atau entry - 2R, sehingga RR hampir selalu menjadi 2.00.

Akibat:

- Filter `min_rr` tidak benar-benar memfilter setup.
- Bot tidak mengecek apakah ada target struktur yang realistis.

Revisi:

- TP harus ke liquidity pool lawan:
  - LONG target: minor high setelah MSS, range midpoint, atau 4H resistance terdekat.
  - SHORT target: minor low setelah MSS, range midpoint, atau 4H support terdekat.
- Setup hanya valid jika target struktur memberi minimal 1.6R-2.0R.

### 5. Tidak ada market regime filter khusus Strategy C

Liquidity sweep reversal paling baik di range/mean-reversion atau di pullback trend besar, bukan saat trend impulsif kuat melawan arah.

Revisi:

- Hindari LONG jika 4H bearish impulsif.
- Hindari SHORT jika 4H bullish impulsif.
- Hindari entry saat candle 4H sedang expansion kuat searah breakdown/breakout.
- Hindari pair dengan funding ekstrem dan spread buruk.

## Strategy C v2 Yang Disarankan

### LONG

Syarat:

1. 4H trend tidak bearish impulsif.
2. Harga berada dekat 4H support, range low, atau prior liquidity low.
3. 15m sweep low:
   - low menembus swing low,
   - close kembali di atas swing low,
   - lower wick minimal 40% range candle,
   - volume minimal 1.8x avg20.
4. Displacement bullish setelah sweep:
   - close bullish kuat,
   - body minimal 50% range,
   - close menembus minor high setelah sweep.
5. Entry hanya saat retest zone sempit.
6. SL di bawah sweep low + buffer.
7. TP ke liquidity high/4H resistance terdekat.
8. Valid hanya jika struktur target memberi minimal 1.7R.

### SHORT

Syarat:

1. 4H trend tidak bullish impulsif.
2. Harga berada dekat 4H resistance, range high, atau prior liquidity high.
3. 15m sweep high:
   - high menembus swing high,
   - close kembali di bawah swing high,
   - upper wick minimal 40% range candle,
   - volume minimal 1.8x avg20.
4. Displacement bearish setelah sweep:
   - close bearish kuat,
   - body minimal 50% range,
   - close menembus minor low setelah sweep.
5. Entry hanya saat retest zone sempit.
6. SL di atas sweep high + buffer.
7. TP ke liquidity low/4H support terdekat.
8. Valid hanya jika struktur target memberi minimal 1.7R.

## Parameter v2 Awal

- Sweep lookback 15m: 32 candle
- 4H location lookback: 30 candle
- Sweep buffer: 0.08%-0.18%
- Wick ratio minimum: 0.40
- Sweep volume ratio minimum: 1.8x avg20
- Displacement body ratio minimum: 0.50
- Displacement volume minimum: 1.20x avg20
- MSS window: 1-4 candle setelah sweep
- Retest tolerance: 0.15%-0.22%
- Fair value gap minimum: 0.05% dan wajib sebagai bukti imbalance
- Lebar maksimum zona retest: 0.60%
- Minimum structural RR: 1.7R
- Max signal age: 8 candle 15m

## Implementasi C v2

Engine sekarang menjalankan urutan berikut tanpa melewati tahap:

1. Menentukan premium/discount range dari 30 candle 4H tertutup.
2. Memastikan extreme sweep dekat pivot/range liquidity 4H.
3. Memvalidasi sweep 15m dengan penetration, wick minimal 40%, dan volume 1.8x.
4. Mencari minor pivot sebelum sweep lalu menunggu displacement close melewati pivot.
5. Memastikan displacement memiliki body dan volume di atas baseline.
6. Mewajibkan FVG, lalu membentuk zona retest sempit dari FVG atau overlap OB+FVG.
7. Menolak setup bila extreme sweep ditembus ulang sebelum entry.
8. Menggunakan liquidity 4H lawan terdekat sebagai TP struktural.
9. Menolak setup jika target tersebut tidak menyediakan minimal 1.7R.
10. Mencatat hasil virtual memakai high/low candle; jika SL dan TP tersentuh pada
    candle yang sama, hasil dicatat konservatif sebagai loss.

Strategy C v2 dievaluasi sebelum cooldown dan gate posisi Jalur A/B. Tujuannya
agar statistik shadow mengukur kualitas setup C, bukan status operasional akun.

## Keputusan Profesional

Jangan aktifkan Strategy C ke real order.

Langkah berikut:

1. Tetap shadow-only.
2. Ubah Strategy C menjadi v2 dengan filter lebih ketat.
3. Pisahkan report `/shadow` antara `smart_money_c` dan reason lain seperti `vol_too_high`.
4. Evaluasi minimal 50-100 closed shadow trade Strategy C v2.
5. Baru pertimbangkan real entry jika:
   - winrate minimal 45%-50%,
   - avgR positif,
   - max losing streak masuk akal,
   - performa tidak hanya bagus di 1-2 pair.

## Catatan Penting

Liquidity sweep adalah strategi yang sangat sensitif terhadap konteks. Tanpa higher-timeframe location, displacement, dan target struktur yang realistis, sweep detector mudah berubah menjadi pemburu reversal acak.
