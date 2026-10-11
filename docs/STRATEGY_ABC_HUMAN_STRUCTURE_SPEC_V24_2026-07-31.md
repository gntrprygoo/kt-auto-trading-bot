# Strategy ABC V2.4 Human Structure Specification

Date: 2026-07-31  
Status: frozen research hypothesis  
Engine: `ABC_V24_HUMAN_EXCLUSIVE`  
Production impact: none

## Purpose

V2.4 translates the user's A/B/C market model into one exclusive state
machine:

- A is a reaction at an active support or resistance boundary.
- B is an accepted breakout followed by a completed, held retest.
- C is a liquidity sweep or failed breakout that reclaims the same active
  level and confirms a market-structure shift.

This document defines structure classification. It does not prove that the
entries have a profitable edge.

## Evidence Boundary

The specification uses structured adjudication dataset `82ccd32d0703`:

- 36 charts reviewed;
- 35 accepted;
- 1 skipped;
- A: 14;
- B: 10;
- C: 11.

The export passed completeness and field-consistency checks. It did not
establish stable path ground truth:

- agreement with the old machine path: 34.48%;
- agreement with the first human review: 22.86%;
- agreement with machine direction: 72.41%;
- 21 of 35 labels, or 60%, satisfied more than one old minimum path rule.

Therefore, the adjudication is a specification input and training sample. It
is not an independent validation sample.

## Information Clock

Every decision uses only information available at the assessment candle:

- macro levels: completed 1D levels derived from completed 4H candles;
- active range: completed 4H structure;
- trigger: completed 15m candles;
- entry simulation: next 15m open.

Future candles, P&L, OI, funding, and calendar results cannot alter the path
assigned at the signal candle.

## Core Identity

Every lifecycle must retain:

- one `range_id`;
- one active `level_id`;
- one parent transition;
- one direction;
- one current state.

A breakout, retest, sweep, reclaim, and MSS count as one setup only when they
belong to the same active level lineage. Similar price action at a different
level cannot complete the lifecycle.

## Current-State Semantics

Checklist fields must describe the state still valid at the assessment candle,
not whether an event happened at any earlier point on the chart.

Examples:

- `breakout_accepted = YES` means acceptance remains valid now;
- a breakout that later re-enters the old range is no longer an active B;
- a sweep counts for C only if it is tied to the active boundary and followed
  by reclaim and MSS;
- an A reaction that later becomes a qualifying sweep is no longer an active
  A candidate.

## Exclusive Precedence

At one assessment candle, use this precedence:

1. completed C;
2. completed B;
3. completed A;
4. incomplete or no setup.

This precedence is not retroactive. A B event can be valid when its retest
holds and later transition into C if acceptance fails. Both events may exist
at different timestamps, but only one state is active at each timestamp.

## Path A

Required:

- active 4H balance and valid boundary;
- support reaction for LONG or resistance reaction for SHORT;
- reaction candle passes the frozen volume and candle-quality rules;
- no active accepted breakout;
- no qualifying same-level sweep during confirmation;
- MSS confirmation under the frozen confirmed-A rule.

Invalidation:

- accepted breakout replaces the range reaction lifecycle;
- qualifying same-level sweep promotes the lifecycle to C confirmation;
- penetration beyond the frozen maximum sweep depth invalidates the pending A;
- expiry without MSS returns the machine to range monitoring.

Target remains the opposite range boundary for diagnostics only.

## Path B

Required:

- expansion closes outside the active resistance for LONG or support for SHORT;
- acceptance reaches the frozen two-of-three outside-close rule;
- acceptance remains valid;
- retest touches the exact broken `level_id`;
- retest closes and holds outside the old range;
- frozen volume and reaction-quality rules pass.

Invalidation:

- re-entry into the old range before B confirmation converts the lifecycle to
  failed-breakout C confirmation;
- re-entry after a B event converts it to failed-B C confirmation;
- waiting for retest is incomplete B, not valid B;
- expiry without a valid retest returns to range monitoring.

## Path C

C has three allowed parents:

1. direct active-boundary sweep;
2. A reaction that develops a same-level sweep;
3. failed breakout or failed B acceptance.

Required:

- penetration of the active level within the frozen sweep-depth range;
- reclaim of that same level;
- directional displacement;
- MSS beyond the frozen local structure level;
- parent transition and `level_id` preserved.

Direction:

- sweep below support, reclaim above, bullish MSS: LONG;
- sweep above resistance, reclaim below, bearish MSS: SHORT;
- failed upside B, reclaim below, bearish MSS: SHORT;
- failed downside B, reclaim above, bullish MSS: LONG.

## Frozen Parameter Policy

V2.4 inherits every numeric parameter from `ABC_V21_COMBINED`.

Only two semantic switches change:

- `allow_failed_b_c = True`;
- `c_supersedes_a_on_same_level_sweep = True`.

No ATR, volume, range width, acceptance count, RR, cost, SL, or target value
was selected from the adjudication outcome.

## Context Policy

Calendar phase, macro bias, OI, and funding remain recorded context only.
They are not hard filters in V2.4.

Historical subgroup results may generate a future hypothesis, but they cannot
be added to this detector without a new pre-registered test and untouched
data.

## Promotion Gate

V2.4 cannot enter live or forward shadow from the adjudication set or the
2019-2026 replay. Promotion requires genuinely unseen observations and both:

- a structure gate with stable human-machine path and direction agreement;
- an outcome gate positive after baseline and stress costs.

Until both pass, V2.4 remains research-only.
