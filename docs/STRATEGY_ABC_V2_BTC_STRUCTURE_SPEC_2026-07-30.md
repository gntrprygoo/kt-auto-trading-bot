# KT Strategy A/B/C v2: BTC Structure Lineage

Date frozen: 2026-07-30

Status: **research-only**. This specification cannot place orders, modify the
production bot, or activate Strategy B/C.

## Objective

Translate the user's two-year BTC market observation into a reviewable,
closed-candle state model before evaluating profitability.

The model treats A, B, and C as transitions of the same validated level:

1. A is a reaction at a validated range boundary.
2. B is expansion, acceptance, and retest of that exact boundary.
3. C is a liquidity sweep of an A boundary or a failed B lifecycle, followed
   by reclaim, directional displacement, and micro-structure shift.

No path may invent an unrelated level during a transition.

## Information Clock

- Macro levels: completed 1D candles aggregated from six completed 4H candles.
- Structure and range state: completed 4H candles.
- Trigger and confirmation: completed 15m candles.
- Entry diagnostic: next 15m open after the signal candle.
- Current signal candles are never used to create their own pivot level.
- Daily and 4H pivots require completed right-side confirmation bars.

## Level Hierarchy

Every admitted level records:

- stable `level_id`;
- source timeframe: `1D`, `4H`, or `1D+4H`;
- source and confirmation timestamps;
- pivot type;
- distinct touch count;
- age in completed 4H bars;
- post-confirmation test count;
- freshness: `FRESH`, `TESTED`, or `WEAK`;
- median volume-at-level ratio;
- quality score;
- ATR-derived zone width.

Daily levels receive higher structural weight. A 4H-only level requires at
least three distinct touches. Weak or low-score levels cannot form an A range.

The active range has a stable `range_id` derived from its support and resistance
`level_id` values. A new range must persist across two structure updates before
adoption.

## A: Validated Range Reaction

A is eligible only when:

- price remains inside an established support/resistance pair;
- 4H directional efficiency is at most 0.38;
- at least 72% of the latest 30 completed 4H closes remain inside the range;
- range width is between 3 and 18 4H ATR;
- neither boundary is weak;
- the range has been monitored for at least 16 completed 15m bars;
- the trigger touches the boundary zone, closes back inside, and has a
  directional close or rejection wick;
- trigger volume is at least 0.95 of its prior 32-bar median.

One transition key can emit only once for the same range lifecycle.

## B: Expansion, Acceptance, and Exact-Level Retest

B originates only from a boundary of the active A range.

Breakout displacement requires:

- close at least 0.15 15m ATR outside the frozen boundary;
- directional body at least 58%;
- directional close position at least 72%;
- volume at least 1.15 of its prior median;
- initial extension no more than 1.35 ATR.

Acceptance requires at least three of four completed closes outside the frozen
level. Retest must touch that exact `level_id`, close outside the old range,
and provide a directional reaction. The lifecycle retains a unique breakout
transition ID.

After B emits, its frozen level remains monitored for 16 bars so a failed B can
transition to C with the B `event_id` as its parent.

## C: Inherited Liquidity Failure

C has no independent scanner.

Valid sources:

- `A_BOUNDARY`: an active A range boundary is swept and reclaimed.
- `FAILED_B`: a pending, accepted, or emitted B lifecycle loses its frozen
  breakout level.

After the initial sweep/reclaim, C waits up to four completed 15m bars for:

- directional displacement body at least 50%;
- directional close position at least 66%;
- volume at least 1.05 of its prior median;
- close beyond the pre-sweep four-bar micro-structure by 0.04 ATR.

The resulting C event must contain the parent range, breakout, A event, or B
event identifier. A C event without lineage is invalid by construction.

## Exclusivity

The machine has one active mode:

- `RANGE`;
- `BREAKOUT_PENDING`;
- `BREAKOUT_ACCEPTED`;
- `B_HOLD_MONITOR`;
- `SWEEP_CONFIRMING`.

One closed candle can produce at most one event. Breakout, retest, sweep, and
failure states cannot run as parallel independent scanners.

## Risk and Exit Contract

This research does not change the existing production management:

- TP1 at 1R closes 50%;
- TP2 at 2R closes the remainder;
- a +1.5% favorable move activates the existing +1% SL lock;
- active stop wins ambiguous same-candle ordering.

Structural targets are diagnostic only. They cannot replace production SL/TP
without a separate frozen management study and explicit approval.

## Context Policy

- Calendar phase is recorded as context only.
- OI, taker flow, funding, and premium are not joined.
- None of these can filter an entry or modify risk before the price-structure
  label and outcome gates pass.

## Human Structure Gate

The first gate is agreement with the user's chart judgment, not P&L:

- at least 100 reviewed candidates;
- at least 60 emitted-event labels;
- at least 20 A, 10 B, and 10 C emitted labels;
- at least 30 near-boundary controls;
- at least 70% exact overall path precision;
- at least 65% precision per covered path;
- no more than 20% of controls contain a valid setup missed by the engine.

Failure requires a rule or level-detector revision. It must not trigger
parameter searching against P&L.

## Outcome Gate

Only after the human structure gate passes:

- at least 50 non-overlapping BTC trades;
- positive net R;
- profit factor at least 1.15 after base costs;
- average net R at least +0.05R;
- maximum drawdown no more than 12R;
- at least 55% positive non-empty chronological 30-day folds;
- positive stress-cost net R with profit factor at least 1.05;
- each A/B/C path has at least ten trades, non-negative R, and profit factor at
  least 1.00.

Passing both gates permits a separate forward-shadow review. It does not permit
live activation.

