# Strategy E Scalping Frozen Research Spec

Status: research only, no Binance orders, no forward shadow yet.

## Objective

Test whether a short-horizon edge survives chronological validation, realistic
execution assumptions, and pair diversification. Strategy E is independent of
Strategies A, B, C, and D1. Results from retired shadow experiments are not
used to select Strategy E trades.

## Frozen data design

- Symbols: BTCUSDT, ETHUSDT, SOLUSDT.
- Bar interval: 15 minutes.
- Development: start of available data through 2025-08-31 UTC.
- Validation: 2025-09-01 through 2026-02-28 UTC.
- Sealed holdout: 2026-03-01 through the end of available data.
- Entry: next candle open after a confirmed signal candle.
- If stop and target touch in one candle, stop wins.
- Only one Strategy E position per symbol at a time.
- Baseline round-trip cost: 0.14% of notional.
- Stress round-trip cost: 0.20% of notional.
- Funding is not modeled at this research stage. Maximum holding time is 3
  hours; forward shadow must record any observed funding separately.

The holdout must not be inspected unless one frozen candidate passes both the
development and validation gates without parameter changes.

## Frozen hypotheses

### E1 Compression Expansion

Trend-aligned close outside the previous intraday range after volatility
compression, confirmed by candle body, volume expansion, and directional
taker flow. Variants differ only in predeclared strictness and target.

- `E1_BALANCED_15R`
- `E1_STRICT_15R`
- `E1_STRICT_20R`

### E2 Sweep Reclaim

Short-horizon sweep of a previous 5-hour extreme followed by a close back
inside the range, with a dominant rejection wick, elevated volume, and
opposing taker aggression as an absorption proxy.

- `E2_RANGE_RECLAIM_12R`
- `E2_TREND_RECLAIM_15R`

### Round 2, frozen after Round 1 development rejection

Round 1 was rejected before validation because every candidate was negative
after costs. Development diagnostics showed that one-candle reclaim was close
to flat before costs but had a median stop near 0.5%, making turnover cost too
large in R. The following hypotheses require a second confirmed candle and
were frozen before they were run:

- `E3_FAILED_RANGE_15R`: expansion beyond a 5-hour range, then a confirmed
  close back through the broken level and expansion midpoint in a range regime.
- `E3_FAILED_ANY_20R`: the same two-stage failure without the range restriction
  and with a 2R target.
- `E4_JUMP_REVERSAL_15R`: a volume-backed candle larger than 2 ATR followed by
  an opposite close through its midpoint while price is extended from EMA96.

### Round 3, cost-distance test

Round 2 produced positive gross R on the two-stage patterns, but a median stop
of roughly 0.53% to 0.64% made all candidates negative after costs. Before
running Round 3, three final variants were frozen with a minimum 0.8% stop and
longer, still-intraday holding windows:

- `E3_FAILED_WIDE_15R`: failed expansion, 1.5R target, 4-hour maximum hold.
- `E4_JUMP_WIDE_125R`: jump reversal, 1.25R target, 4-hour maximum hold.
- `E4_JUMP_WIDE_15R`: jump reversal, 1.5R target, 6-hour maximum hold.

If these fail development after costs, the 15-minute Strategy E family is
rejected. No further parameter search may use the validation or holdout data.

### Round 4, independent session hypothesis

The event-based families above were rejected. A separate hypothesis is frozen
from documented intraday periodicity in crypto volume and volatility: a
one-hour opening range followed by a trend-aligned, volume-confirmed breakout.
Each symbol can take at most one trade per named session.

- `E5_ASIA_ORB_15R`: range 00:00-01:00 UTC, entries 01:00-07:00 UTC.
- `E5_EUROPE_ORB_15R`: range 07:00-08:00 UTC, entries 08:00-13:00 UTC.
- `E5_US_ORB_15R`: range 13:00-14:00 UTC, entries 14:00-21:00 UTC.

All use a minimum 0.8% risk distance, 1.5R target, next-candle-open entry, and
a maximum 6-hour hold. Session definitions are frozen before development is
run; no best-hour search is permitted.

These candidates use the same next-open execution, cost, stop-first, and
chronological gates. Validation and holdout remain sealed.

Kline taker-buy volume is not a historical order-book reconstruction. It is
treated only as a candle-level trade-flow proxy.

## Development gate

All checks must pass:

- at least 120 closed trades across the three symbols;
- baseline net R positive and profit factor at least 1.15;
- stress net R positive and profit factor at least 1.05;
- at least two of three symbols positive after baseline costs;
- at least 55% of non-empty months positive after baseline costs;
- baseline maximum drawdown no more than 20R.

Candidate ranking is by stress net R only among candidates that pass every
gate. A visually attractive candidate that fails one gate is rejected.

## Validation and holdout gates

The selected candidate is frozen before validation. Validation requires at
least 60 trades and the same profitability, diversification, monthly, and
drawdown checks. The holdout uses the identical frozen rules. Passing all
three periods allows only isolated forward shadow deployment, never immediate
live trading.

No backtest or forward result can guarantee future profit.
