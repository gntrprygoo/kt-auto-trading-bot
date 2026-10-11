# Strategy G - Broad Flow Absorption

Status: `FROZEN_BEFORE_DEVELOPMENT_RUN`

Strategy G tests whether unusually aggressive taker flow that fails to move price
in the same direction contains a selective reversal edge. It is independent of
the rejected residual-momentum family and remains research-only.

## Single frozen rule

- Universe: BTCUSDT, ETHUSDT, XRPUSDT, SOLUSDT, DOGEUSDT, ADAUSDT.
- Prior one-hour return z-score absolute value at least `0.75`.
- Current 15-minute taker imbalance absolute value at least `0.18` and aligned
  with that prior one-hour move.
- Current volume at least `1.40` times its prior 24-hour mean.
- Current candle closes opposite aggressive flow, body at least 30% of range,
  and close in the confirming outer 35% of the range.
- Trade in the candle direction, opposite aggressive flow.
- Entry at next 15-minute open.
- Initial risk: max of signal-candle structural invalidation, `1.30 ATR14`, and
  `0.75%`; reject risk greater than `2.50%`.
- Target: `+1.25R`; time stop: four hours.
- Maximum one Strategy G position across the universe.
- Baseline/stress round-trip cost: `0.14%` / `0.20%`.

## Chronology

- Development: verified common history through 2025-08-31 UTC.
- Validation: 2025-09-01 through 2026-02-28 UTC.
- Final holdout: 2026-03-01 onward.

## Development gate

- At least 50 trades.
- Baseline total R positive and profit factor at least 1.20.
- Stress total R positive and profit factor at least 1.10.
- At least four of six assets positive after baseline costs.
- At least 55% of active months positive.
- Maximum drawdown no greater than 10R.

## Validation gate

- At least 10 trades.
- Baseline total R positive and profit factor at least 1.15.
- Stress total R non-negative.
- At least three assets positive.
- Maximum drawdown no greater than 6R.

## Holdout gate

- At least eight trades.
- Baseline total R positive and profit factor at least 1.10.
- Stress total R non-negative.
- Maximum drawdown no greater than 6R.

Even a full historical pass permits forward shadow only. Because this setup is
rare, no live review is allowed before at least 40 independently closed forward
signals.
