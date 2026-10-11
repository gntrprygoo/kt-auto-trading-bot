# KT Strategy Quality Audit - 2026-07-22

## Executive decision

- Live entry Jalur A/B upgraded to `V8.1-SIDE-AWARE`.
- New Strategy C entries are paused. Existing shadow records remain intact and
  open shadow trades continue to be evaluated until completion.
- Market breadth is retained as telemetry, not used as a mandatory entry gate.
- No existing Binance position, SL, or TP was changed by this deployment.

## Production evidence

Audit window: 2026-07-16 to 2026-07-22.

| Metric | Result |
|---|---:|
| Closed trades | 25 |
| Win rate | 48.0% |
| Total R | -4.880R |
| Profit factor | 0.639 |
| LONG | 5 trades, -0.702R |
| SHORT | 20 trades, -4.178R |

The production sample confirms directional imbalance: 80% of the audited
trades were SHORT and most of the negative result came from that side.

## V8.1 replay evidence

Source: public Binance Futures klines, 30 liquid USDT perpetual pairs, 90-day
window. The data was divided chronologically into train and validation segments.

| Rule | Trades | WR | Total R | Train | Validation |
|---|---:|---:|---:|---:|---:|
| Baseline | 312 | 52.2% | +14R | - | - |
| Old market + score 2/3 proposal | 119 | 47.9% | -5R | -8R | +3R |
| V8.1 side-aware | 103 | 59.2% | +19R | +12R | +7R |
| V8.1 + SL below 3% | 72 | 63.9% | +20R | +13R | +7R |

Selected live rules:

1. Use confirmed 4H candles only.
2. LONG requires EMA21 above EMA55 and strict HH+HL structure.
3. SHORT requires EMA21 below EMA55.
4. SHORT is rejected when price is below 40% of its confirmed 30-candle 4H
   range. This specifically prevents continued shorting near the bottom.
5. Any new setup with raw SL distance at or above 3% is rejected.
6. The tradable universe is capped at 30 liquid pairs while retaining BTC,
   ETH, SOL, BNB, and XRP.

## Strategy C decision

C2 produced no final setup in its observed funnel:

| Funnel stage | Count |
|---|---:|
| Pair-side scans | 97,944 |
| Liquidity sweeps | 755 |
| Valid 4H locations | 300 |
| MSS confirmations | 17 |
| FVG confirmations | 6 |
| Final retest + RR | 0 |

Relaxing C2 into the C3 research candidate increased signal count but did not
create a stable edge over the 90-day replay:

| C3 target model | Trades | WR | Total R |
|---|---:|---:|---:|
| Structural target | 51 | 15.7% | -12.70R |
| Fixed 1R target | 51 | 37.3% | -13R |
| Fixed 1.5R target | 51 | 25.5% | -18.5R |
| Fixed 2R target | 51 | 19.6% | -21R |

Therefore C3 is retained as research code only and is not activated. Loosening
the current C setup simply to generate alerts would add noise, not quality.

## Deployment verification

- VPS service: `active (running)`
- Restart count: `0`
- Active universe: 30 pairs
- Existing live positions after restart: 3
- Strategy C new entries: disabled
- Unit tests: 27 passed
- Python compile and JSON validation: passed
- Rollback backup created before replacement

## Limitations and next checkpoint

Historical replay is not a profit guarantee. It simplifies real fills and may
not fully capture fees, slippage, latency, order-book changes, or changing market
regimes. V8.1 should be judged on a fresh forward sample, not on one or two
trades. The next strategy review should use at least 30 newly closed V8.1 trades
and report side, entry path, realized R, fees, maximum favorable excursion, and
maximum adverse excursion.
