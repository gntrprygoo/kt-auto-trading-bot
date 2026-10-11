# KT Strategy A/B/C v2.1 Frozen Hypotheses

Frozen before variant replay: 2026-07-30

Status: historical research only. No production, shadow, Telegram, VPS, SL, or
TP setting may change from this study.

## Calibration Boundary

Calibration period:

`2024-10-25 through 2025-10-24`

Chronological validation period:

`2025-10-25 through 2026-07-22`

Only calibration attribution was inspected before freezing these hypotheses.
Variant validation results must not be used to redefine the variants.

## Calibration Finding

The 31 non-overlapping calibration trades showed:

- A: 25 trades, -13.881R, PF 0.297.
- B: 1 trade, -1.195R.
- C: 5 trades, +0.918R, PF 1.418.
- LONG: 19 trades, -11.995R.
- SHORT: 12 trades, -2.162R.
- Macro-aligned entries performed worse than macro-opposed entries.
- Daily/4H confluence and freshness filters did not repair expectancy.

Therefore this study does not add an EMA, OI, calendar, session, side, or
profit-derived filter. It tests state-sequence corrections only.

## Frozen Variants

### V20 Baseline

Existing ABC v2 behavior, unchanged.

- A may emit from one completed boundary-reaction candle.
- B acceptance requires three of four closes outside.
- C may originate from an A boundary sweep or a failed B lifecycle.

Purpose: control.

### V21 Confirmed A

Only A changes.

- The initial range-boundary reaction creates `A_CONFIRMING`.
- The reaction records the exact A `level_id`, extreme, and four-bar
  pre-reaction micro-structure.
- A waits at most four completed 15m bars.
- Admission requires directional displacement and a close beyond the frozen
  micro-structure by 0.04 ATR.
- Volume, body, and close-position thresholds match the frozen C displacement
  confirmation.

Purpose: determine whether one-candle A reactions caused the dominant false
entries.

### V21 Faster B

Only B acceptance changes.

- Acceptance window changes from four bars to three.
- Required closes outside change from three to two.
- Breakout displacement, exact-level retest, stop, target, and all other rules
  remain unchanged.

Purpose: test whether B scarcity came from an unnecessarily long acceptance
window without removing acceptance.

### V21 Direct C

Only C provenance changes.

- C from a validated A boundary sweep remains enabled.
- C from pending, accepted, or emitted B failure is recorded as a failed
  lifecycle but is not admitted as a C event.
- Reclaim, displacement, MSS, and exact-level lineage remain mandatory.

Purpose: separate direct liquidity sweeps from failed-breakout reversals.

### V21 Combined

Combines exactly:

- Confirmed A;
- Faster B;
- Direct C only.

No additional parameter or filter is allowed.

## Replay Contract

- Symbol: BTCUSDT only.
- Level hierarchy: completed 1D and 4H.
- Trigger: completed 15m.
- Entry diagnostic: next 15m open.
- Production-compatible management:
  - TP1 1R/50%;
  - TP2 2R/50%;
  - +1.5% favorable trigger moves SL to +1%.
- Base round-trip cost: 0.14%.
- Stress cost: 0.20%.
- Structural target remains diagnostic.
- Calendar remains context only.
- OI, taker flow, funding, and premium remain excluded.

## Acceptance Standard

A variant must pass both calibration and validation independently:

- positive net R;
- profit factor at least 1.10;
- positive stress-cost net R;
- stress profit factor at least 1.00;
- at least 15 calibration and 15 validation trades;
- no more than 12R drawdown in either period;
- at least 50% positive non-empty 60-day folds in each period.

The combined 21-month result must also be positive after stress costs.

Any positive result with fewer than the required trades is classified
`INSUFFICIENT_SAMPLE`, not accepted.

Passing this outcome screen still does not bypass the human structure-label
gate.

