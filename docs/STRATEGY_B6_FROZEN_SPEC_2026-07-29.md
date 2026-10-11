# KT Strategy B6 Expansion-Acceptance Frozen Specification

Date frozen: 2026-07-29

## Purpose

Strategy B6 is a materially new continuation hypothesis. It does not assume
that every breakout continues. It only considers a trade when:

1. the local 4-hour trend and broad crypto market agree;
2. price compressed before the structural break;
3. the break expands range with directional participation;
4. several completed 15-minute candles accept the new side of the level;
5. the natural structural stop is large enough to survive modeled costs; and
6. portfolio controls prevent several correlated altcoin signals from being
   treated as independent risk.

No historical rule can predict the future or guarantee profit. B6 can only
estimate conditional expectancy from information available at each timestamp.

## Frozen Data Protocol

- Universe: the same 30 established Binance USDT perpetual pairs used by B4
  and B5.
- Recent development: 2025-10-25 through 2026-07-22.
- Prior development: 2024-10-25 through 2025-10-24.
- Untouched holdout: 2023-10-25 through 2024-10-24.
- The holdout must remain unopened unless every development check passes.
- Entry: next completed-signal 15-minute candle open.
- Baseline round-trip fee plus slippage: 0.14%.
- Cost stress: 0.20%.
- Same-candle active stop and target: active stop wins.
- Management: current TP1, TP2, +1.5% trigger, +1% SL lock, and 96-hour
  timeout.

## B6 Primary Rules

### Trend and breadth

- Local trend: 4-hour EMA21, EMA55, EMA55 slope, price location, and 12-hour
  return through the existing 3-of-4 regime vote.
- Broad market: completed 4-hour regimes for BTC, ETH, SOL, BNB, and XRP.
- At least three core markets must have valid context.
- Net breadth must be at least +2 for LONG or at most -2 for SHORT.

### Compression and expansion

- Structural trigger: completed 2-hour candles aggregated from contiguous
  15-minute candles.
- Donchian lookback: 24 completed 2-hour candles.
- Level age: 3 through 18 completed 2-hour candles.
- Compression: median true range of the latest 4 pre-break candles divided by
  the latest 20 pre-break candles must be at most 0.82.
- Break close: at least 0.08 ATR beyond the level and no more than 1.10 ATR
  beyond it.
- Break range: 1.05 through 2.80 ATR.
- Break body ratio: at least 0.48.
- Directional close position: at least 0.67.
- Participation: volume ratio at least 1.10 or directional taker-flow ratio at
  least 0.53.

### Acceptance

- Observe at most eight completed 15-minute candles after the 2-hour break.
- Evaluate a rolling four-candle window.
- At least three closes must remain beyond the broken level.
- No close may fail more than 0.30 ATR back through the level.
- Final close must progress at least 0.10 ATR beyond the level and no farther
  than 1.20 ATR to avoid chasing.
- Aggregate directional taker-flow ratio must be at least 0.51.
- Entry occurs at the next 15-minute open after acceptance.

### Stop and portfolio controls

- Stop is beyond both the acceptance-window extreme and a 0.30 trigger-ATR
  structural buffer behind the level.
- Natural stop distance must be at least 0.80% and less than 2.40%.
- Maximum two concurrent B6 positions in historical portfolio replay.
- At most one new same-side B6 position per rolling 60 minutes.
- Simultaneous signals are ranked only by information known at signal time.

## Frozen Neighbor

The neighbor changes parameters modestly without changing the hypothesis:

- 28-candle Donchian lookback;
- level age 3 through 20;
- compression ratio at most 0.88;
- break range 0.95 through 2.90 ATR;
- slightly looser candle and participation thresholds;
- acceptance may occur within ten 15-minute candles;
- stop buffer 0.35 trigger ATR;
- natural stop less than 2.60%.

The neighbor is a robustness test. It cannot replace the primary after results
are observed.

## Development Gate

Every check is mandatory:

- recent trades at least 30;
- prior trades at least 40;
- combined trades at least 85 and at least 45 annualized;
- both periods profitable;
- recent PF at least 1.25 and prior PF at least 1.20;
- combined PF at least 1.30 and average at least +0.10R;
- recent and prior drawdown each at most 10R;
- at least 55% of active 30-day folds profitable;
- worst active fold no worse than -4R;
- at least 15 traded pairs and top positive pair share at most 30%;
- LONG and SHORT each have at least 20 trades, positive net R, and PF at least
  1.05;
- 0.20% cost-stress result remains positive with PF at least 1.15;
- neighbor is profitable in both periods with combined PF at least 1.15.

## Holdout and Promotion Gate

Only after development passes:

- holdout trades at least 40 and at least 35 annualized;
- holdout net R positive, PF at least 1.20, and average at least +0.08R;
- holdout drawdown at most 9R;
- at least 50% of active folds profitable and worst fold no worse than -4R;
- at least 10 traded pairs and top positive pair share at most 35%;
- both sides remain represented and non-negative;
- cost stress and neighbor remain positive;
- all periods combined contain at least 125 trades, PF at least 1.25, average
  at least +0.10R, drawdown at most 14R, and positive cost-stress expectancy.

Passing historical gates authorizes `FORWARD_SHADOW` only. Live orders remain
blocked until at least 50 closed forward-shadow trades pass a separately
frozen forward gate.

