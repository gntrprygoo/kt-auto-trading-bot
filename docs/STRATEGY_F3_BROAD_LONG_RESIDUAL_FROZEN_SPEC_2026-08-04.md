# Strategy F v3 - Broad Long Residual Momentum

Status: `FROZEN_BEFORE_DEVELOPMENT_RUN`

Strategy F v2 found positive long residual momentum on ETH and SOL in extended
development, but failed its maximum-drawdown gate and showed uneven pair quality.
This v3 protocol tests breadth rather than selecting the best historical pair.

## Single frozen rule

The rule and execution parameters are identical to Strategy F v2:

- Factor: BTCUSDT.
- Tradable universe: ETHUSDT, XRPUSDT, SOLUSDT, DOGEUSDT, ADAUSDT.
- Direction: long only.
- Four-hour beta-adjusted residual z-score: at least `+2.00`.
- Taker imbalance: at least `+0.15`.
- Relative volume: at least `1.20`.
- Bullish candle with close in top 40% of its range.
- EMA96 above EMA384 on the traded asset.
- BTC one-hour z-score not below `-0.50`.
- Entry at next 15-minute open.
- Initial risk: max of `1.50 ATR14` and `0.75%`, capped at `2.50%`.
- Target: `+1.75R`; time stop: eight hours.
- Maximum one Strategy F v3 trade across the whole universe.
- Baseline/stress round-trip costs: `0.14%` / `0.20%`.

No pair-specific parameter or ranking adjustment is allowed.

## Chronology

- Development: common verified data from 2021-01 through 2025-08-31 UTC.
- Validation: 2025-09-01 through 2026-02-28 UTC.
- Final holdout: 2026-03-01 onward.

## Development gate

- At least 350 trades.
- Baseline total R positive and profit factor at least 1.15.
- Stress total R positive and profit factor at least 1.05.
- At least four of five traded assets positive after baseline costs.
- At least 55% of active months positive.
- Baseline maximum drawdown no greater than 20R.

## Validation gate

- At least 35 trades.
- Baseline total R positive and profit factor at least 1.10.
- Stress total R non-negative.
- At least three of five assets positive.
- At least 50% of active months positive.
- Maximum drawdown no greater than 10R.

## Holdout gate

- At least 25 trades.
- Baseline total R positive and profit factor at least 1.05.
- Stress total R non-negative.
- At least three of five assets non-negative.
- Maximum drawdown no greater than 10R.

Passing all historical gates permits forward shadow only, followed by at least
30 independently closed trades and a separate live-release review.
