# KT Strategy B6.2 Trend-Runner Frozen Specification

Date frozen: 2026-07-29

## Hypothesis

B6.0 showed that a strict 2-hour expansion trigger was too sparse. B6.1 showed
that 1-hour SHORT expansion-acceptance could identify some continuation, but
its fixed TP2 management left the primary negative and the neighbor only
marginally positive.

B6.2 tests one new structural claim: a continuation signal requires a convex
trend-following exit. The signal rules are frozen from the already-defined
`B61_SHORT_EXPANSION_ACCEPTANCE_NEIGHBOR`; no signal threshold is selected
again after validation. Only the exit architecture changes.

## Signal

- SHORT only.
- All B6.1 neighbor rules for 4-hour local trend, five-core breadth, BTC
  12-hour direction, 1-hour compression and expansion, 15-minute acceptance,
  natural stop, and portfolio clustering remain unchanged.
- Entry remains the next 15-minute open after acceptance.

## Primary Trend Management

Candidate: `B62_SHORT_TREND_RUNNER_2_5`

- Initial structural stop is unchanged.
- TP1 at 1R closes 35% of the position.
- There is no fixed TP2.
- Existing absolute profit protection remains: after +1.5% favorable movement,
  stop moves to +1% from entry.
- At +2R favorable excursion, the remaining position activates a completed
  1-hour Chandelier trail.
- Trail distance: 2.5 times completed 1-hour ATR.
- Trail only moves in the profitable direction and becomes active only when it
  protects price beyond entry.
- Maximum holding period: 5 days; remaining exposure is marked to market.
- An already-active stop wins if several events occur in the same 15-minute
  candle.

## Frozen Exit Neighbors

- `B62_SHORT_TREND_RUNNER_2_0`: 2.0 ATR trail.
- `B62_SHORT_TREND_RUNNER_3_0`: 3.0 ATR trail.

Both neighbors use exactly the same signals and entry prices. They are
robustness checks, not replacements selected after validation.

## Validation

- 2025-10-25 through 2026-07-22 remains the design period.
- 2024-10-25 through 2025-10-24 is validation and must not change B6.2 rules.
- 2023-10-25 through 2024-10-24 remains unopened unless all development and
  validation gates pass.
- Passing historical tests allows forward shadow only. Live orders remain
  disabled until a separately frozen 50-trade forward-shadow gate passes.
