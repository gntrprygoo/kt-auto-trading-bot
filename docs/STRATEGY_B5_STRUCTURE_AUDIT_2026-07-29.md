# KT Strategy B5 Structure Audit - 2026-07-29

## Executive decision

- Strategy B remains `PAUSED_NO_VALIDATED_EDGE`.
- B5 and B5.1 are not admitted to forward shadow or live orders.
- The untouched 2023-2024 holdout was not opened.
- Strategy A, Strategy C, existing positions, SL, TP, and VPS service are
  unchanged.

Low B4 frequency was real, but it was not the only problem. Removing the
bottleneck exposed a negative base edge. Cost-aware and structural filters
improved B5.1, but the selected candidate still failed its frozen development
gate. Continuing to add filters would be data mining.

## B4 funnel diagnosis

Development funnel across 30 pairs:

| Stage | Events | Retained |
|---|---:|---:|
| 4H evaluations | 48,660 | 100.00% |
| Breakouts detected | 81 | 0.17% |
| BTC guard passed | 64 | 0.13% |
| First retest touched | 47 | 0.10% |
| First retest valid | 25 | 0.05% |
| Trades attached | 11 | 0.02% |

Of all 4H evaluations, 34,772 failed the strict trend match, 9,026 had no
price break, and 4,645 used a level that was too recent. The 4H trigger plus a
stack of mandatory `AND` filters made statistical validation impractically
slow.

## B5 structural change

B5 was implemented as a research-only engine:

1. Four-hour candles define the market regime through a 3-of-4 vote.
2. One-hour candles define an objective Donchian breakout level.
3. Breakout quality uses a transparent score while still requiring volume or
   taker-flow participation.
4. Fifteen-minute candles identify the first valid retest.
5. Entry uses the next 15-minute open.
6. Replay uses the bot's TP1, TP2, +1.5% trigger, +1% SL lock, and 96-hour
   timeout.
7. Round-trip fee plus slippage remains 0.14%.
8. ATR and volume baselines exclude the candle being evaluated.

This increased frequency without changing production.

## B5 baseline result

Period: 2025-10-25 through 2026-07-22, 30 pairs.

| Candidate | Trades | WR | Net R | PF | Max DD |
|---|---:|---:|---:|---:|---:|
| B5 Balanced | 626 | 42.97% | -99.476R | 0.745 | 109.451R |
| B5 Neighbor | 827 | 44.26% | -100.305R | 0.797 | 128.916R |
| B5 Strict | 226 | 40.71% | -42.517R | 0.698 | 47.553R |

B5 solved frequency but proved that unfiltered 1H breakout-retest had negative
net expectancy. It generated approximately +40.7R gross before the modeled
cost, then lost -99.476R net.

## Cost diagnosis

The structural stops were often too tight relative to a 0.14% round trip.
Because cost in R equals percentage cost divided by stop distance, small stops
made each trade expensive in risk units.

| Stop risk | Trades | Net R | PF |
|---|---:|---:|---:|
| 0.40-0.59% | 303 | -97.786R | 0.556 |
| 0.60-0.79% | 140 | -16.474R | 0.809 |
| 0.80-0.99% | 78 | +10.643R | 1.312 |
| 1.00-1.49% | 75 | +10.044R | 1.298 |

This supports a cost-aware minimum risk distance. It does not justify widening
stops artificially; the setup must naturally provide enough structural room.

## Frozen B5.1 candidates

Five rules were frozen before the second development period was evaluated.
The primary design was SHORT-only, used level age 8-15 hours, and accepted only
natural stop distances from 0.8% through less than 2.0%.

### Recent development: 270 days

| Candidate | Trades | Net R | PF | Max DD |
|---|---:|---:|---:|---:|
| Cost-aware SHORT | 116 | +30.798R | 1.730 | 12.405R |
| Mature SHORT | 52 | +10.742R | 1.555 | 9.175R |
| Mature SHORT Strict | 31 | +7.856R | 1.757 | 5.614R |
| Retest SHORT | 37 | +10.539R | 1.847 | 3.584R |

### Prior development: 365 days

| Candidate | Trades | Net R | PF | Max DD |
|---|---:|---:|---:|---:|
| Cost-aware SHORT | 196 | +14.353R | 1.156 | 20.685R |
| Mature SHORT | 77 | +3.460R | 1.095 | 12.743R |
| Mature SHORT Strict | 48 | +4.691R | 1.218 | 9.034R |
| Retest SHORT | 56 | -0.018R | 0.999 | 12.929R |

The selected `B51_MATURE_SHORT_STRICT` candidate combined:

- 79 trades over 635 days;
- annualized frequency: 45.43 trades;
- net result: +12.547R;
- average: +0.1588R;
- PF: 1.393;
- max drawdown: 9.034R;
- 25 traded pairs.

## Why it still failed

The frozen development gate required the worst active 30-day fold to be no
worse than -4R. The candidate produced -5.614R.

The loss was clustered. Four SHORT entries opened within 15 minutes on
2026-06-06 while BTC's 12-hour return was still +0.43%; all four hit SL.

Portfolio overlays did not solve the problem robustly:

| Overlay | Trades | Net R | PF | Max DD | Worst month |
|---|---:|---:|---:|---:|---:|
| Max 2 concurrent | 64 | +7.141R | 1.251 | 10.645R | -3.639R |
| Max 3 concurrent | 71 | +10.871R | 1.368 | 9.034R | -4.481R |

Max 2 fell below the frozen frequency and sample gate. Max 3 still failed the
loss-fold gate.

A stricter BTC SHORT alignment removed that cluster, but was not stable in the
prior period. Requiring BTC 12-hour return below -0.5% reduced the combined
sample to 32 trades over 635 days, approximately 18 trades per year. That
recreated B4's original sparse-sample problem.

## Interpretation

The evidence shows a structural trade-off:

- strict filters produce too few trades;
- broad filters expose a negative base edge;
- cost-aware SHORT filters create a modest edge but unstable clustered losses;
- stronger market alignment removes losses by collapsing frequency.

This is not an active runtime bug. It is insufficient and regime-dependent
expectancy in the breakout-retest hypothesis under the available candle and
taker-flow data.

## Operational outcome

- No B5 code was added to `v3_swing_bot_fixed.py`.
- No configuration value was enabled.
- No VPS file was uploaded.
- No systemd restart was performed.
- Strategy B must continue to appear as `PAUSED` in `/status`.

The untouched period from 2023-10-25 through 2024-10-24 remains unused. It
should be reserved for a materially different Strategy B hypothesis, not
another threshold variation of B4 or B5.

## Evidence

- `.audit/2026-07-29-strategy-b5/strategy_b5_development270.json`
- `.audit/2026-07-29-strategy-b5/strategy_b51_development270.json`
- `.audit/2026-07-29-strategy-b5/strategy_b51_development365.json`
- `.audit/2026-07-29-strategy-b5/strategy_b51_preholdout_diagnostic.json`
- `tools/research_strategy_b5.py`
- `tools/research_strategy_b51.py`
- `tools/evaluate_strategy_b51_gate.py`
- `tests/test_strategy_b5_research.py`
- `tests/test_strategy_b51_research.py`
- `tests/test_strategy_b51_gate.py`

## Research basis

- Binance USD-M Futures kline fields:
  https://developers.binance.com/en/docs/products/derivatives-trading-usds-futures/market-data/rest-api/Kline-Candlestick-Data
- Cost-aware walk-forward crypto evaluation:
  https://arxiv.org/abs/2606.00060
- Regime and parameter-robust crypto trend following:
  https://arxiv.org/abs/2602.11708
- Breakout regime alignment and data-snooping controls:
  https://papers.ssrn.com/sol3/papers.cfm?abstract_id=6898600

These sources support the evaluation method. They do not guarantee that a
specific implementation will remain profitable.
