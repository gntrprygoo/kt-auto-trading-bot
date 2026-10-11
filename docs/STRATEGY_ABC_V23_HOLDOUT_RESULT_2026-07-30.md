# Strategy ABC V2.3 Holdout Result

Date: 2026-07-30  
Status: research only  
Production decision: rejected because the sample is insufficient

## Frozen Test

- Symbol: BTCUSDT.
- Period: 2020-10-25 through 2022-10-24.
- Structure: existing 1D/4H map.
- Trigger: existing confirmed-A reaction and MSS.
- A balance width: 6.0 through 10.0 4h ATR.
- Execution path: A only.
- Management and cost assumptions: unchanged.
- Parameter changes after viewing the holdout: none.

## Result

| Metric | Baseline | Stress cost |
|---|---:|---:|
| Completed trades | 4 | 4 |
| Wins / losses | 3 / 1 | 3 / 1 |
| Win rate | 75.00% | 75.00% |
| Total net R | +2.158R | +2.018R |
| Average net R | +0.5394R | +0.5045R |
| Profit factor | 2.980 | 2.789 |
| Maximum drawdown | 1.090R | 1.128R |

Two non-empty 90-day folds were present and both were positive.

## Gate Decision

Passed:

- positive baseline R;
- baseline profit factor;
- positive stress-cost R;
- stress-cost profit factor;
- average R;
- maximum drawdown.

Failed:

- minimum 15 completed trades;
- minimum four non-empty 90-day folds.

Final decision: `REJECT_INSUFFICIENT_SAMPLE`.

The result is encouraging, but four trades cannot establish consistency. It
must not be presented as proof of future profitability and does not authorize
live integration.

## Stop Rule

No more thresholds will be selected from the 2020-2026 outcome records. The
next legitimate test is one of:

1. Complete at least 100 blinded chart labels in the existing review workbench.
2. Collect new forward shadow signals without changing the frozen candidate.

The replacement blind workbench is ready at:
`.audit/2026-07-30-strategy-abc-v2/review_v2_blind/btc_structure_review.html`.

Its dataset ID is `0e90e449d059`, with feasible coverage of A=52, B=19,
C=43, and 36 controls.

## Reproducibility

- Frozen spec:
  `docs/STRATEGY_ABC_V23_BALANCED_RANGE_SPEC_2026-07-30.md`
- Replay:
  `tools/research_strategy_abc_v23.py`
- Machine-readable output:
  `.audit/2026-07-30-strategy-abc-v2/v23_balanced_a_holdout.json`
- Cached market data:
  `.audit/2026-07-30-strategy-abc-v2/holdout_2020_2022_cache`
- Production changed: `false`
