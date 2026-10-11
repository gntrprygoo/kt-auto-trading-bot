# Strategy ABC Human Label Gate Result

Date: 2026-07-30  
Dataset: `0e90e449d059`  
Decision: **RESEARCH_ONLY**

## Review Integrity

- Exported labels: 150
- Accepted labels: 149
- Skipped: 1
- Unique candidates: 150
- Engine-event labels: 114
- Control labels: 35
- Aftermath opened after the decision was locked: 146
- Dataset ID and blind-label schema: valid

The aftermath count does not invalidate the decisions because the workbench
locks each decision before revealing future candles. It does mean this dataset
must not be reused as a fresh blind outcome sample.

## Structure Gate

The structure gate failed.

| Metric | Actual | Required |
| --- | ---: | ---: |
| Overall exact A/B/C agreement | 38.60% | >= 70% |
| A agreement | 38.46% | >= 65% |
| B agreement | 42.11% | >= 65% |
| C agreement | 37.21% | >= 65% |
| Overall control false-negative rate | 88.57% | <= 20% |
| A control false-negative rate | 31.43% | <= 20% |
| B control false-negative rate | 17.14% | <= 20% |
| C control false-negative rate | 40.00% | <= 20% |

The human reviewer marked a valid setup on 31 of 35 near-boundary controls
where the frozen engine emitted no event. This may indicate poor engine recall,
an overly broad human setup definition, or both. The exact-match metric is an
agreement measure; the frozen engine answer key is not independent human ground
truth.

Human decisions:

- Valid A: 41
- Valid B: 41
- Valid C: 54
- No setup: 3
- Level wrong: 3
- Setup incomplete: 7
- Skip: 1

The 136 valid-setup decisions across 150 charts show that the current protocol
did not create enough separation between a setup forming near a level and a
setup fully confirmed at the blue candidate candle. One review note classified
`breakout waiting to retest` as Valid B, while the frozen definition requires
the retest to have completed and held. A calibration pass is required before
these labels can drive detector changes.

## Outcome Gate

The frozen combined engine also failed independently of the labels.

| Metric | Actual | Required |
| --- | ---: | ---: |
| Trades | 96 | >= 50 |
| Net R | -3.870R | > 0R |
| Profit factor | 0.922 | >= 1.15 |
| Average R | -0.0403R | >= +0.05R |
| Max drawdown | 9.94R | <= 12R |
| Stress net R | -9.392R | > 0R |
| Stress profit factor | 0.820 | >= 1.05 |

Path outcome:

- A: 47 trades, +2.982R, PF 1.138
- B: 13 trades, -0.803R, PF 0.889
- C: 36 trades, -6.048R, PF 0.706

## Diagnostic Only

For executed engine events, grouping the existing trades by human decision
produced:

- Human Valid B: 30 trades, +3.990R, PF 1.310
- Human Valid C: 32 trades, -0.923R, PF 0.944
- Human Valid A: 25 trades, -7.415R, PF 0.533

Machine A events relabeled as B contained 12 trades with +5.393R and PF 2.593.
Machine C events confirmed as C contained 11 trades with +1.193R and PF 1.255.
These are research hypotheses only. They are small, selected from the same
sample, omit a structured human side label, and still use the machine's entry
direction and trade management.

## Decision And Next Gate

- No path is promoted to live or forward shadow from this result.
- Production code, VPS configuration, Telegram, SL, TP, and risk settings remain
  unchanged.
- Freeze this export and result as the first-review artifact.
- Run a smaller stratified adjudication pass with explicit fields for level
  validity, side, breakout acceptance, completed retest, sweep, reclaim, and
  market-structure shift.
- Use the adjudication only to clarify structure rules, not to select parameters
  from P&L.
- Any revised detector must be evaluated on genuinely new forward data.

Formal result:
`.audit/2026-07-30-strategy-abc-v2/review_v2_blind/final_gate_human_2026-07-30.json`.

Archived human export:
`.audit/2026-07-30-strategy-abc-v2/review_v2_blind/human_labels_2026-07-30.json`.

SHA-256:
`DDD54A6A42F94235E30EEDF3BEB80EFE3A66E59F27A6F1C9A87B75AD16D9374E`.

The structured adjudication workbench was subsequently frozen with 36 charts
under dataset `82ccd32d0703`. Its protocol is documented in
`docs/STRATEGY_ABC_ADJUDICATION_PROTOCOL_2026-07-30.md`.
