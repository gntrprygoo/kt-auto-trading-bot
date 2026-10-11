# Unified A/B/C Structure Audit

Date: 2026-07-30

Decision: **development failed; no shadow or live integration**.

## What Was Tested

The research engine implements the user's market model as one sequence:

`A range reaction -> B accepted breakout and retest -> C failed breakout or
liquidity sweep and reclaim`.

The implementation is closed-candle and leakage-safe:

- 4H confirmed pivot clusters build S/R.
- 15m candles drive transitions and entries.
- The signal candle is excluded from ATR and volume baselines.
- Entry is the next 15m open.
- Costs, TP1/TP2, SL+, ambiguous-candle ordering, and portfolio limits match
  the existing replay model.

Frozen specification:
`docs/STRATEGY_ABC_UNIFIED_FROZEN_SPEC_2026-07-30.md`.

## Development Result

Period: 2025-10-25 through 2026-07-22.

Universe: 30 fixed pairs, all loaded without replay errors.

| Metric | Primary result | Frozen requirement |
|---|---:|---:|
| Trades | 1,926 | at least 180 |
| Net R | -267.025R | positive |
| Average R | -0.139R | at least +0.08R |
| Profit factor | 0.758 | at least 1.20 |
| Max drawdown | 267.055R | no more than 12R |
| Positive 30-day folds | 0/10 | at least 60% |
| Stress net R | -405.071R | positive |

Path results:

| Path | Trades | Net R | Profit factor |
|---|---:|---:|---:|
| A, range reaction | 589 | -95.938R | 0.728 |
| B, accepted breakout/retest | 160 | -9.264R | 0.891 |
| C, sweep/failed breakout | 1,177 | -161.823R | 0.758 |

Tight and wide neighbors also lost money. The failure is broad rather than one
bad pair, one side, or one month.

## BTC Calendar Audit

The proposed WIB windows were tested on 77 complete months from 2020:

| Phase | Full-history median | 90% bootstrap median interval | Robust |
|---|---:|---:|---|
| Days 1-8 | +1.288% | -0.621% to +2.588% | no |
| Days 9-15 | +1.467% | -0.572% to +2.687% | no |
| Days 16-25 continuation | +1.193% | -0.898% to +3.209% | no |
| Day 26 to month-end | +0.404% | -0.663% to +1.242% | no |

The user's observation is visible in parts of the recent 24-month sample:
days 9-15 had a +2.867% median and month-end had a -1.418% median. However,
days 1-8 still had a +0.344% median, and the full-history effects were not
stable. No phase is enabled as a filter or risk modifier.

## Derivatives Ablation

The available derivatives-complete subset contained 128 admitted trades on
BTC, ETH, and SOL:

| Model | Trades | Net R | Profit factor |
|---|---:|---:|---:|
| M0 price/candle/volume | 128 | -11.723R | 0.842 |
| M1 OI and flow soft weight | 128 | -13.078R | 0.816 |
| M2 hard OI and flow confirmation | 29 | -3.640R | 0.799 |
| M3 funding/premium crowding veto | 124 | -12.293R | 0.831 |

OI did not add edge and materially reduced frequency when used as a hard
condition. It is not adopted.

## Exit Diagnostic

The core five markets appeared profitable only when the entire position was
held for distant structural targets. That result had a median trade near
-1.19R and depended on a small number of 8R-18R winners.

A second diagnostic retained TP1 at 1R and sent the remaining 50% to the
structural target while preserving the current SL+ rule. It lost:

- Core five: -33.951R, PF 0.749.
- BTC only: -6.956R, PF 0.713.
- All 30 pairs: -271.613R, PF 0.755.

The apparent structural-target profit was therefore not robust under the
bot's existing protection behavior.

## Operational Decision

- Unified A/B/C code remains research-only under `tools/`.
- Existing production bot and VPS are unchanged.
- Existing Strategy B stays paused.
- Existing Strategy C configuration is unchanged.
- No Telegram command or notification was added.
- The prior-validation period remains unopened because development failed.
- Forward shadow admission is false.

Artifacts:

- `.audit/2026-07-30-strategy-abc/development_30pairs.json`
- `.audit/2026-07-30-strategy-abc/development_gate.json`
- `.audit/2026-07-30-strategy-abc/btc_calendar_2020_2026.json`
- `.audit/2026-07-30-strategy-abc/management_tp1_structure_30pairs.json`
