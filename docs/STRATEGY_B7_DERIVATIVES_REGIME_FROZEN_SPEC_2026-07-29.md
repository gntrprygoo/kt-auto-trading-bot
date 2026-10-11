# KT Strategy B7 Derivatives-Regime Frozen Specification

Date frozen: 2026-07-29

Status at freeze: research only; Strategy B live remains paused.

## Hypothesis

B6 showed that price-only expansion and acceptance did not survive cost and
neighbor robustness. B7 tests a materially different claim:

> A directional one-hour expansion has better continuation quality when the
> pair is a cross-sectional price leader or laggard, outstanding contracts are
> increasing, aggressive taker flow agrees, and funding/premium are not already
> crowded in the same direction.

This is a conditional research hypothesis, not a claim that open interest or
funding predicts every move.

## Information Clock

- Evaluate only after a completed one-hour candle.
- Use only price, metrics, premium, and settled funding with timestamps less
  than or equal to the decision time.
- Execute at the next available 15-minute open.
- Require at least 20 pairs with valid features at the same decision time.
- A pair is ineligible until all required feature warmups exist.

## Frozen Features

### Price Leadership

Using completed one-hour closes:

- `r24 = log(close_t / close_t-24h)`
- `r72 = log(close_t / close_t-72h)`
- Normalize each return by realized volatility over its matching window.
- Composite momentum is `0.60 * normalized_r24 + 0.40 * normalized_r72`.
- Rank the composite cross-sectionally across valid pairs.

Primary eligibility:

- LONG: momentum percentile at or above 80%.
- SHORT: momentum percentile at or below 20%.

### Expansion Event

- LONG closes above the highest high of the previous 12 completed one-hour
  candles.
- SHORT closes below the lowest low of the previous 12 completed one-hour
  candles.
- Signal candle body is at least 55% of its range.
- Directional close position is at least 70% toward the breakout side.
- Signal quote volume is at least its prior 24-hour median.

The current candle is excluded from every prior-window calculation.

### Derivatives Confirmation

- Compute 12-hour percentage change in `sum_open_interest`, not
  `sum_open_interest_value`, to avoid mechanically counting price appreciation
  as new contracts.
- Require open-interest change above zero.
- Require its cross-sectional percentile at or above 60%.
- Aggregate taker ratio over the latest three completed hourly metric rows.
- LONG requires taker ratio at or above 1.05.
- SHORT requires taker ratio at or below `1 / 1.05`.

### Crowding Veto

- Funding z-score uses the previous 90 settled funding events, including the
  latest event available at the decision time.
- LONG is vetoed when funding z-score is above +1.5.
- SHORT is vetoed when funding z-score is below -1.5.
- Premium z-score uses the previous 168 completed one-hour premium closes.
- LONG is vetoed when premium z-score is above +2.0.
- SHORT is vetoed when premium z-score is below -2.0.
- Zero-variance or missing windows are ineligible, not treated as neutral.

### Dispersion Guard

- At each decision time, calculate cross-sectional standard deviation of
  24-hour returns.
- Compare it with the prior 30-day hourly dispersion distribution.
- Veto new entries above the prior distribution's 90th percentile.
- The current dispersion observation is excluded from its threshold.

This guard is frozen because published evidence on crypto momentum is mixed
and indicates strong state dependence. It is not a threshold selected from B7
trade outcomes.

## Entry, Stop, and Management

- Entry: next 15-minute open after the completed one-hour signal.
- ATR: 14 completed one-hour candles.
- LONG stop: the lower of signal low minus 0.10 ATR or entry minus 1.25 ATR.
- SHORT stop: the higher of signal high plus 0.10 ATR or entry plus 1.25 ATR.
- Reject risk below 0.4% or above 3.0% of entry.
- TP1: 1R, closes 50%.
- TP2: 2R, closes the remaining 50%.
- Existing protection remains: at +1.5% favorable movement, move stop to +1%
  from entry; TP1/TP2 are not altered.
- Maximum replay holding period: 96 hours, then mark to market.
- An already-active stop wins when stop and target are touched in the same
  15-minute candle.

## Portfolio Controls

- Pair cooldown: 24 hours after an admitted signal.
- Maximum two concurrent B7 positions.
- At most one new same-side entry in the same one-hour decision bucket.
- Simultaneous candidates are ordered by momentum distance from the median,
  then open-interest percentile, then deterministic pair name.
- No result-based pair whitelist or blacklist is allowed.

## Frozen Neighbor Family

Only the momentum admission percentile changes:

- Primary `B7_DERIVATIVES_P20`: LONG >= 80%, SHORT <= 20%.
- Tight `B7_DERIVATIVES_P15`: LONG >= 85%, SHORT <= 15%.
- Wide `B7_DERIVATIVES_P25`: LONG >= 75%, SHORT <= 25%.

All other features, costs, entries, stops, exits, and portfolio controls are
identical. Neighbors are robustness checks and cannot replace the primary
after results are seen.

## Cost Model

- Base round-trip fee plus slippage: 0.14% of notional.
- Stress cost: 0.20% of notional.
- Funding payments are reported separately and included in the final B7 net
  result before promotion. Their sign is determined from side and each funding
  event crossed while the position is open.

## Frozen Gates

### Development Gate

Period: 2025-10-25 through 2026-07-22.

- At least 120 admitted portfolio trades.
- Total net R above zero.
- Profit factor at least 1.25.
- Average net R at least +0.10R.
- Maximum drawdown no more than 8R.
- At least three of four equal-time folds positive.
- At least 20 traded pairs.
- No pair contributes more than 25% of positive R.
- LONG and SHORT each have at least 30 trades and profit factor at least 1.05.
- At 0.20% cost: total net R above zero and profit factor at least 1.10.
- Tight and wide neighbors each have positive net R, profit factor at least
  1.05, and non-negative stress-cost net R.

Failure keeps Strategy B paused. Thresholds are not retuned on the same period.

### Prior Validation Gate

Open only if every development check passes.

Period: 2024-10-25 through 2025-10-24.

- At least 100 admitted trades after feature availability.
- Total net R above zero and profit factor at least 1.10.
- Maximum drawdown no more than 10R.
- At least three of five equal-time folds positive.
- Stress-cost profit factor at least 1.00.
- Both sides remain represented.

### Final Historical Holdout

The 2023-10-25 through 2024-10-24 window remains unopened unless development
and prior validation pass. Because the universe was selected later, even a
holdout pass is labeled fixed-universe historical evidence, not pristine
out-of-sample proof.

### Forward Shadow

Historical admission allows shadow only. Live consideration requires:

- At least 50 closed forward-shadow trades.
- At least 30 calendar days.
- Net R above zero and profit factor at least 1.10 after observed costs and
  funding.
- Maximum drawdown no more than 8R.
- No data-staleness, duplicate-order, orphan-order, or risk-control incident.

Live activation remains a separate manual decision.

## Research Integrity

- No production bot code, configuration, journal, API key, or live order is
  changed by B7 research.
- Missing derivatives data fails closed.
- Failed candidates are documented; they are not renamed as successful.
- Profit consistency cannot be promised. The goal is a reproducible,
  risk-controlled conditional edge that survives unseen data.
