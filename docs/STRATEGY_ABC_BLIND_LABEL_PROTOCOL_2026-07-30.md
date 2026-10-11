# Strategy ABC Blind Structure-Label Protocol

Date: 2026-07-30  
Status: mandatory research gate  
Production impact: none

## Purpose

This protocol checks whether the structure engine identifies the same support,
resistance, direction, and A/B/C transition that a human reviewer identifies.
It does not use P&L to decide whether a chart is structurally valid.

The answer key uses the frozen `ABC_V21_COMBINED` structure engine. The
V2.3 6-10 ATR rule remains a separate outcome/admission filter for A. This
separation prevents an outcome-selected width threshold from defining the
human ground truth.

## Blind Review

The workbench does not display:

- whether a candidate is an engine event or a control;
- the engine's expected A/B/C path;
- the engine's expected direction;
- the engine transition name;
- level scores, macro bias, calendar phase, or outcome.

Candidate IDs are anonymized. The answer key is stored in a separate JSON file
and is used only by the evaluator after labels are exported.

Only the chart, candidate time, active level, support, and resistance are
visible.

## Decisions

- `VALID_A`: valid reaction at a range support or resistance boundary, with no
  accepted breakout.
- `VALID_B`: breakout is accepted beyond the exact level and the subsequent
  retest holds.
- `VALID_C`: a liquidity sweep or failed breakout reclaims the inherited level
  and confirms a market-structure shift.
- `NO_SETUP`: no valid A, B, or C setup exists at the candidate time.
- `LEVEL_WRONG`: the displayed support, resistance, or active level is wrong.
- `DIRECTION_WRONG`: a valid setup exists, but the machine direction is wrong.
- `SETUP_INCOMPLETE`: the expected sequence is not complete at the candidate
  time.
- `SKIP`: the chart cannot be judged with sufficient confidence.

## Outcome Protection

Aftermath is unavailable until a decision is saved. Once aftermath is shown,
the decision is locked. This prevents a known result from changing a structure
label.

## Dataset Feasibility

The builder must prove that the selected review set can satisfy:

- at least 20 emitted A examples;
- at least 10 emitted B examples;
- at least 10 emitted C examples;
- at least 30 control examples.

The old 21-month dataset had only three B examples and was therefore
mathematically unable to pass. The first replacement replay over 2020-2026
produced A=18, B=19, and C=39. It fixed B coverage but remained two A examples
short.

Before loading any additional candles, the available-history review start was
frozen at 2019-09-01. This extension exists only to improve label coverage. No
strategy parameter or gate threshold may change after the added period is read.

## Label Gate

- At least 100 accepted labels.
- At least 60 emitted-event labels.
- Overall exact A/B/C precision at least 70%.
- Per-path precision at least 65% after minimum coverage.
- At least 30 labeled controls.
- Overall and per-path control false-negative rate no greater than 20%.

Each path receives a separate gate result. A path may proceed to forward shadow
review only when its own structure gate passes and its historical evidence is
not negative under stress. This never authorizes live deployment.
