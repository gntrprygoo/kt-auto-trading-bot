# Strategy ABC V2.4 Research Result

Date: 2026-07-31  
Decision: **REJECT - NO VALIDATED EDGE**  
Production impact: none

## Final Adjudication

Dataset `82ccd32d0703` is complete:

| Item | Result |
| --- | ---: |
| Exported charts | 36 |
| Accepted labels | 35 |
| Skipped | 1 |
| Valid A | 14 |
| Valid B | 10 |
| Valid C | 11 |
| LONG / SHORT | 15 / 20 |

Agreement:

| Comparison | Exact | Eligible | Rate |
| --- | ---: | ---: | ---: |
| Old machine path | 10 | 29 | 34.48% |
| First human path | 8 | 35 | 22.86% |
| Old machine side | 21 | 29 | 72.41% |

The result is complete enough to write a human specification, but not stable
enough to be treated as exclusive ground truth.

## Minimum-Rule Overlap

The old checklist rules overlapped on 21 of 35 accepted labels:

| Final decision | Minimum rules satisfied | Charts |
| --- | --- | ---: |
| A | A only | 5 |
| A | A and C | 9 |
| B | B only | 5 |
| B | B and C | 5 |
| C | C only | 4 |
| C | A and C | 6 |
| C | B and C | 1 |

This is why V2.4 defines current-state persistence, same-level lineage, and
explicit C/B/A precedence.

## V2.4 Structural Changes

V2.4 inherits all numeric values from `ABC_V21_COMBINED`. It only:

- enables failed breakout and failed B to transition into C;
- promotes pending A to C when a qualifying sweep develops on the same level;
- requires reclaim to still be true when C emits.

No production file or live setting was changed.

## Historical Regression

Period: 2019-09-01 through 2026-07-22.

| Metric | V2.1 combined | V2.4 human-exclusive |
| --- | ---: | ---: |
| Events | 114 | 122 |
| A / B / C | 52 / 19 / 43 | 46 / 18 / 58 |
| Non-overlapping trades | 96 | 101 |
| Net R | -3.870R | -6.539R |
| Average R | -0.0403R | -0.0647R |
| Profit factor | 0.922 | 0.876 |
| Max drawdown | 9.940R | 12.357R |
| Stress net R | -9.392R | -12.013R |

V2.4 improved taxonomy clarity but worsened the historical outcome. It is not
a profitable replacement.

## Path Outcome

| Path | Trades | Baseline R | PF | Stress R |
| --- | ---: | ---: | ---: | ---: |
| A | 42 | +0.534R | 1.026 | -1.469R |
| B | 13 | -3.324R | 0.609 | -4.453R |
| C | 46 | -3.749R | 0.843 | -6.091R |

A is only marginally positive before stress cost. It is not a validated edge.

Transition outcome:

| Transition | Trades | Baseline R | Stress R |
| --- | ---: | ---: | ---: |
| A boundary sweep to C | 33 | -3.293R | -4.993R |
| A reaction sweep to C | 2 | -0.441R | -0.586R |
| Accepted breakout retest B | 13 | -3.324R | -4.453R |
| Failed B/breakout to C | 11 | -0.015R | -0.512R |
| Validated range reaction A | 42 | +0.534R | -1.469R |

## Human-Fit Diagnostic

At the exact 35 adjudication timestamps:

- V2.4 emitted an event at 24 timestamps;
- path matched 7 of those 24, or 29.17%;
- direction matched 18 of 24, or 75.00%.

This diagnostic uses the same charts that informed V2.4 and cannot validate
the detector. Exact-time matching also does not credit a confirmation shifted
to a later candle. Even with those limitations, path fit did not improve
enough to justify promotion.

## Fixed-Horizon Entry Edge

All 122 V2.4 events were measured independently of the current TP logic:

| Horizon | Avg net close R | 95% confidence interval | +1R first rate |
| --- | ---: | ---: | ---: |
| 4 hours | -0.0109R | -0.4934R to +0.4715R | 48.94% |
| 12 hours | +0.0250R | -0.3392R to +0.3892R | 48.31% |
| 24 hours | -0.0487R | -0.5447R to +0.4474R | 52.83% |

Every confidence interval includes zero by a wide margin. The small positive
12-hour mean is not statistically distinguishable from no edge.

The 12-hour result was positive only in 2023 and 2025. It was negative in
2020, 2021, 2022, 2024, and 2026. The apparent B mean was especially unstable:
one 2023 event contributed approximately +9.9R.

Notable diagnostics:

- 4-hour SHORT expectancy was -0.3122R across 67 events, with a 95% interval
  from -0.5206R to -0.1038R;
- B at 4 hours averaged +0.8974R, but its median was -0.3331R and its interval
  was -2.2485R to +4.0432R;
- B's apparent positive mean came from a few large outliers;
- the structural opposite-boundary target produced -33.192R and PF 0.621.

The current problem is primarily entry classification and direction, not only
TP placement.

## Decision

- V2.4 is rejected for live and forward-shadow promotion.
- Strategy A's small baseline gain is not cost robust.
- Strategy B and C remain without validated edge.
- No calendar, macro, side, or transition subgroup may be promoted from this
  same historical sample.
- Production Strategy A, paused B, shadow C, Telegram, VPS, SL, TP, and risk
  settings remain unchanged.
- All 156 unit tests pass.

## Next Research Hypothesis

The next test must be structural and pre-registered:

1. treat downside B acceptance separately from upside B acceptance;
2. require higher-timeframe acceptance persistence before a downside B can
   become SHORT;
3. preserve failed downside breakout as a potential C LONG lifecycle;
4. measure entry edge on an untouched period before testing any exit changes;
5. reject the hypothesis if fixed-horizon edge is not positive after cost.

This hypothesis is motivated by the robustly negative 4-hour SHORT result and
the user's observation that the machine shorts near market bottoms. Its exact
rules must be frozen before loading new data.

## Artifacts

- Human export SHA-256:
  `904B30389DAF76D6D49726B42E9AE7779D7372A6343218E4205308CA91A1BCD5`
- Final adjudication result SHA-256:
  `E02BD20B9632DEEACB104442DEFF3EAC43A45F11D9DE310C03DC50D85A0C635C`
- V2.4 replay SHA-256:
  `F83B1891729BF2DF8DE0C21D2C0438B495F634E5BAA5692872956FD2DE89D2D7`
- Exact-time diagnostic SHA-256:
  `08C4540D4618DED6D97C744ED4A606C697B07D9F74A08C0BD1762162FA215485`
- Entry-edge diagnostic SHA-256:
  `364D613C5036470B1C71414014FFDCF66DFF81B7C8D39940DA947A4FC60CB7F5`

The entry-edge artifact is generated from:
`.audit/2026-07-30-strategy-abc-v2/v24_entry_edge_diagnostic_2019_2026.json`.
