# v3_swing_bot.py — V7.4
# ============================================================
# CHANGELOG V7.4 — SIZING + DUAL TP OVERHAUL (diskusi trade management):
#
# [V7.4-S1  FIXED-NOTIONAL] Ganti fixed-risk sizing ke FIXED NOTIONAL $50.
#                            Sebelumnya: qty = RISK / (entry × sl_pct)
#                            → notional bervariasi tergantung SL distance
#                            → posisi kecil/besar tidak konsisten, evaluasi
#                            sulit, psikologis tidak stabil.
#                            Sekarang: qty = FIXED_NOTIONAL_USDT / entry
#                            → SELALU buka posisi $50 (setelah precision ROUND_DOWN)
#                            → SL/TP tetap mengikuti S/R (tidak berubah)
#                            → P&L dalam % konsisten, lebih mudah dievaluasi
#
# [V7.4-S2  DUAL-TP-PRICE]  Dua harga TP yang BERBEDA (bukan satu harga dgn
#                            dua qty seperti sebelumnya):
#                            TP1: entry + 1× sl_dist (1:1 RR) — lebih dekat,
#                                 lebih mudah terkena, booking profit cepat
#                            TP2: entry + 2× sl_dist (2:1 RR) — lebih jauh,
#                                 biarkan profit berjalan
#                            Qty: 50% di TP1, 50% di TP2
#                            actual_rr minimum tetap 1.5× (berbasis TP2)
#
# [V7.4-S3  SL+-OTOMATIS]   Setelah TP1 hit, SL dipindah ke profit +1%
#                            dari entry secara otomatis. Mekanisme ini
#                            sudah ada (_check_tp1_hit) tapi sekarang lebih
#                            robust: cek flag be_sl_set, bukan hanya tp1_hit,
#                            sehingga tidak ada race condition antara be_monitor
#                            thread dan sync_account thread.
#
# [V7.4-S4  RR-CHECK]       actual_rr sekarang dihitung dari TP2 (bukan TP1)
#                            karena TP1 selalu 1:1 → actual_rr selalu ≈1.0
#                            yang akan selalu gagal rr_too_low check (≥1.5).
#
# Semua fix V7.3.1, V7.3, V7.2, V7.1, V7.0, V6.1 dipertahankan.
# ============================================================

# v3_swing_bot.py — V7.3
# ============================================================
# CHANGELOG V7.3 — DUAL ENTRY: VOLUME + BREAKOUT-RETEST (hasil diskusi mendalam
# dengan user tentang gaya trading personal: S/R untuk SL/TP, entry baik
# langsung di S/R maupun via breakout-retest, konfirmasi candle + volume):
#
# [V7.3-E1  JALUR-A]     Entry langsung di S/R (existing behavior) + konfirmasi
#                         tambahan: volume candle 4H terakhir RENDAH/netral
#                         (< 1.2x avg20 — JALUR_A_MAX_VOL_RATIO). Rasionalnya:
#                         volume rendah di S/R = market diam-diam menghormati
#                         level, BUKAN tekanan besar yang akan menembusnya —
#                         kebalikan logika dari breakout (Jalur B).
#                         Konfirmasi candle: rejection wick ≥38% (tidak berubah).
#
# [V7.3-E2  JALUR-B]     Entry via breakout-retest, alur 4 tahap:
#                         (1) detect_breakout_4h(): 2 candle 4H close di luar
#                             level. C1 (lebih awal, WAJIB) vol ≥1.5x avg20 —
#                             lebih penting/ketat. C2 (konfirmasi, lebih
#                             longgar) vol ≥1.2x avg20.
#                         (2) Breakout tervalidasi → simpan ke breakout_state
#                             (level, bias, timestamp), TIDAK langsung entry.
#                         (3) Tunggu retest: harga kembali dalam 1% dari level
#                             yang ditembus (RETEST_TOLERANCE_PCT). Window
#                             max 20 candle 4H (~3-4 hari, RETEST_MAX_CANDLES_4H)
#                             sebelum breakout dianggap hangus & dibuang.
#                         (4) Retest tercapai + rejection wick candle (logic
#                             sama dgn Jalur A) → entry. SL didasarkan pada
#                             breakout_level ± BREAKOUT_SL_BUFFER_PCT (0.75%,
#                             bukan support/resistance generik) — invalidasi
#                             breakout butuh ruang lebih dari sekadar noise.
#                         State di-clear SETELAH entry tervalidasi penuh
#                         (lolos semua filter SL/TP/RR) untuk mencegah
#                         double-entry dari breakout yang sama.
#
# [V7.3-E3  RSI-HAPUS]   Filter RSI dihapus total dari kedua jalur (konstanta
#                         dipertahankan sbg DEPRECATED, tidak ada logic yg baca).
#                         rsi15 masih dihitung sbg sentinel sanity-check data,
#                         bukan threshold filter lagi.
#
# [V7.3-E4  OI-HAPUS]    Filter OI (open interest) dihapus total dari kedua
#                         jalur (ENABLE_OI_FILTER=False, get_oi_change() tidak
#                         dipanggil lagi). Digantikan konfirmasi volume
#                         langsung dari klines — lebih reliable (data sudah
#                         ada, tidak perlu API call terpisah), dan tidak ada
#                         ambiguitas arah seperti OI (OI naik valid utk LONG
#                         tapi juga valid utk forced-covering SHORT).
#
# [V7.3-E5  STATE-MGMT]  breakout_state dict (thread-safe via breakout_state_lock)
#                         persisten ke disk (BREAKOUT_STATE_PATH) — bertahan
#                         lintas restart bot karena retest window bisa sampai
#                         20 candle 4H. load_breakout_state() dipanggil saat
#                         startup (run_forever). cleanup_expired_breakouts_
#                         housekeeping() dipanggil tiap main_cycle sbg jaring
#                         pengaman kedua (expiry presisi tetap di scan_pair()).
#
# [V7.3-E6  MARKET-STRUCT] market_structure_ok() (HH/HL utk LONG, LL/LH utk
#                         SHORT) sekarang jadi GATE BERSAMA untuk kedua jalur —
#                         termasuk sebelum breakout baru boleh terdeteksi.
#                         Breakout yang searah trend tapi melawan struktur
#                         lebih sering jadi fake move / corrective bounce.
#
# Semua fix V7.2 (V7.2-DYN1-5, V7.2.1-4), V7.1 (FIX1-6), V7.0 (V7-S1-S10),
# dan V6.1 (FIX-R1 s/d FIX-R5) dipertahankan.
# ============================================================
#
# CHANGELOG V7.3.1 — BUGFIX: simbol non-ASCII dari dynamic pair universe
# (ditemukan dari log produksi: pair "币安人生USDT" lolos ke PAIRS lalu
# crash UnicodeEncodeError di setiap fetch_klines):
#
# [V7.3.1-F1] refresh_dynamic_pairs(): tambah filter format simbol — hanya
#             terima [A-Z0-9]+ ASCII murni. Binance kadang punya kontrak
#             promosi dgn nama unicode yang lolos filter status/contractType/
#             quoteAsset tapi bikin urllib.urlopen() crash di semua titik
#             yang membangun URL dari simbol itu.
# [V7.3.1-F2] URL-encode simbol (urllib.parse.quote) di SEMUA titik pembangunan
#             URL berbasis simbol: fetch_klines, get_funding_rate, get_oi_change,
#             get_spread, get_orderbook_notional, validate_pairs_on_startup.
#             Pertahanan lapis kedua kalau ada simbol aneh lolos dari F1
#             (mis. lewat FALLBACK_STATIC_PAIRS manual atau --static-pairs).
# [V7.3.1-F3] validate_pairs_on_startup(): exception APAPUN (bukan cuma
#             HTTPError 400) sekarang menandai pair sebagai invalid.
#             Sebelumnya: exception non-HTTP (mis. UnicodeEncodeError) cuma
#             di-log tapi pair tetap dianggap valid — bot lalu mencoba pair
#             rusak itu setiap cycle, gagal dgn cara sama, selamanya.
# ============================================================

# v3_swing_bot.py — V7.2
# ============================================================
# CHANGELOG V7.2 — DYNAMIC PAIR UNIVERSE (diskusi & analisa profesional):
#
# [V7.2-DYN1 VOLUME-BASED]   List pair statis (PAIRS) digantikan oleh
#                              refresh_dynamic_pairs() — bot menarik daftar
#                              pair sendiri dari Binance /fapi/v1/ticker/24hr
#                              berdasarkan volume 24 jam real, bukan angka
#                              tetap (40/100/165) yang akan selalu basi
#                              karena ranking liquidity pasar berubah terus.
#
# [V7.2-DYN2 FILTERS]         Filter saat seleksi pair:
#                              - status TRADING, contractType PERPETUAL, quoteAsset USDT
#                              - volume 24h >= MIN_PAIR_VOLUME_USDT (default $15jt)
#                              - umur listing >= MIN_LISTING_AGE_DAYS (default 30 hari) —
#                                jaga history cukup untuk SR_LOOKBACK 100x4H (~17 hari)
#                              - dibatasi MAX_DYNAMIC_PAIRS (default 100) — jaga rate
#                                limit & waktu scan tetap masuk akal
#
# [V7.2-DYN3 REFRESH]         Refresh sekali per PAIRS_REFRESH_INTERVAL_SEC (24 jam).
#                              Dicek di run_forever() (startup) dan main_cycle()
#                              (tiap cycle, tapi MURAH — cache freshness check
#                              internal, hit API hanya kalau benar2 due).
#
# [V7.2-DYN4 SAFETY-NET]      Berlapis: cache disk → fallback ke cache lama kalau
#                              fetch gagal → fallback ke FALLBACK_STATIC_PAIRS (40
#                              pair) kalau belum ada cache sama sekali. CORE_PAIRS
#                              (BTC/ETH/SOL/BNB/XRP) selalu dipertahankan di hasil
#                              akhir meski ranking volume turun sesaat.
#
# [V7.2-DYN5 CLI-CONTROL]     CLI baru: --min-pair-volume, --max-pairs,
#                              --static-pairs (opt-out, pakai 40 pair statis saja).
#
# Rationale: filter strategi V7 (rejection candle, market structure, RSI sweet
# spot, time window) sudah sangat selektif. Membatasi pair ke angka kecil
# SEKALIGUS memperketat filter mengurangi peluang sinyal dari dua sisi. Dynamic
# universe memperluas permukaan peluang tanpa mengorbankan kualitas — pair
# dengan S/R tidak reliable (volume rendah) tetap tersingkir lewat volume floor,
# tapi tidak ada batas jumlah arbitrer yang membuang pair liquid yang sebenarnya layak.
#
# Semua fix V7.1 (V7.1-FIX1 s/d V7.1-FIX6), V7.0 (V7-S1 s/d V7-S10), dan
# V6.1 (FIX-R1 s/d FIX-R5) dipertahankan.
# ============================================================

import argparse
import json
import math
import os
import re
import time
import urllib.request
import urllib.error
import subprocess
import hmac
import hashlib
import urllib.parse
import ssl
import traceback
import threading
import tempfile
import shutil
import signal
from decimal import Decimal, ROUND_DOWN, ROUND_UP
from datetime import datetime, timezone, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed

from hybrid_ai_engine import (
    AITradeDecision,
    HybridAIConfig,
    HybridAIEngine,
    HybridAIError,
    HybridAIStateError,
)
from live_ai_market import (
    LiveAIMarketConfig,
    LiveAIMarketEngine,
    LiveAIMarketError,
)

# ---------------------- [V7.2] DYNAMIC PAIR UNIVERSE ----------------------
# Pengganti list pair statis. List statis (berapapun ukurannya) akan selalu
# basi — ranking liquidity pasar berubah terus, pair yang sekarang ramai
# bisa sepi bulan depan dan sebaliknya. Bot sekarang menarik daftar pair
# SENDIRI dari Binance berdasarkan volume 24 jam real, refresh berkala.
#
# Filter yang diterapkan:
# - status TRADING & contractType PERPETUAL & quoteAsset USDT
# - volume 24h >= MIN_PAIR_VOLUME_USDT (jaga kualitas S/R & orderflow)
# - umur listing >= MIN_LISTING_AGE_DAYS (jaga history cukup utk SR_LOOKBACK
#   100 candle x 4h = ~17 hari; pair API baru listing belum punya struktur)
# - dibatasi MAX_DYNAMIC_PAIRS (jaga rate limit & waktu scan tetap masuk akal)
ENABLE_DYNAMIC_PAIRS       = True
MIN_PAIR_VOLUME_USDT       = 15_000_000   # volume 24h minimum (USDT)
MIN_LISTING_AGE_DAYS       = 30
MAX_DYNAMIC_PAIRS          = 30
PAIRS_REFRESH_INTERVAL_SEC = 24 * 3600    # refresh sekali per 24 jam

# Blue chips yang SELALU dipertahankan di universe meski rankingnya turun
# sesaat — jaga-jaga dari anomali data ticker atau volume dip temporer.
CORE_PAIRS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"]

# ---------------------- [V8] LIVE QUALITY GATE ----------------------
# Evidence-based guard for Jalur A/B. The market direction is derived once per
# cycle from five liquid core contracts, while local quality is scored from
# confirmed 4H structure, EMA alignment, and 12h momentum.
ENABLE_QUALITY_GATE              = True
QUALITY_GATE_VERSION             = "V8.2-SR-TOUCH"
QUALITY_MARKET_CORE_PAIRS        = list(CORE_PAIRS)
QUALITY_MARKET_MIN_AGREEMENT     = 4
QUALITY_LOCAL_MIN_SCORE          = 2
QUALITY_MARKET_CACHE_SEC         = 300
QUALITY_SHORT_MIN_RANGE_POSITION = 0.40
QUALITY_MAX_SL_PCT               = 0.03

# Fallback statis — dipakai HANYA jika dynamic fetch gagal total dan belum
# ada cache sama sekali (mis. run pertama kali tanpa koneksi internet sesaat).
FALLBACK_STATIC_PAIRS = [
    "BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT",
    "ADAUSDT", "DOGEUSDT", "LINKUSDT", "AVAXUSDT", "DOTUSDT",
    "SUIUSDT", "APTUSDT", "ARBUSDT", "OPUSDT",
    "INJUSDT", "NEARUSDT", "ATOMUSDT", "TONUSDT", "WIFUSDT",
    "JUPUSDT", "ENAUSDT", "TIAUSDT", "STXUSDT", "LDOUSDT",
    "FTMUSDT", "ONDOUSDT", "HYPEUSDT", "PENDLEUSDT",
    "AAVEUSDT", "UNIUSDT", "GMXUSDT", "RUNEUSDT",
    "1000PEPEUSDT", "1000SHIBUSDT", "1000BONKUSDT",
    "FETUSDT", "RENDERUSDT", "TAOUSDT",
    "HBARUSDT", "KASUSDT", "MKRUSDT", "ICPUSDT",
]

# Hapus duplikat sambil pertahankan urutan
seen = set()
_dedup = []
for p in FALLBACK_STATIC_PAIRS:
    p = p.strip()
    if p and p not in seen:
        seen.add(p)
        _dedup.append(p)
FALLBACK_STATIC_PAIRS = _dedup

# PAIRS akan di-refresh oleh refresh_dynamic_pairs() saat startup (run_forever)
# dan dicek ulang tiap main_cycle() — nilai awal ini cuma fallback sementara
# sebelum fetch dynamic pertama berhasil.
PAIRS = list(FALLBACK_STATIC_PAIRS)

# ---------------------- [FIX-8] SECTOR MAP ----------------------
# Sector correlation guard: tolak jika sector yang sama sudah open
# Cegah double exposure di ecosystem / narrative yang sama
SECTOR_MAP = {
    # BTC ecosystem
    "BTCUSDT":    "btc",
    "ORDIUSDT":   "btc_eco",
    "1000RATSUSDT": "btc_eco",
    # ETH ecosystem
    "ETHUSDT":    "eth_eco",
    "ARBUSDT":    "eth_eco",
    "OPUSDT":     "eth_eco",
    "IMXUSDT":    "eth_eco",
    "STRKUSDT":   "eth_eco",
    "LDOUSDT":    "eth_eco",
    "MANTAUSDT":  "eth_eco",
    "WUSDT":      "eth_eco",
    "EIGENUSDT":  "eth_eco",
    # Solana ecosystem
    "SOLUSDT":    "sol_eco",
    "JUPUSDT":    "sol_eco",
    "PYTHUSDT":   "sol_eco",
    "BOMEUSDT":   "sol_eco",
    "RNDRUSDT":   "sol_eco",
    # BNB ecosystem
    "BNBUSDT":    "bnb_eco",
    # DeFi
    "AAVEUSDT":   "defi",
    "UNIUSDT":    "defi",
    "CRVUSDT":    "defi",
    "MKRUSDT":    "defi",
    "PENDLEUSDT": "defi",
    "GMXUSDT":    "defi",
    "DYDXUSDT":   "defi",
    "RUNEUSDT":   "defi",
    "STGUSDT":    "defi",
    "LQTYUSDT":   "defi",
    # Meme coins
    "DOGEUSDT":       "meme",
    "1000PEPEUSDT":   "meme",
    "1000SHIBUSDT":   "meme",
    "1000BONKUSDT":   "meme",
    "1000FLOKIUSDT":  "meme",
    "MEMEUSDT":       "meme",
    "WIFUSDT":        "meme",
    "NOTUSDT":        "meme",
    "DOGSUSDT":       "meme",
    # AI narrative
    "FETUSDT":    "ai",
    "RENDERUSDT": "ai",
    "AGIXUSDT":   "ai",
    "NMRUSDT":    "ai",
    "AIUSDT":     "ai",
    # Layer 1 alts
    "ADAUSDT":    "l1",
    "DOTUSDT":    "l1",
    "AVAXUSDT":   "l1",
    "ATOMUSDT":   "l1",
    "NEARUSDT":   "l1",
    "APTUSDT":    "l1",
    "SUIUSDT":    "l1",
    "SEIUSDT":    "l1",
    "TONUSDT":    "l1",
    "FTMUSDT":    "l1",
    "INJUSDT":    "l1",
    "ICPUSDT":    "l1",
}
ENABLE_SECTOR_FILTER = True   # [FIX-8] aktifkan sector correlation guard

# ---------------------- CONFIG ----------------------
INTERVAL_SCAN  = "15m"
INTERVAL_TREND = "4h"
LIMIT = 200

# Indicator periods
RSI_PERIOD = 14
EMA_FAST   = 21
EMA_SLOW   = 55
ATR_PERIOD = 14
ATR_MULT   = 2.5    # [V7-S8] was 2.0 → lebih longgar untuk toleransi wick 15m

# Filter
PULLBACK_TOLERANCE_LONG  = 1.020
PULLBACK_TOLERANCE_SHORT = 0.980
NEAR_LEVEL_TOLERANCE     = 0.025   # [V7-S2] was 0.015 → 2.5% tolerance untuk 4H S/R
ENTRY_REACHABLE_PCT      = 0.010   # deprecated di V7, tidak dipakai di entry logic baru

# [V7.3-E3] DEPRECATED — RSI tidak lagi dipakai sebagai filter entry (dihapus
# dari scan_pair). Konstanta dipertahankan agar tidak ada referensi lain yang
# patah, tapi tidak ada logic yang membacanya lagi.
RSI_LONG_MIN  = 40   # DEPRECATED V7.3
RSI_LONG_MAX  = 62   # DEPRECATED V7.3
RSI_SHORT_MIN = 38   # DEPRECATED V7.3
RSI_SHORT_MAX = 60   # DEPRECATED V7.3

# S/R — [V7-S2] S/R sekarang dihitung dari candles_4H
# 100 candle × 4h = 400 jam = ~17 hari history → S/R yang direspek institutional
SR_LOOKBACK    = 100   # was 40 (15m) → sekarang untuk 4h candles
SR_TOUCH_TOL   = 0.008 # was 0.005 → lebih longgar untuk 4h price action
SR_MIN_TOUCHES = 3     # was 2 → 3 touches pada 4H lebih signifikan

# [V7-S7] Time filter: skip Asian dead zone (likuiditas rendah 40-60%)
# [V7.2.4] Dijadikan toggle atas permintaan user — bot dijalankan 24 jam.
# Set True lagi kapan saja kalau mau aktifkan filter jam dead zone.
ENABLE_TIME_FILTER     = False
TRADING_HOUR_START_UTC = 7    # mulai aktif scan jam 07:00 UTC (dipakai kalau ENABLE_TIME_FILTER=True)
TRADING_HOUR_END_UTC   = 23   # stop jam 23:00 UTC (00:00-07:00 = dead zone)

# Orderflow — [V7-S6] lookback diperlebar signifikan
ORDERFLOW_LOOKBACK          = 8    # was 3 (45m) → 8 candle = 2 jam, lebih representatif
ORDERFLOW_BASELINE_LOOKBACK = 20   # was 10 → 20 candle baseline lebih stabil
ORDERFLOW_MIN_RATIO         = 0.56 # was 0.54 → threshold lebih ketat
ORDERFLOW_SPIKE_MULT        = 1.3  # was 1.2 → spike harus lebih jelas

# Rejection candle — [V7-S3]
REJECTION_WICK_MIN_RATIO = 0.38  # lower/upper wick harus >= 38% dari total range candle

# Regime filter
REGIME_MIN_ATR_PCT = 0.001
REGIME_MIN_SLOPE   = 0.0001

# Funding Rate filter — [V7-S9] diperketat dari 0.10% ke 0.03%
FUNDING_RATE_MAX_LONG  =  0.0003  # was 0.0010 → crowded long jika > 0.03%
FUNDING_RATE_MIN_SHORT = -0.0003  # was -0.0010 → crowded short jika < -0.03%
ENABLE_FUNDING_FILTER  = True

# [V7.3-E4] DEPRECATED — OI (open interest) tidak lagi dipakai sebagai filter
# entry. Digantikan oleh konfirmasi volume dari klines langsung (lebih reliable,
# tidak butuh API call terpisah, tidak ada ambiguitas arah seperti OI).
OI_CHANGE_MIN_PCT   = 0.0003  # DEPRECATED V7.3
ENABLE_OI_FILTER    = False   # DEPRECATED V7.3 — dimatikan, tidak dipanggil lagi di scan_pair

# ---------------------- [V7.3] DUAL ENTRY: VOLUME + BREAKOUT-RETEST ----------------------
# Menggantikan RSI/OI dengan dua jalur entry berbasis price action + volume:
#
# JALUR A — entry langsung di S/R (existing), confirm tambahan: volume RENDAH.
#   Volume rendah/netral di S/R = market diam-diam menghormati level, bukan
#   tekanan besar yang akan menembusnya. Kebalikan logika dari breakout.
#
# JALUR B — breakout-retest: level ditembus dulu (volume tinggi, 2 candle 4H),
#   simpan state, tunggu retest, baru entry saat retest dengan rejection candle.
VOLUME_AVG_LOOKBACK       = 20      # candle 4H untuk baseline rata-rata volume
JALUR_A_MAX_VOL_RATIO     = 1.2     # Jalur A: vol candle 4H terakhir < 1.2x avg20 (rendah/netral)
ENABLE_JALUR_A_VOLUME_SHADOW = False  # Hipotesis volume tinggi sudah ditolak dan diarsipkan
BREAKOUT_C1_MIN_VOL_RATIO = 1.5     # candle breakout PERTAMA (wajib, lebih penting)
BREAKOUT_C2_MIN_VOL_RATIO = 1.2     # candle breakout KEDUA (konfirmasi, lebih longgar)
BREAKOUT_LEVEL_BUFFER_PCT = 0.003   # close harus 0.3% di luar level — bukan noise candle
RETEST_TOLERANCE_PCT      = 0.01    # toleransi retest ke level yang ditembus: 1%
RETEST_MAX_CANDLES_4H     = 20      # window retest max (~3-4 hari di 4H) sebelum hangus
BREAKOUT_SL_BUFFER_PCT    = 0.0075  # buffer SL Jalur B: 0.75% (rentang 0.5-1% sesuai diskusi)
STRATEGY_B_VERSION        = 2
# Audit 90 hari 2026-07-22: implementasi lama tidak dapat membuat breakout
# baru karena level memasukkan candle C1/C2. Referensi level sudah diperbaiki,
# tetapi kandidat yang benar belum menunjukkan edge stabil pada validation set.
ENABLE_STRATEGY_B_LIVE    = False
# BREAKOUT_STATE_PATH didefinisikan di bawah, setelah JOURNAL_PATH ada (hindari NameError)

# ---------------------- [V7.3.2] SHADOW SIGNAL TRACKING ----------------------
# Mencatat sinyal "near-miss" — lolos semua syarat KECUALI satu filter spesifik
# yang sedang diuji — tanpa benar-benar eksekusi ke Binance. Tujuan: validasi
# empiris apakah suatu filter benar menambah edge (winrate shadow trade jelek)
# atau cuma mempersempit tanpa alasan kuat (winrate shadow trade bagus, berarti
# filter itu membuang sinyal yang sebenarnya valid).
#
# Scope V1: HANYA filter volume Jalur A (JALUR_A_MAX_VOL_RATIO). Filter lain
# bisa ditambahkan ke daftar trackable di masa depan dengan pola yang sama.
ENABLE_SHADOW_TRACKING = True
SHADOW_DAILY_REPORT_ENABLED = False  # Statistik shadow hanya melalui command /shadow
C6_FORWARD_MIN_CLOSED = 30
SHADOW_TIMEOUT_HOURS   = 7 * 24   # 1 minggu — kalau SL/TP belum kena, ditutup sbg timeout
# SHADOW_TRADES_PATH didefinisikan di bawah, setelah JOURNAL_PATH ada

# ---------------------- SMART MONEY SHADOW RESEARCH ----------------------
# Jalur C tetap shadow-only. C6 Market Strict lolos development 90 hari dan
# holdout 180 hari, tetapi wajib mengumpulkan forward shadow sample sebelum
# dipertimbangkan untuk live. Posisi shadow lama tetap dipantau sampai selesai.
# Jalur C v2 memakai urutan wajib:
# 4H location -> 15m liquidity sweep -> displacement/MSS -> narrow retest
# -> structural liquidity target. Tidak pernah membuka order real.
SMART_MONEY_C_VERSION       = 2
ENABLE_SMART_MONEY_C_SHADOW = False
SMC_SWEEP_LOOKBACK_15M      = 32
SMC_SETUP_MAX_AGE_15M       = 8
SMC_MSS_LOOKBACK_15M        = 12
SMC_MSS_CONFIRM_WINDOW      = 4
SMC_RETEST_TOLERANCE_PCT    = 0.002
SMC_SWEEP_VOL_RATIO_MIN     = 1.8
SMC_SWEEP_BUFFER_PCT        = 0.0008
SMC_SWEEP_MAX_PENETRATION_PCT = 0.015
SMC_SWEEP_WICK_MIN_RATIO    = 0.40
SMC_SL_BUFFER_PCT           = 0.002
SMC_MIN_RR                  = 1.7
SMC_LOCATION_LOOKBACK_4H    = 30
SMC_LOCATION_TOLERANCE_PCT  = 0.006
SMC_PREMIUM_DISCOUNT_PCT    = 0.35
SMC_DISPLACEMENT_BODY_MIN_RATIO = 0.50
SMC_DISPLACEMENT_BODY_MULT  = 1.20
SMC_DISPLACEMENT_VOL_RATIO_MIN = 1.20
SMC_MSS_BREAK_BUFFER_PCT    = 0.0005
SMC_MAX_ZONE_WIDTH_PCT      = 0.006
SMC_REQUIRE_FVG             = True
SMC_FVG_MIN_PCT             = 0.0005
SMC_TARGET_BUFFER_PCT       = 0.001

# Strategy C v3 remains shadow-only. It keeps sweep/location mandatory, but
# treats displacement as a scored confirmation and FVG as confluence instead
# of requiring every textbook element at once.
SMC_V3_SWEEP_LOOKBACK_15M       = 32
SMC_V3_SETUP_MAX_AGE_15M        = 16
SMC_V3_MSS_LOOKBACK_15M         = 12
SMC_V3_MSS_CONFIRM_WINDOW       = 6
SMC_V3_SWEEP_VOL_RATIO_MIN      = 1.60
SMC_V3_SWEEP_WICK_MIN_RATIO     = 0.35
SMC_V3_DISPLACEMENT_MIN_SCORE   = 2
SMC_V3_RETEST_TOLERANCE_PCT     = 0.003
SMC_V3_MAX_ZONE_WIDTH_PCT       = 0.010
SMC_V3_MAX_ENTRY_EXTENSION_PCT  = 0.006
SMC_V3_MIN_RR                   = 1.70
SMC_V3_COUNTERTREND_EXTREME_PCT = 0.20

# Strategy C6 Market Strict (shadow-only): trend-aligned pullback liquidity
# sweep -> opposing-flow absorption -> MSS displacement -> retest, ditambah
# guard arah/return BTC 4H. Nilai ini dibekukan dari audit 2026-07-22.
SMC_C6_SWEEP_LOOKBACK_15M       = 24
SMC_C6_SEARCH_BARS_15M          = 20
SMC_C6_ABSORPTION_MIN           = 0.55
SMC_C6_MSS_FLOW_MIN             = 0.52
SMC_C6_MSS_BODY_MIN_RATIO       = 0.55
SMC_C6_MAX_FAST_DISTANCE_ATR    = 0.60
SMC_C6_TARGET_R                 = 1.50
SMC_C6_TIMEOUT_HOURS            = 96
SMC_C6_MIN_RISK_PCT             = 0.004
SMC_C6_MAX_RISK_PCT             = 0.030

# Risk & sizing — [V7.4-S1] FIXED NOTIONAL menggantikan fixed-risk sizing
# qty = FIXED_NOTIONAL_USDT / entry — SELALU buka posisi $50 (setelah ROUND_DOWN)
# SL/TP tetap mengikuti S/R, tidak berubah.
# RISK_PER_TRADE_USDT dipertahankan untuk Telegram report & backward compat.
FIXED_NOTIONAL_USDT   = 50.0  # selalu buka posisi $50
RISK_PER_TRADE_USDT   = 0.50  # informasional saja (dipakai di report/log, bukan sizing)
RR                    = 2.0
MAX_CONCURRENT_TRADES = 11
LEVERAGE              = 3
MAX_EXPOSURE_MULT     = 4
MIN_BOOK_NOTIONAL     = 10000
BOOK_DEPTH_LIMIT      = 5

# Entry gap filter — deprecated di V7 (digantikan logic baru), nilai tidak dipakai
ENTRY_GAP_MAX_PCT = 0.005

# SL/TP buffer constants
SR_BUF_SL   = 0.008
SR_BUF_TP   = 0.010

# Timeout & stale trade
PENDING_ORDER_TIMEOUT_MIN = 30
STALE_TRADE_CANDLES       = 16

# [V7.4-S2] Dual TP — dua harga berbeda, bukan satu harga dgn split qty
# TP1: 1:1 dari sl_dist → lebih dekat, lebih mudah kena, booking profit cepat
# TP2: 2:1 dari sl_dist → biarkan sisa profit berjalan lebih jauh
# Qty: 50/50 untuk kedua TP
TP1_RR            = 1.0    # TP1 di 1× sl_dist dari entry
TP2_RR            = 2.0    # TP2 di 2× sl_dist dari entry
TP1_QTY_PCT       = 0.50   # 50% posisi tutup di TP1
TP2_QTY_PCT       = 0.50   # 50% posisi lanjut ke TP2
# Alias backward compat (beberapa tempat masih pakai nama lama)
TP1_PCT           = 0.50
TP2_PCT           = 0.50
ENABLE_PARTIAL_TP = True
TP1_HIT_THRESHOLD = 0.70   # qty tersisa ≤70% → TP1 hit (toleransi ROUND_DOWN rounding)

# Sideways filter
SIDEWAYS_EMA_BAND_PCT = 0.005

# Execution
SPREAD_MAX_PCT  = 0.015
FEE_PCT         = 0.0004
SLIPPAGE_PCT    = 0.0005
MIN_STOP_PCT    = 0.003   # [V7-S8] was 0.002 → minimum SL 0.3% (was 0.2%)
LIMIT_TIMEOUT_MIN = 30

# Safety
DAILY_LOSS_LIMIT_R = -6

# Cooldowns
COOLDOWN_MIN              = 20
COOLDOWN_MIN_VOLATILE     = 5
COOLDOWN_AFTER_LOSS_MIN   = 240
ATR_VOLATILE_PCT          = 0.003
SWEEP_VOLUME_MULT         = 2.0
SWEEP_COOLDOWN_MIN        = 120

# [BUGFIX] Batas jumlah posisi terbuka untuk pair yang sama.
# Default 1 untuk mencegah double-entry/averaging tidak sengaja.
# Jika averaging memang diinginkan, naikkan manual ke 2; sync PnL agregat
# di bawah tetap akan membagi realized PnL proporsional per entry.
MAX_SAME_PAIR_OPEN = 1

# Max signal per arah per cycle
MAX_LONG_PER_CYCLE  = 2
MAX_SHORT_PER_CYCLE = 2

# Paths
DATA_DIR = os.path.abspath(os.getenv("KT_BOT_DATA_DIR", os.path.join(os.path.dirname(__file__), "data")))
JOURNAL_PATH      = os.path.join(DATA_DIR, 'journal_v3.json')
LOG_PATH          = os.path.join(DATA_DIR, 'scan_v3.log')
LOG_MAX_BYTES     = 10 * 1024 * 1024
LOG_ROTATE_KEEP   = 2
REPORT_STATE_PATH = os.path.join(DATA_DIR, 'daily_report_state_v3.json')
HEARTBEAT_PATH    = os.path.join(DATA_DIR, 'heartbeat_v3.txt')
CONFIG_PATH       = os.getenv("KT_BOT_CONFIG", os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json"))
USER_REGISTRY_PATH = os.path.join(DATA_DIR, 'user_registry_v1.json')
# [V7.3] State persisten breakout pending-retest — bertahan lintas restart bot
# karena retest window bisa sampai 20 candle 4H (~3-4 hari).
BREAKOUT_STATE_PATH = os.path.join(DATA_DIR, 'breakout_state_v3.json')
# [V7.3.2] State persisten shadow trade tracking — sama pola dgn breakout_state.
SHADOW_TRADES_PATH = os.path.join(DATA_DIR, 'shadow_trades_v3.json')
D1_SHADOW_STATE_PATH = os.path.join(DATA_DIR, "d1_forward_shadow_state.json")
JOURNAL_BACKUP_DIR = os.path.join(os.path.dirname(JOURNAL_PATH), "backups")
ENABLE_STARTUP_AUDIT = True
ENABLE_ORPHAN_ORDER_AUDIT = False
ENABLE_PROFIT_SL_PLUS = True
PROFIT_SL_PLUS_TRIGGER_PCT = 0.015
PROFIT_SL_PLUS_LOCK_PCT = 0.01
AUDIT_ALERT_COOLDOWN_SEC = 6 * 3600
JOURNAL_BACKUP_MIN_INTERVAL_SEC = 6 * 3600
SYNC_SUMMARY_LOG_INTERVAL_SEC = 30 * 60
TERMINAL_CYCLE_LOG_ENABLED = False
LOG_QUIET_MODE = True
LOG_SCAN_DONE_INTERVAL_SEC = 60 * 60

# [FIX-2] Telegram via HTTP API langsung — tidak butuh openclaw/subprocess
# Set via: env var TELEGRAM_BOT_TOKEN  atau  CLI --telegram-token
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TARGET_CHAT_ID     = os.getenv("TELEGRAM_CHAT_ID", "")
ADMIN_CHAT_IDS     = [TARGET_CHAT_ID] if TARGET_CHAT_ID else []
DEFAULT_TRIAL_DAYS = 7
TELEGRAM_COMMANDS_ENABLED = True
BASE_URL           = "https://fapi.binance.com"
BOT_TAG            = "V7.4-SWING"
PUBLIC_VPS_IP      = os.getenv("KT_PUBLIC_VPS_IP", "")
D1_TELEGRAM_COMMAND_VERSION = "D1.0"
D1_SHADOW_SCHEMA = "KT_STRATEGY_D1_FORWARD_SHADOW_V1"
D1_FORWARD_MIN_TRADES = 30
D1_FORWARD_MIN_DAYS = 270
D1_FORWARD_MIN_PF = 1.15
D1_FORWARD_MAX_DD_R = 12.0
D1_SHADOW_HEALTHY_SEC = 45 * 60
D1_SHADOW_DELAYED_SEC = 120 * 60

# Features
ENABLE_REGIME_FILTER     = True
ENABLE_ORDERFLOW_CONFIRM = True
ENABLE_PULLBACK_ENTRY    = True
ENABLE_SWEEP_DETECTION   = True

# Pullback offset
PULLBACK_OFFSET_TICKS = 1

# Rate limit
REQUESTS_PER_MIN = 120
MIN_INTERVAL_BETWEEN_REQUESTS = 60.0 / REQUESTS_PER_MIN

# Runtime globals
TIME_OFFSET_MS    = 0
SIMULATE          = False
MAX_WORKERS       = 8
SYMBOL_FILTERS_CACHE = {}
sweep_cooldowns   = {}
journal_lock      = threading.Lock()
be_action_lock    = threading.Lock()
rate_lock         = threading.Lock()
last_request_time = 0.0
journal           = []
open_trades       = 0
open_trades_lock  = threading.Lock()
INVALID_PAIRS     = set()
invalid_pairs_lock = threading.Lock()
ENTRY_PAUSED      = False
last_journal_backup_at = {}
last_sync_summary_log_at = 0.0
last_sync_summary_key = None
last_log_throttle_at = {}

# [V7.3] Breakout-retest state — key: "{pair}:{bias}" -> dict
# {"level": float, "detected_open_time": int(ms), "detected_at": int(ms),
#  "c1_vol_ratio": float, "c2_vol_ratio": float}
breakout_state      = {}
breakout_state_lock = threading.Lock()

# [V7.3.2] Shadow trade tracking — list of dict, persisten ke SHADOW_TRADES_PATH
shadow_trades      = []
shadow_trades_lock = threading.Lock()
quality_market_cache = {"fetched_at": 0.0, "result": None}
quality_market_cache_lock = threading.Lock()
CONFIG_DATA        = {}
PROJECT_DIR       = os.path.dirname(os.path.abspath(__file__))
USERS_DIR         = os.path.join(PROJECT_DIR, "users")
hybrid_ai_engine_instance = None
hybrid_ai_engine_lock = threading.Lock()
hybrid_ai_execution_lock = threading.Lock()
live_ai_market_engine_instance = None
live_ai_market_engine_lock = threading.Lock()
live_ai_market_thread_lock = threading.Lock()
live_ai_market_thread_started = False

# ---------------------- CONFIG FILE OVERRIDES ----------------------
def _load_config_overrides():
    """
    Optional config.json agar user tidak perlu mengedit script langsung.
    Env var/CLI tetap bisa override nilai sensitif seperti API key dan token.
    """
    global JOURNAL_PATH, LOG_PATH, LOG_MAX_BYTES, LOG_ROTATE_KEEP, REPORT_STATE_PATH, HEARTBEAT_PATH
    global BREAKOUT_STATE_PATH, SHADOW_TRADES_PATH, D1_SHADOW_STATE_PATH, JOURNAL_BACKUP_DIR
    global TELEGRAM_BOT_TOKEN, TARGET_CHAT_ID, BASE_URL, BOT_TAG
    global ADMIN_CHAT_IDS, DEFAULT_TRIAL_DAYS, TELEGRAM_COMMANDS_ENABLED, USER_REGISTRY_PATH
    global FIXED_NOTIONAL_USDT, RISK_PER_TRADE_USDT, LEVERAGE
    global MAX_CONCURRENT_TRADES, MAX_SAME_PAIR_OPEN, DAILY_LOSS_LIMIT_R
    global ENABLE_DYNAMIC_PAIRS, MIN_PAIR_VOLUME_USDT, MAX_DYNAMIC_PAIRS
    global ENABLE_QUALITY_GATE, QUALITY_MARKET_MIN_AGREEMENT
    global QUALITY_LOCAL_MIN_SCORE, QUALITY_MARKET_CACHE_SEC
    global QUALITY_SHORT_MIN_RANGE_POSITION, QUALITY_MAX_SL_PCT
    global ENABLE_JALUR_A_VOLUME_SHADOW
    global STRATEGY_B_VERSION, ENABLE_STRATEGY_B_LIVE
    global SMART_MONEY_C_VERSION, ENABLE_SMART_MONEY_C_SHADOW
    global SHADOW_DAILY_REPORT_ENABLED
    global SMC_SWEEP_VOL_RATIO_MIN, SMC_RETEST_TOLERANCE_PCT
    global SMC_SWEEP_LOOKBACK_15M, SMC_SETUP_MAX_AGE_15M, SMC_MSS_LOOKBACK_15M
    global SMC_MSS_CONFIRM_WINDOW, SMC_MIN_RR, SMC_SWEEP_BUFFER_PCT
    global SMC_SWEEP_MAX_PENETRATION_PCT, SMC_SWEEP_WICK_MIN_RATIO, SMC_SL_BUFFER_PCT
    global SMC_LOCATION_LOOKBACK_4H, SMC_LOCATION_TOLERANCE_PCT, SMC_PREMIUM_DISCOUNT_PCT
    global SMC_DISPLACEMENT_BODY_MIN_RATIO, SMC_DISPLACEMENT_BODY_MULT
    global SMC_DISPLACEMENT_VOL_RATIO_MIN, SMC_MSS_BREAK_BUFFER_PCT
    global SMC_MAX_ZONE_WIDTH_PCT, SMC_REQUIRE_FVG, SMC_FVG_MIN_PCT, SMC_TARGET_BUFFER_PCT
    global SMC_V3_SWEEP_LOOKBACK_15M, SMC_V3_SETUP_MAX_AGE_15M
    global SMC_V3_MSS_LOOKBACK_15M, SMC_V3_MSS_CONFIRM_WINDOW
    global SMC_V3_SWEEP_VOL_RATIO_MIN, SMC_V3_SWEEP_WICK_MIN_RATIO
    global SMC_V3_DISPLACEMENT_MIN_SCORE, SMC_V3_RETEST_TOLERANCE_PCT
    global SMC_V3_MAX_ZONE_WIDTH_PCT, SMC_V3_MAX_ENTRY_EXTENSION_PCT
    global SMC_V3_MIN_RR, SMC_V3_COUNTERTREND_EXTREME_PCT
    global ENABLE_TIME_FILTER, ENABLE_STARTUP_AUDIT, ENABLE_ORPHAN_ORDER_AUDIT
    global ENABLE_PROFIT_SL_PLUS, PROFIT_SL_PLUS_TRIGGER_PCT, PROFIT_SL_PLUS_LOCK_PCT
    global AUDIT_ALERT_COOLDOWN_SEC, JOURNAL_BACKUP_MIN_INTERVAL_SEC
    global SYNC_SUMMARY_LOG_INTERVAL_SEC, TERMINAL_CYCLE_LOG_ENABLED
    global LOG_QUIET_MODE, LOG_SCAN_DONE_INTERVAL_SEC
    global CONFIG_DATA

    if not CONFIG_PATH or not os.path.exists(CONFIG_PATH):
        return

    try:
        with open(CONFIG_PATH, "r", encoding="utf-8-sig") as f:
            cfg = json.load(f)
    except Exception as e:
        print(f"WARNING: config load failed: {e}")
        return
    CONFIG_DATA = cfg

    paths = cfg.get("paths", {}) if isinstance(cfg.get("paths"), dict) else {}
    JOURNAL_PATH      = os.path.expandvars(paths.get("journal_path", JOURNAL_PATH))
    LOG_PATH          = os.path.expandvars(paths.get("log_path", LOG_PATH))
    LOG_MAX_BYTES     = int(paths.get("log_max_bytes", LOG_MAX_BYTES))
    LOG_ROTATE_KEEP   = int(paths.get("log_rotate_keep", LOG_ROTATE_KEEP))
    REPORT_STATE_PATH = os.path.expandvars(paths.get("report_state_path", REPORT_STATE_PATH))
    HEARTBEAT_PATH    = os.path.expandvars(paths.get("heartbeat_path", HEARTBEAT_PATH))
    USER_REGISTRY_PATH = os.path.expandvars(paths.get("user_registry_path", USER_REGISTRY_PATH))
    BREAKOUT_STATE_PATH = os.path.expandvars(paths.get("breakout_state_path", BREAKOUT_STATE_PATH))
    SHADOW_TRADES_PATH  = os.path.expandvars(paths.get("shadow_trades_path", SHADOW_TRADES_PATH))
    D1_SHADOW_STATE_PATH = os.path.expandvars(
        paths.get("d1_shadow_state_path", D1_SHADOW_STATE_PATH)
    )
    JOURNAL_BACKUP_DIR  = os.path.expandvars(paths.get("journal_backup_dir", JOURNAL_BACKUP_DIR))

    telegram = cfg.get("telegram", {}) if isinstance(cfg.get("telegram"), dict) else {}
    TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", telegram.get("bot_token", TELEGRAM_BOT_TOKEN))
    TARGET_CHAT_ID = str(telegram.get("chat_id", TARGET_CHAT_ID))
    _admin_ids = telegram.get("admin_chat_ids", ADMIN_CHAT_IDS)
    if isinstance(_admin_ids, list):
        ADMIN_CHAT_IDS = [str(x) for x in _admin_ids if str(x).strip()]
    elif _admin_ids:
        ADMIN_CHAT_IDS = [str(_admin_ids)]
    if TARGET_CHAT_ID and TARGET_CHAT_ID not in ADMIN_CHAT_IDS:
        ADMIN_CHAT_IDS.append(TARGET_CHAT_ID)
    DEFAULT_TRIAL_DAYS = int(telegram.get("default_trial_days", DEFAULT_TRIAL_DAYS))
    TELEGRAM_COMMANDS_ENABLED = bool(telegram.get("enable_commands", TELEGRAM_COMMANDS_ENABLED))

    binance = cfg.get("binance", {}) if isinstance(cfg.get("binance"), dict) else {}
    BASE_URL = str(binance.get("base_url", BASE_URL))

    product = cfg.get("product", {}) if isinstance(cfg.get("product"), dict) else {}
    BOT_TAG = str(product.get("bot_tag", BOT_TAG))

    risk = cfg.get("risk", {}) if isinstance(cfg.get("risk"), dict) else {}
    FIXED_NOTIONAL_USDT = float(risk.get("fixed_notional_usdt", FIXED_NOTIONAL_USDT))
    RISK_PER_TRADE_USDT = float(risk.get("risk_per_trade_usdt", RISK_PER_TRADE_USDT))
    LEVERAGE = int(risk.get("leverage", LEVERAGE))
    MAX_CONCURRENT_TRADES = int(risk.get("max_concurrent_trades", MAX_CONCURRENT_TRADES))
    MAX_SAME_PAIR_OPEN = int(risk.get("max_same_pair_open", MAX_SAME_PAIR_OPEN))
    DAILY_LOSS_LIMIT_R = float(risk.get("daily_loss_limit_r", DAILY_LOSS_LIMIT_R))

    universe = cfg.get("universe", {}) if isinstance(cfg.get("universe"), dict) else {}
    ENABLE_DYNAMIC_PAIRS = bool(universe.get("enable_dynamic_pairs", ENABLE_DYNAMIC_PAIRS))
    MIN_PAIR_VOLUME_USDT = float(universe.get("min_pair_volume_usdt", MIN_PAIR_VOLUME_USDT))
    MAX_DYNAMIC_PAIRS = int(universe.get("max_dynamic_pairs", MAX_DYNAMIC_PAIRS))

    quality = cfg.get("strategy_quality", {}) if isinstance(cfg.get("strategy_quality"), dict) else {}
    ENABLE_QUALITY_GATE = bool(quality.get("enable", ENABLE_QUALITY_GATE))
    QUALITY_MARKET_MIN_AGREEMENT = max(1, min(
        len(QUALITY_MARKET_CORE_PAIRS),
        int(quality.get("market_min_agreement", QUALITY_MARKET_MIN_AGREEMENT)),
    ))
    QUALITY_LOCAL_MIN_SCORE = max(1, min(
        3,
        int(quality.get("local_min_score", QUALITY_LOCAL_MIN_SCORE)),
    ))
    QUALITY_MARKET_CACHE_SEC = max(
        60,
        int(quality.get("market_cache_sec", QUALITY_MARKET_CACHE_SEC)),
    )
    QUALITY_SHORT_MIN_RANGE_POSITION = max(0.0, min(
        1.0,
        float(quality.get("short_min_range_position", QUALITY_SHORT_MIN_RANGE_POSITION)),
    ))
    QUALITY_MAX_SL_PCT = max(
        0.005,
        float(quality.get("max_sl_pct", QUALITY_MAX_SL_PCT)),
    )

    strategy_a = cfg.get("strategy_a", {}) if isinstance(cfg.get("strategy_a"), dict) else {}
    ENABLE_JALUR_A_VOLUME_SHADOW = bool(strategy_a.get(
        "enable_volume_shadow",
        ENABLE_JALUR_A_VOLUME_SHADOW,
    ))

    strategy_b = cfg.get("strategy_b", {}) if isinstance(cfg.get("strategy_b"), dict) else {}
    STRATEGY_B_VERSION = max(1, int(strategy_b.get("version", STRATEGY_B_VERSION)))
    ENABLE_STRATEGY_B_LIVE = bool(strategy_b.get("enable_live", ENABLE_STRATEGY_B_LIVE))

    smc = cfg.get("smart_money_c", {}) if isinstance(cfg.get("smart_money_c"), dict) else {}
    SMART_MONEY_C_VERSION = max(1, int(smc.get("version", SMART_MONEY_C_VERSION)))
    ENABLE_SMART_MONEY_C_SHADOW = bool(smc.get("enable_shadow", ENABLE_SMART_MONEY_C_SHADOW))
    SHADOW_DAILY_REPORT_ENABLED = bool(smc.get(
        "enable_daily_report",
        SHADOW_DAILY_REPORT_ENABLED,
    ))
    # Config Strategy C v1 memiliki nama parameter yang sama tetapi makna dan
    # threshold berbeda. Hanya config version 2 yang boleh override engine v2;
    # config lama otomatis memakai default v2 yang aman.
    if SMART_MONEY_C_VERSION >= 2:
        SMC_SWEEP_LOOKBACK_15M = int(smc.get("sweep_lookback_15m", SMC_SWEEP_LOOKBACK_15M))
        SMC_SETUP_MAX_AGE_15M = int(smc.get("setup_max_age_15m", SMC_SETUP_MAX_AGE_15M))
        SMC_MSS_LOOKBACK_15M = int(smc.get("mss_lookback_15m", SMC_MSS_LOOKBACK_15M))
        SMC_MSS_CONFIRM_WINDOW = int(smc.get("mss_confirm_window", SMC_MSS_CONFIRM_WINDOW))
        SMC_SWEEP_VOL_RATIO_MIN = float(smc.get("sweep_vol_ratio_min", SMC_SWEEP_VOL_RATIO_MIN))
        SMC_SWEEP_BUFFER_PCT = float(smc.get("sweep_buffer_pct", SMC_SWEEP_BUFFER_PCT))
        SMC_SWEEP_MAX_PENETRATION_PCT = float(smc.get("sweep_max_penetration_pct", SMC_SWEEP_MAX_PENETRATION_PCT))
        SMC_SWEEP_WICK_MIN_RATIO = float(smc.get("sweep_wick_min_ratio", SMC_SWEEP_WICK_MIN_RATIO))
        SMC_RETEST_TOLERANCE_PCT = float(smc.get("retest_tolerance_pct", SMC_RETEST_TOLERANCE_PCT))
        SMC_SL_BUFFER_PCT = float(smc.get("sl_buffer_pct", SMC_SL_BUFFER_PCT))
        SMC_MIN_RR = float(smc.get("min_rr", SMC_MIN_RR))
        SMC_LOCATION_LOOKBACK_4H = int(smc.get("location_lookback_4h", SMC_LOCATION_LOOKBACK_4H))
        SMC_LOCATION_TOLERANCE_PCT = float(smc.get("location_tolerance_pct", SMC_LOCATION_TOLERANCE_PCT))
        SMC_PREMIUM_DISCOUNT_PCT = float(smc.get("premium_discount_pct", SMC_PREMIUM_DISCOUNT_PCT))
        SMC_DISPLACEMENT_BODY_MIN_RATIO = float(smc.get("displacement_body_min_ratio", SMC_DISPLACEMENT_BODY_MIN_RATIO))
        SMC_DISPLACEMENT_BODY_MULT = float(smc.get("displacement_body_mult", SMC_DISPLACEMENT_BODY_MULT))
        SMC_DISPLACEMENT_VOL_RATIO_MIN = float(smc.get("displacement_vol_ratio_min", SMC_DISPLACEMENT_VOL_RATIO_MIN))
        SMC_MSS_BREAK_BUFFER_PCT = float(smc.get("mss_break_buffer_pct", SMC_MSS_BREAK_BUFFER_PCT))
        SMC_MAX_ZONE_WIDTH_PCT = float(smc.get("max_zone_width_pct", SMC_MAX_ZONE_WIDTH_PCT))
        SMC_REQUIRE_FVG = bool(smc.get("require_fvg", SMC_REQUIRE_FVG))
        SMC_FVG_MIN_PCT = float(smc.get("fvg_min_pct", SMC_FVG_MIN_PCT))
        SMC_TARGET_BUFFER_PCT = float(smc.get("target_buffer_pct", SMC_TARGET_BUFFER_PCT))
    if SMART_MONEY_C_VERSION >= 3:
        SMC_V3_SWEEP_LOOKBACK_15M = int(smc.get("v3_sweep_lookback_15m", SMC_V3_SWEEP_LOOKBACK_15M))
        SMC_V3_SETUP_MAX_AGE_15M = int(smc.get("v3_setup_max_age_15m", SMC_V3_SETUP_MAX_AGE_15M))
        SMC_V3_MSS_LOOKBACK_15M = int(smc.get("v3_mss_lookback_15m", SMC_V3_MSS_LOOKBACK_15M))
        SMC_V3_MSS_CONFIRM_WINDOW = int(smc.get("v3_mss_confirm_window", SMC_V3_MSS_CONFIRM_WINDOW))
        SMC_V3_SWEEP_VOL_RATIO_MIN = float(smc.get("v3_sweep_vol_ratio_min", SMC_V3_SWEEP_VOL_RATIO_MIN))
        SMC_V3_SWEEP_WICK_MIN_RATIO = float(smc.get("v3_sweep_wick_min_ratio", SMC_V3_SWEEP_WICK_MIN_RATIO))
        SMC_V3_DISPLACEMENT_MIN_SCORE = max(1, min(3, int(
            smc.get("v3_displacement_min_score", SMC_V3_DISPLACEMENT_MIN_SCORE)
        )))
        SMC_V3_RETEST_TOLERANCE_PCT = float(smc.get("v3_retest_tolerance_pct", SMC_V3_RETEST_TOLERANCE_PCT))
        SMC_V3_MAX_ZONE_WIDTH_PCT = float(smc.get("v3_max_zone_width_pct", SMC_V3_MAX_ZONE_WIDTH_PCT))
        SMC_V3_MAX_ENTRY_EXTENSION_PCT = float(smc.get(
            "v3_max_entry_extension_pct", SMC_V3_MAX_ENTRY_EXTENSION_PCT
        ))
        SMC_V3_MIN_RR = float(smc.get("v3_min_rr", SMC_V3_MIN_RR))
        SMC_V3_COUNTERTREND_EXTREME_PCT = float(smc.get(
            "v3_countertrend_extreme_pct", SMC_V3_COUNTERTREND_EXTREME_PCT
        ))

    safety = cfg.get("safety", {}) if isinstance(cfg.get("safety"), dict) else {}
    ENABLE_TIME_FILTER = bool(safety.get("enable_time_filter", ENABLE_TIME_FILTER))
    ENABLE_STARTUP_AUDIT = bool(safety.get("enable_startup_audit", ENABLE_STARTUP_AUDIT))
    ENABLE_ORPHAN_ORDER_AUDIT = bool(safety.get("enable_orphan_order_audit", ENABLE_ORPHAN_ORDER_AUDIT))
    ENABLE_PROFIT_SL_PLUS = bool(safety.get(
        "enable_profit_sl_plus",
        safety.get("enable_profit_1pct_breakeven", ENABLE_PROFIT_SL_PLUS),
    ))
    # Config lama memakai trigger 1% / lock 0.5%. Parameter lama sengaja
    # diabaikan agar deployment script baru tidak diam-diam kembali ke rule lama.
    if int(safety.get("profit_protection_version", 1)) >= 2:
        PROFIT_SL_PLUS_TRIGGER_PCT = float(safety.get(
            "profit_sl_plus_trigger_pct", PROFIT_SL_PLUS_TRIGGER_PCT
        ))
        PROFIT_SL_PLUS_LOCK_PCT = float(safety.get(
            "profit_sl_plus_lock_pct", PROFIT_SL_PLUS_LOCK_PCT
        ))
    AUDIT_ALERT_COOLDOWN_SEC = int(safety.get("audit_alert_cooldown_sec", AUDIT_ALERT_COOLDOWN_SEC))
    JOURNAL_BACKUP_MIN_INTERVAL_SEC = int(safety.get("journal_backup_min_interval_sec", JOURNAL_BACKUP_MIN_INTERVAL_SEC))
    SYNC_SUMMARY_LOG_INTERVAL_SEC = int(safety.get("sync_summary_log_interval_sec", SYNC_SUMMARY_LOG_INTERVAL_SEC))
    TERMINAL_CYCLE_LOG_ENABLED = bool(safety.get("terminal_cycle_log_enabled", TERMINAL_CYCLE_LOG_ENABLED))

    logging_cfg = cfg.get("logging", {}) if isinstance(cfg.get("logging"), dict) else {}
    LOG_QUIET_MODE = bool(logging_cfg.get("quiet_mode", LOG_QUIET_MODE))
    LOG_SCAN_DONE_INTERVAL_SEC = int(logging_cfg.get("scan_done_interval_sec", LOG_SCAN_DONE_INTERVAL_SEC))

_load_config_overrides()

# ---------------------- DIR SETUP ----------------------
def ensure_dir_for(path):
    d = os.path.dirname(path)
    if d and not os.path.exists(d):
        os.makedirs(d, exist_ok=True)

for _p in [LOG_PATH, JOURNAL_PATH, REPORT_STATE_PATH, HEARTBEAT_PATH,
           BREAKOUT_STATE_PATH, SHADOW_TRADES_PATH, USER_REGISTRY_PATH,
           os.path.join(JOURNAL_BACKUP_DIR, ".keep")]:
    ensure_dir_for(_p)

# ---------------------- UTILITIES ----------------------
def now_ms():
    return int(time.time() * 1000)

def utc_now():
    return datetime.now(timezone.utc)

def utc_hour_now():
    return utc_now().hour

def get_ssl_context():
    return ssl._create_unverified_context() if os.getenv("BINANCE_INSECURE_SSL") == "1" else None

def rotate_log_if_needed():
    if LOG_MAX_BYTES <= 0 or not os.path.exists(LOG_PATH):
        return

    try:
        if os.path.getsize(LOG_PATH) < LOG_MAX_BYTES:
            return

        keep = max(1, int(LOG_ROTATE_KEEP))
        oldest = f"{LOG_PATH}.{keep}"
        if os.path.exists(oldest):
            os.remove(oldest)

        for idx in range(keep - 1, 0, -1):
            src = f"{LOG_PATH}.{idx}"
            dst = f"{LOG_PATH}.{idx + 1}"
            if os.path.exists(src):
                os.replace(src, dst)

        os.replace(LOG_PATH, f"{LOG_PATH}.1")
    except Exception:
        pass

def _log_throttle(key, interval_sec):
    global last_log_throttle_at

    if interval_sec <= 0:
        return True
    now_s = time.time()
    last_s = last_log_throttle_at.get(key, 0.0)
    if now_s - last_s < interval_sec:
        return False
    last_log_throttle_at[key] = now_s
    return True

def should_write_log(text: str):
    if not LOG_QUIET_MODE:
        return True

    lower = str(text).lower()
    important_tokens = (
        "err", "error", "fail", "warn", "warning", "abort", "killswitch",
        "sync_closed", "sync_filled", "sync_cancelled", "order_error",
        "order_filled", "order_cancelled", "setup ", "signal_sent",
        "tp1_hit", "breakeven_complete", "be_sl_place_err",
        "profit_sl_plus", "tp1_sl_plus",
        "restore_old_sl_after_profit_sl_plus",
        "stale_trade_alert", "startup", "shutdown", "bot_stopped",
        "audit_alert", "missing_sl",
    )
    if any(token in lower for token in important_tokens):
        return True

    if lower.startswith("scan_done "):
        if "signals_cycle=0" in lower:
            return _log_throttle("scan_done_no_signal", LOG_SCAN_DONE_INTERVAL_SEC)
        return True

    routine_tokens = (
        ": no_bias ",
        ": order_pending ",
        "send_telegram_ok",
        "sleeping ",
        "all pairs valid",
        "audit_clear",
        "time_sync offset=",
        "breakout_state_loaded",
        "shadow_trades_loaded",
        "resume_pollers: no pending trades found",
        "resume_poller_started",
        "telegram_command_worker_started",
        "be_monitor_thread_started",
        "sync_thread_started",
        "startup_daily_report: no trades today",
    )
    if any(token in lower for token in routine_tokens):
        return False

    return True

def log_line(text: str):
    try:
        if not should_write_log(text):
            return
        ts = now_ms()
        rotate_log_if_needed()
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(f"{ts}\t{text}\n")
    except Exception:
        pass

def heartbeat():
    try:
        with open(HEARTBEAT_PATH, "w", encoding="utf-8") as f:
            f.write(utc_now().isoformat().replace("+00:00", "Z") + "\n")
    except Exception:
        pass

def save_json_atomic(path, data):
    try:
        d = os.path.dirname(path)
        if d and not os.path.exists(d):
            os.makedirs(d, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=d, text=True)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, default=str)
        shutil.move(tmp, path)
    except Exception as e:
        log_line(f"save_json_atomic_err {path} {e}")

def chmod_private(path):
    try:
        if os.name != "nt" and path and os.path.exists(path):
            os.chmod(path, 0o600)
    except Exception:
        pass

def load_json(path):
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8-sig") as f:
            return json.load(f)
    except Exception:
        return None

def fmt_price(x):
    try:
        x = float(x)
        if x >= 1000: return f"{x:.2f}"
        if x >= 100:  return f"{x:.3f}"
        if x >= 1:    return f"{x:.4f}"
        return f"{x:.6f}"
    except Exception:
        return str(x)

# ---------------------- PRECISION ----------------------
def get_symbol_filters(exchange_info, symbol):
    if symbol in SYMBOL_FILTERS_CACHE:
        return SYMBOL_FILTERS_CACHE[symbol]
    if not exchange_info:
        return None, None, 0.0, 0.0
    for s in exchange_info.get("symbols", []):
        if s.get("symbol") == symbol:
            filters = {f["filterType"]: f for f in s.get("filters", [])}
            step = filters.get("LOT_SIZE",     {}).get("stepSize", None)
            tick = filters.get("PRICE_FILTER", {}).get("tickSize", None)
            min_qty = float(filters.get("LOT_SIZE", {}).get("minQty", 0))
            min_notional = 0.0
            if "MIN_NOTIONAL" in filters:
                min_notional = float(filters["MIN_NOTIONAL"].get("notional", 0))
            elif "NOTIONAL" in filters:
                min_notional = float(filters["NOTIONAL"].get("minNotional", 0))
            if step is None or tick is None:
                return None, None, 0.0, 0.0
            step = str(Decimal(step).normalize())
            tick = str(Decimal(tick).normalize())
            if 'E' in step or 'e' in step:
                step = f"{Decimal(step):.10f}".rstrip('0').rstrip('.')
            if 'E' in tick or 'e' in tick:
                tick = f"{Decimal(tick):.10f}".rstrip('0').rstrip('.')
            SYMBOL_FILTERS_CACHE[symbol] = (step, tick, min_qty, min_notional)
            return step, tick, min_qty, min_notional
    return None, None, 0.0, 0.0

def apply_precision(entry, sl, tp, qty, step, tick):
    D      = Decimal
    step_d = D(step)
    tick_d = D(tick)

    def to_tick(val):
        return D(str(val)).quantize(tick_d, rounding=ROUND_DOWN)

    def to_step(val):
        return D(str(val)).quantize(step_d, rounding=ROUND_DOWN)

    def dec_str(d):
        exp = d.as_tuple().exponent
        return str(int(d)) if exp >= 0 else f"{d:.{abs(exp)}f}"

    return to_tick(entry), to_tick(sl), to_tick(tp), to_step(qty), tick_d, step_d, dec_str

# ---------------------- RATE-LIMITED REQUEST ----------------------
PRIVATE_REQUEST_RETRIES = 3
PRIVATE_REQUEST_TIMEOUT_SEC = 8

def rate_limited_wait():
    global last_request_time
    with rate_lock:
        now = time.time()
        elapsed = now - last_request_time
        if elapsed < MIN_INTERVAL_BETWEEN_REQUESTS:
            time.sleep(MIN_INTERVAL_BETWEEN_REQUESTS - elapsed)
        last_request_time = time.time()

def binance_request(method, path, params, api_key, api_secret):
    base_params = dict(params or {})
    retries, backoff = PRIVATE_REQUEST_RETRIES, 1
    for attempt in range(1, retries + 1):
        try:
            # [V7.1-FIX5] Bangun ULANG timestamp, query, signature, dan request
            # di SETIAP attempt — bukan sekali di luar loop.
            # Sebelumnya: retry pakai timestamp basi dari attempt pertama,
            # makin lama backoff makin besar peluang -1021 berulang.
            params = dict(base_params)
            params["timestamp"]  = int(time.time() * 1000) + TIME_OFFSET_MS
            params["recvWindow"] = 30000
            query     = urllib.parse.urlencode(params, doseq=True)
            signature = hmac.new(api_secret.encode(), query.encode(), hashlib.sha256).hexdigest()
            url = f"{BASE_URL}{path}?{query}&signature={signature}"
            req = urllib.request.Request(url, method=method)
            req.add_header("X-MBX-APIKEY", api_key)

            rate_limited_wait()
            with urllib.request.urlopen(req, timeout=PRIVATE_REQUEST_TIMEOUT_SEC, context=get_ssl_context()) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="ignore")
            code = getattr(e, "code", None)
            log_line(f"binance_http_error {path} code={code} body={body[:300]}")
            if code == 400 and "-1021" in body and attempt < retries:
                try:
                    sync_time()
                except Exception as sync_e:
                    log_line(f"time_sync_retry_err {sync_e}")
                time.sleep(0.5)
                continue
            if code in (418, 429) or (500 <= (code or 0) < 600) or (code == 400 and "-1021" in body):
                if attempt < retries:
                    time.sleep(backoff); backoff = min(backoff * 2, 60); continue
            raise RuntimeError(f"HTTP {code}: {body}")
        except Exception as e:
            log_line(f"binance_request_err {path} {e}")
            if attempt < retries:
                time.sleep(backoff); backoff = min(backoff * 2, 60); continue
            raise
    raise RuntimeError("binance_request_failed_after_retries")

def binance_get(path, params, api_key, api_secret):
    return binance_request("GET", path, params, api_key, api_secret)

def binance_post(path, params, api_key, api_secret):
    return binance_request("POST", path, params, api_key, api_secret)

def binance_delete(path, params, api_key, api_secret):
    return binance_request("DELETE", path, params, api_key, api_secret)

def public_get(url):
    """GET tanpa auth — untuk funding rate & OI."""
    try:
        with urllib.request.urlopen(url, timeout=10, context=get_ssl_context()) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        log_line(f"public_get_err {url[:80]} {e}")
        return None

# ---------------------- EXCHANGE INFO ----------------------
def get_exchange_info_cached(api_key=None, api_secret=None):
    cache_path = os.path.join(os.path.dirname(JOURNAL_PATH), "exchange_info_cache.json")
    cached = load_json(cache_path)
    now_ts = int(time.time())
    if cached and cached.get("_cached_at") and now_ts - cached["_cached_at"] < 3600:
        return cached.get("data")
    try:
        url = f"{BASE_URL}/fapi/v1/exchangeInfo"
        with urllib.request.urlopen(url, timeout=15, context=get_ssl_context()) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        save_json_atomic(cache_path, {"_cached_at": now_ts, "data": data})
        return data
    except Exception as e:
        log_line(f"get_exchange_info_err {e}")
        return cached.get("data") if cached else None

# ---------------------- [V7.2] DYNAMIC PAIR UNIVERSE ----------------------
def fetch_24hr_tickers():
    """
    [V7.2] Public endpoint, tidak butuh auth. Return dict symbol -> quoteVolume (USDT).
    Dipakai sebagai basis ranking liquidity untuk refresh_dynamic_pairs().
    """
    url = f"{BASE_URL}/fapi/v1/ticker/24hr"
    data = public_get(url)
    if not data:
        return None
    out = {}
    for d in data:
        try:
            out[d["symbol"]] = float(d.get("quoteVolume", 0))
        except Exception:
            continue
    return out


def _limit_pair_universe(pairs, max_pairs=None):
    """Keep core contracts while enforcing a hard universe size cap."""
    limit = max(1, int(max_pairs or MAX_DYNAMIC_PAIRS))
    unique = []
    seen_pairs = set()
    for pair in pairs or []:
        if pair and pair not in seen_pairs:
            seen_pairs.add(pair)
            unique.append(pair)
    core = [pair for pair in CORE_PAIRS if pair in seen_pairs]
    remainder = [pair for pair in unique if pair not in CORE_PAIRS]
    return (core + remainder)[:limit]


def refresh_dynamic_pairs(api_key=None, api_secret=None, force=False):
    """
    [V7.2] Refresh global PAIRS dari Binance berdasarkan volume 24h real.

    Dipanggil sekali di startup (run_forever) dan dicek ulang tiap main_cycle —
    pemanggilan berulang AMAN dan MURAH karena ada cache freshness check di awal:
    kalau cache masih dalam PAIRS_REFRESH_INTERVAL_SEC, fungsi return cepat
    tanpa hit API sama sekali.

    Safety net berlapis:
    1. ENABLE_DYNAMIC_PAIRS=False → PAIRS tetap FALLBACK_STATIC_PAIRS, tidak fetch.
    2. Fetch gagal tapi ADA cache lama → pakai cache lama (bukan crash/kosong).
    3. Fetch gagal DAN tidak ada cache sama sekali → pakai FALLBACK_STATIC_PAIRS.
    4. Hasil filter < 10 pair (data anomali) → dianggap gagal, fallback ke cache/static.
    5. CORE_PAIRS (BTC/ETH/SOL/BNB/XRP) selalu dipertahankan di hasil akhir.
    """
    global PAIRS
    if not ENABLE_DYNAMIC_PAIRS:
        return

    cache_path = os.path.join(os.path.dirname(JOURNAL_PATH), "dynamic_pairs_cache.json")
    cached  = load_json(cache_path)
    now_ts  = int(time.time())

    if not force and cached and cached.get("_cached_at") and \
       (now_ts - cached["_cached_at"]) < PAIRS_REFRESH_INTERVAL_SEC:
        if cached.get("pairs"):
            PAIRS = _limit_pair_universe(cached["pairs"])
        return   # masih fresh, tidak perlu hit API

    try:
        exchange_info = get_exchange_info_cached(api_key, api_secret)
        tickers       = fetch_24hr_tickers()
        if not exchange_info or not tickers:
            raise RuntimeError("exchange_info atau 24hr tickers kosong/gagal fetch")

        now_ms         = now_ts * 1000
        min_onboard_ms = MIN_LISTING_AGE_DAYS * 24 * 3600 * 1000
        candidates = []
        rejected_format = []
        for s in exchange_info.get("symbols", []):
            symbol = s.get("symbol", "")
            if (s.get("status") != "TRADING"
                    or s.get("contractType") != "PERPETUAL"
                    or s.get("quoteAsset") != "USDT"):
                continue
            # [BUGFIX V7.3.1] Tolak simbol dengan karakter non-standar (non-ASCII,
            # simbol/spasi). Binance kadang punya kontrak promosi/quirky dengan
            # nama unicode (mis. simbol berbahasa Mandarin) yang lolos status/
            # contractType/quoteAsset filter tapi BIKIN CRASH urllib.urlopen()
            # (ascii encode error) di setiap titik yang membangun URL dari simbol
            # ini — fetch_klines, funding rate, OI, orderbook, dst. Filter di
            # sumbernya jauh lebih aman daripada cuma defend di tiap call site.
            if not (symbol.isascii() and re.fullmatch(r"[A-Z0-9]+", symbol)):
                rejected_format.append(symbol)
                continue
            onboard = s.get("onboardDate", 0) or 0
            if onboard and (now_ms - onboard) < min_onboard_ms:
                continue  # listing terlalu baru — history 4H belum cukup utk SR_LOOKBACK
            vol = tickers.get(symbol, 0)
            if vol < MIN_PAIR_VOLUME_USDT:
                continue
            candidates.append((symbol, vol))

        if rejected_format:
            log_line(f"pairs_rejected_format count={len(rejected_format)} "
                     f"symbols={rejected_format[:10]}")

        candidates.sort(key=lambda x: x[1], reverse=True)
        ranked = [c[0] for c in candidates]
        selected = _limit_pair_universe(ranked)

        if len(selected) < 10:
            raise RuntimeError(f"hasil filter terlalu sedikit ({len(selected)} pair) — data dicurigai anomali")

        old_count = len(PAIRS)
        PAIRS = selected
        save_json_atomic(cache_path, {"_cached_at": now_ts, "pairs": PAIRS})
        log_line(f"pairs_refreshed count={len(PAIRS)} (was {old_count}) "
                 f"min_vol=${MIN_PAIR_VOLUME_USDT:,.0f} min_age={MIN_LISTING_AGE_DAYS}d")
        send_telegram(
            f"🔄 [{BOT_TAG}] Pair universe diperbarui: {len(PAIRS)} pair "
            f"(volume ≥ ${MIN_PAIR_VOLUME_USDT/1e6:.0f}jt/hari, umur listing ≥ {MIN_LISTING_AGE_DAYS}hr)"
        )
    except Exception as e:
        log_line(f"pairs_refresh_err {e}")
        if cached and cached.get("pairs"):
            PAIRS = _limit_pair_universe(cached["pairs"])
            log_line(f"pairs_refresh_fallback_cache count={len(PAIRS)}")
        else:
            PAIRS = _limit_pair_universe(FALLBACK_STATIC_PAIRS)
            log_line(f"pairs_refresh_fallback_static count={len(PAIRS)}")

# ---------------------- FUNDING RATE ----------------------
def get_funding_rate(symbol):
    # [BUGFIX V7.3.1] URL-encode simbol — pertahanan lapis kedua kalau ada
    # simbol non-standar (unicode dll) lolos dari filter di refresh_dynamic_pairs().
    url = f"{BASE_URL}/fapi/v1/premiumIndex?symbol={urllib.parse.quote(symbol)}"
    data = public_get(url)
    if data:
        try:
            return float(data.get("lastFundingRate", 0))
        except Exception:
            return None
    return None

# ---------------------- [FIX-4] OPEN INTEREST — 3-candle lookback ----------------------
def get_oi_change(symbol):
    """
    [FIX-4] OI comparison pakai 3-candle lookback (was 1-candle → terlalu noisy).
    Bandingkan OI sekarang vs 3 candle 15m lalu untuk trend yang lebih stabil.
    OI naik + harga naik = trend valid (smart money masuk).
    OI turun + harga naik = distribusi (hati-hati).
    """
    url = f"{BASE_URL}/futures/data/openInterestHist?symbol={urllib.parse.quote(symbol)}&period=15m&limit=5"
    data = public_get(url)
    if not data or len(data) < 4:
        return None, None
    try:
        oi_now  = float(data[-1].get("sumOpenInterest", 0))
        oi_3ago = float(data[-4].get("sumOpenInterest", 0))  # [FIX-4] 3 candle lalu
        if oi_3ago <= 0:
            return oi_now, None
        oi_change_pct = (oi_now - oi_3ago) / oi_3ago
        return oi_now, oi_change_pct
    except Exception:
        return None, None

# ---------------------- ORDERS ----------------------
def place_limit_entry(symbol, side, qty, price, api_key, api_secret, position_side=None):
    payload = {
        "symbol": symbol, "side": side,
        "type": "LIMIT", "timeInForce": "GTC",
        "quantity": qty, "price": price,
    }
    if position_side:
        payload["positionSide"] = position_side
    return binance_post("/fapi/v1/order", payload, api_key, api_secret)

def place_sl_tp(symbol, side, sl_price, tp_price, api_key, api_secret, position_side=None, qty=None):
    """
    SL  → SELALU pakai closePosition=true (tutup semua sisa posisi).
    TP1 → pakai qty eksplisit (40% posisi) agar hanya tutup sebagian.
    """
    def build_sl_payload():
        payload = {
            "algoType":      "CONDITIONAL",
            "symbol":        symbol,
            "side":          side,
            "type":          "STOP_MARKET",
            "triggerPrice":  sl_price,
            "closePosition": "true",
            "workingType":   "MARK_PRICE",
        }
        if position_side:
            payload["positionSide"] = position_side
        return payload

    def build_tp_payload():
        payload = {
            "algoType":     "CONDITIONAL",
            "symbol":       symbol,
            "side":         side,
            "type":         "TAKE_PROFIT_MARKET",
            "triggerPrice": tp_price,
            "workingType":  "MARK_PRICE",
        }
        if qty:
            payload["quantity"] = qty
        else:
            payload["closePosition"] = "true"
        if position_side:
            payload["positionSide"] = position_side
        return payload

    sl = binance_post("/fapi/v1/algoOrder", build_sl_payload(), api_key, api_secret)
    tp = None
    try:
        tp = binance_post("/fapi/v1/algoOrder", build_tp_payload(), api_key, api_secret)
    except RuntimeError as e:
        if "-2021" in str(e):
            log_line(f"{symbol}: tp_skipped_-2021 price={tp_price}")
        else:
            raise
    return sl, tp

def get_account_info(api_key, api_secret):
    return binance_get("/fapi/v2/account", {}, api_key, api_secret)

def get_order(symbol, order_id, api_key, api_secret):
    try:
        return binance_get("/fapi/v1/order", {"symbol": symbol, "orderId": order_id}, api_key, api_secret)
    except Exception as e:
        log_line(f"get_order_err {symbol} {e}")
        return {}

# [V7.1-FIX4] Cache nilai dual_side terakhir yang VALID (bukan default tebakan).
# Dipakai sebagai fallback kalau semua retry get_position_mode() gagal.
_last_known_dual_side = {"value": None}

def get_position_mode(api_key, api_secret):
    """
    [V7.1-FIX4] Retry 3× dengan backoff sebelum menyerah.
    Jika semua retry gagal, PAKAI CACHE nilai terakhir yang valid
    (bukan diam-diam asumsi False/one-way mode).

    Bug lama: exception apapun → return False. Kalau akun sebenarnya
    Hedge Mode dan fetch gagal sesaat (mis. timestamp belum sync),
    bot salah asumsi one-way mode → semua order kena -4061 karena
    positionSide tidak sesuai setting akun yang sebenarnya.
    """
    last_err = None
    for attempt in range(1, 4):
        try:
            data = binance_get("/fapi/v1/positionSide/dual", {}, api_key, api_secret)
            value = bool(data.get("dualSidePosition", False))
            _last_known_dual_side["value"] = value
            return value
        except Exception as e:
            last_err = e
            if attempt < 3:
                time.sleep(1.5 * attempt)
                continue

    cached = _last_known_dual_side["value"]
    if cached is not None:
        log_line(f"get_position_mode_err {last_err} — using cached value={cached}")
        return cached

    # Tidak ada cache sama sekali (benar-benar startup pertama kali) —
    # log sebagai WARNING keras karena ini situasi paling berisiko.
    log_line(f"get_position_mode_err {last_err} — NO CACHE, defaulting False (RISIKO -4061)")
    send_telegram(
        f"⚠️ [{BOT_TAG}] WARNING: gagal deteksi position mode (hedge/one-way) "
        f"setelah 3x retry, dan belum ada cache. Order berikutnya berisiko "
        f"ditolak -4061 jika akun di Hedge Mode. Cek koneksi/API key."
    )
    return False

def ensure_margin_leverage(symbol, api_key, api_secret, leverage):
    try:
        binance_post("/fapi/v1/leverage", {"symbol": symbol, "leverage": leverage}, api_key, api_secret)
    except Exception as e:
        if "leverage not changed" not in str(e).lower():
            log_line(f"set_leverage_err {symbol} {e}")
    try:
        binance_post("/fapi/v1/marginType", {"symbol": symbol, "marginType": "ISOLATED"}, api_key, api_secret)
    except Exception as e:
        if "no need to change" not in str(e).lower() and "-4046" not in str(e):
            log_line(f"set_margin_type_err {symbol} {e}")

# ---------------------- INDICATORS ----------------------
def fetch_klines(symbol: str, interval: str, limit: int = 200):
    """
    [V7.1-FIX6] Retry 3× dengan backoff kecil untuk connection error
    (WinError 10054 dkk). Sebelumnya: sekali gagal langsung skip pair
    tanpa percobaan ulang — coverage scan berkurang saat ada gangguan
    jaringan sesaat (terutama saat startup, banyak thread fetch bersamaan).
    """
    url = f"{BASE_URL}/fapi/v1/klines?symbol={urllib.parse.quote(symbol)}&interval={interval}&limit={limit}"
    retries, backoff = 3, 1.5
    for attempt in range(1, retries + 1):
        try:
            with urllib.request.urlopen(url, timeout=15, context=get_ssl_context()) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            break
        except urllib.error.HTTPError as e:
            if e.code == 400:
                with invalid_pairs_lock:
                    INVALID_PAIRS.add(symbol)
                log_line(f"auto_skip {symbol} HTTP 400")
                raise
            if attempt < retries:
                time.sleep(backoff); backoff *= 2; continue
            raise
        except Exception as e:
            if attempt < retries:
                time.sleep(backoff); backoff *= 2; continue
            raise

    candles = []
    for k in data:
        volume    = float(k[5])
        taker_buy = float(k[9])
        candles.append({
            "open_time": int(k[0]),
            "open":  float(k[1]), "high": float(k[2]),
            "low":   float(k[3]), "close": float(k[4]),
            "volume": volume,
            "taker_buy":  taker_buy,
            "taker_sell": max(volume - taker_buy, 0.0),
            "close_time": int(k[6]),
        })
    return candles

def ema(values, period):
    if len(values) < period:
        return None
    k = 2 / (period + 1)
    val = sum(values[:period]) / period
    for v in values[period:]:
        val = v * k + val * (1 - k)
    return val

def ema_slope(values, period):
    if len(values) < period + 2:
        return None, None
    e_now  = ema(values, period)
    e_prev = ema(values[:-1], period)
    if e_now is None or e_prev is None or e_prev == 0:
        return e_now, None
    return e_now, (e_now - e_prev) / e_prev

def rsi(values, period=14):
    if len(values) < period + 1:
        return None
    gains, losses = [], []
    for i in range(1, period + 1):
        d = values[i] - values[i-1]
        gains.append(max(d, 0)); losses.append(max(-d, 0))
    avg_gain = sum(gains) / period
    avg_loss = sum(losses) / period
    for i in range(period + 1, len(values)):
        d = values[i] - values[i-1]
        avg_gain = (avg_gain * (period-1) + max(d, 0)) / period
        avg_loss = (avg_loss * (period-1) + max(-d, 0)) / period
    if avg_loss == 0:
        return 100.0
    return 100 - (100 / (1 + avg_gain / avg_loss))

def atr(highs, lows, closes, period=14):
    if len(closes) < period + 1:
        return None
    trs = []
    for i in range(1, len(closes)):
        tr = max(highs[i] - lows[i],
                 abs(highs[i] - closes[i-1]),
                 abs(lows[i]  - closes[i-1]))
        trs.append(tr)
    val = sum(trs[:period]) / period
    for tr in trs[period:]:
        val = (val * (period-1) + tr) / period
    return val

# ---------------------- S/R MULTI-TOUCH ----------------------
def support_resistance_multi(candles, lookback=None, min_touches=None):
    """
    [BUGFIX V7.2.1] Signature diperbaiki — sebelumnya fungsi ini cuma terima
    parameter `candles`, padahal scan_pair() (sejak V7-S2) memanggilnya dengan
    kwargs `lookback=` dan `min_touches=`. Mismatch ini bikin TypeError di
    SETIAP pemanggilan scan_pair() untuk SEMUA pair, sejak V7.0 — bot tidak
    pernah benar-benar sampai ke logic entry karena selalu crash duluan di
    titik ini (root cause dari signals_cycle=0 terus-menerus).

    lookback/min_touches sekarang opsional: kalau tidak diisi, fallback ke
    konfigurasi global SR_LOOKBACK/SR_MIN_TOUCHES seperti perilaku asli.
    """
    lookback    = lookback    if lookback    is not None else SR_LOOKBACK
    touch_tol   = SR_TOUCH_TOL
    min_touches = min_touches if min_touches is not None else SR_MIN_TOUCHES

    if len(candles) < 10:
        highs = [c["high"] for c in candles]
        lows  = [c["low"]  for c in candles]
        return min(lows), max(highs)

    chunk = candles[-lookback:] if len(candles) >= lookback else candles
    highs = [c["high"] for c in chunk]
    lows  = [c["low"]  for c in chunk]

    def count_touches(level, prices):
        return sum(1 for p in prices if level > 0 and abs(p - level) / level <= touch_tol)

    close = chunk[-1]["close"]
    swing_highs, swing_lows = [], []

    for i in range(2, len(chunk) - 2):
        h = chunk[i]["high"]
        if h > chunk[i-1]["high"] and h > chunk[i-2]["high"] and \
           h > chunk[i+1]["high"] and h > chunk[i+2]["high"]:
            if count_touches(h, highs) >= min_touches:
                swing_highs.append(h)

        l = chunk[i]["low"]
        if l < chunk[i-1]["low"] and l < chunk[i-2]["low"] and \
           l < chunk[i+1]["low"] and l < chunk[i+2]["low"]:
            if count_touches(l, lows) >= min_touches:
                swing_lows.append(l)

    resistance = min((h for h in swing_highs if h > close), default=max(highs))
    support    = max((l for l in swing_lows  if l < close), default=min(lows))
    return support, resistance

def near_level(price, level, tol=None):
    tol = NEAR_LEVEL_TOLERANCE if tol is None else tol
    if level is None or level <= 0 or price <= 0:
        return False
    return abs(price - level) / level <= tol

# ---------------------- [V7.3] BREAKOUT-RETEST STATE PERSISTENCE ----------------------
def load_breakout_state():
    """
    [V7.3] Load breakout pending-retest dari disk saat startup. Persisten lintas
    restart karena retest window bisa sampai 20 candle 4H (~3-4 hari) — kalau
    tidak di-load ulang, breakout yang terdeteksi sebelum restart akan hilang
    dan bot harus menunggu breakout baru terbentuk dari nol.
    """
    global breakout_state
    data = load_json(BREAKOUT_STATE_PATH)
    with breakout_state_lock:
        breakout_state = data if isinstance(data, dict) else {}
    log_line(f"breakout_state_loaded count={len(breakout_state)}")

def save_breakout_state():
    try:
        save_json_atomic(BREAKOUT_STATE_PATH, breakout_state)
    except Exception as e:
        log_line(f"breakout_state_save_err {e}")

def cleanup_expired_breakouts_housekeeping():
    """
    [V7.3] Housekeeping kasar berbasis wall-clock — dipanggil tiap main_cycle
    untuk buang entry breakout_state yang sudah sangat lama (mis. pair sudah
    tidak lagi masuk dynamic pair universe sehingga tidak pernah dievaluasi
    ulang oleh scan_pair(), sehingga expiry berbasis candle di scan_pair()
    tidak pernah sempat jalan untuk entry itu).

    Expiry presisi (berbasis jumlah candle 4H) tetap dilakukan di scan_pair()
    setiap kali pair itu benar-benar di-scan — ini cuma jaring pengaman kedua.
    """
    # Saat B dipause, state lama dipertahankan sebagai bukti audit dan tidak
    # boleh menghalangi Jalur A atau berubah diam-diam karena housekeeping.
    if not ENABLE_STRATEGY_B_LIVE or not breakout_state:
        return
    cutoff_ms = RETEST_MAX_CANDLES_4H * 4 * 3600 * 1000 * 2  # 2x lipat margin aman
    now = now_ms()
    with breakout_state_lock:
        expired = [k for k, v in breakout_state.items()
                   if now - v.get("detected_at", now) > cutoff_ms]
        for k in expired:
            breakout_state.pop(k, None)
        if expired:
            save_breakout_state()
    if expired:
        log_line(f"breakout_housekeeping_expired count={len(expired)} keys={expired}")

# ---------------------- [V7.3.2] SHADOW SIGNAL TRACKING ----------------------
def load_shadow_trades():
    """[V7.3.2] Load shadow trades dari disk saat startup — persisten lintas restart."""
    global shadow_trades
    data = load_json(SHADOW_TRADES_PATH)
    with shadow_trades_lock:
        shadow_trades = data if isinstance(data, list) else []
    log_line(f"shadow_trades_loaded count={len(shadow_trades)}")

def save_shadow_trades():
    try:
        save_json_atomic(SHADOW_TRADES_PATH, shadow_trades)
    except Exception as e:
        log_line(f"shadow_trades_save_err {e}")

def shadow_compute_sl_tp(bias, entry, support, resistance, candles_15m):
    """
    [V7.3.2] SL/TP virtual untuk shadow trade — versi sederhana dari logic
    SL/TP Jalur A asli (S/R + buffer, diklem oleh recent candle low/high).
    SENGAJA tanpa cabang ATR widening (yang dipakai entry asli) — simplifikasi
    yang disengaja untuk menjaga fungsi ini ringkas dan independen; cukup
    representatif untuk tujuan validasi "apakah arah filter ini benar", bukan
    untuk presisi P&L sampai ke desimal terakhir.
    """
    recent_lows  = [c["low"]  for c in candles_15m[-21:-1]]
    recent_highs = [c["high"] for c in candles_15m[-21:-1]]
    if bias == "LONG":
        sl = min(support * (1 - SR_BUF_SL), min(recent_lows) * (1 - 0.002))
        tp = resistance * (1 - SR_BUF_TP)
        if tp <= entry:
            tp = entry + RR * abs(entry - sl)
    else:
        sl = max(resistance * (1 + SR_BUF_SL), max(recent_highs) * (1 + 0.002))
        tp = support * (1 + SR_BUF_TP)
        if tp >= entry:
            tp = entry - RR * abs(entry - sl)
    return sl, tp

def record_shadow_signal(pair, bias, entry, sl, tp, blocked_reason, blocked_detail, meta=None):
    """
    [V7.3.2] Catat sinyal near-miss sbg shadow trade. Tidak dieksekusi ke
    Binance. Cegah duplikat: skip kalau sudah ada shadow trade OPEN untuk
    kombinasi pair+bias+blocked_reason yang sama (hindari spam tiap cycle
    selama kondisi near-miss yang sama masih berlangsung).
    """
    setup_id = meta.get("setup_id") if isinstance(meta, dict) else None
    with shadow_trades_lock:
        for t in shadow_trades:
            if setup_id and t.get("setup_id") == setup_id:
                return
            if (t.get("pair") == pair and t.get("bias") == bias
                    and t.get("blocked_reason") == blocked_reason
                    and t.get("status") == "SHADOW_OPEN"):
                return
        record = {
            "pair": pair, "bias": bias,
            "blocked_reason": blocked_reason, "blocked_detail": blocked_detail,
            "entry": entry, "sl": sl, "tp": tp,
            "timestamp": now_ms(), "status": "SHADOW_OPEN",
            "closed_at": None, "result_R": None, "close_price": None,
        }
        if isinstance(meta, dict):
            record.update(meta)
        shadow_trades.append(record)
        save_shadow_trades()
    log_line(f"{pair}: shadow_signal_recorded {bias} blocked_by={blocked_reason}"
             f"({blocked_detail}) entry={entry:.4f} sl={sl:.4f} tp={tp:.4f}")

def update_shadow_trades_for_pair(pair, candles_15m):
    """
    [V7.3.2] Cek shadow trade OPEN utk pair ini terhadap harga close terkini.
    Dipanggil dari scan_pair() memakai candles_15m yang SUDAH di-fetch —
    tidak ada API call tambahan, numpang di siklus scan yang sudah berjalan.
    """
    if not candles_15m:
        return
    latest     = candles_15m[-2]
    close      = latest["close"]
    now        = now_ms()
    changed    = False
    with shadow_trades_lock:
        for t in shadow_trades:
            if t.get("pair") != pair or t.get("status") != "SHADOW_OPEN":
                continue
            bias, sl, tp, entry = t["bias"], t["sl"], t["tp"], t["entry"]
            timeout_hours = float(
                t.get("shadow_timeout_hours", SHADOW_TIMEOUT_HOURS)
                or SHADOW_TIMEOUT_HOURS
            )
            timeout_ms = timeout_hours * 3600 * 1000
            is_structural_c = (
                t.get("blocked_reason") in ("smart_money_c_v2", "smart_money_c_v3", "smart_money_c_v6")
                or t.get("strategy_version") in ("C2", "C3", "C6")
            )
            if is_structural_c:
                hit_tp = latest["high"] >= tp if bias == "LONG" else latest["low"] <= tp
                hit_sl = latest["low"] <= sl if bias == "LONG" else latest["high"] >= sl
                # Data OHLC tidak mengetahui urutan intrabar. Jika TP dan SL
                # tersentuh pada candle sama, pencatatan konservatif memilih SL.
                if hit_tp and hit_sl:
                    hit_tp = False
            else:
                hit_tp = (close >= tp) if bias == "LONG" else (close <= tp)
                hit_sl = (close <= sl) if bias == "LONG" else (close >= sl)
            if hit_tp or hit_sl:
                result   = "SHADOW_WIN" if hit_tp else "SHADOW_LOSS"
                risk     = abs(entry - sl)
                if is_structural_c:
                    result_r = (abs(tp - entry) / risk if risk > 0 else 0.0) if hit_tp else -1.0
                    exit_price = tp if hit_tp else sl
                else:
                    reward = abs(close - entry)
                    result_r = (reward / risk if risk > 0 else 0) * (1 if hit_tp else -1)
                    exit_price = close
                t.update({"status": result, "closed_at": now,
                          "close_price": exit_price, "result_R": round(result_r, 2)})
                changed = True
                log_line(f"{pair}: shadow_closed {result} blocked_by={t['blocked_reason']} "
                         f"R={result_r:+.2f}")
            elif now - t.get("timestamp", now) > timeout_ms:
                t.update({"status": "SHADOW_TIMEOUT", "closed_at": now, "close_price": close})
                changed = True
                log_line(f"{pair}: shadow_timeout blocked_by={t['blocked_reason']}")
    if changed:
        save_shadow_trades()


def _shadow_strategy_key(trade):
    reason = trade.get("blocked_reason", "unknown")
    if reason == "smart_money_c_v6" or trade.get("strategy_version") == "C6":
        return "smart_money_c_v6"
    if reason == "smart_money_c_v3" or trade.get("strategy_version") == "C3":
        return "smart_money_c_v3"
    if reason == "smart_money_c_v2" or trade.get("strategy_version") == "C2":
        return "smart_money_c_v2"
    return reason


def _shadow_strategy_label(strategy_key):
    labels = {
        "smart_money_c": "Jalur C v1 (legacy)",
        "smart_money_c_v2": "Jalur C v2 Liquidity Sweep",
        "smart_money_c_v3": "Jalur C v3 Liquidity Reversal",
        "smart_money_c_v6": "Jalur C v6 Market Liquidity Sweep",
        "vol_too_high": "Filter volume Jalur A",
    }
    return labels.get(strategy_key, strategy_key)

def build_shadow_report_text():
    """
    [V7.3.2] Ringkasan performa shadow trade per blocked_reason — winrate dan
    expectancy (avg R). Ini jawaban empiris: kalau shadow trade utk
    "vol_too_high" ternyata winrate-nya bagus, berarti filter volume Jalur A
    membuang sinyal yang sebenarnya valid (perlu dilonggarkan). Kalau
    winrate-nya jelek, filter itu benar menyaring sinyal buruk (pertahankan).
    """
    with shadow_trades_lock:
        closed = [t for t in shadow_trades if t.get("status") in ("SHADOW_WIN", "SHADOW_LOSS")]
        open_count = sum(1 for t in shadow_trades if t.get("status") == "SHADOW_OPEN")
    if not closed:
        return None
    by_reason = {}
    for t in closed:
        by_reason.setdefault(_shadow_strategy_key(t), []).append(t)
    lines = [f"🔬 [{BOT_TAG}] Shadow Signal Report (open={open_count})"]
    for reason, trades in sorted(by_reason.items()):
        wins  = sum(1 for t in trades if t["status"] == "SHADOW_WIN")
        total = len(trades)
        avg_r = sum(t["result_R"] for t in trades) / total
        wr    = wins / total * 100
        lines.append(f"  {_shadow_strategy_label(reason)}: n={total} WR={wr:.0f}% avgR={avg_r:+.2f}")
    return "\n".join(lines)

def send_shadow_report():
    """
    [V7.3.2] Kirim shadow report sekali sehari (gate terpisah dari daily trade
    report — pakai key beda di REPORT_STATE_PATH yang sama, supaya tidak
    saling memblokir kalau salah satu belum siap kirim).
    """
    tz    = timezone(timedelta(hours=7))
    today = datetime.now(tz).date().isoformat()
    state = load_json(REPORT_STATE_PATH) or {}
    if state.get("last_shadow_report_date") == today:
        return
    text = build_shadow_report_text()
    if text is None:
        return  # belum ada shadow trade closed, tidak ada yg dilaporkan
    send_telegram(text)
    state["last_shadow_report_date"] = today
    save_json_atomic(REPORT_STATE_PATH, state)


# ---------------------- [V7.3] VOLUME HELPERS ----------------------
def avg_volume(candles, lookback, exclude_last=2):
    """
    [V7.3] Rata-rata volume `lookback` candle, EXCLUDE `exclude_last` candle
    paling akhir (candle yang sedang dievaluasi sebagai breakout/retest candidate
    tidak boleh ikut menghitung baseline-nya sendiri — itu akan bias hasilnya).
    """
    if len(candles) < lookback + exclude_last:
        return None
    window = candles[-(lookback + exclude_last):-exclude_last]
    vols = [c.get("volume", 0) for c in window]
    if not vols:
        return None
    avgv = sum(vols) / len(vols)
    return avgv if avgv > 0 else None

# ---------------------- [V7.3] BREAKOUT DETECTION (JALUR B) ----------------------
def breakout_reference_levels(candles_4h):
    """Freeze S/R before breakout candles C1/C2 and the open candle.

    Binance returns the still-forming candle as the final item. Jalur B uses
    ``[-3]`` as C1 and ``[-2]`` as C2, so the structural level must be derived
    only from candles before those two confirmations. Including C1/C2 moves the
    resistance/support beyond their own closes and makes a new breakout
    mathematically unreachable.
    """
    history = candles_4h[:-3]
    if len(history) < 10:
        return None, None
    return support_resistance_multi(
        history,
        min_touches=SR_MIN_TOUCHES,
        lookback=SR_LOOKBACK,
    )


def detect_breakout_4h(candles_4h, support, resistance):
    """
    [V7.3] Deteksi breakout 2-candle di timeframe 4H.

    C1 (candles_4h[-3], candle breakout PERTAMA/lebih awal) — WAJIB:
      - close di luar level + buffer (bukan noise tipis)
      - volume >= BREAKOUT_C1_MIN_VOL_RATIO x avg20 (lebih penting/ketat)

    C2 (candles_4h[-2], candle KEDUA/konfirmasi, lebih baru) — KONFIRMASI:
      - close masih di luar level (breakout bertahan, tidak langsung gagal balik)
      - volume >= BREAKOUT_C2_MIN_VOL_RATIO x avg20 (lebih longgar dari C1)

    Return dict {"bullish": bool, "bearish": bool, "c1_vol_ratio": float,
    "c2_vol_ratio": float} atau None kalau data tidak cukup.
    """
    if (len(candles_4h) < VOLUME_AVG_LOOKBACK + 3
            or support is None or resistance is None
            or support <= 0 or resistance <= 0):
        return None

    c1 = candles_4h[-3]   # candle breakout pertama (lebih awal, lebih penting)
    c2 = candles_4h[-2]   # candle breakout kedua (konfirmasi, lebih longgar)

    # Exclude C1, C2, and the still-forming candle. Including C1 in its own
    # baseline dilutes the breakout-volume ratio and disagrees with replay.
    avgv = avg_volume(candles_4h, VOLUME_AVG_LOOKBACK, exclude_last=3)
    if not avgv:
        return None

    c1_ratio = c1.get("volume", 0) / avgv
    c2_ratio = c2.get("volume", 0) / avgv

    result = {"bullish": False, "bearish": False,
              "c1_vol_ratio": c1_ratio, "c2_vol_ratio": c2_ratio}

    res_break_level = resistance * (1 + BREAKOUT_LEVEL_BUFFER_PCT)
    if (c1["close"] > res_break_level and c2["close"] > resistance
            and c1_ratio >= BREAKOUT_C1_MIN_VOL_RATIO
            and c2_ratio >= BREAKOUT_C2_MIN_VOL_RATIO):
        result["bullish"] = True

    sup_break_level = support * (1 - BREAKOUT_LEVEL_BUFFER_PCT)
    if (c1["close"] < sup_break_level and c2["close"] < support
            and c1_ratio >= BREAKOUT_C1_MIN_VOL_RATIO
            and c2_ratio >= BREAKOUT_C2_MIN_VOL_RATIO):
        result["bearish"] = True

    return result

def check_retest(close_price, level, tol_pct=None):
    """[V7.3] Apakah harga sekarang sudah kembali dalam toleransi retest ke level?"""
    if level is None or level <= 0 or close_price is None or close_price <= 0:
        return False
    tol_pct = tol_pct if tol_pct is not None else RETEST_TOLERANCE_PCT
    return abs(close_price - level) / level <= tol_pct

def _smc_candle_metrics(candle, bias):
    high = float(candle["high"])
    low = float(candle["low"])
    open_price = float(candle["open"])
    close = float(candle["close"])
    candle_range = high - low
    if candle_range <= 0:
        return {
            "body_ratio": 0.0,
            "wick_ratio": 0.0,
            "close_position": 0.5,
            "direction_ok": False,
        }
    body_ratio = abs(close - open_price) / candle_range
    if bias == "LONG":
        wick_ratio = (min(open_price, close) - low) / candle_range
        close_position = (close - low) / candle_range
        direction_ok = close > open_price
    else:
        wick_ratio = (high - max(open_price, close)) / candle_range
        close_position = (high - close) / candle_range
        direction_ok = close < open_price
    return {
        "body_ratio": body_ratio,
        "wick_ratio": max(0.0, wick_ratio),
        "close_position": close_position,
        "direction_ok": direction_ok,
    }


def _smc_pivot_levels(candles, side, left=2, right=2):
    pivots = []
    if len(candles) < left + right + 1:
        return pivots
    key = "high" if side == "HIGH" else "low"
    for idx in range(left, len(candles) - right):
        value = candles[idx][key]
        before = [candles[j][key] for j in range(idx - left, idx)]
        after = [candles[j][key] for j in range(idx + 1, idx + right + 1)]
        if side == "HIGH" and value > max(before) and value >= max(after):
            pivots.append({"idx": idx, "level": value})
        elif side == "LOW" and value < min(before) and value <= min(after):
            pivots.append({"idx": idx, "level": value})
    return pivots


def _smc_find_4h_location(candles_4h, bias, sweep_extreme):
    """Validasi bahwa sweep 15m terjadi di liquidity pool 4H bernilai tinggi."""
    closed = candles_4h[:-1]
    if len(closed) < SMC_LOCATION_LOOKBACK_4H:
        return None
    window = closed[-SMC_LOCATION_LOOKBACK_4H:]
    range_low = min(c["low"] for c in window)
    range_high = max(c["high"] for c in window)
    range_size = range_high - range_low
    if range_size <= 0 or sweep_extreme <= 0:
        return None

    range_position = (sweep_extreme - range_low) / range_size
    midpoint = range_low + (range_size * 0.5)
    low_pivots = _smc_pivot_levels(window, "LOW")
    high_pivots = _smc_pivot_levels(window, "HIGH")

    if bias == "LONG":
        if range_position > SMC_PREMIUM_DISCOUNT_PCT:
            return None
        liquidity_levels = [range_low] + [p["level"] for p in low_pivots if p["level"] <= midpoint]
        target_levels = [p["level"] for p in high_pivots if p["level"] > sweep_extreme]
        target_levels.append(range_high)
        zone = "DISCOUNT"
    else:
        if range_position < 1.0 - SMC_PREMIUM_DISCOUNT_PCT:
            return None
        liquidity_levels = [range_high] + [p["level"] for p in high_pivots if p["level"] >= midpoint]
        target_levels = [p["level"] for p in low_pivots if p["level"] < sweep_extreme]
        target_levels.append(range_low)
        zone = "PREMIUM"

    liquidity_level = min(liquidity_levels, key=lambda level: abs(level - sweep_extreme))
    true_ranges = []
    prev_close = window[0]["close"]
    for candle in window[1:]:
        true_ranges.append(max(
            candle["high"] - candle["low"],
            abs(candle["high"] - prev_close),
            abs(candle["low"] - prev_close),
        ))
        prev_close = candle["close"]
    avg_tr = sum(true_ranges[-14:]) / len(true_ranges[-14:]) if true_ranges else 0.0
    tolerance = max(sweep_extreme * SMC_LOCATION_TOLERANCE_PCT, avg_tr * 0.25)
    if abs(sweep_extreme - liquidity_level) > tolerance:
        return None

    return {
        "zone": zone,
        "range_low": range_low,
        "range_high": range_high,
        "range_position": max(0.0, min(1.0, range_position)),
        "liquidity_level": liquidity_level,
        "distance_pct": abs(sweep_extreme - liquidity_level) / liquidity_level,
        "target_levels": sorted(set(target_levels)),
    }


def _smc_find_liquidity_sweep(candles_15m, bias):
    minimum = SMC_SWEEP_LOOKBACK_15M + SMC_SETUP_MAX_AGE_15M + 3
    if len(candles_15m) < minimum:
        return None

    closed = candles_15m[:-1]
    search_start = max(
        SMC_SWEEP_LOOKBACK_15M,
        len(closed) - 1 - SMC_SETUP_MAX_AGE_15M,
    )
    search_end = len(closed) - 3  # sisakan candle untuk MSS dan retest

    for idx in range(search_end, search_start - 1, -1):
        candle = closed[idx]
        prev = closed[idx - SMC_SWEEP_LOOKBACK_15M:idx]
        volume_window = closed[max(0, idx - VOLUME_AVG_LOOKBACK):idx]
        if len(prev) < SMC_SWEEP_LOOKBACK_15M or not volume_window:
            continue
        avg_volume_value = sum(c.get("volume", 0) for c in volume_window) / len(volume_window)
        if avg_volume_value <= 0:
            continue

        vol_ratio = candle.get("volume", 0) / avg_volume_value
        metrics = _smc_candle_metrics(candle, bias)
        if vol_ratio < SMC_SWEEP_VOL_RATIO_MIN:
            continue
        if metrics["wick_ratio"] < SMC_SWEEP_WICK_MIN_RATIO:
            continue

        level = min(c["low"] for c in prev) if bias == "LONG" else max(c["high"] for c in prev)
        extreme = candle["low"] if bias == "LONG" else candle["high"]
        penetration = (
            (level - extreme) / level if bias == "LONG"
            else (extreme - level) / level
        )
        reclaimed = candle["close"] > level if bias == "LONG" else candle["close"] < level
        if not reclaimed:
            continue
        if penetration < SMC_SWEEP_BUFFER_PCT or penetration > SMC_SWEEP_MAX_PENETRATION_PCT:
            continue
        return {
            "idx": idx,
            "level": level,
            "extreme": extreme,
            "penetration_pct": penetration,
            "wick_ratio": metrics["wick_ratio"],
            "vol_ratio": vol_ratio,
            "candle": candle,
        }
    return None


def _smc_find_mss(candles_15m, sweep, bias):
    closed = candles_15m[:-1]
    sweep_idx = sweep["idx"]
    pre_start = max(0, sweep_idx - SMC_MSS_LOOKBACK_15M)
    pre = closed[pre_start:sweep_idx]
    if len(pre) < 5:
        return None

    pivot_side = "HIGH" if bias == "LONG" else "LOW"
    pivots = _smc_pivot_levels(pre, pivot_side, left=1, right=1)
    if pivots:
        pivot = pivots[-1]
        mss_level = pivot["level"]
        pivot_idx = pre_start + pivot["idx"]
    else:
        fallback = pre[-5:]
        if bias == "LONG":
            offset, candle = max(enumerate(fallback), key=lambda item: item[1]["high"])
            mss_level = candle["high"]
        else:
            offset, candle = min(enumerate(fallback), key=lambda item: item[1]["low"])
            mss_level = candle["low"]
        pivot_idx = sweep_idx - len(fallback) + offset

    baseline = closed[max(0, sweep_idx - VOLUME_AVG_LOOKBACK):sweep_idx]
    avg_body = sum(abs(c["close"] - c["open"]) for c in baseline) / len(baseline) if baseline else 0.0
    avg_volume_value = sum(c.get("volume", 0) for c in baseline) / len(baseline) if baseline else 0.0
    start = sweep_idx + 1
    end = min(len(closed), sweep_idx + 1 + SMC_MSS_CONFIRM_WINDOW)

    for idx in range(start, end):
        candle = closed[idx]
        metrics = _smc_candle_metrics(candle, bias)
        body = abs(candle["close"] - candle["open"])
        body_multiple = body / avg_body if avg_body > 0 else 0.0
        vol_ratio = candle.get("volume", 0) / avg_volume_value if avg_volume_value > 0 else 0.0
        break_level = (
            mss_level * (1 + SMC_MSS_BREAK_BUFFER_PCT) if bias == "LONG"
            else mss_level * (1 - SMC_MSS_BREAK_BUFFER_PCT)
        )
        broke_structure = candle["close"] > break_level if bias == "LONG" else candle["close"] < break_level
        if not broke_structure or not metrics["direction_ok"]:
            continue
        if metrics["body_ratio"] < SMC_DISPLACEMENT_BODY_MIN_RATIO:
            continue
        if body_multiple < SMC_DISPLACEMENT_BODY_MULT:
            continue
        if vol_ratio < SMC_DISPLACEMENT_VOL_RATIO_MIN:
            continue
        return {
            "idx": idx,
            "level": mss_level,
            "pivot_idx": pivot_idx,
            "body_ratio": metrics["body_ratio"],
            "body_multiple": body_multiple,
            "vol_ratio": vol_ratio,
            "candle": candle,
        }
    return None


def _smc_find_fvg(closed, sweep_idx, mss_idx, bias):
    for idx in range(max(2, sweep_idx + 1), mss_idx + 1):
        left = closed[idx - 2]
        right = closed[idx]
        if bias == "LONG" and right["low"] > left["high"]:
            area_low, area_high = left["high"], right["low"]
        elif bias == "SHORT" and right["high"] < left["low"]:
            area_low, area_high = right["high"], left["low"]
        else:
            continue
        midpoint = (area_low + area_high) / 2
        if midpoint > 0 and (area_high - area_low) / midpoint >= SMC_FVG_MIN_PCT:
            return {"idx": idx, "area_low": area_low, "area_high": area_high}
    return None


def _smc_retest_area(candles_15m, sweep, mss, location, bias):
    closed = candles_15m[:-1]
    latest_idx = len(closed) - 1
    if latest_idx <= mss["idx"] or latest_idx - sweep["idx"] > SMC_SETUP_MAX_AGE_15M:
        return None

    after_sweep = closed[sweep["idx"] + 1:latest_idx + 1]
    if bias == "LONG" and any(c["low"] < sweep["extreme"] for c in after_sweep):
        return None
    if bias == "SHORT" and any(c["high"] > sweep["extreme"] for c in after_sweep):
        return None

    impulse = closed[sweep["idx"]:mss["idx"] + 1]
    opposite = [
        c for c in impulse
        if (c["close"] < c["open"] if bias == "LONG" else c["close"] > c["open"])
    ]
    order_block = opposite[-1] if opposite else sweep["candle"]
    ob_low = min(order_block["open"], order_block["close"])
    ob_high = max(order_block["open"], order_block["close"])

    fvg = _smc_find_fvg(closed, sweep["idx"], mss["idx"], bias)
    if SMC_REQUIRE_FVG and not fvg:
        return None
    if fvg:
        overlap_low = max(ob_low, fvg["area_low"])
        overlap_high = min(ob_high, fvg["area_high"])
        if overlap_low < overlap_high:
            area_low, area_high = overlap_low, overlap_high
            zone_source = "OB+FVG"
        else:
            area_low, area_high = fvg["area_low"], fvg["area_high"]
            zone_source = "FVG"
    else:
        area_low, area_high = ob_low, ob_high
        zone_source = "OB"

    zone_mid = (area_low + area_high) / 2
    if zone_mid <= 0 or area_high <= area_low:
        return None
    if (area_high - area_low) / zone_mid > SMC_MAX_ZONE_WIDTH_PCT:
        return None

    retest = closed[-1]
    tolerance = zone_mid * SMC_RETEST_TOLERANCE_PCT
    touched = retest["low"] <= area_high + tolerance and retest["high"] >= area_low - tolerance
    close_in_zone = area_low - tolerance <= retest["close"] <= area_high + tolerance
    metrics = _smc_candle_metrics(retest, bias)
    if bias == "LONG":
        reaction_ok = retest["close"] >= zone_mid and (metrics["direction_ok"] or metrics["wick_ratio"] >= 0.25)
        sl = sweep["extreme"] * (1 - SMC_SL_BUFFER_PCT)
        targets = sorted(level for level in location["target_levels"] if level > retest["close"])
    else:
        reaction_ok = retest["close"] <= zone_mid and (metrics["direction_ok"] or metrics["wick_ratio"] >= 0.25)
        sl = sweep["extreme"] * (1 + SMC_SL_BUFFER_PCT)
        targets = sorted((level for level in location["target_levels"] if level < retest["close"]), reverse=True)
    if not touched or not close_in_zone or not reaction_ok or not targets:
        return None

    entry = retest["close"]
    target_level = targets[0]
    tp = (
        target_level * (1 - SMC_TARGET_BUFFER_PCT) if bias == "LONG"
        else target_level * (1 + SMC_TARGET_BUFFER_PCT)
    )
    risk = entry - sl if bias == "LONG" else sl - entry
    reward = tp - entry if bias == "LONG" else entry - tp
    rr = reward / risk if risk > 0 else 0.0
    if risk <= 0 or reward <= 0 or rr < SMC_MIN_RR:
        return None

    return {
        "entry": entry,
        "sl": sl,
        "tp": tp,
        "rr": rr,
        "target_level": target_level,
        "area_low": area_low,
        "area_high": area_high,
        "zone_source": zone_source,
    }


def detect_smart_money_c_v2_shadow(pair, candles_15m, candles_4h, trend_4h, funding=None):
    """Legacy Strategy C v2 retained for regression comparison only."""
    if not ENABLE_SMART_MONEY_C_SHADOW or not ENABLE_SHADOW_TRACKING:
        return None

    candidates = []
    if trend_4h != "BEARISH":
        candidates.append("LONG")
    if trend_4h != "BULLISH":
        candidates.append("SHORT")

    for bias in candidates:
        if bias == "LONG" and funding is not None and funding > FUNDING_RATE_MAX_LONG:
            continue
        if bias == "SHORT" and funding is not None and funding < FUNDING_RATE_MIN_SHORT:
            continue

        sweep = _smc_find_liquidity_sweep(candles_15m, bias)
        if not sweep:
            continue
        location = _smc_find_4h_location(candles_4h, bias, sweep["extreme"])
        if not location:
            continue
        mss = _smc_find_mss(candles_15m, sweep, bias)
        if not mss:
            continue
        area = _smc_retest_area(candles_15m, sweep, mss, location, bias)
        if not area:
            continue

        return {
            "pair": pair,
            "bias": bias,
            "entry": area["entry"],
            "sl": area["sl"],
            "tp": area["tp"],
            "blocked_reason": "smart_money_c_v2",
            "blocked_detail": (
                f"{location['zone'].lower()} sweep={sweep['level']:.6g} "
                f"vol={sweep['vol_ratio']:.2f}x mss={mss['level']:.6g} "
                f"zone={area['zone_source']} rr={area['rr']:.2f}"
            ),
            "meta": {
                "entry_path": "C2_SHADOW",
                "strategy_version": "C2",
                "smc_location_zone": location["zone"],
                "smc_range_position": round(location["range_position"], 4),
                "smc_4h_liquidity_level": location["liquidity_level"],
                "smc_4h_location_distance_pct": round(location["distance_pct"], 5),
                "smc_sweep_level": sweep["level"],
                "smc_sweep_extreme": sweep["extreme"],
                "smc_sweep_penetration_pct": round(sweep["penetration_pct"], 5),
                "smc_sweep_wick_ratio": round(sweep["wick_ratio"], 3),
                "smc_sweep_vol_ratio": round(sweep["vol_ratio"], 3),
                "smc_mss_level": mss["level"],
                "smc_displacement_body_ratio": round(mss["body_ratio"], 3),
                "smc_displacement_body_multiple": round(mss["body_multiple"], 3),
                "smc_displacement_vol_ratio": round(mss["vol_ratio"], 3),
                "smc_area_low": area["area_low"],
                "smc_area_high": area["area_high"],
                "smc_zone_source": area["zone_source"],
                "smc_target_level": area["target_level"],
                "actual_rr": round(area["rr"], 2),
            },
        }
    return None


def _smc_v3_find_liquidity_sweep(candles_15m, bias):
    minimum = SMC_V3_SWEEP_LOOKBACK_15M + 4
    if len(candles_15m) < minimum:
        return None
    closed = candles_15m[:-1]
    search_start = max(
        SMC_V3_SWEEP_LOOKBACK_15M,
        len(closed) - 1 - SMC_V3_SETUP_MAX_AGE_15M,
    )
    search_end = len(closed) - 3
    for idx in range(search_end, search_start - 1, -1):
        candle = closed[idx]
        previous = closed[idx - SMC_V3_SWEEP_LOOKBACK_15M:idx]
        volume_window = closed[max(0, idx - VOLUME_AVG_LOOKBACK):idx]
        if len(previous) < SMC_V3_SWEEP_LOOKBACK_15M or not volume_window:
            continue
        average_volume = sum(c.get("volume", 0) for c in volume_window) / len(volume_window)
        if average_volume <= 0:
            continue

        metrics = _smc_candle_metrics(candle, bias)
        volume_ratio = candle.get("volume", 0) / average_volume
        if volume_ratio < SMC_V3_SWEEP_VOL_RATIO_MIN:
            continue
        if metrics["wick_ratio"] < SMC_V3_SWEEP_WICK_MIN_RATIO:
            continue

        level = min(c["low"] for c in previous) if bias == "LONG" else max(c["high"] for c in previous)
        extreme = candle["low"] if bias == "LONG" else candle["high"]
        penetration = (
            (level - extreme) / level if bias == "LONG"
            else (extreme - level) / level
        )
        reclaimed = candle["close"] > level if bias == "LONG" else candle["close"] < level
        if not reclaimed:
            continue
        if penetration < SMC_SWEEP_BUFFER_PCT or penetration > SMC_SWEEP_MAX_PENETRATION_PCT:
            continue
        return {
            "idx": idx,
            "level": level,
            "extreme": extreme,
            "penetration_pct": penetration,
            "wick_ratio": metrics["wick_ratio"],
            "vol_ratio": volume_ratio,
            "candle": candle,
        }
    return None


def _smc_v3_find_mss(candles_15m, sweep, bias):
    closed = candles_15m[:-1]
    sweep_idx = sweep["idx"]
    pre_start = max(0, sweep_idx - SMC_V3_MSS_LOOKBACK_15M)
    pre = closed[pre_start:sweep_idx]
    if len(pre) < 5:
        return None

    pivot_side = "HIGH" if bias == "LONG" else "LOW"
    pivots = _smc_pivot_levels(pre, pivot_side, left=1, right=1)
    if pivots:
        pivot = pivots[-1]
        mss_level = pivot["level"]
        pivot_idx = pre_start + pivot["idx"]
    else:
        fallback = pre[-5:]
        if bias == "LONG":
            offset, pivot_candle = max(enumerate(fallback), key=lambda item: item[1]["high"])
            mss_level = pivot_candle["high"]
        else:
            offset, pivot_candle = min(enumerate(fallback), key=lambda item: item[1]["low"])
            mss_level = pivot_candle["low"]
        pivot_idx = sweep_idx - len(fallback) + offset

    baseline = closed[max(0, sweep_idx - VOLUME_AVG_LOOKBACK):sweep_idx]
    average_body = sum(abs(c["close"] - c["open"]) for c in baseline) / len(baseline) if baseline else 0.0
    average_volume = sum(c.get("volume", 0) for c in baseline) / len(baseline) if baseline else 0.0
    end = min(len(closed), sweep_idx + 1 + SMC_V3_MSS_CONFIRM_WINDOW)
    for idx in range(sweep_idx + 1, end):
        candle = closed[idx]
        metrics = _smc_candle_metrics(candle, bias)
        body = abs(candle["close"] - candle["open"])
        body_multiple = body / average_body if average_body > 0 else 0.0
        volume_ratio = candle.get("volume", 0) / average_volume if average_volume > 0 else 0.0
        break_level = (
            mss_level * (1 + SMC_MSS_BREAK_BUFFER_PCT) if bias == "LONG"
            else mss_level * (1 - SMC_MSS_BREAK_BUFFER_PCT)
        )
        broke_structure = candle["close"] > break_level if bias == "LONG" else candle["close"] < break_level
        if not broke_structure or not metrics["direction_ok"]:
            continue
        displacement_flags = {
            "body_ratio": metrics["body_ratio"] >= SMC_DISPLACEMENT_BODY_MIN_RATIO,
            "body_multiple": body_multiple >= SMC_DISPLACEMENT_BODY_MULT,
            "volume": volume_ratio >= SMC_DISPLACEMENT_VOL_RATIO_MIN,
        }
        displacement_score = sum(displacement_flags.values())
        if displacement_score < SMC_V3_DISPLACEMENT_MIN_SCORE:
            continue
        return {
            "idx": idx,
            "level": mss_level,
            "pivot_idx": pivot_idx,
            "body_ratio": metrics["body_ratio"],
            "body_multiple": body_multiple,
            "vol_ratio": volume_ratio,
            "displacement_score": displacement_score,
            "displacement_flags": displacement_flags,
            "candle": candle,
        }
    return None


def _smc_v3_retest_area(candles_15m, sweep, mss, location, bias):
    closed = candles_15m[:-1]
    latest_idx = len(closed) - 1
    if latest_idx <= mss["idx"] or latest_idx - sweep["idx"] > SMC_V3_SETUP_MAX_AGE_15M:
        return None

    after_sweep = closed[sweep["idx"] + 1:latest_idx + 1]
    if bias == "LONG" and any(c["low"] < sweep["extreme"] for c in after_sweep):
        return None
    if bias == "SHORT" and any(c["high"] > sweep["extreme"] for c in after_sweep):
        return None

    impulse = closed[sweep["idx"]:mss["idx"] + 1]
    opposite = [
        c for c in impulse
        if (c["close"] < c["open"] if bias == "LONG" else c["close"] > c["open"])
    ]
    order_block = opposite[-1] if opposite else sweep["candle"]
    ob_low = min(order_block["open"], order_block["close"])
    ob_high = max(order_block["open"], order_block["close"])
    if ob_high <= ob_low:
        ob_low, ob_high = order_block["low"], order_block["high"]

    fvg = _smc_find_fvg(closed, sweep["idx"], mss["idx"], bias)
    area_low, area_high = ob_low, ob_high
    zone_source = "OB"
    if fvg:
        overlap_low = max(ob_low, fvg["area_low"])
        overlap_high = min(ob_high, fvg["area_high"])
        if overlap_low < overlap_high:
            area_low, area_high = overlap_low, overlap_high
            zone_source = "OB+FVG"

    zone_mid = (area_low + area_high) / 2
    if zone_mid <= 0 or area_high <= area_low:
        return None
    if (area_high - area_low) / zone_mid > SMC_V3_MAX_ZONE_WIDTH_PCT:
        return None

    retest = closed[-1]
    tolerance = zone_mid * SMC_V3_RETEST_TOLERANCE_PCT
    touched = retest["low"] <= area_high + tolerance and retest["high"] >= area_low - tolerance
    metrics = _smc_candle_metrics(retest, bias)
    if bias == "LONG":
        reaction_ok = retest["close"] >= zone_mid and (metrics["direction_ok"] or metrics["wick_ratio"] >= 0.20)
        extension = max(0.0, retest["close"] - area_high) / zone_mid
        sl = sweep["extreme"] * (1 - SMC_SL_BUFFER_PCT)
        targets = sorted(level for level in location["target_levels"] if level > retest["close"])
    else:
        reaction_ok = retest["close"] <= zone_mid and (metrics["direction_ok"] or metrics["wick_ratio"] >= 0.20)
        extension = max(0.0, area_low - retest["close"]) / zone_mid
        sl = sweep["extreme"] * (1 + SMC_SL_BUFFER_PCT)
        targets = sorted((level for level in location["target_levels"] if level < retest["close"]), reverse=True)
    if not touched or not reaction_ok or extension > SMC_V3_MAX_ENTRY_EXTENSION_PCT or not targets:
        return None

    entry = retest["close"]
    risk = entry - sl if bias == "LONG" else sl - entry
    if risk <= 0:
        return None
    selected = None
    for target_level in targets:
        tp = (
            target_level * (1 - SMC_TARGET_BUFFER_PCT) if bias == "LONG"
            else target_level * (1 + SMC_TARGET_BUFFER_PCT)
        )
        reward = tp - entry if bias == "LONG" else entry - tp
        rr = reward / risk if risk > 0 else 0.0
        if reward > 0 and rr >= SMC_V3_MIN_RR:
            selected = (target_level, tp, rr)
            break
    if not selected:
        return None
    target_level, tp, rr = selected
    return {
        "entry": entry,
        "sl": sl,
        "tp": tp,
        "rr": rr,
        "target_level": target_level,
        "area_low": area_low,
        "area_high": area_high,
        "zone_source": zone_source,
        "has_fvg": bool(fvg),
        "entry_extension_pct": extension,
    }


def detect_smart_money_c_v3_shadow(pair, candles_15m, candles_4h, trend_4h, funding=None):
    """Strategy C v3 liquidity-sweep reversal, shadow-only."""
    if not ENABLE_SMART_MONEY_C_SHADOW or not ENABLE_SHADOW_TRACKING:
        return None
    for bias in ("LONG", "SHORT"):
        if bias == "LONG" and funding is not None and funding > FUNDING_RATE_MAX_LONG:
            continue
        if bias == "SHORT" and funding is not None and funding < FUNDING_RATE_MIN_SHORT:
            continue
        sweep = _smc_v3_find_liquidity_sweep(candles_15m, bias)
        if not sweep:
            continue
        location = _smc_find_4h_location(candles_4h, bias, sweep["extreme"])
        if not location:
            continue

        expected_trend = "BULLISH" if bias == "LONG" else "BEARISH"
        countertrend = trend_4h not in (expected_trend, "SIDEWAYS")
        if countertrend:
            extreme_ok = (
                location["range_position"] <= SMC_V3_COUNTERTREND_EXTREME_PCT
                if bias == "LONG"
                else location["range_position"] >= 1.0 - SMC_V3_COUNTERTREND_EXTREME_PCT
            )
            if not extreme_ok:
                continue

        mss = _smc_v3_find_mss(candles_15m, sweep, bias)
        if not mss:
            continue
        if countertrend and mss["displacement_score"] < 3:
            continue
        area = _smc_v3_retest_area(candles_15m, sweep, mss, location, bias)
        if not area:
            continue

        return {
            "pair": pair,
            "bias": bias,
            "entry": area["entry"],
            "sl": area["sl"],
            "tp": area["tp"],
            "blocked_reason": "smart_money_c_v3",
            "blocked_detail": (
                f"{location['zone'].lower()} sweep={sweep['level']:.6g} "
                f"mss_score={mss['displacement_score']}/3 "
                f"zone={area['zone_source']} rr={area['rr']:.2f}"
            ),
            "meta": {
                "entry_path": "C3_SHADOW",
                "strategy_version": "C3",
                "smc_location_zone": location["zone"],
                "smc_range_position": round(location["range_position"], 4),
                "smc_4h_liquidity_level": location["liquidity_level"],
                "smc_4h_location_distance_pct": round(location["distance_pct"], 5),
                "smc_sweep_level": sweep["level"],
                "smc_sweep_extreme": sweep["extreme"],
                "smc_sweep_penetration_pct": round(sweep["penetration_pct"], 5),
                "smc_sweep_wick_ratio": round(sweep["wick_ratio"], 3),
                "smc_sweep_vol_ratio": round(sweep["vol_ratio"], 3),
                "smc_mss_level": mss["level"],
                "smc_displacement_score": mss["displacement_score"],
                "smc_displacement_body_ratio": round(mss["body_ratio"], 3),
                "smc_displacement_body_multiple": round(mss["body_multiple"], 3),
                "smc_displacement_vol_ratio": round(mss["vol_ratio"], 3),
                "smc_area_low": area["area_low"],
                "smc_area_high": area["area_high"],
                "smc_zone_source": area["zone_source"],
                "smc_has_fvg": area["has_fvg"],
                "smc_target_level": area["target_level"],
                "smc_countertrend": countertrend,
                "smc_trend_4h": trend_4h,
                "actual_rr": round(area["rr"], 2),
            },
        }
    return None


def _smc_c6_atr(candles):
    if len(candles) < ATR_PERIOD + 1:
        return None
    sample = candles[-(ATR_PERIOD + 1):]
    true_ranges = []
    for previous, current in zip(sample[:-1], sample[1:]):
        true_ranges.append(max(
            float(current["high"]) - float(current["low"]),
            abs(float(current["high"]) - float(previous["close"])),
            abs(float(current["low"]) - float(previous["close"])),
        ))
    return sum(true_ranges) / len(true_ranges) if true_ranges else None


def _smc_c6_context_4h(candles_4h):
    closed = list(candles_4h[:-1])
    if len(closed) < 60:
        return None
    closes = [float(c["close"]) for c in closed]
    fast = ema(closes, 21)
    slow = ema(closes, 55)
    atr_4h = _smc_c6_atr(closed)
    _, slow_slope = ema_slope(closes, 55)
    if fast is None or slow is None or atr_4h is None or slow_slope is None:
        return None
    if fast > slow and closes[-1] > slow and slow_slope > 0:
        side = "LONG"
    elif fast < slow and closes[-1] < slow and slow_slope < 0:
        side = "SHORT"
    else:
        side = None
    return {"side": side, "fast": fast, "slow": slow, "atr": atr_4h}


def _smc_c6_flow_ratio(candles, bias):
    buy = sum(float(c.get("taker_buy", 0.0)) for c in candles)
    sell = sum(float(c.get("taker_sell", 0.0)) for c in candles)
    total = buy + sell
    if total <= 0:
        return 0.5
    return buy / total if bias == "LONG" else sell / total


def _smc_c6_absorption_ratio(candle, bias):
    buy = float(candle.get("taker_buy", 0.0))
    sell = float(candle.get("taker_sell", 0.0))
    total = buy + sell
    if total <= 0:
        return 0.5
    return sell / total if bias == "LONG" else buy / total


def _smc_c6_market_ok(bias, market_context):
    if not isinstance(market_context, dict):
        return False
    trend = market_context.get("trend")
    ret_12h = market_context.get("ret_12h")
    if trend not in ("BULLISH", "BEARISH", "SIDEWAYS") or ret_12h is None:
        return False
    trend_ok = trend != "BEARISH" if bias == "LONG" else trend != "BULLISH"
    return_ok = float(ret_12h) >= -0.01 if bias == "LONG" else float(ret_12h) <= 0.01
    return trend_ok and return_ok


def _smc_c6_find_setup(candles_15m, candles_4h, market_context):
    closed = list(candles_15m[:-1])
    latest_idx = len(closed) - 1
    if latest_idx < SMC_C6_SWEEP_LOOKBACK_15M + 15:
        return None
    context = _smc_c6_context_4h(candles_4h)
    if not context or not context["side"]:
        return None
    bias = context["side"]
    if not _smc_c6_market_ok(bias, market_context):
        return None

    search_start = max(
        SMC_C6_SWEEP_LOOKBACK_15M,
        latest_idx - SMC_C6_SEARCH_BARS_15M,
    )
    search_end = latest_idx - 2
    for sweep_idx in range(search_end, search_start - 1, -1):
        sweep = closed[sweep_idx]
        previous = closed[
            sweep_idx - SMC_C6_SWEEP_LOOKBACK_15M:sweep_idx
        ]
        atr_15m = _smc_c6_atr(closed[max(0, sweep_idx - 30):sweep_idx])
        if len(previous) < SMC_C6_SWEEP_LOOKBACK_15M or not atr_15m:
            continue
        level = (
            min(float(c["low"]) for c in previous)
            if bias == "LONG"
            else max(float(c["high"]) for c in previous)
        )
        extreme = float(sweep["low"] if bias == "LONG" else sweep["high"])
        penetration_atr = (
            (level - extreme) / atr_15m
            if bias == "LONG"
            else (extreme - level) / atr_15m
        )
        metrics = _smc_candle_metrics(sweep, bias)
        reclaimed = (
            float(sweep["close"]) > level
            if bias == "LONG"
            else float(sweep["close"]) < level
        )
        absorption = _smc_c6_absorption_ratio(sweep, bias)
        if bias == "LONG":
            location_ok = (
                context["slow"] - 0.50 * context["atr"]
                <= extreme
                <= context["fast"] + SMC_C6_MAX_FAST_DISTANCE_ATR * context["atr"]
            )
            fast_distance_atr = (extreme - context["fast"]) / context["atr"]
        else:
            location_ok = (
                context["fast"] - SMC_C6_MAX_FAST_DISTANCE_ATR * context["atr"]
                <= extreme
                <= context["slow"] + 0.50 * context["atr"]
            )
            fast_distance_atr = (context["fast"] - extreme) / context["atr"]
        if not (
            reclaimed
            and 0.05 <= penetration_atr <= 0.85
            and metrics["wick_ratio"] >= 0.20
            and metrics["close_position"] >= 0.55
            and absorption >= SMC_C6_ABSORPTION_MIN
            and location_ok
        ):
            continue

        pre_structure = closed[max(0, sweep_idx - 8):sweep_idx]
        mss_level = (
            max(float(c["high"]) for c in pre_structure)
            if bias == "LONG"
            else min(float(c["low"]) for c in pre_structure)
        )
        mss = None
        mss_end = min(latest_idx, sweep_idx + 9)
        for mss_idx in range(sweep_idx + 1, mss_end):
            candidate = closed[mss_idx]
            candidate_metrics = _smc_candle_metrics(candidate, bias)
            candidate_atr = _smc_c6_atr(
                closed[max(0, mss_idx - 30):mss_idx + 1]
            )
            if not candidate_atr:
                continue
            broke = (
                float(candidate["close"]) > mss_level
                if bias == "LONG"
                else float(candidate["close"]) < mss_level
            )
            body_atr = (
                abs(float(candidate["close"]) - float(candidate["open"]))
                / candidate_atr
            )
            flow = _smc_c6_flow_ratio([candidate], bias)
            if (
                broke
                and candidate_metrics["direction_ok"]
                and candidate_metrics["body_ratio"] >= SMC_C6_MSS_BODY_MIN_RATIO
                and body_atr >= 0.40
                and flow >= SMC_C6_MSS_FLOW_MIN
            ):
                mss = {
                    "idx": mss_idx,
                    "atr": candidate_atr,
                    "flow": flow,
                    "body_atr": body_atr,
                }
                break
        if not mss or latest_idx <= mss["idx"] or latest_idx - mss["idx"] > 8:
            continue

        after_sweep = closed[sweep_idx + 1:latest_idx + 1]
        breached = (
            any(float(c["low"]) < extreme for c in after_sweep)
            if bias == "LONG"
            else any(float(c["high"]) > extreme for c in after_sweep)
        )
        if breached:
            continue
        retest = closed[latest_idx]
        tolerance = 0.25 * mss["atr"]
        touched = (
            float(retest["low"]) <= mss_level + tolerance
            if bias == "LONG"
            else float(retest["high"]) >= mss_level - tolerance
        )
        retest_metrics = _smc_candle_metrics(retest, bias)
        reclaimed_mss = (
            float(retest["close"]) > mss_level
            if bias == "LONG"
            else float(retest["close"]) < mss_level
        )
        retest_flow = _smc_c6_flow_ratio(closed[max(0, latest_idx - 1):latest_idx + 1], bias)
        if not (
            touched
            and reclaimed_mss
            and retest_metrics["close_position"] >= 0.55
            and (retest_metrics["direction_ok"] or retest_metrics["wick_ratio"] >= 0.20)
            and retest_flow >= 0.48
        ):
            continue

        # The final item is the currently forming candle. Its open is already
        # known at scan time and matches the replay's next-candle-open entry.
        entry = float(candles_15m[-1]["open"])
        stop = (
            extreme - 0.12 * atr_15m
            if bias == "LONG"
            else extreme + 0.12 * atr_15m
        )
        risk = entry - stop if bias == "LONG" else stop - entry
        risk_pct = risk / entry if entry > 0 else 0.0
        if risk <= 0 or not (SMC_C6_MIN_RISK_PCT <= risk_pct <= SMC_C6_MAX_RISK_PCT):
            continue
        target = (
            entry + SMC_C6_TARGET_R * risk
            if bias == "LONG"
            else entry - SMC_C6_TARGET_R * risk
        )
        return {
            "bias": bias,
            "entry": entry,
            "sl": stop,
            "tp": target,
            "sweep": sweep,
            "sweep_idx": sweep_idx,
            "level": level,
            "extreme": extreme,
            "penetration_atr": penetration_atr,
            "absorption": absorption,
            "mss_level": mss_level,
            "mss_flow": mss["flow"],
            "mss_body_atr": mss["body_atr"],
            "retest_flow": retest_flow,
            "fast_distance_atr": fast_distance_atr,
            "risk_pct": risk_pct,
        }
    return None


def detect_smart_money_c_v6_shadow(
    pair,
    candles_15m,
    candles_4h,
    trend_4h,
    funding=None,
    market_context=None,
):
    """Validated C6 candidate; records virtual trades only."""
    if not ENABLE_SMART_MONEY_C_SHADOW or not ENABLE_SHADOW_TRACKING:
        return None
    setup = _smc_c6_find_setup(candles_15m, candles_4h, market_context)
    if not setup:
        return None
    bias = setup["bias"]
    if bias == "LONG" and funding is not None and funding > FUNDING_RATE_MAX_LONG:
        return None
    if bias == "SHORT" and funding is not None and funding < FUNDING_RATE_MIN_SHORT:
        return None
    sweep_time = int(setup["sweep"].get("open_time", 0) or 0)
    return {
        "pair": pair,
        "bias": bias,
        "entry": setup["entry"],
        "sl": setup["sl"],
        "tp": setup["tp"],
        "blocked_reason": "smart_money_c_v6",
        "blocked_detail": (
            f"sweep={setup['level']:.6g} absorb={setup['absorption']:.2f} "
            f"mss_flow={setup['mss_flow']:.2f} target={SMC_C6_TARGET_R:.1f}R"
        ),
        "meta": {
            "entry_path": "C6_SHADOW",
            "strategy_version": "C6",
            "setup_id": f"C6:{pair}:{bias}:{sweep_time}",
            "shadow_timeout_hours": SMC_C6_TIMEOUT_HOURS,
            "smc_sweep_time": sweep_time,
            "smc_sweep_level": setup["level"],
            "smc_sweep_extreme": setup["extreme"],
            "smc_sweep_penetration_atr": round(setup["penetration_atr"], 4),
            "smc_absorption_ratio": round(setup["absorption"], 4),
            "smc_mss_level": setup["mss_level"],
            "smc_mss_flow_ratio": round(setup["mss_flow"], 4),
            "smc_mss_body_atr": round(setup["mss_body_atr"], 4),
            "smc_retest_flow_ratio": round(setup["retest_flow"], 4),
            "smc_fast_distance_atr": round(setup["fast_distance_atr"], 4),
            "risk_pct": round(setup["risk_pct"], 6),
            "actual_rr": SMC_C6_TARGET_R,
        },
    }


def detect_smart_money_c_shadow(
    pair,
    candles_15m,
    candles_4h,
    trend_4h,
    funding=None,
    market_context=None,
):
    if SMART_MONEY_C_VERSION >= 6:
        return detect_smart_money_c_v6_shadow(
            pair,
            candles_15m,
            candles_4h,
            trend_4h,
            funding=funding,
            market_context=market_context,
        )
    detector = detect_smart_money_c_v3_shadow if SMART_MONEY_C_VERSION >= 3 else detect_smart_money_c_v2_shadow
    return detector(pair, candles_15m, candles_4h, trend_4h, funding=funding)

# ---------------------- SWEEP ----------------------
def is_liquidity_sweep(candles_4h):
    if not candles_4h or len(candles_4h) < 7:
        return False
    swing_high = max(c["high"] for c in candles_4h[-7:-2])
    swing_low  = min(c["low"]  for c in candles_4h[-7:-2])
    last = candles_4h[-2]
    vols = [c["volume"] for c in candles_4h[-7:-2]]
    avgv = sum(vols) / len(vols) if vols else 0
    return (last["high"] > swing_high or last["low"] < swing_low) and \
            last["volume"] > avgv * SWEEP_VOLUME_MULT

# ---------------------- [V7-S7] TIME-OF-DAY FILTER ----------------------
def trading_hours_ok() -> bool:
    """
    [V7-S7] Filter jam trading — skip Asian dead zone 00:00–07:00 UTC.
    Likuiditas turun 40-60% di jam ini:
    - Volume rendah → false S/R break, orderflow tidak representatif
    - Spread melebar → fills lebih buruk
    - Whale manipulation lebih mudah (market tipis)
    Active window: 07:00–23:00 UTC (covers London open + NY session + early Asia close)

    [V7.2.4] ENABLE_TIME_FILTER=False (default sekarang) → selalu True, bot
    scan 24 jam penuh tanpa skip jam manapun.
    """
    if not ENABLE_TIME_FILTER:
        return True
    utc_hour = utc_hour_now()
    return TRADING_HOUR_START_UTC <= utc_hour < TRADING_HOUR_END_UTC

# ---------------------- [V7-S3] REJECTION CANDLE DETECT ----------------------
def is_rejection_candle(candle: dict, bias: str) -> bool:
    """
    [V7-S3] Deteksi rejection candle di level S/R — gantikan candle_bullish yang salah.

    Logika:
    - LONG (entry di support): candle harus punya lower wick panjang.
      Lower wick panjang = harga turun ke support, ditolak (bullish rejection).
      Ini membuktikan support DIRESPEK, bukan sekadar price lewat.
      lower_wick  = min(open, close) - low
      wick_ratio  = lower_wick / (high - low)
      Valid jika wick_ratio >= REJECTION_WICK_MIN_RATIO (38%)

    - SHORT (entry di resistance): candle harus punya upper wick panjang.
      Upper wick panjang = harga naik ke resistance, ditolak (bearish rejection).
      upper_wick  = high - max(open, close)
      wick_ratio  = upper_wick / (high - low)
      Valid jika wick_ratio >= REJECTION_WICK_MIN_RATIO (38%)

    Keuntungan vs candle_bullish lama:
    - candle_bullish = price sudah naik → entry terlambat, bukan di pullback
    - rejection_candle = price menyentuh level DAN bounce → entry di titik yang tepat
    """
    try:
        h   = float(candle["high"])
        l   = float(candle["low"])
        o   = float(candle["open"])
        c   = float(candle["close"])
        rng = h - l
        if rng <= 0:
            return False
        if bias == "LONG":
            lower_wick = min(o, c) - l
            return (lower_wick / rng) >= REJECTION_WICK_MIN_RATIO
        else:  # SHORT
            upper_wick = h - max(o, c)
            return (upper_wick / rng) >= REJECTION_WICK_MIN_RATIO
    except Exception:
        return False


def is_rejection_candle_at_level(
    candle: dict,
    bias: str,
    level: float,
    tol: float = None,
) -> bool:
    """Require the rejection wick and S/R interaction on the same candle."""
    if not is_rejection_candle(candle, bias):
        return False
    try:
        level = float(level)
        tolerance = SR_TOUCH_TOL if tol is None else float(tol)
        if level <= 0 or tolerance < 0:
            return False
        if bias == "LONG":
            return float(candle["low"]) <= level * (1 + tolerance)
        if bias == "SHORT":
            return float(candle["high"]) >= level * (1 - tolerance)
        return False
    except Exception:
        return False


# ---------------------- [V7-S4] MARKET STRUCTURE CHECK ----------------------
def market_structure_ok(candles_4h: list, bias: str) -> bool:
    """
    [V7-S4] Validasi Higher Timeframe Market Structure sebelum entry.

    Masalah yang diselesaikan:
    Tanpa ini, bot bisa entry LONG pada corrective bounce dalam downtrend besar —
    4H EMA slope > 0 sesaat tapi struktur makro masih bearish.

    Logika:
    LONG: 4H harus menunjukkan HH (Higher High) ATAU HL (Higher Low)
      → konfirmasi trend bullish nyata, bukan sekadar bounce sementara
    SHORT: 4H harus menunjukkan LL (Lower Low) ATAU LH (Lower High)
      → konfirmasi trend bearish nyata

    Implementasi:
    - Ambil 10 closed candle terakhir dari 4H
    - Bandingkan extreme tertinggi/terendah dari 5 candle pertama vs 5 candle kedua
    - Jika struktur sesuai bias → OK
    - Default True jika data tidak cukup (fail-open, jangan blokir karena kurang data)
    """
    if not candles_4h or len(candles_4h) < 12:
        return True  # data kurang → default allow
    try:
        # 10 closed candle (exclude candle yang masih berjalan)
        recent = candles_4h[-11:-1]
        if len(recent) < 10:
            return True
        half = len(recent) // 2
        first_half  = recent[:half]
        second_half = recent[half:]

        h_first  = max(c["high"] for c in first_half)
        h_second = max(c["high"] for c in second_half)
        l_first  = min(c["low"]  for c in first_half)
        l_second = min(c["low"]  for c in second_half)

        if bias == "LONG":
            hh = h_second > h_first   # Higher High: baru lebih tinggi dari lama
            hl = l_second > l_first   # Higher Low: low baru lebih tinggi dari low lama
            return hh or hl
        else:  # SHORT
            ll = l_second < l_first   # Lower Low: baru lebih rendah dari lama
            lh = h_second < h_first   # Lower High: high baru lebih rendah dari high lama
            return ll or lh
    except Exception:
        return True

# ---------------------- ORDERFLOW ----------------------
def taker_ratio(candles, lookback=ORDERFLOW_LOOKBACK):
    recent = candles[-lookback:]
    buy    = sum(c["taker_buy"]  for c in recent)
    sell   = sum(c["taker_sell"] for c in recent)
    total  = buy + sell
    if total <= 0:
        return 0.0, 0.0, buy, sell
    return buy / total, sell / total, buy, sell

# ---------------------- REGIME FILTER ----------------------
def regime_ok_4h(closes_4h, highs_4h, lows_4h):
    try:
        atr_val = atr(highs_4h, lows_4h, closes_4h, ATR_PERIOD)
        if atr_val is None:
            return False
        atr_pct = atr_val / closes_4h[-1] if closes_4h[-1] else 0
        ema_now, slope = ema_slope(closes_4h, EMA_SLOW)
        if slope is None or ema_now is None:
            return False
        ema_old = ema(closes_4h[:-10], EMA_SLOW) if len(closes_4h) > EMA_SLOW + 10 else None
        ema_moved = True
        if ema_old and ema_old > 0:
            ema_moved = abs(ema_now - ema_old) / ema_old >= SIDEWAYS_EMA_BAND_PCT
        return atr_pct >= REGIME_MIN_ATR_PCT and abs(slope) >= REGIME_MIN_SLOPE and ema_moved
    except Exception:
        return False


# ---------------------- [V8] QUALITY CONTEXT ----------------------
def quality_context_4h(candles_4h, exclude_incomplete=True):
    """Build a strict 4H context from confirmed candles only."""
    closed = list(candles_4h[:-1] if exclude_incomplete else candles_4h)
    if len(closed) < 60:
        return None

    closes = [float(c["close"]) for c in closed]
    ema21 = ema(closes, 21)
    ema55 = ema(closes, 55)
    if ema21 is None or ema55 is None:
        return None

    window = closed[-50:]
    high_pivots = _smc_pivot_levels(window, "HIGH", left=2, right=2)
    low_pivots = _smc_pivot_levels(window, "LOW", left=2, right=2)
    structure = "UNKNOWN"
    if len(high_pivots) >= 2 and len(low_pivots) >= 2:
        higher_high = high_pivots[-1]["level"] > high_pivots[-2]["level"]
        higher_low = low_pivots[-1]["level"] > low_pivots[-2]["level"]
        if higher_high and higher_low:
            structure = "BULLISH"
        elif not higher_high and not higher_low:
            structure = "BEARISH"
        else:
            structure = "MIXED"

    close = closes[-1]
    range_window = closed[-30:]
    range_low = min(float(c["low"]) for c in range_window)
    range_high = max(float(c["high"]) for c in range_window)
    range_position = (
        (close - range_low) / (range_high - range_low)
        if range_high > range_low else 0.5
    )
    return {
        "close": close,
        "ema21": ema21,
        "ema55": ema55,
        "ema_alignment": "BULLISH" if ema21 > ema55 else "BEARISH",
        "structure": structure,
        "ret_12h": (close / closes[-4] - 1.0) if closes[-4] else 0.0,
        "ret_24h": (close / closes[-7] - 1.0) if closes[-7] else 0.0,
        "range_position": max(0.0, min(1.0, range_position)),
        "confirmed_close_time": int(closed[-1].get("close_time", 0) or 0),
    }


def quality_local_snapshot(candles_4h, bias):
    context = quality_context_4h(candles_4h, exclude_incomplete=True)
    if not context:
        return {
            "score": 0,
            "structure": False,
            "ema": False,
            "momentum_12h": False,
            "range_position": None,
            "context": None,
        }
    expected = "BULLISH" if bias == "LONG" else "BEARISH"
    structure_ok = context["structure"] == expected
    ema_ok = context["ema_alignment"] == expected
    momentum_ok = context["ret_12h"] >= 0 if bias == "LONG" else context["ret_12h"] <= 0
    return {
        "score": int(structure_ok) + int(ema_ok) + int(momentum_ok),
        "structure": structure_ok,
        "ema": ema_ok,
        "momentum_12h": momentum_ok,
        "range_position": context["range_position"],
        "context": context,
    }


def quality_live_gate_decision(snapshot, bias):
    """Side-aware V8.1 gate selected from the 90-day segmented replay."""
    if not snapshot or not snapshot.get("context"):
        return False, "context_missing"
    if not snapshot.get("ema"):
        return False, "ema21_55_misaligned"
    if bias == "LONG" and not snapshot.get("structure"):
        return False, "long_structure_not_bullish"
    if bias == "SHORT":
        range_position = snapshot.get("range_position")
        if range_position is None or range_position < QUALITY_SHORT_MIN_RANGE_POSITION:
            return False, f"short_too_low_in_range({range_position})"
    return True, "ok"


def quality_risk_gate_decision(sl_pct):
    if sl_pct >= QUALITY_MAX_SL_PCT:
        return False, f"sl_pct={sl_pct:.3%}"
    return True, "ok"


def build_smc_c6_btc_context(candles_4h):
    context = quality_context_4h(candles_4h, exclude_incomplete=True)
    closed = list(candles_4h[:-1])
    if not context or len(closed) < 60:
        return None
    closes = [float(c["close"]) for c in closed]
    _, slow_slope = ema_slope(closes, 55)
    if slow_slope is None:
        return None
    if (
        context["ema21"] > context["ema55"]
        and context["close"] > context["ema55"]
        and slow_slope > 0
    ):
        trend = "BULLISH"
    elif (
        context["ema21"] < context["ema55"]
        and context["close"] < context["ema55"]
        and slow_slope < 0
    ):
        trend = "BEARISH"
    else:
        trend = "SIDEWAYS"
    return {
        "trend": trend,
        "ret_12h": context["ret_12h"],
        "confirmed_close_time": context["confirmed_close_time"],
    }


def classify_quality_market_regime(candles_by_pair):
    """Require broad agreement across core contracts before a live entry."""
    details = {}
    bull_count = 0
    bear_count = 0
    for pair in QUALITY_MARKET_CORE_PAIRS:
        context = quality_context_4h(candles_by_pair.get(pair, []), exclude_incomplete=True)
        if not context:
            continue
        bullish_parts = (
            context["close"] > context["ema21"],
            context["ret_12h"] > 0,
            context["ret_24h"] > 0,
        )
        vote = "BULLISH" if sum(bullish_parts) >= 2 else "BEARISH"
        details[pair] = vote
        if vote == "BULLISH":
            bull_count += 1
        else:
            bear_count += 1

    core_count = bull_count + bear_count
    direction = "NEUTRAL"
    if core_count >= QUALITY_MARKET_MIN_AGREEMENT:
        if bull_count >= QUALITY_MARKET_MIN_AGREEMENT:
            direction = "BULLISH"
        elif bear_count >= QUALITY_MARKET_MIN_AGREEMENT:
            direction = "BEARISH"
    return {
        "direction": direction,
        "bull_count": bull_count,
        "bear_count": bear_count,
        "core_count": core_count,
        "required": QUALITY_MARKET_MIN_AGREEMENT,
        "details": details,
        "smc_btc_context": build_smc_c6_btc_context(
            candles_by_pair.get("BTCUSDT", [])
        ),
    }


def get_quality_market_regime(force=False):
    global quality_market_cache
    fetched_at = time.time()
    with quality_market_cache_lock:
        cached_at = float(quality_market_cache.get("fetched_at", 0.0) or 0.0)
        cached_result = quality_market_cache.get("result")
        if not force and cached_result and fetched_at - cached_at < QUALITY_MARKET_CACHE_SEC:
            return dict(cached_result)

    candles_by_pair = {}
    fetch_errors = []
    for pair in QUALITY_MARKET_CORE_PAIRS:
        try:
            candles_by_pair[pair] = fetch_klines(pair, INTERVAL_TREND, LIMIT)
        except Exception as exc:
            fetch_errors.append(f"{pair}:{type(exc).__name__}")

    result = classify_quality_market_regime(candles_by_pair)
    result["fetched_at"] = int(fetched_at * 1000)
    result["fetch_error_count"] = len(fetch_errors)
    with quality_market_cache_lock:
        quality_market_cache = {"fetched_at": fetched_at, "result": dict(result)}
    if fetch_errors:
        log_line(f"quality_regime_fetch_errors count={len(fetch_errors)} items={','.join(fetch_errors)}")
    return result

# ---------------------- RESULT_R ----------------------
def calculate_result_r(trade):
    try:
        entry       = float(trade.get("entry", 0))
        sl          = float(trade.get("sl", 0))
        close_price = float(trade.get("close_price", 0))
        side        = trade.get("side", "LONG")
        if not (entry and sl and close_price):
            return None
        sl_dist = abs(entry - sl)
        if sl_dist == 0:
            return None
        pnl = (close_price - entry) if side == "LONG" else (entry - close_price)
        return round(pnl / sl_dist, 3)
    except Exception:
        return None

def _maybe_mark_sl_plus_exit(trade):
    try:
        if not trade.get("sl_plus_set"):
            return
        close_price = float(trade.get("close_price", 0) or 0)
        sl_plus = float(trade.get("sl_plus_price", 0) or 0)
        if close_price <= 0 or sl_plus <= 0:
            return
        if abs(close_price - sl_plus) / sl_plus <= 0.003:
            trade["exit_type"] = "BEP/SL+"
            trade["protection_result"] = "BEP/SL+"
    except Exception:
        return

def _position_key(symbol, position_side=None, side=None):
    symbol = str(symbol or "")
    ps = str(position_side or "").upper()
    if ps in ("LONG", "SHORT"):
        return f"{symbol}:{ps}"
    return f"{symbol}:BOTH"

def _trade_position_key(trade):
    pair = str(trade.get("pair", ""))
    pos_side = str(trade.get("position_side") or "").upper()
    side = str(trade.get("side") or "").upper()
    if pos_side in ("LONG", "SHORT"):
        return _position_key(pair, pos_side)
    return f"{pair}:BOTH:{side}"

def _lookup_live_position(live_positions, trade):
    pair = trade.get("pair", "")
    key = _trade_position_key(trade)
    return live_positions.get(key) or live_positions.get(pair)

def _live_position_count(live_positions):
    seen = set()
    count = 0
    for pos in live_positions.values():
        marker = id(pos)
        if marker in seen:
            continue
        seen.add(marker)
        count += 1
    return count

def _active_same_pair_count(pair, side=None):
    active_statuses = ("OPEN", "PENDING")
    return sum(
        1 for t in journal
        if t.get("pair") == pair
        and t.get("status") in active_statuses
        and (side is None or t.get("side") == side)
    )

def get_hybrid_ai_engine(reset=False):
    global hybrid_ai_engine_instance
    with hybrid_ai_engine_lock:
        if reset:
            hybrid_ai_engine_instance = None
        if hybrid_ai_engine_instance is None:
            raw = CONFIG_DATA.get("hybrid_ai", {})
            config = HybridAIConfig.from_mapping(raw, os.path.dirname(JOURNAL_PATH))
            hybrid_ai_engine_instance = HybridAIEngine(config)
        return hybrid_ai_engine_instance

def get_live_ai_market_engine(reset=False):
    global live_ai_market_engine_instance
    with live_ai_market_engine_lock:
        if reset:
            live_ai_market_engine_instance = None
        if live_ai_market_engine_instance is None:
            raw = CONFIG_DATA.get("ai_market_live", {})
            config = LiveAIMarketConfig.from_mapping(raw, os.path.dirname(JOURNAL_PATH))
            live_ai_market_engine_instance = LiveAIMarketEngine(config)
        return live_ai_market_engine_instance

def _build_live_ai_setup_alert(result):
    decision = result.get("decision") if isinstance(result.get("decision"), dict) else {}
    validation = (
        result.get("validated_plan")
        if isinstance(result.get("validated_plan"), dict)
        else {}
    )
    setup = result.get("setup") if isinstance(result.get("setup"), dict) else {}
    if decision.get("action") != "SETUP" or not validation:
        return None
    return (
        f"{BOT_TAG} | P6 RANGE SETUP (SHADOW)\n"
        "--------------------------------\n"
        f"ID          : {setup.get('id', 'n/a')}\n"
        f"Pair / Side : {decision.get('pair')} / {decision.get('side')}\n"
        f"Range       : {fmt_price(decision.get('range_low'))} - "
        f"{fmt_price(decision.get('range_high'))}\n"
        f"Entry zone  : {fmt_price(decision.get('entry_zone_low'))} - "
        f"{fmt_price(decision.get('entry_zone_high'))}\n"
        f"Trigger     : {str(decision.get('entry_trigger', 'n/a')).replace('_', ' ')}\n"
        f"Invalidasi  : {fmt_price(decision.get('invalidation_level'))}\n"
        f"SL / TP1    : {fmt_price(decision.get('stop_loss'))} / "
        f"{fmt_price(decision.get('take_profit_1'))}\n"
        f"TP2         : {fmt_price(decision.get('take_profit_2'))}\n"
        f"R:R biaya   : {float(validation.get('cost_adjusted_rr_tp1', 0)):.2f} / "
        f"{float(validation.get('cost_adjusted_rr_tp2', 0)):.2f}\n"
        f"Expiry      : {decision.get('expiry_hours')} jam\n\n"
        "Riset shadow saja. Tidak ada order Binance."
    )

def _build_live_ai_lifecycle_alert(result):
    events = result.get("events") if isinstance(result.get("events"), list) else []
    setup = result.get("setup") if isinstance(result.get("setup"), dict) else {}
    if not events or not setup:
        return None
    labels = {
        "FILLED": "Entry shadow tersentuh",
        "TP1_HIT": "TP1 shadow tercapai",
        "TP2_HIT": "TP2 shadow tercapai",
        "SL_HIT": "SL shadow tercapai",
        "EXPIRED": "Setup kedaluwarsa tanpa entry",
        "TIME_EXIT": "Setup ditutup saat expiry",
    }
    event_lines = []
    for event in events:
        label = labels.get(str(event.get("event")))
        if not label:
            continue
        price = float(event.get("price", 0) or 0)
        suffix = f" @ {fmt_price(price)}" if price > 0 else ""
        event_lines.append(f"- {label}{suffix}")
    if not event_lines:
        return None
    result_line = ""
    if setup.get("status") in ("SL_HIT", "TP2_HIT", "EXPIRED", "TIME_EXIT"):
        result_line = f"\nResult      : {float(setup.get('result_r', 0) or 0):+.2f}R"
    return (
        f"{BOT_TAG} | P6 SHADOW UPDATE\n"
        "---------------------------\n"
        f"ID          : {setup.get('id', 'n/a')}\n"
        f"Pair / Side : {setup.get('pair')} / {setup.get('side')}\n"
        f"Status      : {setup.get('status')}\n"
        + "\n".join(event_lines)
        + result_line
        + "\n\nTidak ada order Binance."
    )

def _live_ai_market_worker(api_key, api_secret):
    log_line("ai_market_live_worker_started mode=research_shadow_only")
    while not _shutdown_event.is_set():
        try:
            engine = get_live_ai_market_engine()
            if engine.due():
                auth_verified = False
                symbol_rules = None
                monitoring_setup = bool(engine.summary().get("active_setup"))
                if not monitoring_setup:
                    if api_key and api_secret:
                        try:
                            account = get_account_info(api_key, api_secret)
                            auth_verified = isinstance(account, dict) and bool(account)
                        except Exception as exc:
                            log_line(f"ai_market_live_binance_auth_error {str(exc)[:180]}")
                    exchange_info = get_exchange_info_cached(api_key, api_secret)
                    symbol_rules = {}
                    for symbol in engine.config.symbols:
                        _step, tick, _min_qty, _min_notional = get_symbol_filters(
                            exchange_info, symbol
                        )
                        if not tick:
                            raise LiveAIMarketError(
                                f"Binance tick size tidak tersedia untuk {symbol}"
                            )
                        symbol_rules[symbol] = {"tick_size": float(tick)}
                result = engine.run_once(
                    fetch_klines,
                    auth_verified,
                    symbol_rules=symbol_rules,
                )
                status = result.get("status")
                if status == "RECORDED_SHADOW_ONLY":
                    decision = result.get("decision", {})
                    log_line(
                        f"ai_market_live_recorded snapshot={result.get('snapshot_id')} "
                        f"action={decision.get('action')} pair={decision.get('pair')} "
                        f"side={decision.get('side')}"
                    )
                    if engine.config.notify_admin_on_setup:
                        alert = _build_live_ai_setup_alert(result)
                        if alert:
                            _notify_admins(alert)
                elif status == "MONITORED_SHADOW_SETUP":
                    if result.get("events"):
                        log_line(
                            f"ai_market_live_setup_event id={result.get('setup_id')} "
                            f"status={result.get('setup_status')} "
                            f"events={','.join(str(x.get('event')) for x in result.get('events', []))}"
                        )
                        if engine.config.notify_admin_on_lifecycle:
                            alert = _build_live_ai_lifecycle_alert(result)
                            if alert:
                                _notify_admins(alert)
                elif status not in (
                    "DUPLICATE",
                    "DISABLED",
                    "BUSY",
                ):
                    log_line(
                        f"ai_market_live_status status={status} "
                        f"detail={str(result.get('error', ''))[:180]}"
                    )
        except Exception as exc:
            log_line(f"ai_market_live_worker_error {str(exc)[:240]}")
        interruptible_sleep(60)
    log_line("ai_market_live_worker_stopped")

def start_live_ai_market_thread(api_key, api_secret):
    global live_ai_market_thread_started
    with live_ai_market_thread_lock:
        if live_ai_market_thread_started:
            return True
        try:
            engine = get_live_ai_market_engine()
            summary = engine.summary()
        except Exception as exc:
            log_line(f"ai_market_live_start_error {str(exc)[:240]}")
            return False
        if not summary.get("enabled"):
            log_line("ai_market_live_worker_disabled")
            return False
        if not summary.get("openai_key_present"):
            log_line("ai_market_live_worker_blocked openai_key_missing")
            return False
        if engine.config.require_authenticated_binance and not (api_key and api_secret):
            log_line("ai_market_live_worker_blocked binance_credentials_missing")
            return False
        thread = threading.Thread(
            target=_live_ai_market_worker,
            args=(api_key, api_secret),
            daemon=True,
            name="ai-market-live",
        )
        thread.start()
        live_ai_market_thread_started = True
        return True

def _hybrid_pct_return(values, bars):
    if not values or len(values) <= bars:
        return None
    previous = float(values[-1 - bars])
    current = float(values[-1])
    return current / previous - 1.0 if previous > 0 else None

def _hybrid_runtime_context(pair, account_info=None, now_value=None):
    current = int(now_value or now_ms())
    tz_wib = timezone(timedelta(hours=7))
    today_start = datetime.fromtimestamp(current / 1000, tz_wib).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    today_start_ms = int(today_start.timestamp() * 1000)
    with journal_lock:
        snapshot = list(journal)
    ai_open = [
        trade for trade in snapshot
        if trade.get("status") in ("OPEN", "PENDING")
        and isinstance(trade.get("hybrid_ai"), dict)
    ]
    all_open_pairs = {
        str(trade.get("pair", "")).upper()
        for trade in snapshot
        if trade.get("status") in ("OPEN", "PENDING")
    }
    daily_ai_r = sum(
        float(trade.get("result_R", 0) or 0)
        for trade in snapshot
        if isinstance(trade.get("hybrid_ai"), dict)
        and trade.get("result_R") is not None
        and int(trade.get("closed_at") or trade.get("timestamp", 0) or 0) >= today_start_ms
    )
    account = account_info if isinstance(account_info, dict) else {}
    return {
        "now_ms": current,
        "equity": float(account.get("totalWalletBalance", 0) or 0),
        "available_balance": float(account.get("availableBalance", 0) or 0),
        "open_positions": len(ai_open),
        "open_pairs": sorted(all_open_pairs),
        "daily_r": daily_ai_r,
        "entry_paused": ENTRY_PAUSED,
        "pair": str(pair).upper(),
    }

def _hybrid_quantity_spec(entry, sl, step, min_qty, min_notional, config):
    entry_value = float(entry)
    if entry_value <= 0:
        raise HybridAIError("invalid entry for AI quantity")
    step_d = Decimal(str(step))
    target_qty = Decimal(str(config.max_notional_usdt / entry_value))
    qty_d = (target_qty / step_d).to_integral_value(rounding=ROUND_DOWN) * step_d
    minimum_qty = Decimal(str(min_qty or 0))
    minimum_notional_qty = Decimal(str((min_notional or 0) / entry_value))
    required = max(minimum_qty, minimum_notional_qty)
    if qty_d < required:
        qty_d = (required / step_d).to_integral_value(rounding=ROUND_UP) * step_d
    if qty_d <= 0:
        raise HybridAIError("AI quantity rounds to zero")
    notional = float(qty_d) * entry_value
    if notional > config.max_notional_usdt + 0.02:
        raise HybridAIError("exchange minimum exceeds AI notional cap")
    stop_pct = abs(entry_value - float(sl)) / entry_value
    split_one = ((qty_d * Decimal(str(TP1_QTY_PCT))) / step_d).to_integral_value(
        rounding=ROUND_DOWN
    ) * step_d
    split_two = qty_d - split_one
    partial = bool(split_one > 0 and split_two > 0)
    if not partial:
        split_one = qty_d
        split_two = Decimal("0")
    return {
        "qty": float(qty_d),
        "qty_str": format(qty_d, "f"),
        "tp1_qty_str": format(split_one, "f"),
        "tp2_qty_str": format(split_two, "f") if partial else None,
        "partial_tp": partial,
        "notional_usdt": round(notional, 8),
        "risk_usdt": round(notional * stop_pct, 8),
    }

def _hybrid_review_prepared_signal(setup, env):
    engine = get_hybrid_ai_engine()
    if not engine.config.enabled:
        return None
    quantity = _hybrid_quantity_spec(
        setup["entry"], setup["sl"], setup["step"], setup["min_qty"],
        setup["min_notional"], engine.config,
    )
    candidate = {
        "pair": setup["pair"],
        "side": setup["bias"],
        "signal_time_ms": int(setup["signal_time_ms"]),
        "entry": float(setup["price_str"]),
        "sl": float(setup["sl_str"]),
        "tp": float(setup["tp1_price_str"]),
        "tp2": float(setup["tp2_price_str"]),
        "actual_rr": float(setup["actual_rr"]),
        "stop_pct": abs(float(setup["price_str"]) - float(setup["sl_str"])) / float(setup["price_str"]),
        "notional_usdt": quantity["notional_usdt"],
        "risk_usdt": quantity["risk_usdt"],
        "strategy": str(setup["trade_record"].get("strategy_version", BOT_TAG)),
        "market_context": dict(setup["market_context"]),
    }
    ai_trade_record = dict(setup["trade_record"])
    ai_trade_record.update({
        "fixed_notional": quantity["notional_usdt"],
        "notional_usdt": quantity["notional_usdt"],
        "risk_usdt": quantity["risk_usdt"],
        "qty": quantity["qty"],
        "tp1_qty_str": quantity["tp1_qty_str"],
        "tp2_qty_str": quantity["tp2_qty_str"],
    })
    execution = {
        "pair": setup["pair"],
        "bias": setup["bias"],
        "qty_str": quantity["qty_str"],
        "price_str": setup["price_str"],
        "sl_str": setup["sl_str"],
        "tp1_price_str": setup["tp1_price_str"],
        "tp2_price_str": setup["tp2_price_str"],
        "tp1_qty_str": quantity["tp1_qty_str"],
        "tp2_qty_str": quantity["tp2_qty_str"],
        "partial_tp": quantity["partial_tp"],
        "position_side": setup["position_side"],
        "tick": str(setup["tick"]),
        "trade_record": ai_trade_record,
    }
    runtime = _hybrid_runtime_context(
        setup["pair"], env.get("account_info"), now_value=now_ms()
    )
    return engine.review(candidate, runtime, execution=execution)

def _hybrid_book_price(symbol, side):
    url = f"{BASE_URL}/fapi/v1/ticker/bookTicker?symbol={urllib.parse.quote(symbol)}"
    data = public_get(url)
    if not isinstance(data, dict):
        return None
    key = "askPrice" if side == "LONG" else "bidPrice"
    try:
        value = float(data.get(key, 0) or 0)
        return value if value > 0 else None
    except Exception:
        return None

def _append_hybrid_trade_record(trade_record):
    global open_trades
    with journal_lock:
        journal.append(trade_record)
        save_json_atomic(JOURNAL_PATH, journal)
        with open_trades_lock:
            open_trades = sum(
                1 for trade in journal
                if trade.get("status") in ("OPEN", "PENDING")
            )

def _execute_hybrid_ai_proposal_locked(proposal_id, api_key, api_secret):
    engine = get_hybrid_ai_engine()
    proposal = engine.claim_for_execution(proposal_id)
    execution = proposal.get("execution")
    candidate = proposal.get("candidate")
    decision_raw = proposal.get("decision")
    if not isinstance(execution, dict) or not isinstance(candidate, dict) or not isinstance(decision_raw, dict):
        engine.finish_execution(proposal_id, False, "proposal_payload_invalid")
        return {"success": False, "error": "proposal_payload_invalid"}

    try:
        account = get_account_info(api_key, api_secret) if api_key and api_secret else {}
        runtime = _hybrid_runtime_context(candidate.get("pair"), account)
        decision = AITradeDecision.from_mapping(decision_raw)
        gate = engine.risk_gateway.evaluate(candidate, decision, runtime)
        if not gate.allowed:
            raise HybridAIError("execution risk recheck failed: " + ",".join(gate.reasons))
        if not api_key or not api_secret:
            raise HybridAIError("Binance credentials unavailable")

        pair = str(execution["pair"])
        bias = str(execution["bias"])
        planned_price = float(execution["price_str"])
        current_price = _hybrid_book_price(pair, bias)
        if current_price is None:
            raise HybridAIError("current executable price unavailable")
        deviation = abs(current_price - planned_price) / planned_price
        if deviation > engine.config.max_price_deviation_pct:
            raise HybridAIError(
                f"price moved {deviation:.3%} beyond {engine.config.max_price_deviation_pct:.3%}"
            )

        trade_record = dict(execution["trade_record"])
        trade_record["timestamp"] = now_ms()
        trade_record["signal_timestamp"] = int(candidate.get("signal_time_ms", 0) or 0)
        trade_record["hybrid_ai"] = {
            "proposal_id": proposal_id,
            "mode": proposal.get("mode"),
            "model": proposal.get("openai", {}).get("model"),
            "decision": decision_raw,
        }
        position_side = execution.get("position_side")
        qty_str = str(execution["qty_str"])
        price_str = str(execution["price_str"])
        sl_str = str(execution["sl_str"])
        tp1_price_str = str(execution["tp1_price_str"])
        tp2_price_str = str(execution["tp2_price_str"])

        if SIMULATE:
            trade_record["status"] = "SIMULATED"
            trade_record["sim_price"] = planned_price
            _append_hybrid_trade_record(trade_record)
            engine.finish_execution(proposal_id, True, {"status": "SIMULATED"})
            return {"success": True, "status": "SIMULATED", "trade": trade_record}

        ensure_margin_leverage(pair, api_key, api_secret, min(LEVERAGE, 3))
        order = place_limit_entry(
            pair,
            "BUY" if bias == "LONG" else "SELL",
            qty_str,
            price_str,
            api_key,
            api_secret,
            position_side=position_side,
        )
        trade_record["entry_order_id"] = order.get("orderId")
        trade_record["qty"] = float(qty_str)
        poller = None
        if order.get("status") == "FILLED":
            close_side = "SELL" if bias == "LONG" else "BUY"
            trade_record["sl_tp_placed"] = True
            sl_order, tp_order = place_sl_tp(
                pair, close_side, sl_str, tp1_price_str,
                api_key, api_secret,
                position_side=position_side,
                qty=execution.get("tp1_qty_str"),
            )
            if sl_order:
                trade_record["sl_order_id"] = sl_order.get("orderId") or sl_order.get("algoId")
            if tp_order:
                trade_record["tp_order_id"] = tp_order.get("orderId") or tp_order.get("algoId")
            if execution.get("partial_tp") and execution.get("tp2_qty_str"):
                tp2_order = binance_post("/fapi/v1/algoOrder", {
                    "algoType": "CONDITIONAL",
                    "symbol": pair,
                    "side": close_side,
                    "type": "TAKE_PROFIT_MARKET",
                    "triggerPrice": tp2_price_str,
                    "quantity": execution["tp2_qty_str"],
                    "workingType": "MARK_PRICE",
                    **({"positionSide": position_side} if position_side else {}),
                }, api_key, api_secret)
                trade_record["tp2_order_id"] = tp2_order.get("orderId") or tp2_order.get("algoId")
            trade_record["status"] = "OPEN"
        else:
            trade_record["status"] = "PENDING"
            poller = threading.Thread(
                target=_poll_order_until_filled,
                args=(
                    pair, trade_record, sl_str, tp1_price_str, qty_str,
                    position_side, bias, api_key, api_secret, execution["tick"],
                ),
                daemon=True,
                name=f"ai-poller-{pair}",
            )

        _append_hybrid_trade_record(trade_record)
        if poller:
            poller.start()
        engine.finish_execution(
            proposal_id,
            True,
            {"status": trade_record["status"], "entry_order_id": trade_record.get("entry_order_id")},
        )
        send_telegram(
            f"[{BOT_TAG}] HYBRID AI {proposal.get('mode')}\n"
            f"{pair} {bias} | ID {proposal_id}\n"
            f"Entry {price_str} | SL {sl_str}\n"
            f"TP1 {tp1_price_str} | TP2 {tp2_price_str}\n"
            f"Status {trade_record['status']} | Notional ${candidate.get('notional_usdt', 0):.2f}"
        )
        return {"success": True, "status": trade_record["status"], "trade": trade_record}
    except Exception as exc:
        error = str(exc)[:300]
        try:
            engine.finish_execution(proposal_id, False, error)
        except Exception:
            pass
        log_line(f"hybrid_ai_execution_failed id={proposal_id} {error}")
        return {"success": False, "error": error}

def execute_hybrid_ai_proposal(proposal_id, api_key, api_secret):
    with hybrid_ai_execution_lock:
        return _execute_hybrid_ai_proposal_locked(proposal_id, api_key, api_secret)

def update_closed_trades_result_r():
    global journal
    changed = False
    skip_statuses = {"OPEN", "PENDING", "SIMULATED", "ORDER_ERROR",
                     "PENDING_CANCELLED", "CANCELLED_BY_EXCHANGE", "UNKNOWN"}
    for t in journal:
        if t.get("result_R") is not None:
            continue
        if t.get("status") in skip_statuses:
            continue
        r = calculate_result_r(t)
        if r is not None:
            t["result_R"] = r
            changed = True
    if changed:
        save_json_atomic(JOURNAL_PATH, journal)

# ---------------------- BACKGROUND POLLER ----------------------
def _poll_order_until_filled(pair, trade_record, sl_str, tp_str, qty_str,
                              position_side, bias, api_key, api_secret, tick):
    wait_s = 30 * 60
    poll_interval = 15
    start_wait = time.time()
    elapsed_log = 0

    while time.time() - start_wait < wait_s and not _shutdown_event.is_set():
        time.sleep(poll_interval)
        elapsed = int(time.time() - start_wait)
        ordinfo = get_order(pair, trade_record["entry_order_id"], api_key, api_secret)
        if not ordinfo:
            break
        st = ordinfo.get("status")
        if elapsed - elapsed_log >= 300:
            log_line(f"{pair}: order_pending {elapsed//60}m/30m status={st}")
            elapsed_log = elapsed

        if st == "FILLED":
            trade_record["status"] = "OPEN"
            trade_record["entry"] = float(ordinfo.get("avgPrice") or trade_record["entry"])
            trade_record["qty"]   = float(ordinfo.get("executedQty") or trade_record.get("qty", 0))
            close_side = "SELL" if bias == "LONG" else "BUY"

            # [FIX-11] Race condition guard: cek apakah sync thread sudah place SL/TP
            already_placed = False
            with journal_lock:
                for i, t in enumerate(journal):
                    if t.get("entry_order_id") == trade_record["entry_order_id"]:
                        if t.get("sl_tp_placed"):
                            already_placed = True
                            log_line(f"{pair}: sl_tp_already_placed by sync_thread, skip poll")
                        else:
                            journal[i]["sl_tp_placed"] = True  # [FIX-11] klaim slot
                        break

            if not already_placed:
                try:
                    sl_order, tp_order = place_sl_tp(
                        pair, close_side, sl_str,
                        trade_record["tp1_price_str"],
                        api_key, api_secret,
                        position_side=position_side,
                        qty=trade_record["tp1_qty_str"]
                    )
                    if sl_order:
                        trade_record["sl_order_id"] = sl_order.get("orderId") or sl_order.get("algoId")
                    if tp_order:
                        trade_record["tp_order_id"] = tp_order.get("orderId") or tp_order.get("algoId")
                    else:
                        log_line(f"{pair}: WARNING tp1_not_placed_poll")
                    if ENABLE_PARTIAL_TP and trade_record.get("tp2_price_str"):
                        try:
                            tp2_o = binance_post("/fapi/v1/algoOrder", {
                                "algoType": "CONDITIONAL", "symbol": pair,
                                "side": close_side, "type": "TAKE_PROFIT_MARKET",
                                "triggerPrice": trade_record["tp2_price_str"],
                                "quantity": trade_record.get("tp2_qty_str", qty_str),
                                "workingType": "MARK_PRICE",
                                **({  "positionSide": position_side} if position_side else {})
                            }, api_key, api_secret)
                            trade_record["tp2_order_id"] = tp2_o.get("orderId") or tp2_o.get("algoId")
                        except Exception as _e:
                            log_line(f"{pair}: tp2_place_err_poll {_e}")
                except Exception as e:
                    log_line(f"{pair}: sl_tp_err after fill {e}")

            with journal_lock:
                for i, t in enumerate(journal):
                    if t.get("entry_order_id") == trade_record["entry_order_id"]:
                        journal[i] = trade_record; break
                save_json_atomic(JOURNAL_PATH, journal)
            with open_trades_lock:
                global open_trades
                open_trades = sum(1 for t in journal if t.get("status") in ("OPEN", "PENDING"))
            log_line(f"{pair}: order_filled after {elapsed}s")
            send_telegram(
                f"✅ [{BOT_TAG}] FILLED | {pair} {bias} | "
                f"Entry:{fmt_price(trade_record['entry'])} | SL:{sl_str} | TP:{tp_str}"
            )
            return

        if st in ("CANCELED", "EXPIRED", "REJECTED"):
            trade_record["status"] = "CANCELLED_BY_EXCHANGE"
            with journal_lock:
                for i, t in enumerate(journal):
                    if t.get("entry_order_id") == trade_record["entry_order_id"]:
                        journal[i] = trade_record; break
                save_json_atomic(JOURNAL_PATH, journal)
            with open_trades_lock:
                open_trades = sum(1 for t in journal if t.get("status") in ("OPEN", "PENDING"))
            log_line(f"{pair}: order_{st.lower()}_by_exchange")
            return

    if trade_record["status"] == "PENDING" and not _shutdown_event.is_set():
        try:
            binance_delete("/fapi/v1/order",
                           {"symbol": pair, "orderId": trade_record["entry_order_id"]},
                           api_key, api_secret)
        except Exception:
            pass
        trade_record["status"] = "PENDING_CANCELLED"
        with journal_lock:
            for i, t in enumerate(journal):
                if t.get("entry_order_id") == trade_record["entry_order_id"]:
                    journal[i] = trade_record; break
            save_json_atomic(JOURNAL_PATH, journal)
        with open_trades_lock:
            open_trades = sum(1 for t in journal if t.get("status") in ("OPEN", "PENDING"))
        log_line(f"{pair}: order_cancelled_timeout 30m")

# ---------------------- SCAN PAIR ----------------------
def scan_pair(pair, env):
    global journal, open_trades
    api_key       = env.get("api_key")
    api_secret    = env.get("api_secret")
    exchange_info = env.get("exchange_info")
    dual_side     = env.get("dual_side", False)
    now           = now_ms()

    try:
        # 1. Fetch first so Strategy C shadow remains observable even when the
        # live account has reached its position limit.
        candles_15m = fetch_klines(pair, INTERVAL_SCAN, LIMIT)
        candles_4h  = fetch_klines(pair, INTERVAL_TREND, LIMIT)
        if not candles_15m or not candles_4h:
            return f"{pair}: no_data"

        # Binance includes the still-forming candle as the final item. Every
        # live indicator and decision below uses confirmed candles only.
        closed_15m = candles_15m[:-1]
        closed_4h = candles_4h[:-1]
        if len(closed_15m) < 60 or len(closed_4h) < 60:
            return f"{pair}: insufficient_closed_data"

        # [V7.3.2] Update shadow trade OPEN utk pair ini — numpang di candle
        # yang sudah di-fetch, tidak ada API call tambahan.
        if ENABLE_SHADOW_TRACKING:
            update_shadow_trades_for_pair(pair, candles_15m)

        last_15   = closed_15m[-1]
        closes_15 = [c["close"] for c in closed_15m]
        highs_15  = [c["high"]  for c in closed_15m]
        lows_15   = [c["low"]   for c in closed_15m]
        closes_4h = [c["close"] for c in closed_4h]
        highs_4h  = [c["high"]  for c in closed_4h]
        lows_4h   = [c["low"]   for c in closed_4h]

        # 3. Indicators
        # The 15m EMA21 pullback profile is intentionally not an entry gate.
        # A 635-day parity audit found that it reduced cross-regime edge.
        # [V7.3-E3] rsi15 TIDAK lagi dipakai sebagai filter entry — RSI dihapus.
        # Tetap dihitung sebagai sentinel sanity-check data (None berarti candle
        # tidak cukup/corrupt), bukan untuk threshold band lagi.
        rsi15                = rsi(closes_15, RSI_PERIOD)
        atr15                = atr(highs_15, lows_15, closes_15, ATR_PERIOD)
        ema_trend_4h, slope_4h = ema_slope(closes_4h, EMA_SLOW)

        if None in (rsi15, atr15, ema_trend_4h, slope_4h):
            return f"{pair}: indicator_error"

        # [V7.6-C2] Evaluasi Jalur C sebelum gate operasional Jalur A/B.
        # Dengan begitu statistik shadow mengukur kualitas setup, bukan ikut
        # terpotong cooldown, max posisi, atau status posisi live. Funding tidak
        # di-fetch khusus di sini agar tidak menambah satu request per pair.
        shadow_bullish = closes_4h[-1] > ema_trend_4h and slope_4h > 0
        shadow_bearish = closes_4h[-1] < ema_trend_4h and slope_4h < 0
        shadow_trend_4h = "BULLISH" if shadow_bullish else ("BEARISH" if shadow_bearish else "SIDEWAYS")
        if ENABLE_SMART_MONEY_C_SHADOW and ENABLE_SHADOW_TRACKING:
            smc_signal = detect_smart_money_c_shadow(
                pair,
                candles_15m,
                candles_4h,
                shadow_trend_4h,
                funding=None,
                market_context=env.get("smc_btc_market_context"),
            )
            if smc_signal:
                record_shadow_signal(
                    pair,
                    smc_signal["bias"],
                    smc_signal["entry"],
                    smc_signal["sl"],
                    smc_signal["tp"],
                    smc_signal["blocked_reason"],
                    smc_signal["blocked_detail"],
                    meta=smc_signal.get("meta"),
                )

        # 4. Cooldown — [FIX-R4] gunakan snapshot journal, bukan global langsung
        # Snapshot diambil main_cycle() di bawah journal_lock untuk thread-safety.
        # Operational gate for Jalur A/B. It intentionally comes after the C
        # shadow evaluation so shadow statistics are not starved by live limits.
        with open_trades_lock:
            cur = open_trades
        if cur >= MAX_CONCURRENT_TRADES:
            return f"{pair}: max_trades({cur}/{MAX_CONCURRENT_TRADES})"

        _j = env.get("journal_snapshot") or journal
        pair_trades   = [t for t in _j if t.get("pair") == pair]

        # [BUGFIX] Batas posisi OPEN/PENDING untuk pair yang sama.
        # Tanpa ini pair bisa dibuka 4x atau lebih berturut-turut karena
        # cooldown timer hanya cek jarak waktu, tidak cek status posisi aktif.
        # MAX_SAME_PAIR_OPEN default 1: cegah double-entry pair yang sama.
        open_same_pair = sum(
            1 for t in pair_trades
            if t.get("status") in ("OPEN", "PENDING")
        )
        if open_same_pair >= MAX_SAME_PAIR_OPEN:
            return f"{pair}: max_same_pair({open_same_pair}/{MAX_SAME_PAIR_OPEN})"

        last_ts       = max((t.get("timestamp", 0) for t in pair_trades), default=0)
        atr_pct       = atr15 / last_15["close"] if last_15.get("close") else 0
        last_trade    = max(pair_trades, key=lambda t: t.get("timestamp", 0), default=None)
        last_was_loss = last_trade and last_trade.get("status") == "LOSS"
        if last_was_loss:
            cd_ms = COOLDOWN_AFTER_LOSS_MIN * 60 * 1000
            if last_ts and now - last_ts < cd_ms:
                remaining = int((cd_ms - (now - last_ts)) / 60000)
                return f"{pair}: loss_cooldown({remaining}m left)"
        else:
            dyn_cd = COOLDOWN_MIN_VOLATILE if atr_pct >= ATR_VOLATILE_PCT else COOLDOWN_MIN
            if last_ts and now - last_ts < dyn_cd * 60 * 1000:
                return f"{pair}: cooldown({dyn_cd}m)"

        sc_ts = sweep_cooldowns.get(pair)
        if sc_ts and now - sc_ts < SWEEP_COOLDOWN_MIN * 60 * 1000:
            return f"{pair}: sweep_cooldown"

        # 5. Regime filter (4h)
        if ENABLE_REGIME_FILTER and not regime_ok_4h(closes_4h, highs_4h, lows_4h):
            return f"{pair}: regime_flat"

        # 6. Spread & depth
        if get_spread(pair) > SPREAD_MAX_PCT:
            return f"{pair}: spread_wide"
        if get_orderbook_notional(pair, BOOK_DEPTH_LIMIT) < MIN_BOOK_NOTIONAL:
            return f"{pair}: depth_low"

        # 7. Sweep detection
        if ENABLE_SWEEP_DETECTION and is_liquidity_sweep(candles_4h):
            sweep_cooldowns[pair] = now
            return f"{pair}: sweep_detected"

        # 8. Funding Rate filter
        funding = None
        if ENABLE_FUNDING_FILTER:
            funding = get_funding_rate(pair)

        # 9. [V7.3-E4] OI filter DIHAPUS — digantikan konfirmasi volume langsung
        oi_now, oi_change_pct = None, None

        # 10. [V7-S2] S/R dari candles_4H (bukan 15m) + orderflow
        # 4H S/R = level yang direspek institutional (100 candle = ~17 hari history)
        # 15m S/R hanya 10 jam — terlalu dangkal, sering ditembus noise
        support, resistance = support_resistance_multi(
            closed_4h,
            min_touches=SR_MIN_TOUCHES,
            lookback=SR_LOOKBACK
        )
        buy_ratio, sell_ratio, _, _ = taker_ratio(closed_15m, ORDERFLOW_LOOKBACK)

        # 11. Trend bias (4H EMA55 slope)
        close   = last_15["close"]
        bullish = closes_4h[-1] > ema_trend_4h and slope_4h > 0
        bearish = closes_4h[-1] < ema_trend_4h and slope_4h < 0
        trend_4h = "BULLISH" if bullish else ("BEARISH" if bearish else "SIDEWAYS")

        if trend_4h == "SIDEWAYS":
            return f"{pair}: sideways"

        bias          = None
        entry_path    = None     # "A" (S/R langsung) atau "B" (breakout-retest)
        breakout_level = None    # level yang ditembus, dipakai sbg basis SL di Jalur B
        reasons       = []

        target_bias = "LONG" if trend_4h == "BULLISH" else "SHORT"

        # [V7-S9] Funding filter — tetap berlaku untuk kedua jalur
        if target_bias == "LONG" and funding is not None and funding > FUNDING_RATE_MAX_LONG:
            return f"{pair}: funding_too_high({funding:.4f})"
        if target_bias == "SHORT" and funding is not None and funding < FUNDING_RATE_MIN_SHORT:
            return f"{pair}: funding_too_low({funding:.4f})"

        # [V8.1] Market breadth remains recorded as context, but the 90-day
        # replay rejected it as a mandatory gate. The live decision is side-aware:
        # LONG requires EMA + strict bullish structure; SHORT requires EMA and
        # must not be inside the bottom 40% of its confirmed 4H range.
        quality_market = env.get("quality_market_regime") or {
            "direction": "NEUTRAL", "bull_count": 0, "bear_count": 0,
            "core_count": 0, "required": QUALITY_MARKET_MIN_AGREEMENT,
        }
        quality_local = quality_local_snapshot(candles_4h, target_bias)
        if ENABLE_QUALITY_GATE:
            quality_allowed, quality_reason = quality_live_gate_decision(
                quality_local, target_bias
            )
            if not quality_allowed:
                return f"{pair}: quality_local_block({quality_reason})"

        # [V7-S4] Market structure — gate bersama untuk Jalur A maupun B.
        # Breakout/entry yang searah trend tapi melawan struktur HH/HL (LONG)
        # atau LL/LH (SHORT) lebih sering jadi fake move / corrective bounce.
        if not market_structure_ok(candles_4h, target_bias):
            reasons.append("no_hh_hl_4h" if target_bias == "LONG" else "no_ll_lh_4h")

        # [V7.3] Volume candle 4H terakhir vs baseline — dipakai Jalur A (harus RENDAH)
        avgv_4h        = avg_volume(closed_4h, VOLUME_AVG_LOOKBACK, exclude_last=1)
        last_closed_4h = closed_4h[-1]
        last_vol_ratio = (last_closed_4h.get("volume", 0) / avgv_4h) if avgv_4h else None

        state_key = f"{pair}:{target_bias}"
        with breakout_state_lock:
            pending = (
                dict(breakout_state.get(state_key))
                if ENABLE_STRATEGY_B_LIVE and state_key in breakout_state
                else None
            )

        # [V7.3] Expire breakout pending kalau retest tidak terjadi dalam window
        if pending:
            cur_4h_open_time = closed_4h[-1].get("open_time", 0)
            candles_elapsed  = (cur_4h_open_time - pending.get("detected_open_time", 0)) / (4 * 3600 * 1000)
            if candles_elapsed > RETEST_MAX_CANDLES_4H:
                with breakout_state_lock:
                    breakout_state.pop(state_key, None)
                    save_breakout_state()
                log_line(f"{pair}: breakout_expired level={pending.get('level')} "
                         f"candles_elapsed={candles_elapsed:.0f}>{RETEST_MAX_CANDLES_4H}")
                pending = None

        if not reasons:  # market_structure_ok lolos → lanjut evaluasi jalur
            # ============== JALUR B: cek retest dari breakout yang sudah pending ==============
            if pending:
                level = pending["level"]
                if check_retest(close, level):
                    candle_for_reject = last_15 if is_rejection_candle(last_15, target_bias) else (
                        closed_15m[-2] if is_rejection_candle(closed_15m[-2], target_bias) else None
                    )
                    if candle_for_reject is not None:
                        bias           = target_bias
                        entry_path     = "B"
                        breakout_level = level
                    else:
                        reasons.append("retest_no_rejection")
                else:
                    reasons.append(f"awaiting_retest(level={level:.4f})")

            # ============== JALUR A: S/R langsung + volume RENDAH ==============
            # Hanya dicoba kalau TIDAK ada breakout pending untuk arah ini — kalau
            # breakout sedang ditunggu retest-nya, level S/R lama sudah "ditembus"
            # secara definisi, jadi entry S/R langsung di level lama tidak relevan lagi.
            if bias is None and not pending:
                vol_ok = (last_vol_ratio is None) or (last_vol_ratio < JALUR_A_MAX_VOL_RATIO)

                if target_bias == "LONG":
                    near_sup  = near_level(close, support)
                    above_sup = close > support * (1 - SR_BUF_SL)
                    if near_sup and above_sup and vol_ok:
                        bias = "LONG"; entry_path = "A"
                    else:
                        if not near_sup:  reasons.append(f"not_near_sup({support:.4f}±{NEAR_LEVEL_TOLERANCE:.1%})")
                        if not above_sup: reasons.append(f"below_support({close:.4f}<{support:.4f})")
                        if not vol_ok:    reasons.append(f"vol_too_high({last_vol_ratio:.2f}x>={JALUR_A_MAX_VOL_RATIO}x)")
                        # [V7.3.2] Shadow tracking: near-miss MURNI karena volume —
                        # semua syarat lain (trend, struktur, dekat support, masih
                        # di atas support) sudah lolos. Cek rejection wick juga,
                        # supaya perbandingan apples-to-apples dgn entry asli yg
                        # SELALU butuh rejection candle.
                        if (ENABLE_JALUR_A_VOLUME_SHADOW and ENABLE_SHADOW_TRACKING
                                and near_sup and above_sup and not vol_ok
                                and (is_rejection_candle_at_level(
                                         closed_15m[-1], "LONG", support
                                     )
                                     or is_rejection_candle_at_level(
                                         closed_15m[-2], "LONG", support
                                     ))):
                            sh_sl, sh_tp = shadow_compute_sl_tp("LONG", close, support, resistance, candles_15m)
                            record_shadow_signal(pair, "LONG", close, sh_sl, sh_tp,
                                                  "vol_too_high", f"{last_vol_ratio:.2f}x")
                else:
                    near_res  = near_level(close, resistance)
                    below_res = close < resistance * (1 + SR_BUF_SL)
                    if near_res and below_res and vol_ok:
                        bias = "SHORT"; entry_path = "A"
                    else:
                        if not near_res:  reasons.append(f"not_near_res({resistance:.4f}±{NEAR_LEVEL_TOLERANCE:.1%})")
                        if not below_res: reasons.append(f"above_resistance({close:.4f}>{resistance:.4f})")
                        if not vol_ok:    reasons.append(f"vol_too_high({last_vol_ratio:.2f}x>={JALUR_A_MAX_VOL_RATIO}x)")
                        if (ENABLE_JALUR_A_VOLUME_SHADOW and ENABLE_SHADOW_TRACKING
                                and near_res and below_res and not vol_ok
                                and (is_rejection_candle_at_level(
                                         closed_15m[-1], "SHORT", resistance
                                     )
                                     or is_rejection_candle_at_level(
                                         closed_15m[-2], "SHORT", resistance
                                     ))):
                            sh_sl, sh_tp = shadow_compute_sl_tp("SHORT", close, support, resistance, candles_15m)
                            record_shadow_signal(pair, "SHORT", close, sh_sl, sh_tp,
                                                  "vol_too_high", f"{last_vol_ratio:.2f}x")

            # ============== Deteksi breakout BARU (kalau belum dapat bias & belum ada pending) ==============
            if bias is None and not pending and ENABLE_STRATEGY_B_LIVE:
                bo_support, bo_resistance = breakout_reference_levels(candles_4h)
                bo = detect_breakout_4h(candles_4h, bo_support, bo_resistance)
                if bo:
                    new_level = bo_resistance if target_bias == "LONG" else bo_support
                    triggered = bo["bullish"] if target_bias == "LONG" else bo["bearish"]
                    if triggered:
                        with breakout_state_lock:
                            breakout_state[state_key] = {
                                "pair": pair, "bias": target_bias, "level": new_level,
                                "detected_open_time": closed_4h[-1].get("open_time", 0),
                                "detected_at": now,
                                "c1_vol_ratio": round(bo["c1_vol_ratio"], 2),
                                "c2_vol_ratio": round(bo["c2_vol_ratio"], 2),
                            }
                            save_breakout_state()
                        log_line(
                            f"{pair}: breakout_detected {target_bias} level={new_level:.4f} "
                            f"c1_vol={bo['c1_vol_ratio']:.2f}x c2_vol={bo['c2_vol_ratio']:.2f}x "
                            f"— menunggu retest (max {RETEST_MAX_CANDLES_4H} candle 4H)"
                        )
                        return f"{pair}: breakout_detected_awaiting_retest"

        if bias is None:
            log_line(f"{pair}: no_bias trend={trend_4h} {' '.join(reasons)}")
            return f"{pair}: no_bias"

        # 11b. Max signal per arah per cycle
        _lock = env.get("_signal_lock")
        if _lock:
            with _lock:
                longs_this_cycle  = env["_longs_this_cycle"]
                shorts_this_cycle = env["_shorts_this_cycle"]
                if bias == "LONG" and longs_this_cycle[0] >= MAX_LONG_PER_CYCLE:
                    return f"{pair}: max_long_per_cycle({longs_this_cycle[0]})"
                if bias == "SHORT" and shorts_this_cycle[0] >= MAX_SHORT_PER_CYCLE:
                    return f"{pair}: max_short_per_cycle({shorts_this_cycle[0]})"

        # [FIX-8] Sector correlation guard — pakai snapshot [FIX-R4]
        if ENABLE_SECTOR_FILTER:
            pair_sector = SECTOR_MAP.get(pair)
            if pair_sector:
                sector_open = any(
                    SECTOR_MAP.get(t.get("pair", "")) == pair_sector
                    and t.get("side") == bias
                    and t.get("status") in ("OPEN", "PENDING")
                    for t in _j
                )
                if sector_open:
                    return f"{pair}: sector_correlation({pair_sector})"

        # 12. [FIX-7] Orderflow confirm — baseline 10 candle (was 5)
        if ENABLE_ORDERFLOW_CONFIRM:
            prev = closed_15m[-(ORDERFLOW_LOOKBACK + ORDERFLOW_BASELINE_LOOKBACK):-ORDERFLOW_LOOKBACK]
            avg_buy  = sum(c["taker_buy"]  for c in prev) / max(1, len(prev))
            avg_sell = sum(c["taker_sell"] for c in prev) / max(1, len(prev))
            last_buy  = closed_15m[-1]["taker_buy"]
            last_sell = closed_15m[-1]["taker_sell"]
            if bias == "LONG" and (buy_ratio < ORDERFLOW_MIN_RATIO or last_buy < avg_buy * ORDERFLOW_SPIKE_MULT):
                return f"{pair}: orderflow_fail(buy={buy_ratio:.2f})"
            if bias == "SHORT" and (sell_ratio < ORDERFLOW_MIN_RATIO or last_sell < avg_sell * ORDERFLOW_SPIKE_MULT):
                return f"{pair}: orderflow_fail(sell={sell_ratio:.2f})"

        # 13. Entry, SL, TP
        last_candle = closed_15m[-1]
        prev_candle = closed_15m[-2]

        # [V7-S7] Time-of-day filter — skip Asian dead zone 00:00-07:00 UTC
        if not trading_hours_ok():
            return f"{pair}: dead_hours(UTC {utc_hour_now():02d}:xx)"

        # [V7-S3] Rejection candle confirm — GANTIKAN candle_bullish yang kontradiksi.
        # Untuk Jalur B (breakout-retest), rejection wick SUDAH divalidasi saat
        # menentukan bias di tahap retest check di atas — tidak perlu cek ulang.
        # Untuk Jalur A, wick dan interaksi S/R harus terjadi pada candle yang
        # sama. Sebelumnya wick di lokasi lain bisa lolos hanya karena close
        # kebetulan berada dalam toleransi level.
        rejection_level = support if bias == "LONG" else resistance
        if entry_path == "A" and not is_rejection_candle_at_level(
            last_candle, bias, rejection_level
        ):
            if not is_rejection_candle_at_level(
                prev_candle, bias, rejection_level
            ):
                wick_info = ""
                try:
                    h = last_candle["high"]; l = last_candle["low"]
                    o = last_candle["open"]; c = last_candle["close"]
                    rng = h - l
                    if rng > 0:
                        lw = (min(o, c) - l) / rng
                        uw = (h - max(o, c)) / rng
                        wick_info = f"lw={lw:.0%} uw={uw:.0%}"
                except Exception:
                    pass
                return f"{pair}: no_rejection_wick({wick_info})"

        entry = close

        # [V7-S10] SL candle reference: 20 candle (5h) bukan 5 candle (75m)
        # 5 candle terlalu pendek, swing low/high tidak bermakna untuk SL reference
        recent_lows  = [c["low"]  for c in closed_15m[-20:]]  # 20 candle = 5h
        recent_highs = [c["high"] for c in closed_15m[-20:]]
        recent_low   = min(recent_lows)
        recent_high  = max(recent_highs)

        # [V7.3] Basis SL berbeda per jalur:
        # Jalur A: S/R biasa + buffer SR_BUF_SL (existing behavior, tidak berubah)
        # Jalur B: level BREAKOUT yang ditembus + buffer BREAKOUT_SL_BUFFER_PCT
        #          (lebih lebar — invalidasi breakout butuh ruang lebih dari sekadar noise)
        if entry_path == "B":
            sl_basis_long  = breakout_level
            sl_basis_short = breakout_level
            sl_buf         = BREAKOUT_SL_BUFFER_PCT
        else:
            sl_basis_long  = support
            sl_basis_short = resistance
            sl_buf         = SR_BUF_SL

        if bias == "LONG":
            sl_sr      = sl_basis_long * (1 - sl_buf)
            sl_atr     = entry - ATR_MULT * atr15
            sl_dist_sr = abs(entry - sl_sr)
            sl_dist_min = entry * MIN_STOP_PCT
            sl_dist_max = entry * 0.05

            if sl_dist_min <= sl_dist_sr <= sl_dist_max:
                sl = sl_sr
                sl_source = "breakout_level" if entry_path == "B" else "sr"
            else:
                sl = min(sl_atr, sl_basis_long * (1 - sl_buf))
                sl_source = "atr"

            candle_sl_floor = recent_low * (1 - 0.002)
            if sl > candle_sl_floor:
                sl = candle_sl_floor
                sl_source = sl_source + "+candle"

            sl_dist = abs(entry - sl)

            # TP tetap pakai "resistance" hasil hitung S/R terbaru — untuk Jalur B,
            # ini secara natural sudah jadi level berikutnya DI ATAS level yang baru
            # ditembus (karena support_resistance_multi() dihitung relatif thd close
            # saat ini, yang sudah berada di atas level lama).
            tp_sr      = resistance * (1 - SR_BUF_TP)
            tp_dist_sr = tp_sr - entry
            tp_rr      = entry + RR * sl_dist
            if tp_sr > entry and tp_dist_sr >= sl_dist * 1.5:
                tp = tp_sr
                tp_source = "sr"
            else:
                tp = tp_rr
                tp_source = "rr"

        else:  # SHORT
            sl_sr      = sl_basis_short * (1 + sl_buf)
            sl_atr     = entry + ATR_MULT * atr15
            sl_dist_sr = abs(entry - sl_sr)
            sl_dist_min = entry * MIN_STOP_PCT
            sl_dist_max = entry * 0.05

            if sl_dist_min <= sl_dist_sr <= sl_dist_max:
                sl = sl_sr
                sl_source = "breakout_level" if entry_path == "B" else "sr"
            else:
                sl = max(sl_atr, sl_basis_short * (1 + sl_buf))
                sl_source = "atr"

            candle_sl_ceil = recent_high * (1 + 0.002)
            if sl < candle_sl_ceil:
                sl = candle_sl_ceil
                sl_source = sl_source + "+candle"

            sl_dist = abs(entry - sl)

            tp_sr      = support * (1 + SR_BUF_TP)
            tp_dist_sr = entry - tp_sr
            tp_rr      = entry - RR * sl_dist
            if tp_sr < entry and tp_dist_sr >= sl_dist * 1.5:
                tp = tp_sr
                tp_source = "sr"
            else:
                tp = tp_rr
                tp_source = "rr"

        if sl_dist < entry * MIN_STOP_PCT:
            sl_dist = entry * MIN_STOP_PCT
            sl = entry - sl_dist if bias == "LONG" else entry + sl_dist
            tp = entry + RR * sl_dist if bias == "LONG" else entry - RR * sl_dist
            sl_source = "min_stop"
            tp_source = "rr"

        if sl_dist > entry * 0.05:
            return f"{pair}: sl_too_wide({sl_dist/entry*100:.1f}%>5%)"

        if bias == "LONG" and sl >= entry:
            return f"{pair}: sl_above_entry_bug"
        if bias == "SHORT" and sl <= entry:
            return f"{pair}: sl_below_entry_bug"

        if tp <= 0 or sl <= 0:
            return f"{pair}: invalid_tp_sl"
        if bias == "LONG"  and (sl >= entry or tp <= entry):
            return f"{pair}: sl_tp_logic_err"
        if bias == "SHORT" and (sl <= entry or tp >= entry):
            return f"{pair}: sl_tp_logic_err"

        raw_sl_pct = abs(float(entry) - float(sl)) / float(entry) if float(entry) > 0 else 0.0
        if ENABLE_QUALITY_GATE:
            quality_risk_allowed, quality_risk_reason = quality_risk_gate_decision(raw_sl_pct)
            if not quality_risk_allowed:
                return f"{pair}: quality_risk_block({quality_risk_reason})"

        if bias == "LONG"  and (sl >= entry or tp <= entry):
            return f"{pair}: sl_tp_logic_err"
        if bias == "SHORT" and (sl <= entry or tp >= entry):
            return f"{pair}: sl_tp_logic_err"

        # [V7.4-S4] actual_rr dihitung SETELAH dual-TP block di bawah (berbasis TP2).
        # TIDAK dihitung di sini lagi — placeholder sementara sebelum blok TP.
        # rr_too_low check juga dipindah ke sesudah dual-TP block.

        # [V7.3] Clear breakout_state sesudah semua filter SL/TP logic lolos
        if entry_path == "B":
            with breakout_state_lock:
                breakout_state.pop(state_key, None)
                save_breakout_state()
            log_line(f"{pair}: breakout_state_cleared level={breakout_level} (used for entry)")

        # 14. Precision
        step, tick, min_qty, min_notional = get_symbol_filters(exchange_info, pair) if exchange_info else (None, None, 0.0, 0.0)
        if not (step and tick):
            return f"{pair}: no_filters"

        entry_d, sl_d, tp_d, _, tick_d, step_d, dec_str = apply_precision(entry, sl, tp, 1.0, step, tick)

        # ── [V7.4-S1] SIZING: Fixed NOTIONAL $50 ────────────────────────────────
        # qty = FIXED_NOTIONAL_USDT / entry → SELALU buka posisi $50.
        # Sebelumnya (fixed-risk): qty = RISK / (entry × sl_pct) → notional
        # bervariasi tiap trade, evaluasi dan psikologis tidak konsisten.
        # SL/TP TETAP mengikuti S/R — tidak ada perubahan di sisi itu.
        sl_pct_actual = abs(float(entry_d) - float(sl_d)) / float(entry_d) if float(entry_d) > 0 else 0
        if sl_pct_actual < 0.0005:
            return f"{pair}: sl_pct_too_small({sl_pct_actual:.5f})"

        qty = FIXED_NOTIONAL_USDT / float(entry_d)

        # Safety cap: jangan melebihi available margin
        account   = env.get("account_info") or {"totalWalletBalance": 0, "availableBalance": 0}
        equity    = float(account.get("totalWalletBalance", 0))
        available = float(account.get("availableBalance", 0))
        max_notional = min(equity * MAX_EXPOSURE_MULT, available * LEVERAGE) if equity > 0 else 500.0
        max_notional = max(max_notional, FIXED_NOTIONAL_USDT)

        if qty * float(entry_d) > max_notional:
            qty = max_notional / float(entry_d)
        if min_qty and qty < min_qty:
            qty = min_qty
        if min_notional and qty * float(entry_d) < min_notional:
            if min_notional > max_notional:
                return f"{pair}: min_notional_exceeds_max"
            qty = min_notional / float(entry_d)
        if qty <= 0:
            return f"{pair}: invalid_qty"

        _, _, _, qty_d, tick_d, step_d, dec_str = apply_precision(entry, sl, tp, qty, step, tick)
        if qty_d <= Decimal("0"):
            return f"{pair}: qty_zero"

        # Entry limit is one tick below/above the confirmed 15m close. This is a
        # minimal passive-price offset, not an EMA pullback entry.
        # LONG: limit beli sedikit di bawah close → terisi saat candle berikutnya turun tipis
        # SHORT: limit jual sedikit di atas close → terisi saat candle berikutnya naik tipis
        price_d = Decimal(str(entry_d))
        price_d = price_d - tick_d if bias == "LONG" else price_d + tick_d  # [FIX-5]
        price_d = Decimal(str(price_d)).quantize(Decimal(tick), rounding=ROUND_DOWN)

        if float(qty_d) * float(price_d) > max_notional:
            return f"{pair}: exceeds_max_notional"

        qty_str   = dec_str(qty_d)
        price_str = dec_str(price_d)
        sl_str    = dec_str(sl_d)
        tp_str    = dec_str(tp_d)
        entry = float(entry_d); sl = float(sl_d); tp = float(tp_d)

        # Actual notional untuk logging
        actual_notional = round(float(qty_d) * float(price_d), 2)
        # Risk informatif (bukan basis sizing — hanya untuk laporan)
        implied_risk = round(actual_notional * sl_pct_actual, 2)

        # ── [V7.4-S2] DUAL TP — DUA HARGA BERBEDA ───────────────────────────────
        # Sebelumnya: satu harga TP, split qty (tp1 = tp2 = harga yang sama).
        # Sekarang: TP1 di 1:1 (lebih dekat), TP2 di 2:1 (lebih jauh).
        # Ini menyelesaikan masalah "profit 1-2% tidak kena TP" — TP1 jauh lebih
        # mudah dicapai. Setelah TP1 hit, SL otomatis pindah ke SL+ 1%.
        if ENABLE_PARTIAL_TP:
            if bias == "LONG":
                tp1 = entry + TP1_RR * sl_dist   # 1:1 dari sl_dist (lebih dekat)
                tp2 = entry + TP2_RR * sl_dist   # 2:1 dari sl_dist (lebih jauh)
            else:
                tp1 = entry - TP1_RR * sl_dist
                tp2 = entry - TP2_RR * sl_dist

            # [V7.4-S4] RR check dari TP2 (target akhir), BUKAN TP1.
            # Sebelumnya: actual_rr dihitung dari tp (= tp1) → selalu ≈1.0
            # → selalu gagal rr_too_low ≥1.5 check. TP2 = 2:1 → rr ≈2.0 → lolos.
            actual_rr = abs(tp2 - entry) / abs(entry - sl) if abs(entry - sl) > 0 else 0

            qty1_raw = float(qty_d) * TP1_QTY_PCT
            qty2_raw = float(qty_d) * TP2_QTY_PCT
            _, _, _, qty1_d, _, _, _ = apply_precision(entry, sl, tp1, qty1_raw, step, tick)
            _, _, _, qty2_d, _, _, _ = apply_precision(entry, sl, tp2, qty2_raw, step, tick)

            tp1_price_d   = Decimal(str(tp1)).quantize(Decimal(tick), rounding=ROUND_DOWN)
            tp1_price_str = dec_str(tp1_price_d)
            tp2_price_d   = Decimal(str(tp2)).quantize(Decimal(tick), rounding=ROUND_DOWN)
            tp2_price_str = dec_str(tp2_price_d)

            # Fallback: kalau qty1_d terlalu kecil setelah ROUND_DOWN, pakai full qty
            tp1_qty_str = dec_str(qty1_d if qty1_d > Decimal("0") else qty_d)
            tp2_qty_str = dec_str(qty2_d if qty2_d > Decimal("0") else qty_d)
        else:
            # ENABLE_PARTIAL_TP = False: satu TP di 2:1
            tp1 = tp; tp2 = tp
            actual_rr = abs(tp2 - entry) / abs(entry - sl) if abs(entry - sl) > 0 else 0
            tp1_price_str = tp_str
            tp2_price_str = tp_str
            tp1_qty_str   = qty_str
            tp2_qty_str   = qty_str

        # [V7.4-S4] RR check berbasis TP2 (target akhir, 2:1) — di sini setelah
        # actual_rr dihitung di dalam blok ENABLE_PARTIAL_TP di atas.
        if actual_rr < 1.5:
            return f"{pair}: rr_too_low({actual_rr:.2f})"

        _fund_log = f"{funding:.4f}" if funding is not None else "n/a"
        _bo_log   = f" breakout_level={breakout_level:.4f}" if entry_path == "B" else ""
        log_line(f"{pair}: setup {bias} [Jalur {entry_path}] entry={price_str} sl={sl_str}({sl_source}) "
                 f"tp1={tp1_price_str} tp2={tp2_price_str}({tp_source}) "
                 f"rr={actual_rr:.2f} sl_pct={sl_pct_actual:.3%} "
                 f"notional=${actual_notional:.1f} implied_risk=${implied_risk:.2f} "
                 f"funding={_fund_log} q_ema={quality_local['ema']} "
                 f"q_structure={quality_local['structure']} "
                 f"q_range={quality_local.get('range_position')} "
                 f"market={quality_market.get('direction')}{_bo_log}")

        position_side = "LONG" if (dual_side and bias == "LONG") else ("SHORT" if dual_side else None)

        with journal_lock:
            live_same_pair = _active_same_pair_count(pair)
            if live_same_pair >= MAX_SAME_PAIR_OPEN:
                return f"{pair}: max_same_pair_live({live_same_pair}/{MAX_SAME_PAIR_OPEN})"

        trade_record = {
            "timestamp": now, "pair": pair, "side": bias,
            "entry": entry, "sl": sl,
            "tp": tp,       "tp2": tp2 if ENABLE_PARTIAL_TP else tp,
            "rr": RR,
            "status": "UNKNOWN", "result_R": None,
            "close_notif_sent": False,  # [BUGFIX] cegah duplicate close notification
            "position_side": position_side,
            "funding_rate": funding, "oi_change_pct": oi_change_pct,
            "strategy_version": QUALITY_GATE_VERSION if ENABLE_QUALITY_GATE else BOT_TAG,
            "quality_gate_enabled": ENABLE_QUALITY_GATE,
            "quality_market_direction": quality_market.get("direction"),
            "quality_market_bull_count": quality_market.get("bull_count", 0),
            "quality_market_bear_count": quality_market.get("bear_count", 0),
            "quality_score": quality_local["score"],
            "quality_structure_ok": quality_local["structure"],
            "quality_ema_ok": quality_local["ema"],
            "quality_momentum_12h_ok": quality_local["momentum_12h"],
            "quality_range_position": quality_local.get("range_position"),
            # [V7.3] Jejak jalur entry — penting untuk analisis nanti
            # (membandingkan performa Jalur A vs Jalur B secara terpisah)
            "entry_path":      entry_path,            # "A" atau "B"
            "breakout_level":  breakout_level,         # level yang ditembus (None kalau Jalur A)
            "vol_ratio_4h":    round(last_vol_ratio, 3) if last_vol_ratio is not None else None,
            # Partial TP tracking
            "tp1_hit":        False,
            "tp1_price_str":  tp1_price_str,
            "tp1_qty_str":    tp1_qty_str,
            "tp2_price_str":  tp2_price_str,
            "tp2_qty_str":    tp2_qty_str,
            "be_sl_set":      False,
            "be_trigger":     None,
            "be_1pct_set":    False,
            "be_1pct_notif_sent": False,
            "sl_plus_set":    False,
            "sl_plus_notif_sent": False,
            "sl_plus_price":  None,
            "protection_type": None,
            "partial_pnl":    0.0,
            "sl_source":      sl_source,
            "tp_source":      tp_source,
            "actual_rr":      round(actual_rr, 2),    # berbasis TP2 (2:1 dari sl_dist)
            "tp1_rr":         TP1_RR,
            "tp2_rr":         TP2_RR,
            # [V7.4-S1] Fixed notional $50 — sizing tidak lagi berbasis risk
            "risk_usdt":      round(implied_risk, 2),  # notional × sl_pct (informatif, bukan basis sizing)
            "fixed_notional": actual_notional,          # selalu ~$50
            "sl_pct":         round(sl_pct_actual, 5),
            "notional_usdt":  actual_notional,
            # [FIX-11] Race condition guard
            "sl_tp_placed":   False,
            # [FIX-9] Stale trade tracking
            "stale_notified": False,
        }

        # Hybrid AI is a bounded reviewer placed after every deterministic
        # execution parameter is frozen and before any Binance order is sent.
        # In AI_SHADOW it records only and the existing strategy stays intact.
        hybrid_outcome = None
        try:
            candle_range = max(0.0, float(last_15["high"]) - float(last_15["low"]))
            candle_body = abs(float(last_15["close"]) - float(last_15["open"]))
            candle_close_location = (
                (float(last_15["close"]) - float(last_15["low"])) / candle_range
                if candle_range > 0 else 0.5
            )
            hybrid_outcome = _hybrid_review_prepared_signal({
                "pair": pair,
                "bias": bias,
                "signal_time_ms": int(last_15.get("close_time") or now),
                "entry": entry,
                "sl": sl,
                "step": step,
                "tick": tick,
                "min_qty": min_qty,
                "min_notional": min_notional,
                "price_str": price_str,
                "sl_str": sl_str,
                "tp1_price_str": tp1_price_str,
                "tp2_price_str": tp2_price_str,
                "actual_rr": actual_rr,
                "position_side": position_side,
                "trade_record": trade_record,
                "market_context": {
                    "entry_path": entry_path,
                    "trend_4h": trend_4h,
                    "return_1h": _hybrid_pct_return(closes_15, 4),
                    "return_4h": _hybrid_pct_return(closes_15, 16),
                    "return_12h": _hybrid_pct_return(closes_15, 48),
                    "btc_market_direction": quality_market.get("direction"),
                    "btc_breadth_bull": quality_market.get("bull_count", 0),
                    "btc_breadth_bear": quality_market.get("bear_count", 0),
                    "quality_score": quality_local.get("score"),
                    "quality_ema": quality_local.get("ema"),
                    "quality_structure": quality_local.get("structure"),
                    "quality_momentum_12h": quality_local.get("momentum_12h"),
                    "quality_range_position": quality_local.get("range_position"),
                    "buy_ratio": buy_ratio,
                    "sell_ratio": sell_ratio,
                    "volume_ratio_4h": last_vol_ratio,
                    "funding_rate": funding,
                    "atr_pct_15m": atr_pct,
                    "candle_body_ratio": candle_body / candle_range if candle_range > 0 else 0,
                    "candle_close_location": candle_close_location,
                    "support": support,
                    "resistance": resistance,
                    "stop_source": sl_source,
                    "target_source": tp_source,
                },
            }, env)
        except Exception as hybrid_error:
            try:
                hybrid_mode = get_hybrid_ai_engine().current_mode()
            except Exception:
                hybrid_mode = "AI_SHADOW"
            log_line(f"hybrid_ai_review_error {pair} mode={hybrid_mode} {str(hybrid_error)[:300]}")
            if hybrid_mode != "AI_SHADOW":
                return f"{pair}: hybrid_ai_fail_closed"

        if hybrid_outcome is not None:
            proposal = hybrid_outcome.proposal or {}
            decision = proposal.get("decision") or {}
            log_line(
                f"hybrid_ai_review {pair} id={hybrid_outcome.proposal_id} "
                f"mode={hybrid_outcome.mode} status={hybrid_outcome.status} "
                f"action={decision.get('action', 'ERROR')} "
                f"confidence={decision.get('confidence', 'n/a')}"
            )
            if hybrid_outcome.route == "DEFER":
                if hybrid_outcome.created:
                    thesis = str(decision.get("thesis", "-")).replace("\n", " ")[:180]
                    send_telegram_to_chat(
                        TARGET_CHAT_ID,
                        f"{_command_header('AI APPROVAL')}\n"
                        f"ID          : {hybrid_outcome.proposal_id}\n"
                        f"Pair        : {pair} {bias}\n"
                        f"Confidence  : {float(decision.get('confidence', 0)):.0%}\n"
                        f"Quality     : {decision.get('setup_quality', 0)}/100\n"
                        f"Entry / SL  : {price_str} / {sl_str}\n"
                        f"TP1 / TP2   : {tp1_price_str} / {tp2_price_str}\n"
                        f"Notional    : ${proposal.get('candidate', {}).get('notional_usdt', 0):.2f}\n"
                        f"Analisis    : {thesis}\n\n"
                        f"/ai_approve {hybrid_outcome.proposal_id}\n"
                        f"/ai_reject {hybrid_outcome.proposal_id}\n"
                        "Proposal otomatis kedaluwarsa dalam 5 menit."
                    )
                return f"{pair}: hybrid_ai_pending_approval"
            if hybrid_outcome.route == "BLOCK":
                return f"{pair}: hybrid_ai_blocked({hybrid_outcome.status})"
            if hybrid_outcome.route == "EXECUTE":
                result = execute_hybrid_ai_proposal(
                    hybrid_outcome.proposal_id, api_key, api_secret
                )
                if result.get("success"):
                    _lock = env.get("_signal_lock")
                    if _lock:
                        with _lock:
                            if bias == "LONG":
                                env["_longs_this_cycle"][0] += 1
                            else:
                                env["_shorts_this_cycle"][0] += 1
                    return f"{pair}: signal_sent_hybrid_ai"
                return f"{pair}: hybrid_ai_execution_failed"
            if (
                hybrid_outcome.mode == "AI_SHADOW"
                and not get_hybrid_ai_engine().config.preserve_baseline_in_shadow
            ):
                return f"{pair}: hybrid_ai_shadow_recorded"
            if hybrid_outcome.mode == "AI_SHADOW":
                trade_record["hybrid_ai_shadow_review"] = {
                    "proposal_id": hybrid_outcome.proposal_id,
                    "status": hybrid_outcome.status,
                    "decision": decision,
                }

        if api_key and api_secret and not SIMULATE:
            try:
                ensure_margin_leverage(pair, api_key, api_secret, LEVERAGE)
                order = place_limit_entry(
                    pair, "BUY" if bias == "LONG" else "SELL",
                    qty_str, price_str, api_key, api_secret,
                    position_side=position_side
                )
                trade_record["entry_order_id"] = order.get("orderId")
                trade_record["qty"] = float(qty_d)
                if order.get("status") == "FILLED":
                    close_side = "SELL" if bias == "LONG" else "BUY"
                    trade_record["sl_tp_placed"] = True  # [FIX-11]
                    sl_o, tp_o = place_sl_tp(pair, close_side, sl_str,
                                             trade_record["tp1_price_str"],
                                             api_key, api_secret,
                                             position_side=position_side,
                                             qty=trade_record["tp1_qty_str"])
                    if sl_o: trade_record["sl_order_id"] = sl_o.get("orderId") or sl_o.get("algoId")
                    if tp_o: trade_record["tp_order_id"] = tp_o.get("orderId") or tp_o.get("algoId")
                    else: log_line(f"{pair}: WARNING tp1_not_placed")
                    if ENABLE_PARTIAL_TP:
                        try:
                            tp2_o = binance_post("/fapi/v1/algoOrder", {
                                "algoType": "CONDITIONAL", "symbol": pair,
                                "side": close_side, "type": "TAKE_PROFIT_MARKET",
                                "triggerPrice": trade_record["tp2_price_str"],
                                "quantity": trade_record["tp2_qty_str"],
                                "workingType": "MARK_PRICE",
                                **({  "positionSide": position_side} if position_side else {})
                            }, api_key, api_secret)
                            trade_record["tp2_order_id"] = tp2_o.get("orderId") or tp2_o.get("algoId")
                        except Exception as _e:
                            log_line(f"{pair}: tp2_place_err {_e}")
                    trade_record["status"] = "OPEN"
                else:
                    trade_record["status"] = "PENDING"
                    t = threading.Thread(
                        target=_poll_order_until_filled,
                        args=(pair, trade_record, sl_str, tp_str, qty_str,
                              position_side, bias, api_key, api_secret, tick),
                        daemon=True, name=f"poller-{pair}"
                    )
                    t.start()
                    log_line(f"{pair}: polling background started")
            except Exception as e:
                trade_record["status"] = "ORDER_ERROR"
                trade_record["order_error"] = str(e)
                log_line(f"order_error {pair} {str(e)[:300]}\n{traceback.format_exc()[:500]}")
        else:
            trade_record["status"] = "SIMULATED"
            trade_record["qty"]    = float(qty_d)
            trade_record["sim_price"] = float(price_d)

        with journal_lock:
            journal.append(trade_record)
            save_json_atomic(JOURNAL_PATH, journal)
            with open_trades_lock:
                open_trades = sum(1 for t in journal if t.get("status") in ("OPEN", "PENDING"))

        if trade_record["status"] in ("OPEN", "PENDING", "SIMULATED"):
            _lock = env.get("_signal_lock")
            if _lock:
                with _lock:
                    if bias == "LONG":
                        env["_longs_this_cycle"][0]  += 1
                    else:
                        env["_shorts_this_cycle"][0] += 1

            fund_str = f" | Funding:{funding:.4f}" if funding is not None else ""
            rr_str   = f"{actual_rr:.2f}"
            jalur_str = f"[Jalur {entry_path}]"
            send_telegram(
                f"🚨 [{BOT_TAG}] {pair} {bias} {jalur_str}\n"
                f"Entry: {fmt_price(entry)} | SL: {fmt_price(sl)} ({sl_source})\n"
                f"TP1: {tp1_price_str} (1:1) | TP2: {tp2_price_str} (2:1, {tp_source})\n"
                f"RR: 1:{rr_str} | Notional: ${actual_notional:.1f} | "
                f"Risk: ~${implied_risk:.2f} ({sl_pct_actual:.2%} SL)"
                f"{fund_str}"
            )
            return f"{pair}: signal_sent"
        return f"{pair}: {trade_record['status']}"

    except Exception as e:
        log_line(f"scan_err {pair} {e}\n{traceback.format_exc()[:500]}")
        return f"{pair}: err"

# ---------------------- HELPERS ----------------------
def sync_time():
    global TIME_OFFSET_MS
    try:
        url = f"{BASE_URL}/fapi/v1/time"
        with urllib.request.urlopen(url, timeout=10, context=get_ssl_context()) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            TIME_OFFSET_MS = int(data.get("serverTime", 0)) - int(time.time() * 1000)
            log_line(f"time_sync offset={TIME_OFFSET_MS}")
    except Exception as e:
        log_line(f"time_sync_err {e}")

def get_spread(symbol):
    try:
        url = f"{BASE_URL}/fapi/v1/ticker/bookTicker?symbol={urllib.parse.quote(symbol)}"
        with urllib.request.urlopen(url, timeout=5, context=get_ssl_context()) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            bid = float(data.get("bidPrice", 0))
            ask = float(data.get("askPrice", 0))
            mid = (bid + ask) / 2 if (bid and ask) else 0
            return (ask - bid) / mid if mid else 1
    except Exception:
        return 1

def get_orderbook_notional(symbol, limit=5):
    try:
        url = f"{BASE_URL}/fapi/v1/depth?symbol={urllib.parse.quote(symbol)}&limit={limit}"
        with urllib.request.urlopen(url, timeout=7, context=get_ssl_context()) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        bids = sum(float(p) * float(q) for p, q in data.get("bids", []))
        asks = sum(float(p) * float(q) for p, q in data.get("asks", []))
        return bids + asks
    except Exception:
        return 0

# ---------------------- [FIX-2] TELEGRAM via HTTP API langsung ----------------------
def send_telegram_to_chat(chat_id, message: str):
    """
    [FIX-2] Direct Telegram Bot HTTP API — tidak butuh subprocess/openclaw.
    Syarat: set TELEGRAM_BOT_TOKEN via env var atau --telegram-token CLI arg.
    Tidak ada sanitasi karakter — pesan terkirim persis seperti ditulis.
    """
    if not TELEGRAM_BOT_TOKEN:
        log_line("send_telegram_skip: TELEGRAM_BOT_TOKEN not set (set via env or --telegram-token)")
        return
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        payload = json.dumps({
            "chat_id": str(chat_id),
            "text": message,
            "disable_web_page_preview": True,
        }).encode("utf-8")
        req = urllib.request.Request(
            url, data=payload,
            headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=15, context=get_ssl_context()) as resp:
            result = json.loads(resp.read().decode("utf-8"))
            if not result.get("ok"):
                log_line(f"send_telegram_api_fail: {result.get('description', '?')}")
            else:
                log_line(f"send_telegram_ok len={len(message)}")
    except Exception as e:
        log_line(f"send_telegram_err {e}")

def send_telegram(message: str):
    lower = str(message or "").lower()
    startup_tokens = (
        "bot v7.4 started",
        "startup sync",
        "bot restarted",
        "all-time report",
    )
    if any(token in lower for token in startup_tokens):
        if _log_throttle("telegram_startup_suppressed", 3600):
            log_line(f"telegram_startup_suppressed len={len(str(message or ''))}")
        return
    send_telegram_to_chat(TARGET_CHAT_ID, message)

def telegram_api(method, payload=None, timeout=15):
    if not TELEGRAM_BOT_TOKEN:
        return None
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/{method}"
        data = json.dumps(payload or {}).encode("utf-8")
        req = urllib.request.Request(
            url, data=data,
            headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=timeout, context=get_ssl_context()) as resp:
            result = json.loads(resp.read().decode("utf-8"))
        if not result.get("ok"):
            log_line(f"telegram_api_fail method={method} desc={result.get('description', '?')}")
        return result
    except Exception as e:
        log_line(f"telegram_api_err method={method} {e}")
        return None

def delete_telegram_message(chat_id, message_id):
    if not chat_id or not message_id:
        return False
    result = telegram_api(
        "deleteMessage",
        {"chat_id": chat_id, "message_id": message_id},
        timeout=8,
    )
    return bool(result and result.get("ok"))

def load_control_state():
    global ENTRY_PAUSED
    state = load_json(REPORT_STATE_PATH) or {}
    ENTRY_PAUSED = bool(state.get("entry_paused", False))

def set_entry_paused(paused, reason="telegram"):
    global ENTRY_PAUSED
    ENTRY_PAUSED = bool(paused)
    state = load_json(REPORT_STATE_PATH) or {}
    state["entry_paused"] = ENTRY_PAUSED
    state["entry_pause_updated_at"] = now_ms()
    state["entry_pause_reason"] = reason
    save_json_atomic(REPORT_STATE_PATH, state)
    log_line(f"entry_paused_set paused={ENTRY_PAUSED} reason={reason}")

def _command_header(title):
    return f"KT AUTO TRADING BOT\n{BOT_TAG} | {title}\n" + ("-" * 28)

def _entry_status_text():
    return "PAUSED - entry baru berhenti" if ENTRY_PAUSED else "ACTIVE - entry baru aktif"

def _mode_text():
    return "SIMULATE / DRY RUN" if SIMULATE else "REAL TRADING"

def _yes_no(value):
    return "ON" if value else "OFF"

def _iso_utc_from_ms(ms):
    if not ms:
        return None
    return datetime.fromtimestamp(ms / 1000, timezone.utc).isoformat().replace("+00:00", "Z")

def _ms_from_days(days):
    return now_ms() + int(days) * 24 * 3600 * 1000

def load_user_registry():
    data = load_json(USER_REGISTRY_PATH)
    if isinstance(data, dict) and isinstance(data.get("users"), dict):
        return data
    return {"version": 1, "users": {}}

def save_user_registry(registry):
    registry["version"] = 1
    save_json_atomic(USER_REGISTRY_PATH, registry)
    chmod_private(USER_REGISTRY_PATH)

def is_admin_chat(chat_id):
    return str(chat_id) in {str(x) for x in ADMIN_CHAT_IDS}

def _user_display(user):
    username = user.get("username")
    name = user.get("first_name") or user.get("name") or ""
    if username:
        return f"@{username}"
    return name or str(user.get("chat_id", "?"))

def _upsert_registered_user(chat_id, profile=None):
    registry = load_user_registry()
    users = registry.setdefault("users", {})
    cid = str(chat_id)
    now = now_ms()
    existing = users.get(cid, {})
    profile = profile or {}
    user = {
        **existing,
        "chat_id": cid,
        "username": profile.get("username") or existing.get("username"),
        "first_name": profile.get("first_name") or existing.get("first_name"),
        "last_name": profile.get("last_name") or existing.get("last_name"),
        "status": existing.get("status", "pending"),
        "license_status": existing.get("license_status", "pending"),
        "created_at": existing.get("created_at", now),
        "updated_at": now,
        "expires_at": existing.get("expires_at"),
        "notes": existing.get("notes", ""),
    }
    users[cid] = user
    save_user_registry(registry)
    return user

def _get_registry_user(chat_id):
    registry = load_user_registry()
    return registry.get("users", {}).get(str(chat_id))

def _is_user_active(user):
    if not user:
        return False
    if user.get("status") != "active":
        return False
    expires_at = user.get("expires_at")
    return not expires_at or int(expires_at) >= now_ms()

def _format_user_account(user, admin_view=False):
    if not user:
        return "Akun belum terdaftar. Kirim /register untuk mulai."
    expires_at = user.get("expires_at")
    expiry = _iso_utc_from_ms(expires_at) if expires_at else "manual/no expiry"
    active_s = "YES" if _is_user_active(user) else "NO"
    lines = [
        f"Chat ID       : {user.get('chat_id')}",
        f"User          : {_user_display(user)}",
        f"Status        : {user.get('status', 'unknown')}",
        f"License       : {user.get('license_status', 'unknown')}",
        f"Active        : {active_s}",
        f"Expiry UTC    : {expiry}",
    ]
    if admin_view and user.get("notes"):
        lines.append(f"Notes         : {user.get('notes')}")
    return "\n".join(lines)

def _managed_user_paths(chat_id):
    base = os.path.join(USERS_DIR, str(chat_id))
    cfg_path = os.path.join(base, "config.json")
    pid_path = os.path.join(base, "worker.pid")
    return base, cfg_path, pid_path

def _load_managed_user_config(chat_id):
    _, cfg_path, _ = _managed_user_paths(chat_id)
    cfg = load_json(cfg_path)
    return cfg if isinstance(cfg, dict) else None

def _managed_worker_pid(chat_id):
    _, _, pid_path = _managed_user_paths(chat_id)
    try:
        if os.path.exists(pid_path):
            with open(pid_path, "r", encoding="utf-8") as f:
                return f.read().strip()
    except Exception:
        return ""
    return ""

def _managed_heartbeat_age(cfg):
    try:
        path = cfg.get("paths", {}).get("heartbeat_path")
        if path and os.path.exists(path):
            return int(time.time() - os.path.getmtime(path))
    except Exception:
        return None
    return None

def _managed_journal(cfg):
    path = cfg.get("paths", {}).get("journal_path")
    data = load_json(path) if path else None
    return data if isinstance(data, list) else []

def _managed_credentials(cfg):
    binance = cfg.get("binance", {}) if isinstance(cfg.get("binance"), dict) else {}
    return binance.get("api_key"), binance.get("api_secret")

def _managed_risk(cfg):
    return cfg.get("risk", {}) if isinstance(cfg.get("risk"), dict) else {}

def _mask_secret(value, left=6, right=4):
    value = str(value or "").strip()
    if not value:
        return "belum ada"
    if len(value) <= left + right:
        return value[:2] + "***"
    return value[:left] + "..." + value[-right:]

def _api_setup_state(user):
    state = user.get("api_setup") if isinstance(user, dict) else None
    return state if isinstance(state, dict) else {}

def _set_registry_api_setup(chat_id, setup_state=None, extra=None):
    registry = load_user_registry()
    users = registry.setdefault("users", {})
    cid = str(chat_id)
    user = users.get(cid, {"chat_id": cid, "created_at": now_ms(), "status": "pending", "license_status": "pending"})
    user["updated_at"] = now_ms()
    if setup_state:
        user["api_setup"] = setup_state
    else:
        user.pop("api_setup", None)
    if extra:
        user.update(extra)
    users[cid] = user
    save_user_registry(registry)
    return user

def _managed_config_template(chat_id, api_key, api_secret):
    base = load_json(CONFIG_PATH) or {}
    user_base, _, _ = _managed_user_paths(chat_id)
    data_dir = os.path.join(user_base, "data")
    logs_dir = os.path.join(user_base, "logs")
    backups_dir = os.path.join(user_base, "backups")
    base_risk = base.get("risk", {}) if isinstance(base.get("risk"), dict) else {}
    base_safety = base.get("safety", {}) if isinstance(base.get("safety"), dict) else {}
    protection_v2 = int(base_safety.get("profit_protection_version", 1)) >= 2
    return {
        "product": {
            "bot_tag": f"KT-U{str(chat_id)[-4:]}",
        },
        "telegram": {
            "bot_token": TELEGRAM_BOT_TOKEN or base.get("telegram", {}).get("bot_token", ""),
            "chat_id": str(chat_id),
            "admin_chat_ids": ADMIN_CHAT_IDS,
            "default_trial_days": DEFAULT_TRIAL_DAYS,
            "enable_commands": False,
        },
        "binance": {
            "base_url": base.get("binance", {}).get("base_url", BASE_URL),
            "api_key": api_key,
            "api_secret": api_secret,
        },
        "risk": {
            "fixed_notional_usdt": base_risk.get("fixed_notional_usdt", 50),
            "risk_per_trade_usdt": base_risk.get("risk_per_trade_usdt", 0.5),
            "leverage": min(int(base_risk.get("leverage", 3) or 3), 5),
            "max_concurrent_trades": min(int(base_risk.get("max_concurrent_trades", 5) or 5), 7),
            "max_same_pair_open": 1,
            "daily_loss_limit_r": max(float(base_risk.get("daily_loss_limit_r", -3) or -3), -4),
        },
        "universe": base.get("universe", {
            "enable_dynamic_pairs": True,
            "min_pair_volume_usdt": 15000000,
            "max_dynamic_pairs": 30,
        }),
        "strategy_quality": base.get("strategy_quality", {
            "enable": True,
            "market_min_agreement": 4,
            "local_min_score": 2,
            "market_cache_sec": 300,
            "short_min_range_position": 0.40,
            "max_sl_pct": 0.03,
        }),
        "strategy_a": {
            "enable_volume_shadow": False,
            "research_status": "volume_shadow_retired_2026_08_04",
        },
        "strategy_b": {
            "version": 2,
            "enable_live": False,
            "research_status": "paused_no_validated_edge",
        },
        "smart_money_c": {
            "version": 6,
            "enable_shadow": False,
            "research_status": "forward_shadow_validation",
        },
        "safety": {
            **base_safety,
            "profit_protection_version": 2,
            "enable_profit_sl_plus": bool(base_safety.get(
                "enable_profit_sl_plus",
                base_safety.get("enable_profit_1pct_breakeven", True),
            )),
            "profit_sl_plus_trigger_pct": (
                float(base_safety.get("profit_sl_plus_trigger_pct", 0.015))
                if protection_v2 else 0.015
            ),
            "profit_sl_plus_lock_pct": (
                float(base_safety.get("profit_sl_plus_lock_pct", 0.01))
                if protection_v2 else 0.01
            ),
            "enable_time_filter": bool(base_safety.get("enable_time_filter", False)),
            "enable_startup_audit": bool(base_safety.get("enable_startup_audit", True)),
            "enable_orphan_order_audit": bool(base_safety.get("enable_orphan_order_audit", False)),
            "audit_alert_cooldown_sec": int(base_safety.get("audit_alert_cooldown_sec", 21600)),
        },
        "logging": base.get("logging", {
            "quiet_mode": True,
            "scan_done_interval_sec": 3600,
        }),
        "paths": {
            "journal_path": os.path.join(data_dir, "journal_v3.json"),
            "log_path": os.path.join(logs_dir, "scan_v3.log"),
            "log_max_bytes": 10485760,
            "log_rotate_keep": 2,
            "report_state_path": os.path.join(data_dir, "daily_report_state_v3.json"),
            "heartbeat_path": os.path.join(data_dir, "heartbeat_v3.txt"),
            "user_registry_path": USER_REGISTRY_PATH,
            "breakout_state_path": os.path.join(data_dir, "breakout_state_v3.json"),
            "shadow_trades_path": os.path.join(data_dir, "shadow_trades_v3.json"),
            "journal_backup_dir": backups_dir,
        },
    }

def _save_managed_user_config(chat_id, api_key, api_secret):
    _, cfg_path, _ = _managed_user_paths(chat_id)
    cfg = _managed_config_template(chat_id, api_key, api_secret)
    existing = load_json(cfg_path)
    if isinstance(existing, dict):
        for key in ("risk", "universe", "strategy_quality", "strategy_a", "strategy_b", "smart_money_c", "safety", "logging"):
            if isinstance(existing.get(key), dict):
                cfg[key] = existing[key]
    save_json_atomic(cfg_path, cfg)
    chmod_private(cfg_path)
    return cfg

def _delete_managed_api_credentials(chat_id):
    _, cfg_path, _ = _managed_user_paths(chat_id)
    cfg = load_json(cfg_path)
    if not isinstance(cfg, dict):
        return False
    binance = cfg.setdefault("binance", {})
    binance["api_key"] = ""
    binance["api_secret"] = ""
    save_json_atomic(cfg_path, cfg)
    chmod_private(cfg_path)
    return True

def _validate_user_api(api_key, api_secret):
    if len(str(api_key or "").strip()) < 20 or len(str(api_secret or "").strip()) < 20:
        return False, "API key/secret terlalu pendek atau tidak lengkap."
    try:
        acct = get_account_info(api_key, api_secret)
        if acct is None:
            return False, "Binance tidak mengembalikan data account."
        return True, "OK"
    except Exception as e:
        msg = str(e)
        if "-2015" in msg:
            return False, "API key invalid, permission salah, atau IP whitelist belum berisi IP VPS."
        if "-1021" in msg:
            return False, "Timestamp Binance tidak sinkron. Coba ulang sebentar lagi."
        return False, msg[:120]

def _notify_admins(text):
    for admin_id in ADMIN_CHAT_IDS:
        try:
            send_telegram_to_chat(str(admin_id), text)
        except Exception:
            pass

RISK_PRESETS = {
    "conservative": {
        "label": "Conservative",
        "fixed_notional_usdt": 25,
        "leverage": 2,
        "max_concurrent_trades": 3,
        "daily_loss_limit_r": -2,
    },
    "standard": {
        "label": "Standard",
        "fixed_notional_usdt": 50,
        "leverage": 3,
        "max_concurrent_trades": 5,
        "daily_loss_limit_r": -3,
    },
    "growth": {
        "label": "Growth",
        "fixed_notional_usdt": 75,
        "leverage": 3,
        "max_concurrent_trades": 7,
        "daily_loss_limit_r": -4,
    },
}

RISK_PRESET_ALIASES = {
    "aman": "conservative",
    "safe": "conservative",
    "konservatif": "conservative",
    "conservative": "conservative",
    "standar": "standard",
    "standard": "standard",
    "normal": "standard",
    "growth": "growth",
    "agresif": "growth",
    "aggressive": "growth",
}

RISK_FIELD_ALIASES = {
    "notional": "fixed_notional_usdt",
    "modal": "fixed_notional_usdt",
    "size": "fixed_notional_usdt",
    "fixed_notional": "fixed_notional_usdt",
    "fixed_notional_usdt": "fixed_notional_usdt",
    "leverage": "leverage",
    "lev": "leverage",
    "max": "max_concurrent_trades",
    "maxtrade": "max_concurrent_trades",
    "max_trades": "max_concurrent_trades",
    "max_concurrent": "max_concurrent_trades",
    "max_concurrent_trades": "max_concurrent_trades",
    "daily": "daily_loss_limit_r",
    "daily_limit": "daily_loss_limit_r",
    "daily_loss": "daily_loss_limit_r",
    "daily_loss_limit_r": "daily_loss_limit_r",
}

RISK_FIELD_LABELS = {
    "fixed_notional_usdt": "Notional/trade",
    "leverage": "Leverage",
    "max_concurrent_trades": "Max concurrent",
    "daily_loss_limit_r": "Daily loss limit",
}

RISK_FIELD_BOUNDS = {
    "fixed_notional_usdt": (10, 500),
    "leverage": (1, 5),
    "max_concurrent_trades": (1, 20),
    "daily_loss_limit_r": (-10, -1),
}

def _risk_level_label(risk):
    try:
        notional = float(risk.get("fixed_notional_usdt", 0) or 0)
        leverage = int(risk.get("leverage", 0) or 0)
        max_trades = int(risk.get("max_concurrent_trades", 0) or 0)
    except Exception:
        return "Perlu dicek"
    if notional <= 25 and leverage <= 2 and max_trades <= 3:
        return "Aman / awal"
    if notional <= 75 and leverage <= 3 and max_trades <= 7:
        return "Normal"
    return "Tinggi - gunakan hati-hati"

def _risk_change_note(managed=False):
    if managed:
        return (
            "\n\nCatatan:\n"
            "- Setting tersimpan di config user.\n"
            "- Untuk worker user terpisah, perubahan berlaku setelah worker user direstart otomatis/oleh admin.\n"
            "- Posisi yang sudah terbuka tidak diubah otomatis."
        )
    return (
        "\n\nCatatan:\n"
        "- Setting tersimpan di config bot.\n"
        "- Untuk bot utama VPS, perubahan berlaku otomatis mulai scan/order berikutnya.\n"
        "- Posisi yang sudah terbuka tidak diubah otomatis."
    )

def _format_risk_settings(risk, title, include_help=True):
    level = _risk_level_label(risk)
    notional = float(risk.get("fixed_notional_usdt", 0) or 0)
    leverage = int(risk.get("leverage", 0) or 0)
    max_trades = int(risk.get("max_concurrent_trades", 0) or 0)
    max_same = int(risk.get("max_same_pair_open", 1) or 1)
    daily = float(risk.get("daily_loss_limit_r", 0) or 0)
    lines = [
        f"{_command_header(title)}",
        f"Profil risiko : {level}",
        "",
        f"Notional/trade  : ${notional:.0f}",
        f"Leverage        : {leverage}x",
        f"Max concurrent  : {max_trades}",
        f"Max same pair   : {max_same}",
        f"Daily loss limit: {daily:g}R",
    ]
    if include_help:
        lines.extend([
            "",
            "Ubah cepat",
            "/risk preset conservative",
            "/risk preset standard",
            "/risk preset growth",
            "",
            "Ubah manual",
            "/risk set notional 50",
            "/risk set leverage 3",
            "/risk set max 5",
            "/risk set daily -3",
            "",
            "Info lengkap: /risk help",
        ])
    return "\n".join(lines)

def _build_risk_help_text(title="RISK MANAGEMENT"):
    return (
        f"{_command_header(title)}\n"
        "Atur risk management langsung dari Telegram.\n\n"
        "Preset aman untuk user baru:\n"
        "- conservative: $25/trade, 2x, max 3 posisi, limit -2R\n"
        "- standard: $50/trade, 3x, max 5 posisi, limit -3R\n"
        "- growth: $75/trade, 3x, max 7 posisi, limit -4R\n\n"
        "Command:\n"
        "/risk\n"
        "/risk preset conservative\n"
        "/risk preset standard\n"
        "/risk preset growth\n"
        "/risk set notional 50\n"
        "/risk set leverage 3\n"
        "/risk set max 5\n"
        "/risk set daily -3\n\n"
        "Batas aman Telegram:\n"
        "- Notional: $10 sampai $500\n"
        "- Leverage: 1x sampai 5x\n"
        "- Max posisi: 1 sampai 20\n"
        "- Daily limit: -1R sampai -10R\n\n"
        "Catatan: bot tidak menjamin profit. Futures tetap berisiko."
    )

def _normalize_risk_value(field, raw_value):
    if field not in RISK_FIELD_BOUNDS:
        raise ValueError("Field risk tidak dikenal.")
    try:
        value = float(str(raw_value).replace("$", "").replace(",", "."))
    except Exception:
        raise ValueError("Nilai harus berupa angka.")
    lo, hi = RISK_FIELD_BOUNDS[field]
    if not (lo <= value <= hi):
        label = RISK_FIELD_LABELS.get(field, field)
        raise ValueError(f"{label} harus di antara {lo:g} dan {hi:g}.")
    if field in ("leverage", "max_concurrent_trades"):
        return int(value)
    return round(value, 2)

def _save_risk_config(path, risk_updates):
    cfg = load_json(path)
    if not isinstance(cfg, dict):
        raise ValueError("Config tidak ditemukan atau tidak valid.")
    risk = cfg.setdefault("risk", {})
    if not isinstance(risk, dict):
        risk = {}
        cfg["risk"] = risk
    risk.update(risk_updates)
    save_json_atomic(path, cfg)
    return cfg

def _apply_live_risk_updates(risk_updates):
    global FIXED_NOTIONAL_USDT, RISK_PER_TRADE_USDT, LEVERAGE
    global MAX_CONCURRENT_TRADES, MAX_SAME_PAIR_OPEN, DAILY_LOSS_LIMIT_R
    if "fixed_notional_usdt" in risk_updates:
        FIXED_NOTIONAL_USDT = float(risk_updates["fixed_notional_usdt"])
    if "risk_per_trade_usdt" in risk_updates:
        RISK_PER_TRADE_USDT = float(risk_updates["risk_per_trade_usdt"])
    if "leverage" in risk_updates:
        LEVERAGE = int(risk_updates["leverage"])
    if "max_concurrent_trades" in risk_updates:
        MAX_CONCURRENT_TRADES = int(risk_updates["max_concurrent_trades"])
    if "max_same_pair_open" in risk_updates:
        MAX_SAME_PAIR_OPEN = int(risk_updates["max_same_pair_open"])
    if "daily_loss_limit_r" in risk_updates:
        DAILY_LOSS_LIMIT_R = float(risk_updates["daily_loss_limit_r"])

def _handle_risk_command(parts, cfg_path, managed=False):
    cfg = load_json(cfg_path)
    if not isinstance(cfg, dict):
        return f"{_command_header('RISK MANAGEMENT')}\nConfig tidak ditemukan atau tidak valid."
    risk = _managed_risk(cfg)
    if len(parts) == 1:
        title = "CLIENT RISK" if managed else "RISK SETTINGS"
        return _format_risk_settings(risk, title)

    action = parts[1].lower()
    if action in ("help", "panduan", "menu"):
        return _build_risk_help_text("CLIENT RISK" if managed else "RISK MANAGEMENT")

    if action == "preset":
        if len(parts) < 3:
            return (
                f"{_command_header('RISK PRESET')}\n"
                "Format: /risk preset conservative|standard|growth"
            )
        key = RISK_PRESET_ALIASES.get(parts[2].lower())
        if not key:
            return (
                f"{_command_header('RISK PRESET')}\n"
                "Preset tidak dikenal.\n\n"
                "Pilihan: conservative, standard, growth"
            )
        preset = dict(RISK_PRESETS[key])
        label = preset.pop("label")
        cfg = _save_risk_config(cfg_path, preset)
        if not managed:
            _apply_live_risk_updates(preset)
        log_line(f"risk_updated source=telegram preset={key} managed={managed}")
        return (
            f"{_command_header('RISK UPDATED')}\n"
            f"Preset aktif: {label}\n\n"
            f"{_format_risk_settings(_managed_risk(cfg), 'RISK SNAPSHOT', include_help=False)}"
            f"{_risk_change_note(managed)}"
        )

    if action == "set":
        if len(parts) < 4:
            return (
                f"{_command_header('RISK SET')}\n"
                "Format:\n"
                "/risk set notional 50\n"
                "/risk set leverage 3\n"
                "/risk set max 5\n"
                "/risk set daily -3"
            )
        field = RISK_FIELD_ALIASES.get(parts[2].lower())
        if not field:
            return (
                f"{_command_header('RISK SET')}\n"
                "Field tidak dikenal.\n\n"
                "Pilihan: notional, leverage, max, daily"
            )
        try:
            value = _normalize_risk_value(field, parts[3])
        except ValueError as e:
            return f"{_command_header('RISK SET')}\n{e}"
        cfg = _save_risk_config(cfg_path, {field: value})
        if not managed:
            _apply_live_risk_updates({field: value})
        label = RISK_FIELD_LABELS.get(field, field)
        log_line(f"risk_updated source=telegram field={field} value={value} managed={managed}")
        return (
            f"{_command_header('RISK UPDATED')}\n"
            f"{label} diubah menjadi {value:g}.\n\n"
            f"{_format_risk_settings(_managed_risk(cfg), 'RISK SNAPSHOT', include_help=False)}"
            f"{_risk_change_note(managed)}"
        )

    return (
        f"{_command_header('RISK MANAGEMENT')}\n"
        "Command tidak dikenal.\n\n"
        "Gunakan /risk help untuk panduan."
    )

def _managed_access_error(chat_id):
    user = _get_registry_user(chat_id)
    cfg = _load_managed_user_config(chat_id)
    if not user:
        return (
            f"{_command_header('MANAGED ACCESS')}\n"
            "Akun belum terdaftar. Kirim /register terlebih dahulu."
        )
    if not _is_user_active(user):
        return (
            f"{_command_header('MANAGED ACCESS')}\n"
            "Akun belum aktif atau license sudah expired.\n\n"
            f"{_format_user_account(user)}"
        )
    if not cfg:
        return (
            f"{_command_header('MANAGED ACCESS')}\n"
            "Akun sudah approved, tetapi worker pribadi belum dibuat admin.\n\n"
            "Admin perlu menjalankan managed worker create/start untuk Chat ID Anda."
        )
    return None

def build_managed_status_text(chat_id):
    err = _managed_access_error(chat_id)
    if err:
        return err
    cfg = _load_managed_user_config(chat_id)
    journal_data = _managed_journal(cfg)
    open_count = sum(1 for t in journal_data if t.get("status") == "OPEN")
    pending_count = sum(1 for t in journal_data if t.get("status") == "PENDING")
    pid = _managed_worker_pid(chat_id) or "n/a"
    age = _managed_heartbeat_age(cfg)
    age_s = f"{age}s ago" if age is not None else "n/a"
    risk = _managed_risk(cfg)
    return (
        f"{_command_header('CLIENT STATUS')}\n"
        f"Chat ID     : {chat_id}\n"
        f"Worker PID  : {pid}\n"
        f"Heartbeat   : {age_s}\n"
        f"Open/Pending: {open_count}/{pending_count}\n"
        f"Journal     : {len(journal_data)} records\n"
        f"Notional    : ${float(risk.get('fixed_notional_usdt', 0)):.0f}/trade\n"
        f"Leverage    : {risk.get('leverage', '?')}x\n"
        f"Max trades  : {risk.get('max_concurrent_trades', '?')}"
    )

def build_managed_health_text(chat_id):
    err = _managed_access_error(chat_id)
    if err:
        return err
    cfg = _load_managed_user_config(chat_id)
    api_key, api_secret = _managed_credentials(cfg)
    checks = [
        ("Worker config", "OK"),
        ("API key", "OK" if api_key else "MISSING"),
        ("API secret", "OK" if api_secret else "MISSING"),
    ]
    age = _managed_heartbeat_age(cfg)
    checks.append(("Heartbeat", f"{age}s ago" if age is not None else "MISSING"))
    journal_data = _managed_journal(cfg)
    checks.append(("Journal", f"OK ({len(journal_data)} records)"))
    if api_key and api_secret:
        try:
            acct = get_account_info(api_key, api_secret)
            checks.append(("Binance account", "OK" if acct else "EMPTY"))
        except Exception as e:
            checks.append(("Binance account", f"FAIL ({str(e)[:40]})"))
    lines = [f"{name:<16}: {status}" for name, status in checks]
    return f"{_command_header('CLIENT HEALTH')}\n" + "\n".join(lines)

def build_managed_positions_text(chat_id):
    err = _managed_access_error(chat_id)
    if err:
        return err
    cfg = _load_managed_user_config(chat_id)
    api_key, api_secret = _managed_credentials(cfg)
    if api_key and api_secret:
        return build_positions_text(api_key, api_secret)
    journal_data = _managed_journal(cfg)
    open_list = [t for t in journal_data if t.get("status") in ("OPEN", "PENDING")]
    lines = [_format_trade_line(t, idx=i + 1) for i, t in enumerate(open_list)]
    body = _limited_lines(lines, 20) if lines else "Tidak ada OPEN/PENDING di journal user."
    return f"{_command_header('CLIENT POSITIONS')}\n{body}"

def build_managed_orders_text(chat_id):
    err = _managed_access_error(chat_id)
    if err:
        return err
    cfg = _load_managed_user_config(chat_id)
    api_key, api_secret = _managed_credentials(cfg)
    if not (api_key and api_secret):
        return f"{_command_header('CLIENT ORDERS')}\nAPI user belum lengkap di worker config."
    return build_orders_text(api_key, api_secret)

def build_managed_report_text(chat_id, period):
    err = _managed_access_error(chat_id)
    if err:
        return err
    cfg = _load_managed_user_config(chat_id)
    return build_report_text(period=period, trades_source=_managed_journal(cfg))

def build_managed_shadow_text(chat_id):
    err = _managed_access_error(chat_id)
    if err:
        return err
    cfg = _load_managed_user_config(chat_id)
    shadow_path = cfg.get("paths", {}).get("shadow_trades_path")
    data = load_json(shadow_path) if shadow_path else None
    trades = data if isinstance(data, list) else []
    return build_shadow_command_text(trades_source=trades, title="CLIENT SHADOW")

def build_managed_d1_shadow_text(chat_id):
    err = _managed_access_error(chat_id)
    if err:
        return err
    return build_d1_shadow_command_text()

def build_managed_risk_text(chat_id):
    err = _managed_access_error(chat_id)
    if err:
        return err
    cfg = _load_managed_user_config(chat_id)
    risk = _managed_risk(cfg)
    return _format_risk_settings(risk, "CLIENT RISK")

def handle_managed_risk_command(chat_id, parts):
    err = _managed_access_error(chat_id)
    if err:
        return err
    _, cfg_path, _ = _managed_user_paths(chat_id)
    return _handle_risk_command(parts, cfg_path, managed=True)

def build_register_text(chat_id, profile=None):
    user = _upsert_registered_user(chat_id, profile)
    return (
        f"{_command_header('REGISTRATION')}\n"
        "Pendaftaran diterima.\n\n"
        f"{_format_user_account(user)}\n\n"
        "Status awal: pending.\n"
        "Admin perlu approve sebelum layanan managed/Semi-SaaS aktif.\n\n"
        "Langkah berikut:\n"
        "1. Baca risk disclosure.\n"
        "2. Setup Binance Futures.\n"
        "3. Buat API key tanpa withdrawal permission.\n"
        "4. Jalankan /setup_api.\n"
        "5. Tunggu admin approval."
    )

def build_myaccount_text(chat_id):
    user = _get_registry_user(chat_id)
    return f"{_command_header('MY ACCOUNT')}\n{_format_user_account(user)}"

def build_license_text(chat_id):
    user = _get_registry_user(chat_id)
    if not user:
        return f"{_command_header('LICENSE')}\nAkun belum terdaftar. Kirim /register."
    return (
        f"{_command_header('LICENSE')}\n"
        f"{_format_user_account(user)}\n\n"
        "Catatan: license mengaktifkan akses layanan managed. "
        "Real trading tetap membutuhkan setup Binance API yang aman."
    )

def build_onboarding_text():
    return (
        f"{_command_header('ONBOARDING')}\n"
        "Alur client mobile-only:\n\n"
        "1. /register\n"
        "2. Baca risk disclosure\n"
        "3. Setup Binance Futures\n"
        "4. Baca /api_guide untuk membuat API key\n"
        "5. Admin approve/license\n"
        "6. Setup API lewat /setup_api\n"
        "7. /health\n"
        "8. Simulate/trial\n"
        "9. Real mode kecil\n\n"
        "Bot tidak menjamin profit. Futures tetap berisiko tinggi."
    )

def build_api_guide_text():
    return (
        f"{_command_header('BINANCE API GUIDE')}\n"
        "Panduan membuat API key untuk KT Auto Trading Bot.\n\n"
        "Sebelum mulai\n"
        "1. Akun Binance sudah aktif.\n"
        "2. Futures account sudah dibuka.\n"
        "3. 2FA/Authenticator Binance sudah aktif.\n\n"
        "Langkah di Binance\n"
        "1. Buka Binance, masuk ke Account/Profile.\n"
        "2. Pilih API Management.\n"
        "3. Pilih Create API.\n"
        "4. Pilih System generated API key jika tersedia.\n"
        "5. Beri nama singkat, contoh: ktbot.\n"
        "6. Selesaikan verifikasi email/2FA.\n\n"
        "Permission wajib\n"
        "- Enable Reading: ON\n"
        "- Enable Futures: ON\n"
        "- Enable Spot/Margin: OFF jika tidak diperlukan\n"
        "- Enable Withdrawals: WAJIB OFF\n\n"
        "IP whitelist\n"
        f"Masukkan IP VPS bot: {PUBLIC_VPS_IP}\n\n"
        "Setelah API dibuat\n"
        "1. Copy API Key.\n"
        "2. Copy API Secret saat pertama kali muncul.\n"
        "3. Kembali ke Telegram.\n"
        "4. Jalankan /setup_api.\n\n"
        "Penting: jika Withdrawal aktif, jangan lanjut. Hapus API itu dan buat ulang."
    )

def build_setup_api_text(chat_id, profile=None):
    user = _upsert_registered_user(chat_id, profile)
    state = {
        "step": "awaiting_api_key",
        "started_at": now_ms(),
        "updated_at": now_ms(),
    }
    _set_registry_api_setup(chat_id, state)
    return (
        f"{_command_header('SETUP API')}\n"
        "Kita mulai setup Binance API dengan mode aman.\n\n"
        "Wajib di Binance:\n"
        "1. Enable Futures sudah aktif.\n"
        "2. API permission: Read ON.\n"
        "3. API permission: Futures ON.\n"
        "4. Withdrawal wajib OFF.\n"
        f"5. IP whitelist isi IP VPS: {PUBLIC_VPS_IP}\n\n"
        "Belum tahu cara buat API key?\n"
        "Baca dulu: /api_guide\n\n"
        "Catatan keamanan:\n"
        "- Telegram bot chat dipakai untuk early access agar praktis.\n"
        "- Bot akan mencoba menghapus pesan API key/secret setelah diterima.\n"
        "- Jangan pernah aktifkan withdrawal permission.\n"
        "- Anda bisa hapus API kapan saja dengan /delete_api.\n\n"
        "Langkah berikut:\n"
        "Kirim API Key dengan format:\n"
        "/api_key API_KEY_ANDA\n\n"
        f"Status akun: {user.get('status', 'pending')}"
    )

def build_api_key_text(chat_id, api_key):
    user = _get_registry_user(chat_id)
    if not user:
        user = _upsert_registered_user(chat_id)
    api_key = str(api_key or "").strip()
    if len(api_key) < 20:
        return (
            f"{_command_header('API KEY')}\n"
            "API Key terlihat belum lengkap.\n\n"
            "Format:\n"
            "/api_key API_KEY_ANDA"
        )
    state = {
        "step": "awaiting_api_secret",
        "pending_api_key": api_key,
        "updated_at": now_ms(),
        "started_at": _api_setup_state(user).get("started_at", now_ms()),
    }
    _set_registry_api_setup(chat_id, state, {"api_status": "awaiting_secret"})
    return (
        f"{_command_header('API KEY SAVED')}\n"
        f"API Key diterima: {_mask_secret(api_key)}\n\n"
        "Sekarang kirim API Secret dengan format:\n"
        "/api_secret API_SECRET_ANDA\n\n"
        "Pesan secret akan coba dihapus otomatis setelah diterima."
    )

def build_api_secret_text(chat_id, api_secret):
    user = _get_registry_user(chat_id)
    if not user:
        return f"{_command_header('API SETUP')}\nKirim /setup_api terlebih dahulu."
    state = _api_setup_state(user)
    api_key = state.get("pending_api_key")
    if not api_key:
        return (
            f"{_command_header('API SETUP')}\n"
            "API Key belum tersimpan.\n\n"
            "Mulai ulang dengan /setup_api."
        )
    api_secret = str(api_secret or "").strip()
    ok, detail = _validate_user_api(api_key, api_secret)
    if not ok:
        _set_registry_api_setup(
            chat_id,
            {
                "step": "awaiting_api_key",
                "last_error": detail,
                "updated_at": now_ms(),
                "started_at": state.get("started_at", now_ms()),
            },
            {"api_status": "validation_failed"},
        )
        return (
            f"{_command_header('API VALIDATION FAILED')}\n"
            "API belum bisa dipakai.\n\n"
            f"Detail: {detail}\n\n"
            "Cek ulang di Binance:\n"
            "- Futures permission ON\n"
            "- Read permission ON\n"
            "- Withdrawal permission OFF\n"
            "- IP whitelist berisi IP VPS\n\n"
            "Setelah diperbaiki, ulangi /setup_api."
        )
    cfg = _save_managed_user_config(chat_id, api_key, api_secret)
    extra = {
        "api_status": "connected",
        "api_key_masked": _mask_secret(api_key),
        "api_connected_at": now_ms(),
    }
    user = _set_registry_api_setup(chat_id, None, extra)
    _notify_admins(
        f"{_command_header('API READY')}\n"
        "User API sudah valid dan config user sudah tersimpan.\n\n"
        f"Chat ID: {chat_id}\n"
        f"User   : {_user_display(user)}\n"
        f"API    : {_mask_secret(api_key)}\n\n"
        "Langkah admin:\n"
        f"/admin_approve {chat_id}"
    )
    risk = _managed_risk(cfg)
    return (
        f"{_command_header('API CONNECTED')}\n"
        "API berhasil divalidasi dari server bot.\n\n"
        f"API Key : {_mask_secret(api_key)}\n"
        f"Risk    : ${float(risk.get('fixed_notional_usdt', 0)):.0f}/trade, "
        f"{risk.get('leverage', '?')}x, max {risk.get('max_concurrent_trades', '?')} posisi\n\n"
        "Admin akan review dan mengaktifkan layanan.\n"
        "Gunakan /api_status untuk cek status setup."
    )

def build_api_status_text(chat_id):
    user = _get_registry_user(chat_id)
    cfg = _load_managed_user_config(chat_id)
    api_key, api_secret = _managed_credentials(cfg) if cfg else ("", "")
    setup = _api_setup_state(user or {})
    status = (user or {}).get("api_status") or ("connected" if api_key and api_secret else "not_connected")
    lines = [
        f"{_command_header('API STATUS')}",
        f"Akun       : {(user or {}).get('status', 'belum register')}",
        f"License    : {(user or {}).get('license_status', 'pending')}",
        f"API status : {status}",
        f"API key    : {_mask_secret(api_key or (user or {}).get('api_key_masked', ''))}",
    ]
    if setup:
        lines.append(f"Setup step : {setup.get('step', 'unknown')}")
        if setup.get("last_error"):
            lines.append(f"Last error : {setup.get('last_error')}")
    if api_key and api_secret:
        lines.extend([
            "",
            "Status: API tersimpan di config user.",
            "Admin perlu approve/start worker sebelum trading berjalan.",
        ])
    else:
        lines.extend([
            "",
            "API belum tersambung.",
            "Mulai dengan /setup_api.",
        ])
    return "\n".join(lines)

def build_delete_api_text(chat_id):
    deleted = _delete_managed_api_credentials(chat_id)
    _set_registry_api_setup(chat_id, None, {
        "api_status": "deleted",
        "api_key_masked": "",
        "api_deleted_at": now_ms(),
    })
    _notify_admins(
        f"{_command_header('API DELETED')}\n"
        f"User menghapus API dari config.\n\nChat ID: {chat_id}"
    )
    return (
        f"{_command_header('API DELETED')}\n"
        "API key dan secret sudah dihapus dari config bot."
        if deleted else
        f"{_command_header('API DELETED')}\n"
        "Tidak ada config API aktif yang ditemukan.\n"
        "Setup pending juga sudah dibersihkan."
    )

def build_cancel_setup_text(chat_id):
    _set_registry_api_setup(chat_id, None, {"api_status": "setup_cancelled"})
    return (
        f"{_command_header('SETUP CANCELLED')}\n"
        "Setup API dibatalkan.\n\n"
        "Mulai lagi kapan saja dengan /setup_api."
    )

def build_admin_users_text(status_filter=None):
    registry = load_user_registry()
    users = list(registry.get("users", {}).values())
    if status_filter:
        users = [u for u in users if u.get("status") == status_filter]
    if not users:
        return f"{_command_header('ADMIN USERS')}\nBelum ada user."
    users = sorted(users, key=lambda u: u.get("created_at", 0), reverse=True)
    lines = []
    for user in users[:30]:
        exp = _iso_utc_from_ms(user.get("expires_at")) if user.get("expires_at") else "no-exp"
        api_status = user.get("api_status", "no-api")
        lines.append(
            f"{user.get('chat_id')} | {_user_display(user)} | "
            f"{user.get('status')} | {user.get('license_status')} | api {api_status} | exp {exp}"
        )
    extra = f"\n...dan {len(users)-30} user lain" if len(users) > 30 else ""
    return f"{_command_header('ADMIN USERS')}\n" + "\n".join(lines) + extra

def _admin_set_user_status(chat_id, status, days=None, note=""):
    registry = load_user_registry()
    users = registry.setdefault("users", {})
    cid = str(chat_id)
    user = users.get(cid, {"chat_id": cid, "created_at": now_ms()})
    user["status"] = status
    user["license_status"] = "active" if status == "active" else status
    user["updated_at"] = now_ms()
    if days is not None:
        user["expires_at"] = _ms_from_days(int(days))
    if note:
        user["notes"] = note
    users[cid] = user
    save_user_registry(registry)
    return user

def build_admin_approve_text(args):
    if len(args) < 2:
        return f"{_command_header('ADMIN APPROVE')}\nFormat: /admin_approve CHAT_ID [days]"
    days = int(args[2]) if len(args) >= 3 else DEFAULT_TRIAL_DAYS
    user = _admin_set_user_status(args[1], "active", days=days, note="approved by admin")
    return f"{_command_header('ADMIN APPROVE')}\nUser approved {days} hari.\n\n{_format_user_account(user, admin_view=True)}"

def build_admin_revoke_text(args):
    if len(args) < 2:
        return f"{_command_header('ADMIN REVOKE')}\nFormat: /admin_revoke CHAT_ID [reason]"
    reason = " ".join(args[2:]) if len(args) > 2 else "revoked by admin"
    user = _admin_set_user_status(args[1], "revoked", note=reason)
    return f"{_command_header('ADMIN REVOKE')}\nUser revoked.\n\n{_format_user_account(user, admin_view=True)}"

def build_admin_extend_text(args):
    if len(args) < 3:
        return f"{_command_header('ADMIN EXTEND')}\nFormat: /admin_extend CHAT_ID days"
    user = _admin_set_user_status(args[1], "active", days=int(args[2]), note="extended by admin")
    return f"{_command_header('ADMIN EXTEND')}\nLicense diperpanjang {args[2]} hari dari sekarang.\n\n{_format_user_account(user, admin_view=True)}"

def _limited_lines(lines, limit=20):
    if len(lines) <= limit:
        return "\n".join(lines)
    return "\n".join(lines[:limit]) + f"\n...dan {len(lines) - limit} item lainnya"

def _format_trade_line(t, idx=None):
    pair = t.get("pair", "?")
    side = t.get("side", "?")
    status = t.get("status", "?")
    entry = fmt_price(t.get("entry", 0))
    sl = fmt_price(t.get("sl", 0))
    tp1 = t.get("tp1_price_str") or fmt_price(t.get("tp", 0))
    tp2 = t.get("tp2_price_str") or fmt_price(t.get("tp2", t.get("tp", 0)))
    pnl = t.get("unrealized_pnl")
    pnl_s = f" | uPnL ${pnl:+.2f}" if isinstance(pnl, (int, float)) else ""
    prefix = f"{idx}. " if idx is not None else ""
    return (
        f"{prefix}{pair} | {side} | {status}\n"
        f"   Entry {entry} | SL {sl}\n"
        f"   TP1 {tp1} | TP2 {tp2}{pnl_s}"
    )

def build_status_text(api_key=None, api_secret=None):
    with journal_lock:
        snap = list(journal)
    open_count = sum(1 for t in snap if t.get("status") == "OPEN")
    pending_count = sum(1 for t in snap if t.get("status") == "PENDING")
    closed_count = sum(1 for t in snap if t.get("result_R") is not None)
    with open_trades_lock:
        live_open = open_trades
    strategy_b_status = "LIVE" if ENABLE_STRATEGY_B_LIVE else "PAUSED"
    strategy_c_status = (
        f"SHADOW C{SMART_MONEY_C_VERSION}"
        if ENABLE_SMART_MONEY_C_SHADOW
        else "PAUSED"
    )
    return (
        f"{_command_header('STATUS')}\n"
        f"Mode        : {_mode_text()}\n"
        f"Entry       : {_entry_status_text()}\n"
        f"Strategi    : A LIVE | B {strategy_b_status} | C {strategy_c_status}\n"
        f"Universe    : {len(PAIRS)} pair | invalid {len(INVALID_PAIRS)}\n"
        f"Workers     : {MAX_WORKERS}\n"
        f"Posisi      : OPEN {open_count} | PENDING {pending_count}\n"
        f"Counter     : {live_open}/{MAX_CONCURRENT_TRADES}\n"
        f"Closed data : {closed_count} trade\n"
        f"\nRisk Snapshot\n"
        f"Notional    : ${FIXED_NOTIONAL_USDT:.0f}/trade\n"
        f"Leverage    : {LEVERAGE}x\n"
        f"Daily limit : {DAILY_LOSS_LIMIT_R}R"
    )

def build_positions_text(api_key=None, api_secret=None):
    if api_key and api_secret and not SIMULATE:
        live_positions = _get_all_positions(api_key, api_secret)
        if live_positions is not None:
            lines = []
            seen = set()
            for key, pos in live_positions.items():
                if ":" not in str(key) or key in seen:
                    continue
                seen.add(key)
                amt = float(pos.get("positionAmt", 0) or 0)
                if abs(amt) <= 0:
                    continue
                symbol = pos.get("symbol", "?")
                entry = pos.get("entryPrice", "?")
                upnl = float(pos.get("unRealizedProfit", 0) or 0)
                side = "LONG" if amt > 0 else "SHORT"
                lines.append(
                    f"{len(lines) + 1}. {symbol} | {side}\n"
                    f"   Qty {amt} | Entry {entry}\n"
                    f"   uPnL ${upnl:+.2f}"
                )
            body = _limited_lines(lines, 20) if lines else "Tidak ada posisi live di Binance."
            return f"{_command_header('LIVE POSITIONS')}\n{body}"

    with journal_lock:
        open_list = [t for t in journal if t.get("status") in ("OPEN", "PENDING")]
    lines = [_format_trade_line(t, idx=i + 1) for i, t in enumerate(open_list)]
    body = _limited_lines(lines, 20) if lines else "Tidak ada OPEN/PENDING di journal."
    return f"{_command_header('JOURNAL POSITIONS')}\n{body}"

def build_orders_text(api_key=None, api_secret=None):
    if not (api_key and api_secret) or SIMULATE:
        return (
            f"{_command_header('ORDERS')}\n"
            "Live order hanya tersedia di REAL mode dengan API key."
        )
    live_orders = _get_all_open_orders(api_key, api_secret)
    if live_orders is None:
        return f"{_command_header('ORDERS')}\nGagal mengambil open orders dari Binance."
    orders = [o for k, o in live_orders.items() if not str(k).startswith("__meta_")]
    if not orders:
        return f"{_command_header('ORDERS')}\nTidak ada open order."
    lines = []
    for o in orders[:25]:
        oid = o.get("algoId") or o.get("orderId")
        symbol = _order_symbol(o)
        typ = o.get("type") or o.get("origType") or o.get("orderType")
        side = o.get("side", "?")
        trigger = o.get("triggerPrice") or o.get("stopPrice") or o.get("price") or "?"
        lines.append(
            f"{len(lines) + 1}. {symbol} | {side} | {typ}\n"
            f"   Trigger {trigger}\n"
            f"   ID {oid}"
        )
    return f"{_command_header('OPEN ORDERS')}\n{_limited_lines(lines, 25)}"

def _period_start_ms(period, tz):
    now = datetime.now(tz)
    if period == "today":
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    elif period == "week":
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        start = today_start - timedelta(days=today_start.weekday())
    elif period == "month":
        start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    else:
        return None
    return int(start.timestamp() * 1000)

def build_report_text(period="today", trades_source=None):
    tz = timezone(timedelta(hours=7))
    labels = {
        "today": "REPORT HARI INI",
        "week": "REPORT MINGGU INI",
        "month": "REPORT BULAN INI",
        "alltime": "REPORT ALL TIME",
    }
    label = labels.get(period, "REPORT")
    trades = list(journal if trades_source is None else trades_source)
    start_ms = _period_start_ms(period, tz)
    if start_ms is not None:
        trades = [t for t in trades if t.get("timestamp", 0) >= start_ms]
    d = _build_report_stats(trades)
    expectancy = d["avg_r"]
    pnl_label = "REALIZED P&L" if any(t.get("realized_pnl") is not None for t in trades) else "EST. P&L"
    best_pair = d["best_pair"]
    worst_pair = d["worst_pair"]
    best_pair_s = f"{best_pair[0]} {best_pair[1]['total_r']:+.2f}R" if best_pair[0] else "n/a"
    worst_pair_s = f"{worst_pair[0]} {worst_pair[1]['total_r']:+.2f}R" if worst_pair[0] else "n/a"
    return (
        f"{_command_header(label)}\n"
        f"Total trade : {d['total']}\n"
        f"Closed      : {d['closed']}\n"
        f"Win/Loss/BE : {d['wins']} / {d['losses']} / {d['be']}\n"
        f"BEP/SL+     : {d['sl_plus']}\n"
        f"Winrate     : {d['win_rate']:.1f}%\n"
        f"Avg R       : {expectancy:+.2f}R\n"
        f"Total R     : {d['total_r']:+.2f}R\n"
        f"Max DD      : {d['max_drawdown_r']:.2f}R\n"
        f"{pnl_label:<12}: ${d['total_dollar']:+.2f}\n"
        f"ProfitFact. : {d['pf']:.2f}\n"
        f"\nPair\n"
        f"Best        : {best_pair_s}\n"
        f"Worst       : {worst_pair_s}\n"
        f"\nEntry Path\n"
        f"{_format_group_perf(d['path_perf'], max_items=4)}"
    )

def build_risk_text():
    risk = {
        "fixed_notional_usdt": FIXED_NOTIONAL_USDT,
        "leverage": LEVERAGE,
        "max_concurrent_trades": MAX_CONCURRENT_TRADES,
        "max_same_pair_open": MAX_SAME_PAIR_OPEN,
        "daily_loss_limit_r": DAILY_LOSS_LIMIT_R,
    }
    return (
        _format_risk_settings(risk, "RISK SETTINGS")
        + "\n\nSystem safety\n"
        + f"Entry state   : {_entry_status_text()}\n"
        + f"Dynamic pairs : {_yes_no(ENABLE_DYNAMIC_PAIRS)}\n"
        + f"Min volume    : ${MIN_PAIR_VOLUME_USDT:,.0f}\n"
        + f"Time filter   : {_yes_no(ENABLE_TIME_FILTER)}\n"
        + f"Startup audit : {_yes_no(ENABLE_STARTUP_AUDIT)}\n"
        + f"Orphan audit  : {_yes_no(ENABLE_ORPHAN_ORDER_AUDIT)}"
    )

def _fmt_shadow_price(value):
    try:
        return fmt_price(float(value))
    except Exception:
        return "?"

def _fmt_shadow_age(ts):
    if not ts:
        return "n/a"
    age_min = max(0, int((now_ms() - int(ts)) / 60000))
    if age_min < 60:
        return f"{age_min}m"
    age_h = age_min / 60
    if age_h < 48:
        return f"{age_h:.1f}h"
    return f"{age_h / 24:.1f}d"

def _shadow_status_label(status):
    labels = {
        "SHADOW_OPEN": "OPEN",
        "SHADOW_WIN": "WIN",
        "SHADOW_LOSS": "LOSS",
        "SHADOW_TIMEOUT": "TIMEOUT",
    }
    return labels.get(status, status or "?")


def _shadow_performance_metrics(trades):
    closed = sorted(
        [
            t for t in trades
            if t.get("status") in ("SHADOW_WIN", "SHADOW_LOSS")
            and isinstance(t.get("result_R"), (int, float))
        ],
        key=lambda t: (t.get("closed_at") or t.get("timestamp") or 0),
    )
    results = [float(t.get("result_R", 0) or 0) for t in closed]
    gross_profit = sum(value for value in results if value > 0)
    gross_loss = abs(sum(value for value in results if value < 0))
    equity = 0.0
    peak = 0.0
    max_drawdown = 0.0
    for value in results:
        equity += value
        peak = max(peak, equity)
        max_drawdown = max(max_drawdown, peak - equity)
    if gross_loss > 0:
        profit_factor = gross_profit / gross_loss
    elif gross_profit > 0:
        profit_factor = math.inf
    else:
        profit_factor = 0.0
    return {
        "closed": closed,
        "count": len(closed),
        "wins": sum(1 for value in results if value > 0),
        "total_r": sum(results),
        "avg_r": (sum(results) / len(results)) if results else 0.0,
        "profit_factor": profit_factor,
        "max_drawdown_r": max_drawdown,
    }


def build_shadow_command_text(trades_source=None, title="SHADOW SIGNAL"):
    if trades_source is None:
        data = load_json(SHADOW_TRADES_PATH)
        trades = data if isinstance(data, list) else []
    else:
        trades = list(trades_source or [])

    c6_trades = [
        t for t in trades
        if _shadow_strategy_key(t) == "smart_money_c_v6"
    ]
    legacy_count = len(trades) - len(c6_trades)
    open_trades = [t for t in c6_trades if t.get("status") == "SHADOW_OPEN"]
    timeouts = [t for t in c6_trades if t.get("status") == "SHADOW_TIMEOUT"]
    metrics = _shadow_performance_metrics(c6_trades)
    closed = metrics["closed"]
    count = metrics["count"]
    wr = (metrics["wins"] / count * 100) if count else 0.0
    pf = metrics["profit_factor"]
    pf_text = "INF" if math.isinf(pf) else f"{pf:.2f}"

    if count < C6_FORWARD_MIN_CLOSED:
        decision = "COLLECTING - NOT APPROVED LIVE"
    elif (
        metrics["total_r"] > 0
        and pf > 1.20
        and metrics["max_drawdown_r"] <= 10.0
    ):
        decision = "CHECKPOINT PASS - MANUAL REVIEW REQUIRED"
    else:
        decision = "HOLD - FORWARD GATE FAILED"

    c_status = (
        f"ACTIVE C{SMART_MONEY_C_VERSION} FORWARD"
        if ENABLE_SMART_MONEY_C_SHADOW
        else "PAUSED"
    )
    lines = [
        f"{_command_header(title)}",
        "Mode        : SHADOW ONLY - NO ORDER",
        f"Status      : {c_status}",
        f"Progress    : {count} / {C6_FORWARD_MIN_CLOSED} closed",
        f"Open        : {len(open_trades)}",
        f"Timeout     : {len(timeouts)}",
        "",
        "C6 Forward Performance",
        f"Winrate     : {wr:.1f}% ({metrics['wins']}/{count})",
        f"Avg R       : {metrics['avg_r']:+.2f}R",
        f"Total R     : {metrics['total_r']:+.2f}R",
        f"ProfitFact. : {pf_text}",
        f"Max DD      : {metrics['max_drawdown_r']:.2f}R",
        f"Keputusan   : {decision}",
    ]

    if not c6_trades:
        lines.extend(["", "Belum ada setup C6 forward yang tercatat."])

    recent = sorted(c6_trades, key=lambda t: t.get("timestamp", 0), reverse=True)[:5]
    lines.append("")
    lines.append("C6 Data Terbaru")
    if not recent:
        lines.append("n/a")
    for i, t in enumerate(recent, 1):
        r_val = t.get("result_R")
        r_s = f" | R {float(r_val):+.2f}" if isinstance(r_val, (int, float)) else ""
        lines.append(
            f"{i}. {t.get('pair', '?')} {t.get('bias', '?')} | {_shadow_status_label(t.get('status'))}{r_s}\n"
            f"   Entry {_fmt_shadow_price(t.get('entry'))} | SL {_fmt_shadow_price(t.get('sl'))} | TP {_fmt_shadow_price(t.get('tp'))}\n"
            f"   Umur {_fmt_shadow_age(t.get('timestamp'))}"
        )

    lines.append("")
    lines.append("Arsip Audit 04-08-2026")
    lines.append("C1 legacy: RETIRED - tidak merekam setup baru.")
    lines.append("A high-volume shadow: RETIRED - filter volume live dipertahankan.")
    if legacy_count:
        lines.append(f"Legacy tersisa di file aktif: {legacy_count} (menunggu migrasi arsip).")
    lines.append("Laporan ini hanya tampil saat /shadow diminta.")
    return "\n".join(lines)

def _d1_safe_float(value):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None

def _d1_safe_int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None

def _d1_wib_time(timestamp_ms, date_only=False):
    timestamp_ms = _d1_safe_int(timestamp_ms)
    if timestamp_ms is None or timestamp_ms <= 0:
        return "n/a"
    try:
        value = datetime.fromtimestamp(
            timestamp_ms / 1000,
            timezone(timedelta(hours=7)),
        )
    except (OSError, OverflowError, ValueError):
        return "n/a"
    return value.strftime("%d-%m-%Y" if date_only else "%d-%m-%Y %H:%M WIB")

def _d1_age(timestamp_ms, current_ms):
    timestamp_ms = _d1_safe_int(timestamp_ms)
    current_ms = _d1_safe_int(current_ms)
    if timestamp_ms is None or current_ms is None:
        return "n/a"
    age_min = max(0, int((current_ms - timestamp_ms) / 60000))
    if age_min < 60:
        return f"{age_min}m"
    age_hours = age_min / 60
    if age_hours < 48:
        return f"{age_hours:.1f}h"
    return f"{age_hours / 24:.1f}d"

def _d1_format_r(value):
    return "n/a" if value is None else f"{value:+.3f}R"

def _d1_format_pf(value):
    if value is None:
        return "n/a"
    if math.isinf(value):
        return "INF"
    return f"{value:.3f}"

def _d1_shadow_metrics(state):
    raw_trades = state.get("closed_trades", [])
    if not isinstance(raw_trades, list):
        raw_trades = []
        integrity_ok = False
    else:
        integrity_ok = True

    seen_ids = set()
    ordered_values = []
    funding_values = []
    recent = []
    for trade in raw_trades:
        if not isinstance(trade, dict):
            integrity_ok = False
            continue
        trade_id = str(trade.get("trade_id", "")).strip()
        exit_time = _d1_safe_int(trade.get("exit_time"))
        stress_r = _d1_safe_float(trade.get("observed_stress_net_R"))
        funding_r = _d1_safe_float(trade.get("observed_funding_R"))
        if (
            not trade_id
            or trade_id in seen_ids
            or exit_time is None
            or stress_r is None
            or funding_r is None
        ):
            integrity_ok = False
            continue
        seen_ids.add(trade_id)
        ordered_values.append((exit_time, stress_r))
        funding_values.append(funding_r)
        recent.append(trade)

    ordered_values.sort(key=lambda item: item[0])
    values = [value for _, value in ordered_values]
    total_r = sum(values) if values else None
    average_r = total_r / len(values) if values else None
    gains = sum(value for value in values if value > 0)
    losses = abs(sum(value for value in values if value < 0))
    if not values:
        profit_factor = None
    elif losses == 0:
        profit_factor = float("inf") if gains > 0 else 0.0
    else:
        profit_factor = gains / losses

    equity = 0.0
    peak = 0.0
    max_drawdown = 0.0
    for value in values:
        equity += value
        peak = max(peak, equity)
        max_drawdown = max(max_drawdown, peak - equity)

    monitor_started_at = _d1_safe_int(state.get("monitor_started_at"))
    last_poll_at = _d1_safe_int(state.get("last_poll_at"))
    if not monitor_started_at or not last_poll_at:
        integrity_ok = False

    current_position = state.get("current_position")
    if current_position is not None:
        if not isinstance(current_position, dict):
            integrity_ok = False
        else:
            required_position_values = (
                _d1_safe_int(current_position.get("entry_time")),
                _d1_safe_float(current_position.get("entry")),
                _d1_safe_float(current_position.get("initial_stop")),
                _d1_safe_float(current_position.get("active_stop")),
            )
            if any(value is None for value in required_position_values):
                integrity_ok = False

    reconciliation = state.get("funding_reconciliation")
    metadata_ok = isinstance(reconciliation, dict)
    unreconciled = (
        _d1_safe_int(reconciliation.get("unreconciled_trades"))
        if metadata_ok
        else None
    )
    funding_complete = bool(
        metadata_ok
        and unreconciled == 0
        and len(values) == len(raw_trades)
    )
    without_best = total_r - max(values) if values else None
    recent.sort(key=lambda row: int(row["exit_time"]), reverse=True)
    return {
        "closed": len(raw_trades),
        "valid_closed": len(values),
        "total_r": total_r,
        "average_r": average_r,
        "profit_factor": profit_factor,
        "max_drawdown_r": max_drawdown if values else None,
        "funding_r": sum(funding_values) if values else None,
        "without_best_r": without_best,
        "funding_complete": funding_complete,
        "unreconciled": unreconciled,
        "integrity_ok": integrity_ok,
        "recent": recent[:3],
    }

def _d1_worker_status(last_poll_at, current_ms):
    last_poll_at = _d1_safe_int(last_poll_at)
    if not last_poll_at:
        return "UNKNOWN"
    age_sec = max(0, (current_ms - last_poll_at) / 1000)
    if age_sec <= D1_SHADOW_HEALTHY_SEC:
        return "HEALTHY"
    if age_sec <= D1_SHADOW_DELAYED_SEC:
        return "DELAYED"
    return "STALE"

def build_d1_shadow_command_text(state_source=None, now_ms_value=None):
    state = load_json(D1_SHADOW_STATE_PATH) if state_source is None else state_source
    if not isinstance(state, dict):
        return (
            f"{_command_header('D1 FORWARD SHADOW')}\n"
            "Status      : STATE BELUM TERSEDIA\n"
            "Mode        : LONG ONLY / NO ORDER\n\n"
            "Worker D1 belum dapat dibaca. Hubungi admin untuk pemeriksaan.\n"
            "Command ini tidak mengakses API privat dan tidak membuat order."
        )
    if state.get("schema") != D1_SHADOW_SCHEMA:
        return (
            f"{_command_header('D1 FORWARD SHADOW')}\n"
            "Status      : STATE TIDAK VALID\n"
            "Mode        : LONG ONLY / NO ORDER\n\n"
            "Schema state tidak cocok. Data tidak ditampilkan agar tidak menyesatkan."
        )

    current_ms = int(now_ms_value if now_ms_value is not None else now_ms())
    metrics = _d1_shadow_metrics(state)
    worker_status = _d1_worker_status(state.get("last_poll_at"), current_ms)
    started_at = _d1_safe_int(state.get("monitor_started_at"))
    elapsed_days = (
        max(0.0, (current_ms - started_at) / (24 * 3600 * 1000))
        if started_at
        else 0.0
    )
    position = state.get("current_position")
    market_status = "LONG OPEN" if isinstance(position, dict) else "NEUTRAL"
    metric_available = (
        metrics["valid_closed"] == metrics["closed"]
        and metrics["closed"] > 0
    )
    forward_ready = all([
        metrics["closed"] >= D1_FORWARD_MIN_TRADES,
        elapsed_days >= D1_FORWARD_MIN_DAYS,
        metrics["funding_complete"],
        metric_available,
        metrics["total_r"] > 0 if metric_available else False,
        metrics["profit_factor"] >= D1_FORWARD_MIN_PF if metric_available else False,
        metrics["max_drawdown_r"] <= D1_FORWARD_MAX_DD_R if metric_available else False,
        metrics["without_best_r"] > 0 if metric_available else False,
        metrics["integrity_ok"],
        worker_status == "HEALTHY",
    ])
    if not metrics["integrity_ok"]:
        decision = "HOLD - STATE CHECK NEEDED"
    elif worker_status in ("STALE", "UNKNOWN"):
        decision = "HOLD - WORKER STALE"
    elif forward_ready:
        decision = "READY FOR HUMAN REVIEW"
    else:
        decision = "COLLECTING FORWARD DATA"

    if metrics["funding_complete"]:
        funding_status = "COMPLETE"
    elif metrics["unreconciled"] is None:
        funding_status = "PENDING / UNKNOWN"
    else:
        funding_status = f"PENDING ({metrics['unreconciled']})"

    lines = [
        f"{_command_header('D1 FORWARD SHADOW')}",
        f"Spec        : D1 TSMOM 7/30/90 ({D1_TELEGRAM_COMMAND_VERSION})",
        "Mode        : LONG ONLY / NO ORDER",
        f"Worker      : {worker_status}",
        f"Market      : {market_status}",
        (
            f"Last poll   : {_d1_wib_time(state.get('last_poll_at'))}"
            f" ({_d1_age(state.get('last_poll_at'), current_ms)})"
        ),
        f"Last 4H     : {_d1_wib_time(state.get('last_closed_4h'))}",
        "",
        "Forward Gate",
        f"Trade       : {metrics['closed']} / {D1_FORWARD_MIN_TRADES}",
        f"Durasi      : {elapsed_days:.1f} / {D1_FORWARD_MIN_DAYS} hari",
        f"Funding     : {funding_status}",
        f"Integrity   : {'OK' if metrics['integrity_ok'] else 'CHECK'}",
        f"Keputusan   : {decision}",
        "",
        "Forward Performance",
        f"Closed      : {metrics['closed']}",
        f"Stress R    : {_d1_format_r(metrics['total_r'])}",
        f"Avg R       : {_d1_format_r(metrics['average_r'])}",
        f"ProfitFact. : {_d1_format_pf(metrics['profit_factor'])}",
        f"Max DD      : {_d1_format_r(metrics['max_drawdown_r'])}",
        f"Funding R   : {_d1_format_r(metrics['funding_r'])}",
        f"Tanpa best  : {_d1_format_r(metrics['without_best_r'])}",
        "",
        "Posisi D1",
    ]

    if isinstance(position, dict):
        signal_returns = position.get("signal_returns", {})
        return_parts = []
        if isinstance(signal_returns, dict):
            for window in ("7", "30", "90"):
                value = _d1_safe_float(signal_returns.get(window))
                if value is not None:
                    return_parts.append(f"{window}d {value * 100:+.2f}%")
        lines.extend([
            f"Side        : {str(position.get('side', 'LONG')).upper()}",
            f"Entry       : {_fmt_shadow_price(position.get('entry'))}",
            f"SL awal     : {_fmt_shadow_price(position.get('initial_stop'))}",
            f"SL aktif    : {_fmt_shadow_price(position.get('active_stop'))}",
            (
                f"Sejak       : {_d1_wib_time(position.get('entry_time'))}"
                f" ({_d1_age(position.get('entry_time'), current_ms)})"
            ),
            f"Momentum    : {' | '.join(return_parts) if return_parts else 'n/a'}",
        ])
    else:
        lines.append("Tidak ada posisi shadow aktif.")

    if metrics["recent"]:
        lines.extend(["", "3 Close Terakhir"])
        for trade in metrics["recent"]:
            reason = str(trade.get("exit_reason", "EXIT")).replace("_", " ")
            result_r = _d1_safe_float(trade.get("observed_stress_net_R"))
            funding_r = _d1_safe_float(trade.get("observed_funding_R"))
            lines.append(
                f"{_d1_wib_time(trade.get('exit_time'), date_only=True)} | "
                f"{reason} | {_d1_format_r(result_r)} | fund {_d1_format_r(funding_r)}"
            )

    lines.extend([
        "",
        "Riset global BTCUSDT 4H, bukan trade akun Anda.",
        "Tidak ada aktivasi live otomatis; hasil akhir wajib ditinjau manusia.",
    ])
    return "\n".join(lines)

def build_health_text(api_key=None, api_secret=None):
    checks = []

    checks.append(("Config file", "OK" if os.path.exists(CONFIG_PATH) else "MISSING"))
    checks.append(("Telegram token", "OK" if TELEGRAM_BOT_TOKEN else "MISSING"))
    checks.append(("Telegram chat ID", "OK" if TARGET_CHAT_ID else "MISSING"))
    checks.append(("Binance API key", "OK" if api_key else "MISSING"))
    checks.append(("Binance API secret", "OK" if api_secret else "MISSING"))

    journal_status = "OK"
    try:
        with journal_lock:
            load_journal()
            journal_count = len(journal)
    except Exception as e:
        journal_status = f"FAIL ({str(e)[:40]})"
        journal_count = 0
    checks.append(("Journal", f"{journal_status} ({journal_count} records)"))

    heartbeat_age = "n/a"
    try:
        if os.path.exists(HEARTBEAT_PATH):
            age_sec = int(time.time() - os.path.getmtime(HEARTBEAT_PATH))
            heartbeat_age = f"{age_sec}s ago"
    except Exception:
        heartbeat_age = "unknown"
    checks.append(("Heartbeat", heartbeat_age))

    if api_key and api_secret and not SIMULATE:
        try:
            acct = get_account_info(api_key, api_secret)
            checks.append(("Binance account", "OK" if acct else "EMPTY"))
        except Exception as e:
            checks.append(("Binance account", f"FAIL ({str(e)[:40]})"))

        live_positions = _get_all_positions(api_key, api_secret)
        if live_positions is None:
            checks.append(("Live positions", "FAIL"))
        else:
            checks.append(("Live positions", f"OK ({_live_position_count(live_positions)} open)"))

        live_orders = _get_all_open_orders(api_key, api_secret)
        if live_orders is None:
            checks.append(("Open orders", "FAIL"))
        else:
            order_count = len([k for k in live_orders if not str(k).startswith("__meta_")])
            checks.append(("Open orders", f"OK ({order_count})"))
    else:
        checks.append(("Binance live check", "SKIP (simulate/no API)"))

    lines = [f"{name:<18}: {status}" for name, status in checks]
    return (
        f"{_command_header('HEALTH CHECK')}\n"
        f"Mode              : {_mode_text()}\n"
        f"Entry             : {_entry_status_text()}\n"
        f"Config path       : {CONFIG_PATH}\n"
        "\nChecks\n"
        + "\n".join(lines)
    )

def build_hybrid_ai_status_text():
    try:
        engine = get_hybrid_ai_engine()
        summary = engine.summary()
    except Exception as exc:
        return (
            f"{_command_header('HYBRID AI STATUS')}\n"
            f"State       : ERROR\n"
            f"Detail      : {str(exc)[:160]}\n\n"
            "AI approval dan live otomatis terkunci."
        )
    live_gate = summary.get("live_gate", {})
    statuses = summary.get("statuses", {})
    accepted = statuses.get("SHADOW_ACCEPTED", 0)
    skipped = statuses.get("SHADOW_SKIPPED", 0) + statuses.get("AI_ERROR", 0)
    return (
        f"{_command_header('HYBRID AI STATUS')}\n"
        f"Enabled     : {_yes_no(summary.get('enabled'))}\n"
        f"Mode        : {summary.get('mode')}\n"
        f"Model       : {summary.get('model')}\n"
        f"OpenAI key  : {'READY' if summary.get('api_key_present') else 'MISSING'}\n"
        f"Live config : {'UNLOCKED' if summary.get('allow_live') else 'LOCKED'}\n"
        f"Replay gate : {'PASSED' if live_gate.get('passed') else 'LOCKED'}\n"
        f"Pending     : {summary.get('pending', 0)}\n"
        f"Shadow      : {accepted} accepted / {skipped} skipped-error\n"
        f"Total review: {summary.get('total', 0)}\n\n"
        "AI hanya menjadi reviewer. Side, harga, SL, TP, quantity, dan risk tetap ditentukan mesin deterministic."
    )

def build_hybrid_ai_pending_text():
    try:
        engine = get_hybrid_ai_engine()
        pending = engine.store.pending(now_ms())
    except Exception as exc:
        return f"{_command_header('AI PENDING')}\nGagal membaca state: {str(exc)[:160]}"
    if not pending:
        return f"{_command_header('AI PENDING')}\nTidak ada proposal aktif."
    lines = []
    for proposal in pending[:10]:
        candidate = proposal.get("candidate", {})
        decision = proposal.get("decision", {})
        remaining = max(0, int((int(proposal.get("expires_at_ms", 0)) - now_ms()) / 1000))
        lines.append(
            f"{proposal.get('id')} | {candidate.get('pair')} {candidate.get('side')} | "
            f"conf {float(decision.get('confidence', 0)):.0%} | {remaining}s"
        )
    return (
        f"{_command_header('AI PENDING')}\n"
        + "\n".join(lines)
        + "\n\nGunakan /ai_approve ID atau /ai_reject ID."
    )

def build_live_ai_market_text():
    try:
        summary = get_live_ai_market_engine().summary()
    except Exception as exc:
        return (
            f"{_command_header('OPENAI LIVE MARKET') }\n"
            f"State       : ERROR\n"
            f"Detail      : {str(exc)[:160]}\n\n"
            "Tidak ada order yang dikirim."
        )
    latest = summary.get("latest") if isinstance(summary.get("latest"), dict) else None
    counts = summary.get("decision_counts", {})
    setup_stats = summary.get("setup_stats", {})
    active_setup = (
        summary.get("active_setup")
        if isinstance(summary.get("active_setup"), dict)
        else None
    )
    base = (
        f"{_command_header('OPENAI LIVE MARKET')}\n"
        f"Mode        : RESEARCH SHADOW ONLY\n"
        f"Enabled     : {_yes_no(summary.get('enabled'))}\n"
        f"Model       : {summary.get('model')}\n"
        f"Prompt      : {summary.get('prompt_version') or summary.get('prompt_id')}\n"
        f"OpenAI key  : {'READY' if summary.get('openai_key_present') else 'MISSING'}\n"
        f"Binance     : "
        f"{'VERIFIED' if latest and latest.get('binance_auth_verified') else 'NOT VERIFIED'}\n"
        f"Order access: LOCKED\n"
        f"Total scan  : {summary.get('scan_count', 0)}\n"
        f"Decision    : {counts.get('SETUP', 0)} setup / "
        f"{counts.get('NO_TRADE', 0)} no-trade\n"
        f"Shadow      : {setup_stats.get('closed', 0)} closed | "
        f"{float(setup_stats.get('total_r', 0) or 0):+.2f}R"
    )
    if not latest:
        error = summary.get("last_error")
        detail = f"\nError       : {str(error)[:160]}" if error else ""
        return (
            base
            + detail
            + "\n\nBelum ada snapshot live yang berhasil dianalisis. "
              "Worker akan mencoba pada jadwal berikutnya."
        )
    if latest.get("feature_set") != summary.get("feature_set"):
        return (
            base
            + "\n\nHasil dari kontrak data lama disembunyikan karena tidak lolos "
              "standar grounding harga terbaru. Menunggu scan baru."
        )
    decision = latest.get("decision") if isinstance(latest.get("decision"), dict) else {}
    decision_ms = int(latest.get("decision_time_ms", 0) or 0)
    if decision_ms:
        decision_time = datetime.fromtimestamp(
            decision_ms / 1000, timezone(timedelta(hours=7))
        ).strftime("%d-%m-%Y %H:%M WIB")
    else:
        decision_time = "n/a"
    evidence = decision.get("evidence") if isinstance(decision.get("evidence"), list) else []
    risk_flags = (
        decision.get("risk_flags") if isinstance(decision.get("risk_flags"), list) else []
    )
    evidence_text = "\n".join(f"- {item}" for item in evidence[:4]) or "- Tidak ada"
    risk_text = "\n".join(f"- {item}" for item in risk_flags[:4]) or "- Tidak ada"
    usage = latest.get("openai", {}).get("usage", {}) if isinstance(latest.get("openai"), dict) else {}
    token_total = usage.get("total_tokens", "n/a") if isinstance(usage, dict) else "n/a"
    validated = (
        latest.get("validated_plan")
        if isinstance(latest.get("validated_plan"), dict)
        else None
    )
    context = (
        latest.get("market_context")
        if isinstance(latest.get("market_context"), dict)
        else None
    )
    market_text = ""
    if context:
        market_text = (
            "\n\nReferensi market (Binance)\n"
            f"Harga close : {fmt_price(context.get('last_close'))} USDT\n"
            f"Range 24h   : {fmt_price(context.get('range_low_24h'))} - "
            f"{fmt_price(context.get('range_high_24h'))} USDT "
            f"(posisi {float(context.get('range_position_24h_pct', 0) or 0):.2f}%)\n"
            f"Range 7d    : {fmt_price(context.get('range_low_7d'))} - "
            f"{fmt_price(context.get('range_high_7d'))} USDT "
            f"(posisi {float(context.get('range_position_7d_pct', 0) or 0):.2f}%)"
        )
    setup_text = ""
    if decision.get("action") == "SETUP" and validated:
        setup_text = (
            "\n\nSetup P6 tervalidasi\n"
            f"Basis range : {decision.get('range_basis')}\n"
            f"Range AI    : {fmt_price(decision.get('range_low'))} - "
            f"{fmt_price(decision.get('range_high'))}\n"
            f"Entry zone  : {fmt_price(decision.get('entry_zone_low'))} - "
            f"{fmt_price(decision.get('entry_zone_high'))}\n"
            f"Trigger     : {str(decision.get('entry_trigger', 'n/a')).replace('_', ' ')}\n"
            f"Invalidasi  : {fmt_price(decision.get('invalidation_level'))}\n"
            f"SL          : {fmt_price(decision.get('stop_loss'))}\n"
            f"TP1         : {fmt_price(decision.get('take_profit_1'))}\n"
            f"TP2         : {fmt_price(decision.get('take_profit_2'))}\n"
            f"R:R biaya   : {float(validated.get('cost_adjusted_rr_tp1', 0)):.2f} / "
            f"{float(validated.get('cost_adjusted_rr_tp2', 0)):.2f}\n"
            f"Expiry      : {decision.get('expiry_hours')} jam"
        )
    shadow_text = ""
    if active_setup:
        filled = float(active_setup.get("entry_price", 0) or 0)
        entry_line = f"\nFill shadow : {fmt_price(filled)}" if filled > 0 else ""
        shadow_text = (
            "\n\nLifecycle shadow\n"
            f"ID / Status : {active_setup.get('id')} / {active_setup.get('status')}"
            f"{entry_line}\n"
            f"TP1 hit     : {_yes_no(active_setup.get('tp1_hit'))}"
        )
    return (
        base
        + "\n\nAnalisis terbaru\n"
        + f"Waktu       : {decision_time}\n"
        + f"Action      : {decision.get('action', 'n/a')}\n"
        + f"Pair / Side : {decision.get('pair', 'n/a')} / {decision.get('side', 'n/a')}\n"
        + f"Regime      : {decision.get('regime', 'n/a')}\n"
        + f"Confidence  : {float(decision.get('confidence', 0) or 0):.0%}\n"
        + f"Quality     : {decision.get('setup_quality', 0)}/100\n"
        + f"Token       : {token_total}"
        + market_text
        + setup_text
        + shadow_text
        + "\n\n"
        + "Evidence\n"
        + evidence_text
        + "\n\nRisk flags\n"
        + risk_text
        + "\n\nThesis\n"
        + str(decision.get("thesis", "n/a"))
        + "\n\nCatatan: setup P6 ini belum memiliki edge historis yang valid. "
          "Semua level dan lifecycle hanya shadow; tidak ada order Binance."
    )

def handle_hybrid_ai_command(cmd, parts, chat_id, api_key, api_secret):
    if not is_admin_chat(chat_id):
        return f"{_command_header('ACCESS DENIED')}\nCommand Hybrid AI hanya untuk admin."
    try:
        engine = get_hybrid_ai_engine()
        if cmd == "/ai_status":
            return build_hybrid_ai_status_text()
        if cmd == "/ai_pending":
            return build_hybrid_ai_pending_text()
        if cmd == "/ai_mode":
            if len(parts) < 2:
                return (
                    f"{_command_header('AI MODE')}\n"
                    "Format: /ai_mode shadow|approval|live\n"
                    "AI_LIVE tetap membutuhkan config dan replay gate."
                )
            aliases = {
                "shadow": "AI_SHADOW",
                "approval": "AI_APPROVAL",
                "live": "AI_LIVE",
            }
            requested = aliases.get(parts[1].lower())
            if not requested:
                return f"{_command_header('AI MODE')}\nMode harus shadow, approval, atau live."
            mode = engine.set_mode(requested)
            log_line(f"hybrid_ai_mode_changed mode={mode} by={chat_id}")
            return (
                f"{_command_header('AI MODE')}\n"
                f"Mode aktif: {mode}\n\n"
                "Perubahan tersimpan atomik dan berlaku untuk kandidat berikutnya."
            )
        if cmd in ("/ai_approve", "/ai_reject"):
            if len(parts) < 2:
                return f"{_command_header('AI APPROVAL')}\nFormat: {cmd} PROPOSAL_ID"
            proposal_id = parts[1].upper()
            if cmd == "/ai_reject":
                proposal = engine.reject(proposal_id, str(chat_id))
                log_line(f"hybrid_ai_rejected id={proposal_id} by={chat_id}")
                return (
                    f"{_command_header('AI REJECTED')}\n"
                    f"ID: {proposal_id}\nStatus: {proposal.get('status')}\nTidak ada order yang dikirim."
                )
            engine.approve(proposal_id, str(chat_id))
            result = execute_hybrid_ai_proposal(proposal_id, api_key, api_secret)
            if result.get("success"):
                return (
                    f"{_command_header('AI EXECUTION')}\n"
                    f"ID     : {proposal_id}\n"
                    f"Status : {result.get('status')}\n"
                    "Risk dan harga telah divalidasi ulang sebelum eksekusi."
                )
            return (
                f"{_command_header('AI EXECUTION BLOCKED')}\n"
                f"ID     : {proposal_id}\n"
                f"Detail : {result.get('error', 'unknown')[:180]}\n"
                "Tidak ada retry order otomatis."
            )
    except (HybridAIError, HybridAIStateError, ValueError) as exc:
        return (
            f"{_command_header('HYBRID AI BLOCKED')}\n"
            f"Detail: {str(exc)[:180]}\n\n"
            "Tidak ada order yang dikirim."
        )
    except Exception as exc:
        log_line(f"hybrid_ai_command_error cmd={cmd} {str(exc)[:300]}")
        return (
            f"{_command_header('HYBRID AI ERROR')}\n"
            "Command gagal secara aman. Tidak ada order yang dikirim."
        )
    return None

def build_help_text():
    return (
        f"{_command_header('COMMAND CENTER')}\n"
        "Gunakan command ini untuk memantau dan mengontrol bot.\n"
        "\nMonitoring\n"
        "/register  - daftar sebagai calon user\n"
        "/myaccount - lihat status akun\n"
        "/license   - lihat status license\n"
        "/onboarding - panduan setup client\n"
        "/api_guide - cara membuat API Binance\n"
        "/setup_api - setup Binance API aman\n"
        "/api_status - cek status API\n"
        "/delete_api - hapus API dari config bot\n"
        "/status    - status bot dan mode entry\n"
        "/health    - cek koneksi dan kesiapan bot\n"
        "/positions - posisi live atau journal aktif\n"
        "/orders    - open orders Binance\n"
        "/report    - performa hari ini\n"
        "/weekly    - performa minggu ini\n"
        "/monthly   - performa bulan ini\n"
        "/alltime   - performa keseluruhan\n"
        "/shadow    - pantau shadow signal Jalur C\n"
        "/d1shadow  - pantau Strategy D1 forward shadow\n"
        "/ai_status - status Hybrid AI Engine\n"
        "/ai_market - analisis market live OpenAI (shadow)\n"
        "/ai_pending - proposal AI menunggu approval\n"
        "\nControl\n"
        "/pause     - hentikan entry baru\n"
        "/resume    - aktifkan entry baru\n"
        "/risk      - lihat/atur risk management\n"
        "/risk help - panduan setting risk\n"
        "/ai_mode shadow|approval|live - mode Hybrid AI (admin)\n"
        "/ai_approve ID - setujui proposal AI (admin)\n"
        "/ai_reject ID - tolak proposal AI (admin)\n"
        "/cancel_setup - batalkan setup API\n"
        "/help      - tampilkan menu ini\n"
        "\nAdmin\n"
        "/admin_users\n"
        "/admin_approve CHAT_ID [days]\n"
        "/admin_revoke CHAT_ID [reason]\n"
        "/admin_extend CHAT_ID days\n"
        "\nCatatan: /pause tidak menutup posisi. Bot tetap monitor posisi existing."
    )

def handle_telegram_command(text, api_key=None, api_secret=None, chat_id=None, profile=None, message_id=None):
    parts = (text or "").strip().split()
    if not parts:
        return None
    cmd = parts[0].lower()
    if "@" in cmd:
        cmd = cmd.split("@", 1)[0]
    if cmd in ("/start", "/help"):
        return build_help_text()
    if cmd == "/register":
        return build_register_text(chat_id, profile)
    if cmd == "/myaccount":
        return build_myaccount_text(chat_id)
    if cmd == "/license":
        return build_license_text(chat_id)
    if cmd == "/onboarding":
        return build_onboarding_text()
    if cmd == "/api_guide":
        return build_api_guide_text()
    if cmd == "/setup_api":
        return build_setup_api_text(chat_id, profile)
    if cmd == "/api_key":
        if len(parts) < 2:
            return f"{_command_header('API KEY')}\nFormat: /api_key API_KEY_ANDA"
        return build_api_key_text(chat_id, parts[1])
    if cmd == "/api_secret":
        if len(parts) < 2:
            return f"{_command_header('API SECRET')}\nFormat: /api_secret API_SECRET_ANDA"
        return build_api_secret_text(chat_id, parts[1])
    if cmd == "/api_status":
        return build_api_status_text(chat_id)
    if cmd == "/delete_api":
        return build_delete_api_text(chat_id)
    if cmd == "/cancel_setup":
        return build_cancel_setup_text(chat_id)

    if cmd == "/ai_market":
        if not is_admin_chat(chat_id):
            return f"{_command_header('ACCESS DENIED')}\nCommand AI market hanya untuk admin."
        return build_live_ai_market_text()

    if cmd in ("/ai_status", "/ai_pending", "/ai_mode", "/ai_approve", "/ai_reject"):
        return handle_hybrid_ai_command(
            cmd, parts, chat_id, api_key, api_secret
        )

    if cmd.startswith("/admin_") or cmd in ("/admin_users", "/admin_pending"):
        if not is_admin_chat(chat_id):
            return f"{_command_header('ACCESS DENIED')}\nCommand ini hanya untuk admin."
        if cmd == "/admin_users":
            return build_admin_users_text()
        if cmd == "/admin_pending":
            return build_admin_users_text(status_filter="pending")
        if cmd == "/admin_approve":
            return build_admin_approve_text(parts)
        if cmd == "/admin_revoke":
            return build_admin_revoke_text(parts)
        if cmd == "/admin_extend":
            return build_admin_extend_text(parts)

    client_read_commands = {
        "/status", "/health", "/positions", "/orders", "/report", "/weekly",
        "/monthly", "/alltime", "/shadow", "/d1shadow", "/risk"
    }
    client_control_commands = {"/pause", "/resume"}
    if cmd in client_read_commands and not is_admin_chat(chat_id):
        if cmd == "/status":
            return build_managed_status_text(chat_id)
        if cmd == "/health":
            return build_managed_health_text(chat_id)
        if cmd == "/positions":
            return build_managed_positions_text(chat_id)
        if cmd == "/orders":
            return build_managed_orders_text(chat_id)
        if cmd == "/report":
            return build_managed_report_text(chat_id, "today")
        if cmd == "/weekly":
            return build_managed_report_text(chat_id, "week")
        if cmd == "/monthly":
            return build_managed_report_text(chat_id, "month")
        if cmd == "/alltime":
            return build_managed_report_text(chat_id, "alltime")
        if cmd == "/shadow":
            return build_managed_shadow_text(chat_id)
        if cmd == "/d1shadow":
            return build_managed_d1_shadow_text(chat_id)
        if cmd == "/risk":
            return handle_managed_risk_command(chat_id, parts)

    if cmd in client_control_commands and not is_admin_chat(chat_id):
        return (
            f"{_command_header('CONTROL PENDING')}\n"
            "Pause/resume worker pribadi belum diaktifkan dari Telegram client.\n"
            "Untuk sementara hubungi admin agar worker dihentikan/dijalankan."
        )

    if cmd == "/status":
        return build_status_text(api_key, api_secret)
    if cmd == "/health":
        return build_health_text(api_key, api_secret)
    if cmd == "/positions":
        return build_positions_text(api_key, api_secret)
    if cmd == "/orders":
        return build_orders_text(api_key, api_secret)
    if cmd == "/report":
        with journal_lock:
            load_journal()
        return build_report_text("today")
    if cmd == "/weekly":
        with journal_lock:
            load_journal()
        return build_report_text("week")
    if cmd == "/monthly":
        with journal_lock:
            load_journal()
        return build_report_text("month")
    if cmd == "/alltime":
        with journal_lock:
            load_journal()
        return build_report_text("alltime")
    if cmd == "/shadow":
        return build_shadow_command_text()
    if cmd == "/d1shadow":
        return build_d1_shadow_command_text()
    if cmd == "/pause":
        set_entry_paused(True, "telegram")
        return (
            f"{_command_header('ENTRY PAUSED')}\n"
            "Status entry baru: PAUSED\n"
            "\nBot tidak akan membuka posisi baru.\n"
            "Posisi existing tetap dimonitor, termasuk sync, audit, report, SL/TP, dan breakeven monitor."
        )
    if cmd == "/resume":
        set_entry_paused(False, "telegram")
        return (
            f"{_command_header('ENTRY ACTIVE')}\n"
            "Status entry baru: ACTIVE\n"
            "\nBot kembali mencari setup sesuai rule strategi.\n"
            "Risk control, max position, dan daily kill switch tetap aktif."
        )
    if cmd == "/risk":
        if len(parts) == 1:
            return build_risk_text()
        return _handle_risk_command(parts, CONFIG_PATH, managed=False)
    return None

def _telegram_command_worker(api_key=None, api_secret=None):
    if not TELEGRAM_BOT_TOKEN:
        log_line("telegram_command_worker_skip: token not set")
        return
    state = load_json(REPORT_STATE_PATH) or {}
    offset = int(state.get("telegram_update_offset", 0) or 0)
    log_line("telegram_command_worker_started")

    def dispatch_command(chat_id, text, profile, message_id=None):
        try:
            first = (text or "").strip().split(maxsplit=1)[0].lower()
            if "@" in first:
                first = first.split("@", 1)[0]
            if first in ("/api_key", "/api_secret"):
                if delete_telegram_message(chat_id, message_id):
                    log_line(f"telegram_sensitive_message_deleted chat_id={chat_id} command={first}")
                else:
                    log_line(f"telegram_sensitive_message_delete_failed chat_id={chat_id} command={first}")
            response = handle_telegram_command(
                text, api_key, api_secret,
                chat_id=chat_id,
                profile=profile,
                message_id=message_id,
            )
            if response:
                send_telegram_to_chat(chat_id, response)
        except Exception as e:
            log_line(f"telegram_command_dispatch_err chat_id={chat_id} {e}")
            try:
                send_telegram_to_chat(
                    chat_id,
                    f"{_command_header('COMMAND ERROR')}\n"
                    "Command sedang gagal diproses. Coba ulang sebentar lagi.\n"
                    "Jika command membutuhkan Binance, kemungkinan koneksi exchange sedang lambat."
                )
            except Exception:
                pass

    while not _shutdown_event.is_set():
        try:
            result = telegram_api(
                "getUpdates",
                {"offset": offset, "timeout": 25, "allowed_updates": ["message"]},
                timeout=35,
            )
            updates = result.get("result", []) if result else []
            for upd in updates:
                offset = max(offset, int(upd.get("update_id", 0)) + 1)
                msg = upd.get("message") or {}
                chat = msg.get("chat") or {}
                chat_id = str(chat.get("id", ""))
                text = msg.get("text", "")
                if not text.startswith("/"):
                    continue
                profile = msg.get("from") or chat
                threading.Thread(
                    target=dispatch_command,
                    args=(chat_id, text, profile, msg.get("message_id")),
                    daemon=True,
                    name=f"telegram-command-{chat_id}",
                ).start()

            if updates:
                state = load_json(REPORT_STATE_PATH) or {}
                state["telegram_update_offset"] = offset
                save_json_atomic(REPORT_STATE_PATH, state)
        except Exception as e:
            log_line(f"telegram_command_worker_err {e}")
            interruptible_sleep(10)

def start_telegram_command_thread(api_key=None, api_secret=None):
    t = threading.Thread(
        target=_telegram_command_worker,
        args=(api_key, api_secret),
        daemon=True,
        name="telegram-commands"
    )
    t.start()

def load_journal():
    global journal
    j = load_json(JOURNAL_PATH)
    journal = j if isinstance(j, list) else []

def save_journal():
    save_json_atomic(JOURNAL_PATH, journal)

def backup_journal(reason="manual", min_interval_sec=0):
    global last_journal_backup_at

    if not os.path.exists(JOURNAL_PATH):
        return None

    now_s = time.time()
    reason_key = str(reason)
    if min_interval_sec and now_s - last_journal_backup_at.get(reason_key, 0.0) < min_interval_sec:
        return None

    try:
        os.makedirs(JOURNAL_BACKUP_DIR, exist_ok=True)
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        safe_reason = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(reason)).strip("_") or "backup"
        dst = os.path.join(JOURNAL_BACKUP_DIR, f"journal_v3_{ts}_{safe_reason}.json")
        shutil.copy2(JOURNAL_PATH, dst)
        last_journal_backup_at[reason_key] = now_s
        log_line(f"journal_backup_created reason={safe_reason} path={dst}")
        return dst
    except Exception as e:
        log_line(f"journal_backup_err reason={reason} {e}")
        return None

# ---------------------- [FIX-R2] RESUME PENDING POLLERS ----------------------
def _resume_pending_pollers(api_key, api_secret):
    """
    [FIX-R2] Resume poll threads untuk PENDING trade yang tersisa dari sesi sebelumnya.
    Poll thread adalah daemon thread — otomatis mati saat bot shutdown.
    Tanpa fungsi ini, PENDING trade tidak pernah di-update ke OPEN/CANCELLED
    karena tidak ada yang me-poll Binance API untuk order mereka.

    Dipanggil satu kali di startup, setelah startup_sync selesai.
    """
    with journal_lock:
        pending = [t for t in journal if t.get("status") == "PENDING"]

    if not pending:
        log_line("resume_pollers: no pending trades found")
        return

    log_line(f"resume_pollers: {len(pending)} PENDING trade(s) — starting poll threads")
    exchange_info = get_exchange_info_cached(api_key, api_secret)

    resumed = []
    for trade in pending:
        pair          = trade.get("pair", "")
        bias          = trade.get("side", "LONG")
        sl_str        = str(trade.get("sl", ""))
        tp_str        = str(trade.get("tp", ""))
        qty_str       = str(trade.get("qty", ""))
        position_side = trade.get("position_side")
        step, tick, _, _ = (
            get_symbol_filters(exchange_info, pair)
            if exchange_info else (None, None, 0, 0)
        )

        t = threading.Thread(
            target=_poll_order_until_filled,
            args=(pair, trade, sl_str, tp_str, qty_str,
                  position_side, bias, api_key, api_secret, tick),
            daemon=True,
            name=f"poller-resume-{pair}"
        )
        t.start()
        resumed.append(pair)
        log_line(f"resume_poller_started {pair} order_id={trade.get('entry_order_id')}")

    if resumed:
        send_telegram(
            f"⚡ [{BOT_TAG}] Restart — {len(resumed)} PENDING order dilanjutkan polling:\n"
            + ", ".join(resumed)
        )

# ---------------------- [FIX-R5] STARTUP DAILY REPORT ----------------------
def send_startup_daily_report():
    """
    [FIX-R5] Kirim rekap hari ini saat restart — SELALU, tanpa cek last_report_date.
    Tujuan: user dapat snapshot terkini begitu bot restart, tidak menunggu EOD.

    Setelah kirim, reset last_report_date = None agar send_daily_report()
    masih bisa mengirim EOD report di akhir hari (tidak terblokir).
    """
    tz       = timezone(timedelta(hours=7))
    today    = datetime.now(tz).date().isoformat()
    start_ms = int(
        datetime.now(tz).replace(hour=0, minute=0, second=0, microsecond=0)
        .timestamp() * 1000
    )
    today_trades = [t for t in journal if t.get("timestamp", 0) >= start_ms]

    if not today_trades:
        log_line("startup_daily_report: no trades today, skip")
        return

    d          = _build_report_stats(today_trades)
    a          = _build_report_stats(list(journal))
    open_count = sum(1 for t in today_trades if t.get("status") in ("OPEN", "PENDING"))

    top = sorted(
        [t for t in today_trades if t.get("result_R") is not None],
        key=lambda x: x.get("result_R", 0), reverse=True
    )
    top_str = f"{top[0]['pair']} R={top[0]['result_R']:+.2f}" if top else "n/a"

    send_telegram(
        f"🔄 [{BOT_TAG}] BOT RESTARTED — Rekap {today}\n"
        f"Trades: {d['total']} | Open/Pending: {open_count} | Closed: {d['closed']}\n"
        f"W: {d['wins']} L: {d['losses']} BE: {d['be']} SL+: {d['sl_plus']}\n"
        f"WinRate: {d['win_rate']:.1f}% | TotalR: {d['total_r']:+.2f} "
        f"| DD: {d['max_drawdown_r']:.2f}R | P&L: ${d['total_dollar']:+.2f}\n"
        f"Best: {top_str}\n"
        f"-- ALL TIME --\n"
        f"Closed: {a['closed']} | WinRate: {a['win_rate']:.1f}%\n"
        f"TotalR: {a['total_r']:+.2f} | DD: {a['max_drawdown_r']:.2f}R | "
        f"P&L: ${a['total_dollar']:+.2f} | PF: {a['pf']:.2f}\n"
        f"Best pair: {_format_pair_pick(a['best_pair'])}"
    )

    # Reset agar send_daily_report() bisa kirim lagi nanti (EOD report tidak terblokir)
    state = load_json(REPORT_STATE_PATH) or {}
    state["last_report_date"] = None
    save_json_atomic(REPORT_STATE_PATH, state)
    log_line(f"startup_daily_report_sent trades={d['total']} open={open_count}")

def _trade_dollar_pnl(trade):
    if trade.get("realized_pnl") is not None:
        return float(trade.get("realized_pnl") or 0)
    return trade.get("result_R", 0) * trade.get(
        "risk_usdt",
        trade.get("fixed_notional", FIXED_NOTIONAL_USDT) * trade.get("sl_pct", 0.01)
    )

def _max_drawdown_r(closed):
    if not closed:
        return 0.0
    ordered = sorted(
        closed,
        key=lambda t: (t.get("closed_at") or t.get("timestamp") or 0)
    )
    equity = 0.0
    peak = 0.0
    max_dd = 0.0
    for trade in ordered:
        equity += trade.get("result_R", 0) or 0
        peak = max(peak, equity)
        max_dd = min(max_dd, equity - peak)
    return round(max_dd, 2)

def _group_performance(closed, key_name):
    groups = {}
    for trade in closed:
        key = trade.get(key_name) or "UNKNOWN"
        item = groups.setdefault(key, {
            "count": 0, "wins": 0, "losses": 0, "total_r": 0.0, "total_pnl": 0.0
        })
        r = trade.get("result_R", 0) or 0
        item["count"] += 1
        item["wins"] += 1 if r > 0 else 0
        item["losses"] += 1 if r < 0 else 0
        item["total_r"] += r
        item["total_pnl"] += _trade_dollar_pnl(trade)

    for item in groups.values():
        item["win_rate"] = (item["wins"] / item["count"] * 100) if item["count"] else 0
        item["avg_r"] = (item["total_r"] / item["count"]) if item["count"] else 0
        item["total_r"] = round(item["total_r"], 2)
        item["avg_r"] = round(item["avg_r"], 2)
        item["total_pnl"] = round(item["total_pnl"], 2)

    return groups

def _format_group_perf(groups, max_items=3):
    if not groups:
        return "n/a"
    rows = sorted(groups.items(), key=lambda x: x[1]["total_r"], reverse=True)[:max_items]
    return ", ".join(
        f"{name}: {data['total_r']:+.2f}R/{data['count']}t"
        for name, data in rows
    )

def _format_pair_pick(pair_tuple):
    name, data = pair_tuple
    if not name or not data:
        return "n/a"
    return f"{name} {data['total_r']:+.2f}R/{data['count']}t"

def _build_report_stats(trades_list):
    closed    = [t for t in trades_list if t.get("result_R") is not None]
    wins      = [t for t in closed if t.get("result_R", 0) > 0]
    losses    = [t for t in closed if t.get("result_R", 0) < 0]
    be_trades = [t for t in closed if t.get("result_R", 0) == 0]
    sl_plus_trades = [
        t for t in closed
        if t.get("exit_type") == "BEP/SL+" or t.get("protection_result") == "BEP/SL+"
    ]
    total_r   = sum(t.get("result_R", 0) for t in closed)
    avg_r     = total_r / len(closed) if closed else 0
    win_rate  = len(wins) / len(closed) * 100 if closed else 0
    pf        = abs(sum(t.get("result_R",0) for t in wins)) / abs(sum(t.get("result_R",0) for t in losses)) if losses else 0
    # [V7.4-S1] Total dollar P&L dihitung dari notional × sl_pct × result_R
    # Sebelumnya: result_R × risk_usdt — tapi risk_usdt sekarang = implied risk (notional × sl_pct)
    # bukan fixed, jadi tetap pakai risk_usdt yang tersimpan di trade_record (sudah benar).
    # Override lama: gunakan realized_pnl Binance jika tersedia.
    total_dollar = sum(_trade_dollar_pnl(t) for t in closed)
    pair_perf = _group_performance(closed, "pair")
    path_perf = _group_performance(closed, "entry_path")
    best_pair = max(pair_perf.items(), key=lambda x: x[1]["total_r"], default=(None, None))
    worst_pair = min(pair_perf.items(), key=lambda x: x[1]["total_r"], default=(None, None))
    return {
        "total": len(trades_list), "closed": len(closed),
        "wins": len(wins), "losses": len(losses), "be": len(be_trades),
        "sl_plus": len(sl_plus_trades),
        "win_rate": win_rate, "avg_r": avg_r, "total_r": total_r,
        "pf": pf, "total_dollar": total_dollar,
        "max_drawdown_r": _max_drawdown_r(closed),
        "best_pair": best_pair,
        "worst_pair": worst_pair,
        "pair_perf": pair_perf,
        "path_perf": path_perf,
    }

def send_daily_report():
    tz    = timezone(timedelta(hours=7))
    today = datetime.now(tz).date().isoformat()
    state = load_json(REPORT_STATE_PATH) or {}
    if state.get("last_report_date") == today:
        return
    start_ms     = int(datetime.now(tz).replace(hour=0,minute=0,second=0,microsecond=0).timestamp()*1000)
    today_trades = [t for t in journal if t.get("timestamp", 0) >= start_ms]
    all_trades   = list(journal)

    if not today_trades:
        return

    d = _build_report_stats(today_trades)
    a = _build_report_stats(all_trades)

    top = sorted([t for t in today_trades if t.get("result_R") is not None],
                 key=lambda x: x.get("result_R", 0), reverse=True)
    top_str = f"{top[0]['pair']} R={top[0]['result_R']:+.2f}" if top else "n/a"

    send_telegram(
        f"📊 [{BOT_TAG}] Daily Report {today}\n"
        f"Trades: {d['total']} | Closed: {d['closed']}\n"
        f"W: {d['wins']} L: {d['losses']} BE: {d['be']} SL+: {d['sl_plus']}\n"
        f"WinRate: {d['win_rate']:.1f}% | AvgR: {d['avg_r']:.2f} | "
        f"TotalR: {d['total_r']:+.2f} | DD: {d['max_drawdown_r']:.2f}R | "
        f"P&L: ${d['total_dollar']:+.2f}\n"
        f"PF: {d['pf']:.2f} | Best: {top_str} | Worst: {_format_pair_pick(d['worst_pair'])}\n"
        f"-- ALL TIME --\n"
        f"Closed: {a['closed']} | WinRate: {a['win_rate']:.1f}%\n"
        f"TotalR: {a['total_r']:+.2f} | DD: {a['max_drawdown_r']:.2f}R | "
        f"P&L: ${a['total_dollar']:+.2f} | PF: {a['pf']:.2f}"
    )
    state["last_report_date"] = today
    save_json_atomic(REPORT_STATE_PATH, state)

def send_alltime_report():
    all_trades = list(journal)
    a = _build_report_stats(all_trades)
    best_str = _format_group_perf(a["pair_perf"], max_items=5)
    worst_rows = sorted(a["pair_perf"].items(), key=lambda x: x[1]["total_r"])[:5]
    worst_str = " | ".join(
        f"{name}: {data['total_r']:+.2f}R/{data['count']}t"
        for name, data in worst_rows
    ) if worst_rows else "n/a"
    send_telegram(
        f"📈 [{BOT_TAG}] ALL-TIME REPORT\n"
        f"Total: {a['total']} | Closed: {a['closed']}\n"
        f"W: {a['wins']} L: {a['losses']} BE: {a['be']} SL+: {a['sl_plus']}\n"
        f"WinRate: {a['win_rate']:.1f}% | AvgR: {a['avg_r']:.2f}\n"
        f"TotalR: {a['total_r']:+.2f} | DD: {a['max_drawdown_r']:.2f}R | "
        f"P&L: ${a['total_dollar']:+.2f} | PF: {a['pf']:.2f}\n"
        f"Path: {_format_group_perf(a['path_perf'], max_items=4)}\n"
        f"Best:  {best_str}\n"
        f"Worst: {worst_str}"
    )

# ---------------------- STARTUP VALIDATION ----------------------
def validate_pairs_on_startup():
    global INVALID_PAIRS
    invalid = []
    for pair in PAIRS:
        # [BUGFIX V7.3.1] URL-encode simbol — pertahanan lapis kedua.
        url = f"{BASE_URL}/fapi/v1/klines?symbol={urllib.parse.quote(pair)}&interval=1m&limit=1"
        try:
            with urllib.request.urlopen(url, timeout=10, context=get_ssl_context()) as resp:
                resp.read()
        except urllib.error.HTTPError as e:
            if e.code == 400:
                invalid.append(pair)
                log_line(f"startup_invalid {pair} (http_400)")
            else:
                log_line(f"startup_check_err {pair} HTTP {e.code}")
        except Exception as e:
            # [BUGFIX V7.3.1] SEBELUMNYA: exception non-HTTPError (mis. simbol
            # unicode/aneh memicu UnicodeEncodeError) hanya di-log tapi pair
            # TIDAK ditandai invalid — akibatnya pair itu tetap ada di PAIRS,
            # dicoba ulang setiap scan_pair() di SETIAP cycle, gagal selamanya
            # dengan cara yang sama, buang waktu (3x retry tiap percobaan) dan
            # spam log tanpa henti. Sekarang exception apapun saat validasi
            # dasar gagal = pair juga ditandai invalid, bukan cuma HTTP 400.
            invalid.append(pair)
            log_line(f"startup_invalid {pair} (exception: {e})")
        time.sleep(0.1)
    with invalid_pairs_lock:
        INVALID_PAIRS = set(invalid)
    if invalid:
        chunk_size = 5
        for i in range(0, len(invalid), chunk_size):
            chunk = invalid[i:i+chunk_size]
            send_telegram(f"⚠️ [{BOT_TAG}] Pair invalid di-skip: {', '.join(chunk)}")
            time.sleep(1)
        log_line(f"invalid_pairs: {invalid}")
    else:
        log_line("all pairs valid ✅")


# ============================================================
# ACCOUNT SYNC — background thread, jalan setiap 2 menit.
# ============================================================

_sync_api_key    = None
_sync_api_secret = None
_sync_thread     = None

def _sync_worker():
    """
    [V7.1-FIX3] Tunggu SYNC_INTERVAL_SEC SEBELUM iterasi pertama.
    Bug lama: thread ini langsung sync_account_to_journal() di detik pertama,
    RACE dengan startup sync sinkronus (FIX-R1) yang juga jalan di waktu
    hampir bersamaan di main thread. Dua request /fapi/v2/positionRisk
    ditembak nyaris bersamaan saat TIME_OFFSET_MS belum tentu valid,
    memperbesar peluang -1021 dan kontensi journal_lock.

    Startup sync sinkronus sudah menangani reconciliation awal —
    background thread cukup mulai sync periodik SETELAH itu.
    """
    SYNC_INTERVAL_SEC = 120
    interruptible_sleep(SYNC_INTERVAL_SEC)   # [V7.1-FIX3] grace period awal
    while not _shutdown_event.is_set():
        try:
            if _sync_api_key and _sync_api_secret:
                sync_account_to_journal(_sync_api_key, _sync_api_secret)
        except Exception as e:
            log_line(f"sync_worker_err {e}")
        interruptible_sleep(SYNC_INTERVAL_SEC)

def start_sync_thread(api_key, api_secret):
    global _sync_api_key, _sync_api_secret, _sync_thread
    _sync_api_key    = api_key
    _sync_api_secret = api_secret
    _sync_thread = threading.Thread(
        target=_sync_worker,
        daemon=True,
        name="account-sync"
    )
    _sync_thread.start()
    log_line("sync_thread_started interval=120s")

def _get_all_positions(api_key, api_secret):
    """
    [V7.1-FIX2] Return None saat API gagal (BUKAN {}).
    Bug lama: {} dipakai untuk "tidak ada posisi" DAN "API error" —
    tidak bisa dibedakan. Akibatnya error transient (-1021 dkk) bisa
    membuat sync_account_to_journal() menganggap semua trade OPEN
    sudah closed, padahal sebenarnya masih open di exchange.
    """
    try:
        data = binance_get("/fapi/v2/positionRisk", {}, api_key, api_secret)
        positions = {}
        for d in data:
            if abs(float(d.get("positionAmt", 0))) <= 0:
                continue
            symbol = str(d.get("symbol", ""))
            pos_side = str(d.get("positionSide", "BOTH") or "BOTH").upper()
            positions[_position_key(symbol, pos_side)] = d
            if pos_side == "BOTH" or symbol not in positions:
                positions[symbol] = d
        return positions
    except Exception as e:
        log_line(f"sync_get_positions_err {e}")
        return None   # [V7.1-FIX2] None = gagal fetch, BUKAN "kosong"

def _get_all_open_orders(api_key, api_secret):
    """[V7.1-FIX2] Sama seperti _get_all_positions — None saat gagal."""
    try:
        data = binance_get("/fapi/v1/openOrders", {}, api_key, api_secret)
        orders = {"__meta_algo_checked__": False}
        for d in data:
            oid = d.get("orderId")
            if oid is not None:
                orders[str(oid)] = d

        try:
            algo_data = binance_get("/fapi/v1/openAlgoOrders", {}, api_key, api_secret)
            orders["__meta_algo_checked__"] = True
            for d in algo_data:
                oid = d.get("orderId")
                aid = d.get("algoId")
                if oid is not None:
                    orders[str(oid)] = d
                if aid is not None:
                    orders[str(aid)] = d
        except Exception as e:
            log_line(f"sync_get_open_algo_orders_warn {e}")

        return orders
    except Exception as e:
        log_line(f"sync_get_open_orders_err {e}")
        return None   # [V7.1-FIX2] None = gagal fetch, BUKAN "kosong"

def _order_symbol(order):
    return str(order.get("symbol") or order.get("origSymbol") or "")

def _order_position_key(order):
    symbol = _order_symbol(order)
    pos_side = str(order.get("positionSide", "BOTH") or "BOTH").upper()
    return _position_key(symbol, pos_side)

def _is_protective_stop_order(order):
    typ = str(order.get("type") or order.get("origType") or order.get("orderType") or "").upper()
    return "STOP" in typ and "TAKE_PROFIT" not in typ

def _is_protective_exit_order(order):
    typ = str(order.get("type") or order.get("origType") or order.get("orderType") or "").upper()
    return "STOP" in typ or "TAKE_PROFIT" in typ

def _send_audit_alert(kind, title, lines):
    state = load_json(REPORT_STATE_PATH) or {}
    audit_state = state.get("audit_alerts", {}) if isinstance(state.get("audit_alerts"), dict) else {}

    if not lines:
        item = audit_state.get(kind, {}) if isinstance(audit_state.get(kind), dict) else {}
        if item.get("hash"):
            audit_state[kind] = {
                "hash": "",
                "last_sent": int(time.time()),
                "count": 0,
            }
            state["audit_alerts"] = audit_state
            save_json_atomic(REPORT_STATE_PATH, state)
            log_line(f"audit_clear kind={kind}")
        return

    fingerprint = hashlib.sha256("\n".join(sorted(lines)).encode("utf-8")).hexdigest()
    item = audit_state.get(kind, {}) if isinstance(audit_state.get(kind), dict) else {}

    now = int(time.time())
    last_sent = int(item.get("last_sent", 0) or 0)
    last_hash = item.get("hash")
    should_send = (
        fingerprint != last_hash
        or AUDIT_ALERT_COOLDOWN_SEC <= 0
        or now - last_sent >= AUDIT_ALERT_COOLDOWN_SEC
    )

    if not should_send:
        return

    log_line(f"audit_alert_sent kind={kind} count={len(lines)} hash={fingerprint[:12]}")
    for line in lines[:50]:
        log_line(f"audit_alert_item kind={kind} {line}")

    send_telegram(
        f"{title}\n"
        + "\n".join(lines[:10])
        + ("\n...cek log untuk sisanya" if len(lines) > 10 else "")
    )
    audit_state[kind] = {
        "hash": fingerprint,
        "last_sent": now,
        "count": len(lines),
    }
    state["audit_alerts"] = audit_state
    save_json_atomic(REPORT_STATE_PATH, state)

def audit_live_safety(live_positions, live_orders, journal_snapshot=None):
    """
    P1 safety audit:
    - posisi live yang tidak punya SL aktif => alert keras Telegram
    - SL/TP aktif yang tidak cocok dengan posisi/journal => orphan alert
    """
    if not ENABLE_STARTUP_AUDIT and not ENABLE_ORPHAN_ORDER_AUDIT:
        return
    if live_positions is None or live_orders is None:
        return

    algo_checked = bool(live_orders.get("__meta_algo_checked__"))
    orders = [o for k, o in live_orders.items() if not str(k).startswith("__meta_")]

    live_keys = set()
    for key, pos in live_positions.items():
        if ":" not in str(key):
            continue
        if abs(float(pos.get("positionAmt", 0) or 0)) > 0:
            live_keys.add(str(key))

    source_journal = journal_snapshot if journal_snapshot is not None else journal
    open_journal_keys = {
        _trade_position_key(t)
        for t in source_journal
        if t.get("status") == "OPEN"
    }

    alert_lines = []
    if ENABLE_STARTUP_AUDIT and algo_checked:
        stop_keys = {_order_position_key(o) for o in orders if _is_protective_stop_order(o)}
        for key in sorted(live_keys):
            if key not in stop_keys:
                pos = live_positions.get(key)
                if not pos:
                    continue
                symbol = pos.get("symbol", key.split(":")[0])
                amt = float(pos.get("positionAmt", 0) or 0)
                entry = pos.get("entryPrice", "?")
                alert_lines.append(f"{symbol} qty={amt} entry={entry} tidak punya SL aktif")
    elif ENABLE_STARTUP_AUDIT:
        log_line("audit_missing_sl_skipped: open algo orders not available")

    orphan_lines = []
    if ENABLE_ORPHAN_ORDER_AUDIT:
        for order in orders:
            if not _is_protective_exit_order(order):
                continue
            key = _order_position_key(order)
            if key in live_keys or key in open_journal_keys:
                continue
            oid = order.get("algoId") or order.get("orderId")
            symbol = _order_symbol(order)
            typ = order.get("type") or order.get("origType") or order.get("orderType")
            orphan_lines.append(f"{symbol} {typ} id={oid}")

    _send_audit_alert(
        "missing_sl",
        f"🚨 [{BOT_TAG}] AUDIT POSISI LIVE TANPA SL",
        alert_lines,
    )
    _send_audit_alert(
        "orphan_orders",
        f"⚠️ [{BOT_TAG}] AUDIT ORPHAN SL/TP ORDER",
        orphan_lines,
    )

def cleanup_closed_position_orders(position_keys, live_positions, live_orders, api_key, api_secret):
    """
    Cancel protective SL/TP orders after a position is confirmed closed.

    Safety rules:
    - Only cancel STOP/TAKE_PROFIT orders.
    - Only cancel keys that no longer exist in live_positions.
    - Respect hedge mode by matching symbol + positionSide.
    """
    if not position_keys or live_positions is None or live_orders is None:
        return 0

    live_keys = {
        str(key)
        for key, pos in live_positions.items()
        if ":" in str(key) and abs(float(pos.get("positionAmt", 0) or 0)) > 0
    }
    safe_keys = {str(key) for key in position_keys if str(key) not in live_keys}
    if not safe_keys:
        return 0

    orders = [o for k, o in live_orders.items() if not str(k).startswith("__meta_")]
    cancelled = 0
    for order in orders:
        if not _is_protective_exit_order(order):
            continue
        key = _order_position_key(order)
        if key not in safe_keys:
            continue

        symbol = _order_symbol(order)
        algo_id = order.get("algoId")
        order_id = order.get("orderId")
        typ = order.get("type") or order.get("origType") or order.get("orderType")
        try:
            if algo_id:
                binance_delete("/fapi/v1/algoOrder", {"symbol": symbol, "algoId": algo_id}, api_key, api_secret)
                log_line(f"closed_position_order_cancelled {symbol} {typ} algoId={algo_id} key={key}")
            elif order_id:
                binance_delete("/fapi/v1/order", {"symbol": symbol, "orderId": order_id}, api_key, api_secret)
                log_line(f"closed_position_order_cancelled {symbol} {typ} orderId={order_id} key={key}")
            else:
                log_line(f"closed_position_order_cancel_skip {symbol} {typ} key={key} no_id")
                continue
            cancelled += 1
        except Exception as e:
            log_line(f"closed_position_order_cancel_err {symbol} {typ} key={key} {e}")

    return cancelled

def _get_trade_pnl(symbol, api_key, api_secret, start_time_ms, end_time_ms=None):
    try:
        total = 0.0
        seen = 0
        cursor = int(start_time_ms or 0)
        end_ms = int(end_time_ms) if end_time_ms else None

        while True:
            params = {
                "symbol":     symbol,
                "incomeType": "REALIZED_PNL",
                "startTime":  cursor,
                "limit":      1000,
            }
            if end_ms:
                params["endTime"] = end_ms

            data = binance_get("/fapi/v1/income", params, api_key, api_secret)
            if not data:
                break

            seen += len(data)
            total += sum(float(d.get("income", 0)) for d in data)

            if len(data) < 1000:
                break
            last_time = max(int(d.get("time", cursor)) for d in data)
            next_cursor = last_time + 1
            if next_cursor <= cursor or (end_ms and next_cursor > end_ms):
                break
            cursor = next_cursor

        return total if seen else None
    except Exception as e:
        log_line(f"sync_get_pnl_err {symbol} {e}")
        return None

def sync_account_to_journal(api_key, api_secret):
    """
    Sinkronisasi journal dengan kondisi akun Binance Futures nyata.
    2 API call per 2 menit (positionRisk + openOrders).
    [FIX-10] close_price dihitung dari implied PnL/qty, bukan asumsi tp/sl.
    [FIX-11] sl_tp_placed flag digunakan untuk cegah race dengan poll thread.
    """
    global journal, open_trades, last_sync_summary_log_at, last_sync_summary_key

    if not api_key or not api_secret:
        return

    try:
        live_positions = _get_all_positions(api_key, api_secret)
        live_orders    = _get_all_open_orders(api_key, api_secret)

        # [V7.1-FIX2] ABORT TOTAL jika salah satu fetch gagal — JANGAN sentuh
        # journal sama sekali. Bug lama: positions={} akibat API error
        # ditafsirkan sebagai "tidak ada posisi" → trade OPEN asli ditandai
        # CLOSED paksa, padahal masih open di exchange (data loss kritikal).
        if live_positions is None or live_orders is None:
            log_line(
                f"sync_account_aborted: fetch_failed "
                f"positions={'OK' if live_positions is not None else 'FAILED'} "
                f"orders={'OK' if live_orders is not None else 'FAILED'} "
                f"— journal TIDAK diubah, retry di siklus sync berikutnya"
            )
            return

        backup_journal("pre_sync", min_interval_sec=JOURNAL_BACKUP_MIN_INTERVAL_SEC)
        with journal_lock:
            audit_snapshot = list(journal)
        audit_live_safety(live_positions, live_orders, audit_snapshot)

        changed        = False
        closed_notifs  = []
        processed_closed_groups = set()
        cleanup_position_keys = set()

        with journal_lock:
            for i, trade in enumerate(journal):
                status = trade.get("status")

                if status == "OPEN":
                    pair = trade.get("pair", "")
                    pos  = _lookup_live_position(live_positions, trade)

                    if pos:
                        unreal = float(pos.get("unRealizedProfit", 0))
                        if trade.get("unrealized_pnl") != round(unreal, 4):
                            trade["unrealized_pnl"] = round(unreal, 4)
                            journal[i] = trade
                            changed = True
                    else:
                        group_key = _trade_position_key(trade)
                        if group_key in processed_closed_groups:
                            continue
                        processed_closed_groups.add(group_key)
                        cleanup_position_keys.add(group_key)

                        group_indices = [
                            idx for idx, t in enumerate(journal)
                            if t.get("status") == "OPEN"
                            and _trade_position_key(t) == group_key
                        ]
                        group_trades = [journal[idx] for idx in group_indices]
                        entry_ts = min((t.get("timestamp", 0) for t in group_trades), default=trade.get("timestamp", 0))
                        closed_ts = now_ms()
                        realized_total = _get_trade_pnl(pair, api_key, api_secret, entry_ts, closed_ts + 60_000)

                        qty_sum = sum(float(t.get("qty", 0) or 0) for t in group_trades)
                        equal_weight = 1 / len(group_trades) if group_trades else 0

                        for idx, gt in zip(group_indices, group_trades):
                            entry     = float(gt.get("entry", 0) or 0)
                            sl        = float(gt.get("sl", 0) or 0)
                            tp        = float(gt.get("tp", 0) or 0)
                            qty_total = float(gt.get("qty", 0) or 0)
                            side      = gt.get("side", "LONG")

                            realized = None
                            if realized_total is not None:
                                weight = (qty_total / qty_sum) if qty_sum > 0 else equal_weight
                                realized = realized_total * weight
                                gt["realized_pnl"] = round(realized, 4)
                                # [FIX-10/14] close_price dari PnL yang sudah
                                # diatribusikan, bukan total PnL posisi agregat.
                                if entry > 0 and qty_total > 0:
                                    if side == "LONG":
                                        implied_close = entry + realized / qty_total
                                    else:
                                        implied_close = entry - realized / qty_total
                                    gt["close_price"] = round(implied_close, 8)
                                else:
                                    gt["close_price"] = tp if realized > 0 else sl
                                gt["status"] = "WIN" if realized > 0 else ("LOSS" if realized < 0 else "CLOSED")
                            else:
                                gt["status"] = "CLOSED"

                            r = calculate_result_r(gt)
                            if r is not None:
                                gt["result_R"] = r
                            _maybe_mark_sl_plus_exit(gt)

                            gt["closed_at"] = closed_ts
                            journal[idx] = gt
                            changed = True

                            r_str = f"R={r:.2f}" if r is not None else "R=?"
                            pnl_s = f"PnL={realized:.4f}" if realized is not None else ""
                            log_line(f"sync_closed {pair} {side} {gt['status']} {r_str} {pnl_s} group={group_key}")
                            closed_notifs.append(f"{pair} {side} {gt['status']} {r_str}")

                elif status == "PENDING":
                    pair     = trade.get("pair", "")
                    order_id = str(trade.get("entry_order_id", ""))

                    if order_id not in live_orders:
                        pos = _lookup_live_position(live_positions, trade)
                        if pos:
                            # [FIX-11] Jangan place SL/TP — itu tugas poll thread
                            # Sync hanya update status; sl_tp_placed flag sudah diatur poll thread
                            trade["status"] = "OPEN"
                            trade["entry"]  = float(pos.get("entryPrice", trade.get("entry", 0)))
                            trade["qty"]    = abs(float(pos.get("positionAmt", trade.get("qty", 0))))
                            trade["unrealized_pnl"] = float(pos.get("unRealizedProfit", 0))
                            journal[i] = trade
                            changed    = True
                            log_line(f"sync_filled {pair} order_id={order_id}")
                            closed_notifs.append(f"{pair} PENDING->OPEN (filled)")
                        else:
                            trade["status"]    = "PENDING_CANCELLED"
                            trade["closed_at"] = now_ms()
                            journal[i] = trade
                            changed    = True
                            log_line(f"sync_cancelled {pair} order_id={order_id}")

            live_open_count = _live_position_count(live_positions)
            live_pend_count = sum(
                1 for t in journal
                if t.get("status") == "PENDING"
                and str(t.get("entry_order_id", "")) in live_orders
            )
            real_open = live_open_count + live_pend_count

            with open_trades_lock:
                old_count   = open_trades
                open_trades = real_open

            if changed:
                save_json_atomic(JOURNAL_PATH, journal)

        if cleanup_position_keys:
            cancelled = cleanup_closed_position_orders(
                cleanup_position_keys,
                live_positions,
                live_orders,
                api_key,
                api_secret,
            )
            if cancelled:
                log_line(f"closed_position_order_cleanup_done count={cancelled} keys={sorted(cleanup_position_keys)}")

        closed_count = len([n for n in closed_notifs if "WIN" in n or "LOSS" in n])
        sync_summary_key = (live_open_count, live_pend_count, old_count, real_open, closed_count)
        now_s = time.time()
        should_log_sync = (
            changed
            or closed_count > 0
            or sync_summary_key != last_sync_summary_key
            or now_s - last_sync_summary_log_at >= SYNC_SUMMARY_LOG_INTERVAL_SEC
        )
        if should_log_sync:
            log_line(
                f"sync_done positions={live_open_count} pending={live_pend_count} "
                f"open_trades={old_count}->{real_open} "
                f"closed={closed_count}"
            )
            last_sync_summary_key = sync_summary_key
            last_sync_summary_log_at = now_s

        # ── Kirim notif close dengan dua perbaikan ─────────────────────────────
        # [BUGFIX-NOTIF-1] Flag close_notif_sent di trade_record — cegah duplikat.
        #   Trade bisa kena dua sync cycle berturut-turut saat baru saja closed,
        #   sehingga notif dikirim 2x dengan R yang sama persis.
        #
        # [BUGFIX-NOTIF-2] Grup same-pair + same-side + same-status dari SEMUA
        #   trade yang belum pernah dinotif (bukan hanya dari cycle ini).
        #   Alasan: posisi averaging sering close di cycle BERBEDA (beda 120-an detik)
        #   sehingga tidak bisa di-grup via closed_notifs yang hanya berisi cycle ini.
        #   Solusi: scan SELURUH journal untuk WIN/LOSS yang belum dinotif, grup, kirim.
        #   Dengan cara ini: 4x FILUSDT LONG WIN yang close di 4 cycle berbeda
        #   akan tetap digabung menjadi 1 pesan dengan Avg R dan Total PnL.

        # Kumpulkan semua trade WIN/LOSS yang belum dinotif
        unnotified = [
            t for t in journal
            if t.get("status") in ("WIN", "LOSS")
            and not t.get("close_notif_sent")
        ]

        if unnotified:
            # Grup per pair:side:status
            groups: dict = {}
            for trade in unnotified:
                pair_t = trade.get("pair", "")
                side_t = trade.get("side", "")
                stat_t = trade.get("status", "")
                key    = f"{pair_t}:{side_t}:{stat_t}"
                if key not in groups:
                    groups[key] = {
                        "pair": pair_t, "side": side_t, "status": stat_t,
                        "r_values": [], "pnls": [], "trades": []
                    }
                r_val = trade.get("result_R")
                pnl   = trade.get("realized_pnl") or 0
                if r_val is not None:
                    groups[key]["r_values"].append(r_val)
                groups[key]["pnls"].append(pnl)
                groups[key]["trades"].append(trade)
                trade["close_notif_sent"] = True   # tandai sudah dinotif

            save_json_atomic(JOURNAL_PATH, journal)

            # Kirim satu notif per grup
            for key, g in groups.items():
                r_list  = g["r_values"]
                pnl_sum = sum(g["pnls"])
                count   = len(g["trades"])
                emoji   = "✅" if g["status"] == "WIN" else "❌"

                if not r_list:
                    send_telegram(
                        f"{emoji} [{BOT_TAG}] {g['pair']} {g['side']} {g['status']}"
                    )
                    continue

                if count > 1:
                    # Beberapa posisi averaging → tampilkan rata-rata
                    avg_r   = sum(r_list) / len(r_list)
                    r_parts = " | ".join(f"{r:.2f}" for r in r_list)
                    pnl_str = f" | Total PnL: ${pnl_sum:.2f}" if pnl_sum != 0 else ""
                    send_telegram(
                        f"{emoji} [{BOT_TAG}] {g['pair']} {g['side']} "
                        f"{g['status']} ×{count}\n"
                        f"Avg R: {avg_r:+.2f}{pnl_str}\n"
                        f"R tiap posisi: {r_parts}"
                    )
                else:
                    # Satu posisi → format normal
                    r_val   = r_list[0]
                    pnl_str = f" | PnL: ${pnl_sum:.2f}" if pnl_sum != 0 else ""
                    send_telegram(
                        f"{emoji} [{BOT_TAG}] {g['pair']} {g['side']} "
                        f"{g['status']} R={r_val:+.2f}{pnl_str}"
                    )

    except Exception as e:
        log_line(f"sync_account_err {e}\n{traceback.format_exc()[:400]}")


# ============================================================
# PROFIT PROTECTION MONITOR — cek TP1 hit setiap 30 detik
# [FIX-9] Stale trade notification juga di-handle di sini
# [FIX-12] TP1 hit threshold 0.70 (was 0.65)
# ============================================================

def _position_profit_pct(entry, mark_price, side):
    if entry <= 0 or mark_price <= 0:
        return 0.0
    if side == "LONG":
        return (mark_price - entry) / entry
    return (entry - mark_price) / entry


def _sl_plus_price_str(entry, side, tick=None):
    raw = (
        entry * (1 + PROFIT_SL_PLUS_LOCK_PCT)
        if side == "LONG"
        else entry * (1 - PROFIT_SL_PLUS_LOCK_PCT)
    )
    if not tick:
        return str(raw)
    rounding = ROUND_DOWN if side == "LONG" else ROUND_UP
    return str(Decimal(str(raw)).quantize(Decimal(tick), rounding=rounding))


def _check_tp1_hit(trade, api_key, api_secret):
    """
    Cek TP1 hit dan pindahkan SL sisa posisi ke SL+ 1% dari entry.
    Urutan yang benar:
    1. Cancel TP2 order yang masih aktif (bukan cancel SL dulu!)
    2. Pasang BE SL dengan qty EKSPLISIT (bukan closePosition=true)
       — closePosition=true ditolak Binance kalau ada algo order lain aktif
    3. Cancel SL lama
    4. Pasang ulang TP2 dengan qty yang tersisa (current_qty)

    Bug lama: langsung pasang BE SL dengan closePosition=true tanpa cancel TP2
    dulu → Binance tolak -4130 karena ada algo order "close all" yang sudah
    ada. be_sl_set tidak pernah jadi True → monitor retry tiap 30s selamanya.
    """
    if not ENABLE_PARTIAL_TP:
        return
    if trade.get("tp1_hit") or trade.get("be_sl_set"):
        return
    if trade.get("be_sl_in_progress"):
        started_at = int(trade.get("be_sl_started_at", 0) or 0)
        if started_at and now_ms() - started_at > 10 * 60 * 1000:
            log_line(f"{trade.get('pair', '?')}: stale_be_in_progress_reset")
            trade["be_sl_in_progress"] = False
            with journal_lock:
                save_json_atomic(JOURNAL_PATH, journal)
        else:
            return
    if trade.get("status") != "OPEN":
        return

    pair          = trade.get("pair")
    side          = trade.get("side", "LONG")
    entry         = float(trade.get("entry", 0))
    qty_total     = float(trade.get("qty", 0))
    sl_order_id   = trade.get("sl_order_id")
    tp2_order_id  = trade.get("tp2_order_id")
    position_side = trade.get("position_side")

    if not (pair and entry and qty_total and sl_order_id):
        return

    with be_action_lock:
        if trade.get("tp1_hit") or trade.get("be_sl_set") or trade.get("be_sl_in_progress"):
            return

    try:
        positions = binance_get("/fapi/v2/positionRisk", {}, api_key, api_secret)

        def _match_pos(p):
            if p.get("symbol") != pair: return False
            if abs(float(p.get("positionAmt", 0))) <= 0: return False
            if position_side:
                return p.get("positionSide", "BOTH") == position_side
            return True

        pos = next((p for p in positions if _match_pos(p)), None)
        if not pos:
            with be_action_lock:
                trade["be_sl_in_progress"] = False
                with journal_lock:
                    save_json_atomic(JOURNAL_PATH, journal)
            return

        current_qty = abs(float(pos.get("positionAmt", 0)))

        if current_qty <= qty_total * TP1_HIT_THRESHOLD:
            mark_price = float(pos.get("markPrice", 0) or 0)
            profit_pct = _position_profit_pct(entry, mark_price, side)
            step, tick, _, _ = SYMBOL_FILTERS_CACHE.get(pair, (None, None, 0, 0))
            sl_plus_str = _sl_plus_price_str(entry, side, tick)
            sl_plus_value = float(sl_plus_str)
            tick_value = float(tick or 0)
            price_gap = max(tick_value, entry * 0.00001)
            stop_is_valid = (
                mark_price > sl_plus_value + price_gap
                if side == "LONG"
                else mark_price < sl_plus_value - price_gap
            )
            # SL+ 1% harus berada di sisi yang valid terhadap mark price.
            # Jika TP1 lebih dekat dari 1%, SL lama tetap aktif sambil menunggu.
            if not stop_is_valid:
                if _log_throttle(f"tp1_sl_plus_wait:{pair}:{side}", 30 * 60):
                    log_line(
                        f"{pair}: tp1_sl_plus_wait mark_profit={profit_pct:.4f} "
                        f"required_lock={PROFIT_SL_PLUS_LOCK_PCT:.4f}"
                    )
                return
            with be_action_lock:
                if trade.get("tp1_hit") or trade.get("be_sl_set") or trade.get("be_sl_in_progress"):
                    return
                trade["be_sl_in_progress"] = True
                trade["be_sl_started_at"] = now_ms()
                with journal_lock:
                    save_json_atomic(JOURNAL_PATH, journal)

            log_line(f"{pair}: tp1_hit detected qty={current_qty:.6f} orig={qty_total:.6f} threshold={TP1_HIT_THRESHOLD}")

            close_side = "SELL" if side == "LONG" else "BUY"

            try:
                # Step 1: Cancel TP2 DULU — ini yang bikin -4130.
                # BE SL tidak bisa dipasang kalau TP2 algo order masih aktif
                # karena Binance melarang dua algo order "close" sekaligus.
                if tp2_order_id:
                    try:
                        binance_delete("/fapi/v1/algoOrder",
                                       {"symbol": pair, "algoId": tp2_order_id},
                                       api_key, api_secret)
                        log_line(f"{pair}: tp2_cancelled_for_be algoId={tp2_order_id}")
                    except Exception as _e:
                        log_line(f"{pair}: tp2_cancel_warn (non-fatal, mungkin sudah expired) {_e}")

                # Step 2: Pasang BE SL dengan qty EKSPLISIT (bukan closePosition=true).
                # Harus pakai qty karena closePosition=true tidak diizinkan
                # kalau ada order aktif lain. Qty = current_qty (sisa posisi setelah TP1).
                be_payload = {
                    "algoType":    "CONDITIONAL",
                    "symbol":      pair,
                    "side":        close_side,
                    "type":        "STOP_MARKET",
                    "triggerPrice": sl_plus_str,
                    "quantity":    str(current_qty),
                    "workingType": "MARK_PRICE",
                }
                if position_side:
                    be_payload["positionSide"] = position_side
                be_order    = binance_post("/fapi/v1/algoOrder", be_payload, api_key, api_secret)
                be_order_id = be_order.get("orderId") or be_order.get("algoId")
                log_line(f"{pair}: tp1_sl_plus_placed at {sl_plus_str} algoId={be_order_id} qty={current_qty}")

                # Step 3: Cancel SL lama (sekarang sudah aman)
                try:
                    binance_delete("/fapi/v1/algoOrder",
                                   {"symbol": pair, "algoId": sl_order_id},
                                   api_key, api_secret)
                    log_line(f"{pair}: old_sl_cancelled algoId={sl_order_id}")
                except Exception as _e:
                    log_line(f"{pair}: old_sl_cancel_warn {_e}")

                # Step 4: Pasang ulang TP2 dengan qty yang tersisa
                # Catatan: /fapi/v1/algoOrder tidak mendukung "reduceOnly"
                # (hanya valid di /fapi/v1/order biasa). Qty + side yang
                # benar sudah cukup untuk menjadi reduce-only secara efektif.
                tp2_str = trade.get("tp2_price_str") or trade.get("tp2")
                new_tp2_id = None
                if tp2_str:
                    try:
                        tp2_o = binance_post("/fapi/v1/algoOrder", {
                            "algoType":    "CONDITIONAL",
                            "symbol":      pair,
                            "side":        close_side,
                            "type":        "TAKE_PROFIT_MARKET",
                            "triggerPrice": tp2_str,
                            "quantity":    str(current_qty),
                            "workingType": "MARK_PRICE",
                            **({  "positionSide": position_side} if position_side else {})
                        }, api_key, api_secret)
                        new_tp2_id = tp2_o.get("orderId") or tp2_o.get("algoId")
                        log_line(f"{pair}: tp2_replaced algoId={new_tp2_id} qty={current_qty}")
                    except Exception as _e:
                        log_line(f"{pair}: tp2_replace_warn (non-fatal) {_e}")

                # Update journal
                trade["sl_order_id"]  = be_order_id
                trade["tp2_order_id"] = new_tp2_id
                trade["tp1_hit"]      = True
                trade["be_sl_set"]    = True
                trade["sl_plus_set"]  = True
                trade["protection_type"] = "BEP/SL+"
                trade["be_trigger"]   = "tp1_sl_plus"
                trade["be_price"]     = float(sl_plus_str)
                trade["sl_plus_price"] = float(sl_plus_str)
                trade["sl_plus_lock_pct"] = PROFIT_SL_PLUS_LOCK_PCT
                trade["be_profit_pct"] = round(profit_pct, 5)
                trade["be_mark_price"] = mark_price
                trade["be_sl_in_progress"] = False
                trade["be_completed_at"] = now_ms()
                should_notify = not trade.get("be_notif_sent")
                trade["be_notif_sent"] = True
                with journal_lock:
                    save_json_atomic(JOURNAL_PATH, journal)
                log_line(f"{pair}: tp1_sl_plus_complete sl={sl_plus_str} new_tp2_id={new_tp2_id}")
                if should_notify:
                    send_telegram(
                        f"🔒 [{BOT_TAG}] {pair} {side}\n"
                        f"TP1 hit — SL+ dipindah ke {sl_plus_str} "
                        f"(+{PROFIT_SL_PLUS_LOCK_PCT * 100:.2f}% dari entry).\n"
                        f"TP2 masih aktif di {tp2_str}"
                    )
                return

            except Exception as e:
                log_line(f"{pair}: be_sl_place_err {e}")
                with be_action_lock:
                    trade["be_sl_in_progress"] = False
                    trade["be_last_error"] = str(e)[:200]
                    with journal_lock:
                        save_json_atomic(JOURNAL_PATH, journal)
                # JANGAN set tp1_hit/be_sl_set di sini —
                # biarkan monitor retry di cycle berikutnya

    except Exception as e:
        log_line(f"tp1_check_err {pair} {e}")
        with be_action_lock:
            trade["be_sl_in_progress"] = False
            trade["be_last_error"] = str(e)[:200]
            with journal_lock:
                save_json_atomic(JOURNAL_PATH, journal)

def _check_profit_sl_plus(trade, api_key, api_secret):
    """
    Saat posisi running profit sesuai PROFIT_SL_PLUS_TRIGGER_PCT,
    pindahkan SL ke SL+ sesuai PROFIT_SL_PLUS_LOCK_PCT.
    TP1/TP2 tidak disentuh.
    """
    if not ENABLE_PROFIT_SL_PLUS:
        return
    if trade.get("sl_plus_set") or trade.get("be_sl_in_progress"):
        return
    if trade.get("status") != "OPEN":
        return

    pair          = trade.get("pair")
    side          = trade.get("side", "LONG")
    entry         = float(trade.get("entry", 0) or 0)
    qty_total     = float(trade.get("qty", 0) or 0)
    sl_order_id   = trade.get("sl_order_id")
    position_side = trade.get("position_side")

    if not (pair and entry > 0 and sl_order_id):
        return

    try:
        positions = binance_get("/fapi/v2/positionRisk", {}, api_key, api_secret)

        def _match_pos(p):
            if p.get("symbol") != pair:
                return False
            if abs(float(p.get("positionAmt", 0))) <= 0:
                return False
            if position_side:
                return p.get("positionSide", "BOTH") == position_side
            return True

        pos = next((p for p in positions if _match_pos(p)), None)
        if not pos:
            return

        mark_price = float(pos.get("markPrice", 0) or 0)
        if mark_price <= 0:
            return

        profit_pct = _position_profit_pct(entry, mark_price, side)
        close_side = "SELL" if side == "LONG" else "BUY"

        if profit_pct < PROFIT_SL_PLUS_TRIGGER_PCT:
            return

        current_qty = abs(float(pos.get("positionAmt", 0) or 0))
        position_reduced = bool(qty_total and current_qty <= qty_total * TP1_HIT_THRESHOLD)

        with be_action_lock:
            if trade.get("sl_plus_set") or trade.get("be_sl_in_progress"):
                return
            trade["be_sl_in_progress"] = True
            trade["be_sl_started_at"] = now_ms()
            with journal_lock:
                save_json_atomic(JOURNAL_PATH, journal)

        step, tick, _, _ = SYMBOL_FILTERS_CACHE.get(pair, (None, None, 0, 0))
        sl_plus_str = _sl_plus_price_str(entry, side, tick)

        old_sl_price = trade.get("sl")
        restored_old_sl = False

        try:
            # Jangan ubah TP1/TP2. Hanya ganti SL lama ke SL+.
            binance_delete("/fapi/v1/algoOrder",
                           {"symbol": pair, "algoId": sl_order_id},
                           api_key, api_secret)
            log_line(f"{pair}: old_sl_cancelled_for_profit_sl_plus algoId={sl_order_id}")

            be_payload = {
                "algoType":      "CONDITIONAL",
                "symbol":        pair,
                "side":          close_side,
                "type":          "STOP_MARKET",
                "triggerPrice":  sl_plus_str,
                "workingType":   "MARK_PRICE",
            }
            if position_reduced:
                be_payload["quantity"] = str(current_qty)
            else:
                be_payload["closePosition"] = "true"
            if position_side:
                be_payload["positionSide"] = position_side

            be_order = binance_post("/fapi/v1/algoOrder", be_payload, api_key, api_secret)
            be_order_id = be_order.get("orderId") or be_order.get("algoId")

            trade["sl_order_id"] = be_order_id
            trade["be_sl_set"] = True
            trade["be_1pct_set"] = True  # backward compatibility journal lama
            trade["sl_plus_set"] = True
            trade["protection_type"] = "BEP/SL+"
            trade["be_trigger"] = "profit_1_5pct_sl_plus"
            trade["be_price"] = float(sl_plus_str)
            trade["sl_plus_price"] = float(sl_plus_str)
            trade["sl_plus_lock_pct"] = PROFIT_SL_PLUS_LOCK_PCT
            trade["be_profit_pct"] = round(profit_pct, 5)
            trade["be_mark_price"] = mark_price
            trade["be_completed_at"] = now_ms()
            trade["be_sl_in_progress"] = False
            if position_reduced:
                trade["tp1_hit"] = True

            should_notify = not (trade.get("sl_plus_notif_sent") or trade.get("be_1pct_notif_sent"))
            trade["sl_plus_notif_sent"] = True
            trade["be_1pct_notif_sent"] = True
            with journal_lock:
                save_json_atomic(JOURNAL_PATH, journal)

            log_line(f"{pair}: profit_sl_plus_complete mark={mark_price} profit_pct={profit_pct:.4f} sl_plus={sl_plus_str}")
            if should_notify:
                send_telegram(
                    f"🔒 [{BOT_TAG}] {pair} {side}\n"
                    f"Harga sudah running +{profit_pct * 100:.2f}% dari entry.\n"
                    f"SL+ dipasang di {sl_plus_str} (+{PROFIT_SL_PLUS_LOCK_PCT * 100:.2f}% dari entry).\n"
                    f"TP1/TP2 tetap aktif seperti semula."
                )

        except Exception as e:
            # Kalau SL+ gagal setelah SL lama dicancel, coba restore SL lama.
            if old_sl_price:
                try:
                    restore_payload = {
                        "algoType":      "CONDITIONAL",
                        "symbol":        pair,
                        "side":          close_side,
                        "type":          "STOP_MARKET",
                        "triggerPrice":  str(old_sl_price),
                        "closePosition": "true",
                        "workingType":   "MARK_PRICE",
                    }
                    if position_side:
                        restore_payload["positionSide"] = position_side
                    restored = binance_post("/fapi/v1/algoOrder", restore_payload, api_key, api_secret)
                    trade["sl_order_id"] = restored.get("orderId") or restored.get("algoId")
                    restored_old_sl = True
                except Exception as restore_e:
                    log_line(f"{pair}: restore_old_sl_after_profit_sl_plus_err {restore_e}")

            trade["be_sl_in_progress"] = False
            trade["be_last_error"] = str(e)[:200]
            with journal_lock:
                save_json_atomic(JOURNAL_PATH, journal)
            log_line(f"{pair}: profit_sl_plus_err {e} restored_old_sl={restored_old_sl}")

    except Exception as e:
        log_line(f"profit_sl_plus_check_err {trade.get('pair', '?')} {e}")
        with be_action_lock:
            trade["be_sl_in_progress"] = False
            trade["be_last_error"] = str(e)[:200]
            with journal_lock:
                save_json_atomic(JOURNAL_PATH, journal)


def _be_monitor_worker():
    """
    Background thread: cek TP1 hit dan stale trade setiap 30 detik.
    [FIX-9]  Stale trade notification jika posisi OPEN > 4 jam tanpa TP1.
    [FIX-12] TP1 hit threshold 0.70.
    """
    BE_INTERVAL       = 30
    STALE_LIMIT_MS    = STALE_TRADE_CANDLES * 15 * 60 * 1000  # [FIX-9]
    _dual_side_cache  = [None]

    while not _shutdown_event.is_set():
        try:
            if _sync_api_key and _sync_api_secret:
                if _dual_side_cache[0] is None:
                    try:
                        _dual_side_cache[0] = get_position_mode(_sync_api_key, _sync_api_secret)
                    except Exception:
                        _dual_side_cache[0] = False

                open_list = [t for t in journal if t.get("status") == "OPEN"]
                if open_list:
                    changed = False
                    for trade in open_list:
                        # Inject dual_side ke trade
                        if trade.get("position_side") is None and _dual_side_cache[0]:
                            trade["position_side"] = "LONG" if trade.get("side") == "LONG" else "SHORT"

                        # Trigger profit 1.5% -> SL+ 1%; tidak mengubah TP1/TP2.
                        _check_profit_sl_plus(trade, _sync_api_key, _sync_api_secret)

                        # TP1 hit check
                        if ENABLE_PARTIAL_TP and not trade.get("tp1_hit"):
                            _check_tp1_hit(trade, _sync_api_key, _sync_api_secret)

                        # [FIX-9] Stale trade notification
                        if (not trade.get("stale_notified")
                                and not trade.get("tp1_hit")
                                and not trade.get("be_sl_set")):
                            age_ms = now_ms() - trade.get("timestamp", now_ms())
                            if age_ms > STALE_LIMIT_MS:
                                age_h = age_ms / 3_600_000
                                pair  = trade.get("pair", "?")
                                side  = trade.get("side", "?")
                                entry = trade.get("entry", 0)
                                log_line(f"stale_trade_alert {pair} age={age_h:.1f}h")
                                send_telegram(
                                    f"⏰ [{BOT_TAG}] STALE TRADE\n"
                                    f"{pair} {side} | Entry: {fmt_price(entry)}\n"
                                    f"Sudah {age_h:.1f} jam tanpa TP1 — monitor manual"
                                )
                                trade["stale_notified"] = True
                                changed = True

                    if changed:
                        with journal_lock:
                            save_json_atomic(JOURNAL_PATH, journal)

        except Exception as e:
            log_line(f"be_monitor_err {e}")
        interruptible_sleep(BE_INTERVAL)

# ---------------------- MAIN CYCLE ----------------------
def main_cycle(api_key=None, api_secret=None):
    heartbeat()

    # [V7.2] Cek apakah pair universe perlu di-refresh (sekali per
    # PAIRS_REFRESH_INTERVAL_SEC). Murah untuk dipanggil tiap cycle —
    # ada cache freshness check internal, hit API hanya kalau benar2 due.
    refresh_dynamic_pairs(api_key, api_secret)

    # [V7.3] Housekeeping kasar untuk breakout_state — buang entry yang sudah
    # sangat lama (mis. pair drop dari dynamic universe sehingga expiry presisi
    # di scan_pair() tidak pernah sempat jalan untuk entry itu).
    cleanup_expired_breakouts_housekeeping()

    quality_market_regime = (
        get_quality_market_regime()
        if ENABLE_QUALITY_GATE or ENABLE_SMART_MONEY_C_SHADOW
        else {
            "direction": "DISABLED", "bull_count": 0, "bear_count": 0,
            "core_count": 0, "required": QUALITY_MARKET_MIN_AGREEMENT,
        }
    )

    _acct = {}
    if api_key and api_secret:
        try:
            _acct = get_account_info(api_key, api_secret)
        except Exception as _e:
            log_line(f"get_account_info_err {_e}")
    env = {
        "api_key":       api_key,
        "api_secret":    api_secret,
        "exchange_info": get_exchange_info_cached(api_key, api_secret),
        "dual_side":     get_position_mode(api_key, api_secret) if (api_key and api_secret) else False,
        "account_info":  _acct,
        "long_count":    threading.local(),
        "short_count":   threading.local(),
        "_signal_lock":  threading.Lock(),
        "_longs_this_cycle":  [0],
        "_shorts_this_cycle": [0],
        "journal_snapshot":   [],   # [FIX-R4] akan diisi di bawah setelah load_journal
        "quality_market_regime": quality_market_regime,
        "smc_btc_market_context": quality_market_regime.get("smc_btc_context"),
    }

    # [FIX-R3] load_journal() di bawah journal_lock — cegah race dengan sync thread
    # yang sedang memodifikasi journal in-memory sebelum save ke disk.
    # Setelah load, ambil snapshot untuk dibaca scan_pair() [FIX-R4].
    with journal_lock:
        load_journal()
        env["journal_snapshot"] = list(journal)
    update_closed_trades_result_r()

    with open_trades_lock:
        global open_trades
        journal_open = sum(1 for t in journal if t.get("status") in ("OPEN", "PENDING"))
        open_trades  = max(open_trades, journal_open)

    # Daily loss kill switch — hitung HARI INI saja (WIB UTC+7)
    tz_wib         = timezone(timedelta(hours=7))
    today_start    = datetime.now(tz_wib).replace(hour=0, minute=0, second=0, microsecond=0)
    today_start_ms = int(today_start.timestamp() * 1000)
    daily_R = sum(
        t.get("result_R", 0)
        for t in journal
        if t.get("result_R") is not None and t.get("timestamp", 0) >= today_start_ms
    )
    if daily_R <= DAILY_LOSS_LIMIT_R:
        # [V7.4-S1] Estimasi dollar loss: DAILY_LOSS_LIMIT_R trade full SL
        # dengan notional $50 dan SL rata-rata ~1% → ~$0.50/trade
        dollar_loss = abs(daily_R) * (FIXED_NOTIONAL_USDT * 0.01)
        send_telegram(
            f"🛑 [{BOT_TAG}] KillSwitch!\n"
            f"Daily R={daily_R:.2f} | ~${dollar_loss:.2f} estimasi loss hari ini"
        )
        log_line(f"killswitch daily_R={daily_R:.2f}")
        return

    if ENTRY_PAUSED:
        log_line("scan_skipped entry_paused=true")
        send_daily_report()
        if ENABLE_SHADOW_TRACKING and SHADOW_DAILY_REPORT_ENABLED:
            send_shadow_report()
        save_journal()
        return

    summary_lines = []
    signal_sent   = False

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        active_pairs = [p for p in PAIRS if p not in INVALID_PAIRS]
        futures = {executor.submit(scan_pair, pair, env): pair for pair in active_pairs}
        for fut in as_completed(futures):
            pair = futures[fut]
            try:
                res = fut.result()
                if res:
                    summary_lines.append(res)
                    if "signal_sent" in res:
                        signal_sent = True
            except Exception as e:
                log_line(f"scan_future_err {pair} {e}")

    # [BUGFIX V7.2.3] Hitung berapa pair yang ke-block oleh gate max_trades.
    # scan_pair() sengaja TIDAK log_line() per-pair untuk kasus ini (hindari
    # spam 91 baris identik/cycle), tapi efeknya: kalau open_trades >= limit,
    # log jadi kosong total tanpa penjelasan — bikin user bingung apakah bot
    # benar2 scan atau diam. Sekarang dirangkum dalam SATU baris di scan_done.
    max_trades_blocked = sum(1 for r in summary_lines if ": max_trades(" in r)
    quality_local_blocked = sum(1 for r in summary_lines if ": quality_local_block(" in r)
    quality_risk_blocked = sum(1 for r in summary_lines if ": quality_risk_block(" in r)

    # [FIX-13] signals_today: hitung hanya trade hari ini (bukan all-time)
    signals_today = sum(
        1 for t in journal
        if t.get("status") in ("OPEN", "PENDING", "SIMULATED")
        and t.get("timestamp", 0) >= today_start_ms
    )
    log_line(
        f"scan_done signals_today={signals_today} "
        f"signals_cycle={sum(1 for r in summary_lines if 'signal_sent' in r)} "
        f"open={open_trades} active={len(active_pairs)} "
        f"max_trades_blocked={max_trades_blocked}/{len(active_pairs)} "
        f"quality_market={quality_market_regime.get('direction')} "
        f"breadth={quality_market_regime.get('bull_count', 0)}B/"
        f"{quality_market_regime.get('bear_count', 0)}S "
        f"quality_blocked={quality_local_blocked}L/{quality_risk_blocked}R"
    )
    if TERMINAL_CYCLE_LOG_ENABLED:
        print(
            f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] "
            f"scan_done | signals_cycle={sum(1 for r in summary_lines if 'signal_sent' in r)} "
            f"| open={open_trades} | active_pairs={len(active_pairs)}"
        )
    if max_trades_blocked == len(active_pairs) and max_trades_blocked > 0:
        log_line(
            f"NOTE: SEMUA pair ke-block gate max_trades "
            f"({open_trades}/{MAX_CONCURRENT_TRADES}) — strategi tidak dievaluasi "
            f"cycle ini, tunggu salah satu trade close."
        )

    send_daily_report()
    if ENABLE_SHADOW_TRACKING and SHADOW_DAILY_REPORT_ENABLED:
        send_shadow_report()
    save_journal()

# ---------------------- SHUTDOWN ----------------------
_shutdown_event = threading.Event()

def _handle_shutdown(signum, frame):
    print("\n🛑 Stopping bot...")
    log_line("shutdown_signal_received")
    _shutdown_event.set()

signal.signal(signal.SIGINT,  _handle_shutdown)
signal.signal(signal.SIGTERM, _handle_shutdown)

def interruptible_sleep(seconds):
    deadline = time.time() + seconds
    while time.time() < deadline:
        if _shutdown_event.is_set():
            return
        time.sleep(min(1.0, deadline - time.time()))

# ---------------------- RUN FOREVER ----------------------
def run_forever(run_interval_min=15, api_key=None, api_secret=None):
    RUN_INTERVAL_SEC = run_interval_min * 60
    backoff = 0

    # [V7.2] Refresh pair universe PALING AWAL — sebelum log/telegram startup,
    # supaya jumlah pair yang dilaporkan akurat (bukan angka fallback statis).
    # Endpoint publik, tidak butuh api_key — aman dipanggil meski SIMULATE.
    log_line("pairs_refresh: fetching dynamic pair universe...")
    refresh_dynamic_pairs(api_key, api_secret)

    log_line(f"startup V7.4 pairs={len(PAIRS)} fixed_notional=${FIXED_NOTIONAL_USDT:.0f} tp1_rr={TP1_RR} tp2_rr={TP2_RR}")
    print("")
    print("=" * 60)
    print(f"KT Auto Trading Bot {BOT_TAG} is RUNNING")
    print(f"Mode       : {'SIMULATE / DRY RUN' if SIMULATE else 'REAL TRADING'}")
    print(f"Pairs      : {len(PAIRS)}")
    print(f"Interval   : {run_interval_min} minute(s)")
    print(f"Workers    : {MAX_WORKERS}")
    print(f"Notional   : ${FIXED_NOTIONAL_USDT:.0f}/trade")
    print(f"Telegram   : {'ON' if TELEGRAM_BOT_TOKEN else 'OFF'}")
    print(f"Started UTC: {utc_now().isoformat().replace('+00:00', 'Z')}")
    print("Tekan Ctrl+C untuk stop bot dengan aman.")
    print("=" * 60)
    print("")
    _hours_str = (
        f"{TRADING_HOUR_START_UTC:02d}:00–{TRADING_HOUR_END_UTC:02d}:00 UTC"
        if ENABLE_TIME_FILTER else "24 jam (filter jam OFF)"
    )
    send_telegram(
        f"🚀 [{BOT_TAG}] Bot V7.4 started!\n"
        f"Pairs: {len(PAIRS)} (dynamic, vol≥${MIN_PAIR_VOLUME_USDT/1e6:.0f}jt) | "
        f"Interval: {run_interval_min}m | Workers: {MAX_WORKERS}\n"
        f"Notional/trade: ${FIXED_NOTIONAL_USDT:.0f} | TP1: 1:1 | TP2: 2:1 | "
        f"Daily limit: {DAILY_LOSS_LIMIT_R}R\n"
        f"SR_MIN_TOUCHES: {SR_MIN_TOUCHES} | SR_LOOKBACK: {SR_LOOKBACK}×4H | "
        f"Sector filter: {ENABLE_SECTOR_FILTER}\n"
        f"Funding MAX: {FUNDING_RATE_MAX_LONG:.4f} | Active hours: {_hours_str}"
    )
    load_journal()
    load_control_state()
    load_breakout_state()
    load_shadow_trades()
    if TELEGRAM_COMMANDS_ENABLED:
        start_telegram_command_thread(api_key, api_secret)
    else:
        log_line("telegram_command_worker_disabled")
    log_line("startup_alltime_report_suppressed: use /alltime")
    validate_pairs_on_startup()

    if api_key and api_secret and not SIMULATE:
        # [V7.1-FIX1] sync_time() HARUS jalan paling awal, sebelum request
        # authenticated apapun (start_sync_thread, sync_account_to_journal,
        # get_position_mode di main_cycle). Bug lama: sync_time() hanya
        # dipanggil di dalam while loop, SETELAH semua startup sync di atas
        # sudah jalan dengan TIME_OFFSET_MS=0 — memicu -1021 "timestamp
        # outside recvWindow" di request authenticated pertama.
        log_line("time_sync: syncing clock before any authenticated request...")
        sync_time()

        start_sync_thread(api_key, api_secret)
        _be_t = threading.Thread(target=_be_monitor_worker, daemon=True, name="be-monitor")
        _be_t.start()
        log_line("be_monitor_thread_started interval=30s")

        # [FIX-R1] Sync SINKRONUS sebelum cycle pertama — eliminasi race condition.
        # Tanpa ini, main_cycle() bisa jalan lebih dulu dari sync thread,
        # membaca journal stale: trade OPEN/CLOSED saat offline belum direkonsiliasi.
        log_line("startup_sync: reconciling journal before first cycle...")
        log_line("startup_sync_notice_suppressed")
        try:
            sync_account_to_journal(api_key, api_secret)
            log_line("startup_sync_done")
        except Exception as _e:
            log_line(f"startup_sync_err {_e}")

        # [FIX-R2] Resume poll threads untuk PENDING trade dari sesi lalu.
        _resume_pending_pollers(api_key, api_secret)

        # OpenAI live market analysis runs in an isolated shadow-only thread.
        # It never calls order functions and never sends Binance credentials
        # or account data to OpenAI.
        start_live_ai_market_thread(api_key, api_secret)

        # [FIX-R5] Kirim rekap hari ini segera setelah restart (tidak tunggu EOD).
        log_line("startup_daily_report_suppressed: use /report")

    while not _shutdown_event.is_set():
        start = time.time()
        try:
            sync_time()   # tetap di-refresh tiap cycle untuk jaga akurasi clock
            main_cycle(api_key, api_secret)
            backoff = 0
        except Exception as e:
            if _shutdown_event.is_set():
                break
            log_line(f"main_cycle_err {e}\n{traceback.format_exc()[:500]}")
            backoff = min(600, (backoff or 60) * 2)
            interruptible_sleep(backoff)

        if _shutdown_event.is_set():
            break

        elapsed   = time.time() - start
        sleep_for = RUN_INTERVAL_SEC - (elapsed % RUN_INTERVAL_SEC)
        if sleep_for > 0:
            log_line(f"sleeping {sleep_for:.0f}s")
            interruptible_sleep(sleep_for)

    print("\n✅ Bot V7.4 stopped.")
    log_line("bot_stopped_gracefully")

# ---------------------- CLI ----------------------
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="V7.4 Swing Bot — Fixed Notional + Dual TP")
    parser.add_argument("--simulate",       action="store_true")
    parser.add_argument("--max-workers",    type=int,   default=8,
                        help="Worker threads (rekomendasi 8 untuk ~60-100 pair dynamic)")
    parser.add_argument("--run-interval",   type=int,   default=15)
    parser.add_argument("--api-key",        type=str,   default=None)
    parser.add_argument("--api-secret",     type=str,   default=None)
    # [V7.4-S1] CLI untuk fixed notional (menggantikan --risk-usdt)
    parser.add_argument("--notional",       type=float, default=None,
                        help="Ukuran posisi tetap dalam USDT (default 50.0). "
                             "Contoh: --notional 100 untuk buka posisi $100/trade.")
    # --risk-usdt dipertahankan untuk backward compat, tapi tidak berpengaruh pada sizing
    parser.add_argument("--risk-usdt",      type=float, default=0.50,
                        help="[DEPRECATED V7.4] Tidak lagi mengatur sizing. "
                             "Sizing sekarang via --notional. Dipertahankan untuk compat.")
    # [FIX-2] CLI untuk Telegram bot token
    parser.add_argument("--telegram-token", type=str,   default=None,
                        help="Telegram Bot Token. Bisa juga via env: TELEGRAM_BOT_TOKEN.")
    # [V7.2] CLI untuk kontrol dynamic pair universe
    parser.add_argument("--min-pair-volume", type=float, default=None,
                        help="Volume 24h minimum (USDT) agar pair masuk universe scan "
                             "(default 15,000,000 = $15jt/hari).")
    parser.add_argument("--max-pairs",       type=int,   default=None,
                        help="Batas maksimum jumlah pair di universe dynamic (default 100).")
    parser.add_argument("--static-pairs",   action="store_true",
                        help="Matikan dynamic pair refresh, pakai FALLBACK_STATIC_PAIRS saja.")
    args = parser.parse_args()

    SIMULATE             = args.simulate
    MAX_WORKERS          = max(1, min(20, args.max_workers))
    run_interval         = max(1, args.run_interval)
    if args.notional is not None:
        FIXED_NOTIONAL_USDT = max(5.0, args.notional)   # [V7.4-S1] minimum $5

    # [V7.2] Dynamic pair universe config dari CLI
    if args.min_pair_volume is not None:
        MIN_PAIR_VOLUME_USDT = max(0, args.min_pair_volume)
    if args.max_pairs is not None:
        MAX_DYNAMIC_PAIRS = max(10, args.max_pairs)
    ENABLE_DYNAMIC_PAIRS = not args.static_pairs
    if args.static_pairs:
        PAIRS = list(FALLBACK_STATIC_PAIRS)
        log_line(f"static_pairs_mode count={len(PAIRS)} (dynamic refresh dimatikan)")

    # [FIX-2] Telegram token: CLI > env var
    if args.telegram_token:
        TELEGRAM_BOT_TOKEN = args.telegram_token
    # (jika tidak ada, TELEGRAM_BOT_TOKEN sudah diset dari os.getenv di atas)

    _cfg_binance = CONFIG_DATA.get("binance", {}) if isinstance(CONFIG_DATA.get("binance"), dict) else {}
    api_key    = args.api_key or os.getenv("BINANCE_API_KEY") or _cfg_binance.get("api_key")
    api_secret = (
        args.api_secret
        or os.getenv("BINANCE_API_SECRET")
        or os.getenv("BINANCE_SECRET_KEY")
        or _cfg_binance.get("api_secret")
        or _cfg_binance.get("secret_key")
    )

    if not api_key or not api_secret:
        print("ERROR: API key tidak ditemukan.")
        print("  python v3_swing_bot.py --api-key KEY --api-secret SECRET")
        exit(1)

    if not TELEGRAM_BOT_TOKEN:
        print("WARNING: TELEGRAM_BOT_TOKEN tidak diset.")
        print("  Set via: --telegram-token YOUR_TOKEN")
        print("  atau env: set TELEGRAM_BOT_TOKEN=YOUR_TOKEN")
        print("  Bot tetap jalan tapi tanpa notif Telegram.")
        print()

    log_line(f"starting V7.4 SIMULATE={SIMULATE} MAX_WORKERS={MAX_WORKERS} "
             f"pairs_fallback={len(PAIRS)} fixed_notional=${FIXED_NOTIONAL_USDT:.0f} "
             f"tp1_rr={TP1_RR} tp2_rr={TP2_RR} "
             f"min_pair_volume=${MIN_PAIR_VOLUME_USDT:,.0f} max_pairs={MAX_DYNAMIC_PAIRS} "
             f"dynamic_pairs={ENABLE_DYNAMIC_PAIRS}")
    run_forever(run_interval, api_key, api_secret)
