# Strategy ABC Structured Adjudication Protocol

Date: 2026-07-30  
Dataset: `82ccd32d0703`  
Parent blind review: `0e90e449d059`  
Status: human adjudication required  
Production impact: none

## Purpose

The first 150-chart blind review found substantial disagreement between the
human reviewer and the frozen structure engine. It also exposed a limitation in
the original review form: direction and individual confirmation steps were not
recorded as structured fields.

This adjudication pass clarifies those fields on a smaller, deterministic
subset. It does not select trading parameters and does not promote any strategy.

## Selection

The workbench contains 36 charts selected without using P&L:

| Stratum | Charts |
| --- | ---: |
| Machine A, prior human B | 6 |
| Machine A, prior human C | 4 |
| Machine B, prior human C | 5 |
| Machine C, prior human A | 4 |
| Machine C, prior human B | 5 |
| Control, prior human A/B/C | 2 each |
| Human/machine agreement A/B/C anchors | 2 each |

Selection and display order are deterministic hashes. Candidate IDs are
re-anonymized.

## Blind Protection

The browser does not receive:

- engine event/control status;
- machine A/B/C path;
- machine direction or transition;
- the prior human decision;
- the selection stratum;
- P&L or any outcome;
- candles after the blue assessment line.

There is no aftermath button. The separate answer key is used only after the
adjudication export is frozen.

## Required Fields

Every non-skip decision requires:

- active level valid: yes, no, or unclear;
- side: long, short, none, or unclear;
- range-boundary reaction;
- accepted breakout;
- completed retest;
- retest hold;
- liquidity sweep;
- reclaim;
- market-structure shift.

## Decision Constraints

### Valid A

- level valid = yes;
- side = long or short;
- range-boundary reaction = yes;
- accepted breakout = no.

### Valid B

- level valid = yes;
- side = long or short;
- accepted breakout = yes;
- retest completed = yes;
- retest held = yes.

`Waiting for retest` is not Valid B. It is Setup Incomplete.

### Valid C

- level valid = yes;
- side = long or short;
- sweep = yes;
- reclaim = yes;
- MSS = yes.

### Other

- Level Wrong requires level valid = no.
- No Setup and Setup Incomplete still require the full checklist so the missing
  condition can be identified.
- Skip may be used when the chart cannot be judged confidently.

## Handoff

The browser saves progress to local storage. Exported schema:
`KT_BTC_STRUCTURE_ADJUDICATION_LABELS_V1_BLIND`.

After all 36 charts are exported:

1. freeze and hash the export;
2. evaluate checklist consistency before comparing with the answer key;
3. create an explicit human structure specification;
4. implement detector changes without consulting P&L;
5. use only genuinely new forward candles for performance validation.

Workbench:
`.audit/2026-07-30-strategy-abc-v2/adjudication_v1/btc_structure_adjudication.html`.
