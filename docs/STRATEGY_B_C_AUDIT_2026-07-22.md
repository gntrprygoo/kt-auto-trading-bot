# KT Strategy B and C Audit - 2026-07-22

> Superseded for Strategy C by `STRATEGY_B_C_OPTIMIZATION_2026-07-22.md`.
> Strategy B remains paused; validated C6 is now enabled for forward shadow only.

## Executive decision

- Strategy A remains live with the `V8.1-SIDE-AWARE` quality gate.
- Strategy B is paused for new live entries.
- Strategy C remains paused for new shadow entries.
- Existing Binance positions, protective SL/TP orders, journal records, and
  historical shadow records are not changed.
- Old Strategy B pending states remain stored as audit evidence, but are ignored
  by the live scanner and cannot block Strategy A.

This is a risk-control decision. Signal frequency is not increased when the
available evidence does not show a stable out-of-sample edge.

## Data and method

- Production journal and scanner snapshot: VPS data captured 2026-07-22.
- Replay market data: public Binance Futures klines.
- Universe: 30 liquid USDT perpetual pairs, including the five core pairs.
- Replay window: 2026-04-23 through 2026-07-22.
- Chronological split: train before 2026-06-07, validation from 2026-06-07.
- Outcomes were checked at fixed 1R and 2R targets without claiming that replay
  fills exactly reproduce live fees, slippage, latency, or intrabar ordering.

## Strategy B production evidence

| Metric | Result |
|---|---:|
| Journal records | 7 |
| Closed trades | 6 |
| Win / loss | 3 / 3 |
| Win rate | 50.0% |
| Total R | -0.027R |
| Average R | -0.004R |
| Profit factor | 0.992 |
| Pending cancelled | 1 |

The observed live sample is small and approximately break-even. It is not
enough to establish an edge or justify relaxing filters.

Scanner evidence contained 20 historical breakout detections, 10 expirations,
3 states consumed by entries, and 8 pending states in the latest snapshot.

## Strategy B root cause

The live scanner calculated support/resistance from `closed_4h`, a window that
already included breakout candles C1 and C2. The S/R function then selected a
new resistance above the latest close or a new support below it.

That creates a logical lock:

- bullish C1 is required to close above resistance plus a buffer, while that
  resistance has already moved above C1/C2;
- bearish C1 is required to close below support minus a buffer, while that
  support has already moved below C1/C2.

The 90-day replay reproduced this exactly: the current-level implementation
generated zero new breakout candidates. The corrected implementation freezes
S/R using only candles before C1, C2, and the still-open candle.

## Strategy B replay

| Candidate | Setups | Train 1R | Validation 1R | All 1R | Decision |
|---|---:|---:|---:|---:|---|
| Current moving level | 0 | 0R | 0R | 0R | Invalid implementation |
| Anchored level, current strict guards | 5 | 0R | -3R | -3R | Reject |
| Anchored, taker-ratio orderflow | 11 | +1R | 0R | +1R | Insufficient |
| Anchored, no orderflow gate | 29 | +4R | -3R | +1R | Reject |
| Anchored, sweep exempt, no orderflow | 41 | +3R | -2R | +1R | Reject |

The most selective corrected candidate produced only 11 trades. Its validation
segment was flat at 1R and lost 4R at the 2R target. LONG validation was also
negative. Removing more filters increased frequency but made validation
negative. None of the variants was robust across train, validation, target, and
direction, so the corrected engine is retained as research code and not enabled
for live orders.

## Strategy C audit

Current status: paused. Historical Strategy C v1 shadow records contain 16
closed trades: 2 wins, 14 losses, and -28.04R, with 2 old records still open at
the snapshot time. Those old records remain observable; no new C entry is
recorded.

Strategy C v2 funnel:

| Funnel stage | Count |
|---|---:|
| Pair-side scans | 97,944 |
| Liquidity sweeps | 755 |
| Valid 4H locations | 300 |
| MSS confirmations | 17 |
| FVG confirmations | 6 |
| Final retest plus RR | 0 |

Strategy C v3 90-day research result:

| Target model | Trades | Win rate | Total R |
|---|---:|---:|---:|
| Structural target | 51 | 15.7% | -12.70R |
| Fixed 1R | 51 | 37.3% | -13R |
| Fixed 1.5R | 51 | 25.5% | -18.5R |
| Fixed 2R | 51 | 19.6% | -21R |

C2 is too restrictive, while C3 creates more setups without a positive edge.
Neither version should be activated merely to produce more alerts.

## Production changes

1. Added an explicit `strategy_b.enable_live=false` kill switch.
2. Added a pre-C1/C2 anchored S/R helper and regression coverage.
3. Disabled consumption and expiration of archived B pending states while B is
   paused.
4. Kept Strategy A independent from archived B pending states.
5. Kept `smart_money_c.enable_shadow=false`.
6. Added `A LIVE | B PAUSED | C PAUSED` to the Telegram `/status` response.

## Deployment verification

- Local regression suite: 32 tests passed.
- Python compile and JSON parsing: passed.
- Staging and production SHA-256 checksums: identical.
- VPS service: active and running, restart count 0.
- First production cycle: completed across 30 active pairs.
- Binance sync after restart: 3 positions, 0 pending, 3 journal opens.
- Post-restart log: no traceback, polling conflict, or scan error.
- Telegram admin audit update: delivered once.
- Rollback backup: `/opt/kt-auto-trading-bot/backups/deploy-v81-20260722T024329Z`.

## Re-entry criteria

Strategy B or C should return only as shadow tracking first. A candidate should
not become live until it has, at minimum:

- positive train and validation results after estimated costs;
- at least 30 closed forward shadow samples;
- profit factor above 1.20 with controlled drawdown;
- no dependence on one pair, one direction, or one short market regime;
- deterministic tests for candle closure, level anchoring, state expiry, and
  order lifecycle.

Historical results and replay are not a guarantee of future performance.
