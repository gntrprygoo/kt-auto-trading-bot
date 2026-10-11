# Strategy F v2 - Long Residual Momentum

Status: `FROZEN_BEFORE_VALIDATION`

Strategy F v1 development across 2021-01 through 2025-08 rejected all 12
two-sided candidates. One pre-validation diagnostic was sufficiently coherent to
form a new hypothesis: the strict eight-hour residual-momentum candidate was
positive only on the long side.

This v2 document freezes that hypothesis before validation is opened. The
candidate remains research-only and cannot place orders.

## Single frozen candidate

Name: `F2_LONG_RESIDUAL_MOMENTUM_8H`

- Assets: ETHUSDT and SOLUSDT only.
- Direction: long only.
- Market factor: BTCUSDT.
- Beta: trailing 14-day 15-minute-return beta, using prior bars only.
- Signal: four-hour beta-adjusted residual z-score at least `+2.00`.
- Flow confirmation: 15-minute normalized taker imbalance at least `+0.15`.
- Relative volume: at least `1.20` times its prior 24-hour mean.
- Candle: bullish body at least 25% of range and close in the top 40%.
- Trend: asset EMA96 above EMA384.
- BTC veto: BTC one-hour return z-score must not be below `-0.50`.
- Entry: next 15-minute bar open.
- Initial risk: max of `1.50 ATR14` and `0.75%` of entry, capped at `2.50%`.
- Target: `+1.75R`.
- Time stop: eight hours.
- Portfolio concurrency: one Strategy F v2 trade at a time.
- Baseline round-trip cost: `0.14%`.
- Stress round-trip cost: `0.20%`.

No parameter may change during validation or holdout.

## Frozen chronology

- Development: common data from 2021-01 through 2025-08-31 UTC.
- Validation: 2025-09-01 through 2026-02-28 UTC.
- Final holdout: 2026-03-01 onward.

The validation period may be opened only if the recomputed long-only development
candidate passes its gate. The final holdout may be opened only if validation
passes.

## Development gate

- At least 180 trades.
- Baseline total R positive and profit factor at least 1.15.
- Stress total R positive and profit factor at least 1.05.
- ETH and SOL both positive after baseline costs.
- At least 55% of active months positive.
- Baseline maximum drawdown no greater than 15R.

## Validation gate

- At least 18 trades.
- Baseline total R positive and profit factor at least 1.10.
- Stress total R non-negative.
- At least 50% of active months positive.
- Maximum drawdown no greater than 8R.

## Holdout gate

- At least 15 trades.
- Baseline total R positive and profit factor at least 1.05.
- Stress total R non-negative.
- Maximum drawdown no greater than 8R.

## Release rule

Passing all three historical stages permits forward shadow only. It does not
permit live orders. Forward shadow requires at least 30 independently closed
trades and a separate release review.
