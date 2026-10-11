# KT Indicator Foundation Audit - 2026-07-29

## Executive decision

- The EMA calculation is mathematically correct and uses confirmed candles.
- The production S/R algorithm is retained; its clustered replacement failed
  the prior-market validation period.
- The stricter EMA trend and 15m EMA pullback profiles are rejected.
- A narrow S/R safety correction is approved:
  - S/R distance is now independent of a pair's nominal price.
  - A rejection wick must interact with the selected S/R level on the same
    candle.
- This is a quality and drawdown improvement, not a guarantee of profit.

## Runtime trace

The audit followed data from Binance klines through the live entry decision.

1. Binance returns the currently forming candle as the final item.
2. `scan_pair()` removes that item for both 15m and 4H calculations.
3. EMA55 trend, ATR, S/R, volume, and orderflow use confirmed candles.
4. Strategy C receives raw arrays but its detector excludes the incomplete
   candle internally.
5. Breakout reference levels are frozen before C1 and C2.

No live lookahead or incomplete-candle use was found in the current Strategy A
EMA/S/R path.

## Findings

### EMA

The EMA implementation uses an SMA seed followed by the standard recursive
exponential update. EMA55 slope is normalized against the prior EMA. Unit tests
confirmed the calculation.

The 15m EMA21 was calculated in `scan_pair()` but did not affect entry. The
runtime comment also incorrectly described a one-tick passive limit offset as
an EMA pullback. The dead calculation and misleading wording were removed.

Adding a real 15m EMA pullback gate did not improve cross-regime performance,
so it remains inactive.

### S/R

The legacy S/R implementation has known design limitations:

- its touch count counts nearby candle highs/lows rather than distinct pivot
  events;
- when no qualifying pivot exists, it falls back to the lookback extreme;
- fixed percentage zones do not fully adapt to volatility.

A clustered, distinct-pivot, ATR-aware replacement was tested rather than
assumed to be better. It performed well in the recent period but failed badly
in the prior period, so it was not promoted.

Two objective bugs were confirmed:

1. `near_level()` tripled tolerance for prices below `0.001`, making identical
   percentage structures behave differently based only on nominal price.
2. A candle could satisfy the wick-shape rule without its wick touching the
   S/R level being traded.

Both defects are corrected without replacing the main S/R algorithm.

## Frozen replay protocol

- Universe: 30 established Binance Futures USDT pairs.
- Development: 2025-10-25 through 2026-07-22, 270 days.
- Prior-market validation: 2024-10-25 through 2025-10-24, 365 days.
- Total observation span: 635 days.
- Entry: next 15m open after a confirmed signal.
- Cost: 0.14% round-trip fee plus slippage.
- Management: TP1 at 1R for 50%, TP2 at 2R for 50%, +1.5% trigger,
  +1% SL lock, and 96-hour timeout.
- Conservative same-candle ordering: an already active stop is evaluated first.
- Variants were frozen before either replay result was inspected.

The replay isolates indicator foundations. It does not reproduce spread
availability, funding availability, global concurrency, sector caps, or exact
limit-order fills.

## Results

### Development 270 days

| Variant | Trades | Net R | PF | Max DD |
|---|---:|---:|---:|---:|
| Legacy parity | 235 | +24.930R | 1.321 | 7.691R |
| S/R wick touches level | 112 | +18.162R | 1.448 | 6.481R |
| Clustered S/R | 53 | +14.433R | 1.857 | 6.753R |
| Clustered S/R + strict EMA | 37 | +6.749R | 1.496 | 6.324R |
| Clustered + strict EMA + 15m pullback | 27 | +4.043R | 1.393 | 5.197R |

### Prior-market validation 365 days

| Variant | Trades | Net R | PF | Max DD |
|---|---:|---:|---:|---:|
| Legacy parity | 229 | -5.416R | 0.945 | 19.583R |
| S/R wick touches level | 123 | +0.847R | 1.016 | 13.944R |
| Clustered S/R | 69 | -11.738R | 0.687 | 16.934R |
| Clustered S/R + strict EMA | 49 | -8.604R | 0.675 | 13.270R |
| Clustered + strict EMA + 15m pullback | 34 | -10.509R | 0.496 | 14.156R |

### Combined approved correction

| Metric | Legacy | S/R touch correction |
|---|---:|---:|
| Trades | 464 | 235 |
| Net R | +19.513R | +19.009R |
| Avg R/trade | +0.0421R | +0.0809R |
| Profit factor | 1.111 | 1.202 |
| Max drawdown | 19.583R | 13.944R |
| Worst 30-day fold | -6.055R | -4.686R |

The correction retained almost the same total modeled R with roughly half the
turnover, increased average expectancy and profit factor, and reduced maximum
drawdown. Combined long performance was +11.471R with PF 1.338. Combined short
performance was +7.537R with PF 1.125.

The prior-period short side remained marginal at PF 0.972. It must be monitored
forward and is not evidence of a guaranteed edge.

## Operational status

- Strategy A production runtime version: `V8.2-SR-TOUCH`.
- Strategy B: remains paused.
- Strategy C6: remains shadow-only.
- S/R clustered replacement: rejected.
- Strict EMA replacement: rejected.
- Existing SL/TP and profit-protection rules: unchanged.
- VPS deployment completed at 2026-07-29 13:53 WIB with rollback backup:
  `/opt/kt-auto-trading-bot/backups/deploy-v82-sr-touch-20260729T065309Z`.
- Post-deploy status: active, one worker, zero systemd restarts, current
  heartbeat, and no warning-level journal entries.
- The pre-existing global entry state remains paused by a Telegram command
  issued at 2026-07-29 12:35 WIB. Position management remains active. New
  entries require an explicit `/resume`.

Research and gate artifacts:

- `tools/audit_indicator_foundation.py`
- `tools/evaluate_indicator_foundation_gate.py`
- `tests/test_indicator_foundation_audit.py`
- `tests/test_indicator_foundation_gate.py`
- `.audit/2026-07-29-indicator-foundation/foundation_gate.json`
