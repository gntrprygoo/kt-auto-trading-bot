# Strategy F2R - Risk-Controlled Long Residual Momentum

Status: `FROZEN_BEFORE_VALIDATION`

Strategy F2R does not change Strategy F v2 signals, entries, stops, targets, or
cost assumptions. It addresses the sole failed development gate by expressing
drawdown at a fixed account-risk budget.

## Frozen signal

The signal is exactly `F2_LONG_RESIDUAL_MOMENTUM_8H`:

- ETHUSDT and SOLUSDT, long only, BTC factor.
- Four-hour beta-adjusted residual z-score at least +2.00.
- Taker imbalance at least +0.15 and relative volume at least 1.20.
- Bullish candle, EMA96 above EMA384, BTC one-hour z-score not below -0.50.
- Next 15-minute open entry.
- Initial market stop distance: max of 1.50 ATR14 and 0.75%, capped at 2.50%.
- Target +1.75R, time stop eight hours.
- Baseline/stress round-trip cost 0.14% / 0.20%.
- Maximum one position.

## Frozen account risk

- Risk per accepted trade: `0.35%` of current account equity at the initial stop.
- No martingale, averaging down, or leverage-based risk increase.
- Position quantity is derived from stop distance and the 0.35% risk budget.
- Historical account-return estimates compound neither wins nor losses; they are
  conservative linear risk-budget equivalents for gate comparison.

Sizing does not change trade R, profit factor, win rate, or signal selection. It
only maps R drawdown into account drawdown.

## Chronology

- Development: common history through 2025-08-31 UTC.
- Validation: 2025-09-01 through 2026-02-28 UTC.
- Final holdout: 2026-03-01 onward.

## Development gate

- At least 180 trades.
- Baseline total R positive and PF at least 1.15.
- Stress total R positive and PF at least 1.05.
- ETH and SOL both positive.
- At least 55% of active months positive.
- Account-equivalent baseline maximum drawdown no greater than 8%.

## Validation gate

- At least 18 trades.
- Baseline total R positive and PF at least 1.10.
- Stress total R non-negative.
- At least 50% of active months positive.
- Account-equivalent maximum drawdown no greater than 4%.

## Holdout gate

- At least 15 trades.
- Baseline total R positive and PF at least 1.05.
- Stress total R non-negative.
- Account-equivalent maximum drawdown no greater than 4%.

Passing all historical stages permits forward shadow only. It cannot place live
orders before at least 30 independently closed shadow trades and a separate
release decision.
