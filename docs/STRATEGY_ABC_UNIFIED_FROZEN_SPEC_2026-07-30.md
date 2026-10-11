# KT Unified A/B/C Structure Engine

Date frozen: 2026-07-30

Status: historical research only. Existing live Strategy A remains unchanged,
Strategy B remains paused, and Strategy C remains on its previous shadow
version until this specification passes its frozen gates.

## Core Model

A, B, and C are states of one market structure, not independent scanners:

1. **A, range reaction:** price respects an established support or resistance.
2. **B, accepted breakout:** a boundary breaks, price is accepted outside it,
   and the old boundary holds on retest.
3. **C, liquidity sweep or failed breakout:** price trades beyond a known
   boundary, cannot remain there, and reclaims the old structure.

A failed pullback is not automatically C. C requires a known liquidity
boundary, an excursion beyond it, failed acceptance, reclaim, and a directional
closed-candle reaction.

The logic is symmetric:

- LONG A at support, SHORT A at resistance.
- LONG B after resistance becomes support, SHORT B after support becomes
  resistance.
- LONG C after support liquidity is swept and reclaimed, SHORT C after
  resistance liquidity is swept and reclaimed.

## Information Clock

- Structure uses completed 4-hour candles only.
- Entries use completed 15-minute candles only.
- Entry is the next 15-minute open.
- The signal candle is excluded from ATR and volume baselines.
- Pivot levels require two completed candles to the left and right.
- Derivatives joins use latest-at-or-before timestamps.
- No nearest-time, centered rolling, or future-bar joins are allowed.

## Structure Map

- Lookback: 60 completed 4-hour candles.
- Confirmed pivot width: two candles left and two candles right.
- Pivot clusters: within 0.35 4-hour ATR.
- Minimum touches per level: two.
- Minimum containing range: 3 ATR.
- Maximum containing range: 18 ATR.
- Support and resistance are the best active clustered pair surrounding price.
- Zone half-width: 0.18 ATR.

Neighbor checks change the cluster and confirmation strictness, not the core
state definitions.

## Path A

A is admitted only when the containing range remains balanced:

- 20-bar directional efficiency no more than 0.40.
- Both boundaries were confirmed within the latest 40 four-hour candles.
- Range width no more than 10 ATR.
- Price touches the boundary zone without a qualifying sweep.
- The 15-minute reaction wick is at least 50% of candle range.
- Directional close position is at least 58%.
- Volume is at least 0.90 of its prior 32-bar median.

This distinction prevents a large momentum candle pressing through a level
from being mislabeled as a clean rejection.

## Path B

Breakout candidate:

- Close at least 0.12 15-minute ATR outside the frozen boundary.
- Directional body at least 50%.
- Directional close position at least 68%.
- Volume at least 1.10 of its prior 32-bar median.
- Initial extension no more than 1.50 ATR.

Acceptance:

- At least three of four completed 15-minute closes remain outside.
- Pending breakout expires after eight bars if acceptance is absent.

Retest:

- Return within 0.30 ATR of the old boundary.
- Close remains outside by at least 0.05 ATR.
- Directional close or rejection wick confirms the response.
- Volume is at least 0.85 of its prior median.
- Accepted retest window expires after 64 bars.

## Path C

Direct range sweep:

- Excursion between 0.08 and 0.90 ATR beyond a known boundary.
- Close reclaims the old range by at least 0.05 ATR.
- Directional close or rejection wick confirms the response.
- Volume is at least 1.05 of its prior median.

Failed B:

- A pending or accepted breakout closes back inside the old range by at least
  0.05 ATR.
- The opposite directional close or wick confirms reclaim.
- The frozen breakout extreme becomes the stop reference.

## Stops, Targets, and Replay

- Stop is beyond the reaction/sweep extreme and at least 0.15 ATR beyond the
  structural boundary.
- Risk below 0.4% or above 3.0% is rejected.
- Structural target is the opposite range boundary for A/C and the next known
  external level for B. B falls back to 2R if no external level exists.
- Minimum planned structural reward is 1.15R.

The promotion baseline uses the bot's current management:

- TP1 at 1R closes 50%.
- TP2 at 2R closes the remainder.
- A +1.5% favorable move activates the existing +1% SL lock.
- An already-active stop wins on ambiguous same-candle touches.
- Replay timeout is 96 hours and marks the remainder to market.
- Base round-trip fee plus slippage is 0.14%; stress cost is 0.20%.

The structural target result is diagnostic. It cannot replace current
management without a separately frozen management test and explicit approval.

## Calendar Hypothesis

Non-overlapping WIB windows:

- Days 1-8: proposed bearish prior.
- Days 9-15: proposed bullish prior.
- Days 16-25: proposed continuation prior.
- Day 26 through month-end: proposed correction prior.

Calendar never creates an entry. A phase can modify risk only when a
2020-present independent BTC audit has:

- At least 48 complete months.
- Median in the proposed direction.
- A 90% bootstrap median interval excluding zero in that direction.
- At least 60% annual direction stability.
- Portfolio profit factor improves by at least 0.03 without drawdown worsening
  by more than 1R.

## Derivatives Ablation

The frozen comparison uses the same derivatives-complete signals:

- M0: price, candle, and volume baseline.
- M1: OI and taker-flow soft risk weighting.
- M2: OI rising plus aligned taker-flow hard diagnostic.
- M3: funding/premium crowding veto diagnostic.

OI has no direction by itself. A soft modifier requires at least 100 eligible
trades across ten pairs, at least +0.03 profit-factor improvement, and no more
than 1R additional drawdown. A hard OI filter is not approved by this spec.

## Frozen Development Gate

Period: 2025-10-25 through 2026-07-22.

- At least 180 portfolio trades.
- Positive net R.
- Profit factor at least 1.20.
- Average net R at least +0.08R.
- Maximum drawdown no more than 12R.
- At least 60% positive non-empty 30-day folds.
- LONG and SHORT each have at least 50 trades, non-negative R, and profit
  factor at least 1.05.
- A and C each have at least 30 trades; B has at least 20.
- Every path has non-negative R and profit factor at least 1.00.
- Stress-cost net R is positive with profit factor at least 1.05.
- No pair contributes more than 25% of positive R.
- Tight and wide neighbors each have positive base and stress net R, with base
  profit factor at least 1.05.

Any failure keeps the unified engine out of shadow and live operation.

## Prior Validation Gate

This period remains closed unless every development check passes.

Period: 2024-10-25 through 2025-10-24.

- At least 150 portfolio trades.
- Positive net R and profit factor at least 1.10.
- Maximum drawdown no more than 15R.
- At least 55% positive non-empty 30-day folds.
- Stress net R non-negative with profit factor at least 1.00.
- At least 35 trades on each side.
- At least 15 trades from each path.

Passing development and prior validation permits forward shadow only. Live
activation remains a separate manual decision after at least 50 closed shadow
trades, 30 calendar days, positive net R, profit factor at least 1.10, and no
execution or risk-control incident.
