# Strategy A/B/C v2 Implementation Record

Date: 2026-07-30

Decision: **research-only; first human structure and outcome gates failed**.

## Delivered

- `tools/abc_structure_engine_v2.py`
  - BTC 1D/4H/15m information clock.
  - Stable level and range lineage.
  - Mutually exclusive A/B/C lifecycle.
  - C requires inherited level, reclaim, displacement, and MSS.
- `tools/research_strategy_abc_v2.py`
  - BTC-only closed-candle replay.
  - Existing production management diagnostic.
  - Structural target diagnostic kept separate.
  - Calendar context only; no derivatives join.
- `tools/build_btc_structure_review.py`
  - Offline desktop/mobile chart review.
  - Labels stored in browser local storage.
  - JSON import/export.
  - Aftermath hidden by default to reduce outcome bias.
- `tools/evaluate_strategy_abc_v2_gate.py`
  - Human label precision and missed-control gate.
  - Chronological outcome gate.
  - Promotion remains false unless both gates pass.

Frozen specification:
`docs/STRATEGY_ABC_V2_BTC_STRUCTURE_SPEC_2026-07-30.md`.

## Dataset

Symbol: BTCUSDT.

Available local history:

- 15m: 2024-10-20 through 2026-07-26.
- 4H warm-up: 2024-08-25 through 2026-07-22.
- Replay window: 2024-10-25 through 2026-07-22.

This is approximately 21 months of replay coverage. It is the longest
continuous 15m/4H BTC dataset already present locally.

## Initial Candidate Replay

The v2 detector produced:

| Item | Count |
|---|---:|
| Engine events | 87 |
| A | 68 |
| B | 3 |
| C | 16 |
| Near-boundary controls | 182 |
| Non-overlapping outcome trades | 64 |

Lineage integrity:

- 87 unique event IDs;
- 46 unique level IDs;
- 66 unique range IDs;
- zero C events without a parent transition;
- zero duplicate transition keys.

This is a large noise reduction from v1, but B coverage is currently too low
for the frozen label gate. Controls allow the user to identify missed B setups
and distinguish a detector problem from a genuinely rare market state.

## Outcome Diagnostic

Existing management on the 64 non-overlapping records:

| Metric | Result |
|---|---:|
| Net R | -32.461R |
| Average R | -0.5072R |
| Profit factor | 0.340 |
| Max drawdown | 32.547R |

This result is recorded transparently but cannot yet drive parameter changes.
The human structure gate must establish whether the machine selected the same
levels and transitions the user would select. Outcome optimization before that
step would optimize the wrong representation.

## Review Dataset

Workbench:
`.audit/2026-07-30-strategy-abc-v2/review/btc_structure_review.html`.

Dataset ID: `f82e201d0156`.

Candidate mix:

- 87 engine events;
- 63 evenly distributed near-boundary controls;
- 150 total charts.

Available decisions:

- Valid A;
- Valid B;
- Valid C;
- Tidak ada setup;
- Level salah;
- Arah salah;
- Setup belum lengkap;
- Lewati.

The default chart excludes candles after the candidate timestamp. The
`Tampilkan aftermath` control reveals them only when deliberately requested.

### V2 blind replacement

The first workbench was retired before labeling because its gate was
mathematically impossible: it contained only three B events while the frozen
gate required ten.

Replacement workbench:
`.audit/2026-07-30-strategy-abc-v2/review_v2_blind/btc_structure_review.html`.

Dataset ID: `0e90e449d059`.

Coverage:

| Candidate class | Count |
|---|---:|
| A engine events | 52 |
| B engine events | 19 |
| C engine events | 43 |
| Blinded controls | 36 |
| Total | 150 |

All feasibility checks pass without lowering a threshold. The answer key uses
the frozen `ABC_V21_COMBINED` structure engine over all available BTCUSDT
Futures history from September 2019 through July 2026. The V2.3 6-10 ATR rule
remains a separate A outcome filter.

Blind-review protections:

- anonymized candidate IDs;
- engine event/control status hidden;
- expected path, direction, transition, macro, calendar, scores, and outcome
  hidden;
- answer key stored separately from browser data and exported labels;
- aftermath disabled until a label is saved;
- label locked after aftermath is shown;
- deterministic randomized review order;
- minimum 30 controls reserved by the sampler.

Desktop and 390px mobile layouts were verified with Playwright. Label,
aftermath-lock, import/export, and stale-dataset rejection were also tested.

Protocol:
`docs/STRATEGY_ABC_BLIND_LABEL_PROTOCOL_2026-07-30.md`.

Final first-review status:

- dataset feasibility: pass;
- accepted human labels: 149;
- overall exact A/B/C agreement: 38.60%;
- overall control false-negative rate: 88.57%;
- structure-label gate: fail;
- outcome gate: fail;
- promotion allowed: false;
- production changed: false.

Full result:
`docs/STRATEGY_ABC_HUMAN_LABEL_GATE_RESULT_2026-07-30.md`.

## Safety Boundary

No change was made to:

- `v3_swing_bot_fixed.py`;
- production config or API credentials;
- VPS worker or service;
- Telegram commands or notifications;
- live Strategy A;
- paused Strategy B;
- existing Strategy C shadow setting;
- current SL, TP1, TP2, or SL+ behavior.

Initial gate decision: `RESEARCH_ONLY`.

## Frozen Follow-up Tests

The loss attribution was followed by a fixed sequence of tests. No production
setting was changed.

### V2.1 transition variants

Five variants were replayed on the 2024-2026 development history. The combined
variant reduced the loss materially, but did not establish a stable edge:

| Period | Trades | Net R | Profit factor |
|---|---:|---:|---:|
| Calibration | 11 | -1.278R | 0.817 |
| Validation | 16 | +1.118R | 1.156 |
| Full period | 27 | -0.160R | 0.989 |
| Full period, stress cost | 27 | -2.011R | 0.867 |

Decision: `INSUFFICIENT_SAMPLE`.

### V2.2 confirmed A

The confirmed-A path was frozen before loading 2022-2024:

| Metric | Result |
|---|---:|
| Trades | 16 |
| Net R | -5.511R |
| Stress-cost R | -6.343R |
| Profit factor | 0.474 |
| Positive 90-day folds | 3 of 8 |

Decision: `REJECT`. The recent A result was regime-dependent.

### V2.3 balanced-range A

The final numeric hypothesis restricted only A setup initiation to a 6-10 ATR
balance. It was frozen before loading the untouched 2020-2022 holdout.

| Metric | Result |
|---|---:|
| Trades | 4 |
| Wins / losses | 3 / 1 |
| Net R | +2.158R |
| Average R | +0.5394R |
| Profit factor | 2.980 |
| Max drawdown | 1.090R |
| Stress-cost R | +2.018R |
| Stress-cost profit factor | 2.789 |
| Positive active 90-day folds | 2 of 2 |

The payoff and cost checks passed. The minimum-trade and minimum-fold checks
failed. Decision: `REJECT_INSUFFICIENT_SAMPLE`.

No additional numeric filter may be selected from these records. The next
valid research input is the frozen human chart-label dataset or genuinely new
forward data.

Result record:
`docs/STRATEGY_ABC_V23_HOLDOUT_RESULT_2026-07-30.md`.

## V2.4 human-exclusive state machine

The final 36-chart structured adjudication was completed on 2026-07-30:

- 35 accepted labels and 1 skip;
- machine path agreement: 34.48%;
- prior human path agreement: 22.86%;
- machine direction agreement: 72.41%;
- 60% of accepted labels satisfied multiple old minimum path rules.

V2.4 therefore formalized current-state persistence and same-level precedence
without tuning any numeric parameter. It enabled failed-B to C transitions and
pending-A to C promotion on a same-level sweep.

Historical regression failed:

- 101 trades;
- -6.539R;
- PF 0.876;
- stress result -12.013R;
- fixed-horizon entry expectancy statistically indistinguishable from zero.

Decision: `REJECT_NO_VALIDATED_EDGE`.

Specification:
`docs/STRATEGY_ABC_HUMAN_STRUCTURE_SPEC_V24_2026-07-31.md`.

Result:
`docs/STRATEGY_ABC_V24_RESEARCH_RESULT_2026-07-31.md`.
