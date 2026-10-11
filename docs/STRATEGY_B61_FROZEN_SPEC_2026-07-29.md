# KT Strategy B6.1 Asymmetric Expansion-Acceptance Frozen Specification

Date frozen: 2026-07-29

## Why B6.1 Exists

B6.0 used a 2-hour structural trigger. Its recent-development funnel produced
97 armed expansions, 17 accepted events, and only 9 trades with a valid natural
stop. The primary result was +0.581R with PF 1.126, while its neighbor lost
-4.872R. B6.0 therefore failed before prior validation or untouched holdout.

B6.1 changes the hypothesis rather than merely changing one threshold:

- Strategy B is asymmetric because B5.1 showed continuation evidence only on
  the SHORT side.
- A 1-hour trigger restores enough observations for validation.
- Completed 4-hour breadth and non-positive BTC 12-hour return prevent SHORT
  entries against a rising broad market.
- Multi-candle acceptance replaces first-touch retest entry.
- Cost-aware natural stops and the B6 portfolio overlay remain mandatory.
- LONG is diagnostic only and cannot be promoted by this specification.

## Frozen Primary

Candidate: `B61_SHORT_EXPANSION_ACCEPTANCE`

- Side: SHORT only.
- Trigger: completed 1-hour candles aggregated from four contiguous 15-minute
  candles.
- Local regime: completed 4-hour 3-of-4 vote, minimum score 3.
- Core breadth: BTC, ETH, SOL, BNB, and XRP; net score at most -2.
- BTC completed 12-hour return: at most 0%.
- Donchian lookback: 36 completed 1-hour candles.
- Level age: 8 through 18 completed 1-hour candles.
- Compression: latest 6 versus 24 pre-break true-range medians, ratio at most
  0.92.
- Break: 0.06 through 1.15 ATR beyond the level.
- Break range: 0.75 through 2.60 ATR.
- Body at least 0.42 and directional close position at least 0.62.
- Participation: volume ratio at least 1.05 or directional flow at least 0.52.
- Acceptance: at least 3 of 4 closes below the level within 8 completed
  15-minute candles; failure no deeper than 0.30 ATR back above the level;
  final progress 0.08 through 1.25 ATR; directional flow at least 0.50.
- Structural stop buffer: 0.60 trigger ATR above the level and beyond the
  acceptance-window extreme.
- Natural stop: at least 0.80% and less than 2.20%.
- Portfolio: maximum two concurrent B6 positions and one new same-side signal
  per rolling 60 minutes.

## Frozen Neighbor

Candidate: `B61_SHORT_EXPANSION_ACCEPTANCE_NEIGHBOR`

The neighbor keeps the same hypothesis but uses:

- 30-hour channel;
- level age 6 through 20;
- compression ratio at most 0.96;
- break range 0.70 through 2.80 ATR;
- slightly looser candle, participation, and acceptance thresholds;
- 0.55 trigger-ATR stop buffer;
- natural stop less than 2.40%.

The neighbor is only a robustness test and cannot replace the primary after
prior validation is inspected.

## Validation Protocol

- Recent 2025-10-25 through 2026-07-22 is the design period.
- Prior 2024-10-25 through 2025-10-24 is the first B6.1 validation period.
- The 2023-10-25 through 2024-10-24 holdout remains unopened unless every
  development and prior-validation check passes.
- Historical passing authorizes forward shadow only, never immediate live
  orders.

