# AI Market Scanner Prompt Research Result

Date: 2026-08-06

Status: `REJECTED_PROMPT_ONLY_NO_VALIDATED_EDGE`

## Decision

The direct prompt-only market scanner is rejected for `AI_SIGNAL`,
`AI_APPROVAL`, and `AI_LIVE`.

Two development tournaments completed across 240 outcome-independent market
snapshots per prompt. No prompt passed the frozen development gate. Unseen
validation remained sealed and was not queried.

This result does not prove that every future AI-assisted method must fail. It
does show that these prompt-only methods did not produce a cost-robust edge and
must not be promoted.

## Dataset and execution contract

- Development: 240 stratified snapshots, 2021-07 through 2023-12.
- Sealed validation: 240 snapshots, 2024-01 through 2024-10.
- Universe: BTC, ETH, SOL, ADA, DOGE, and XRP perpetual USDT markets.
- Features: confirmed OHLCV, taker flow, trend, volatility, range location, and
  cross-market relative strength.
- No future outcome, OI, funding, order book, balance, or credential entered a
  model request.
- Entry: next 15-minute open.
- Stop: maximum of 0.75 percent or 1.5 ATR, capped at 3 percent.
- Target: 2R; maximum hold: 12 hours.
- Baseline cost: 0.14 percent; stress cost: 0.20 percent.
- Maximum one simultaneous position.

## V1 result

V1 was too conservative. It produced only 24 raw `TRADE` decisions across all
three prompts, and every one was blocked by the frozen confidence, quality, or
risk-flag gate.

An offline development-only ablation removed those blocks to check whether the
raw selections contained hidden value:

| Prompt | Raw trades | Baseline R | Stress R | Baseline PF |
| --- | ---: | ---: | ---: | ---: |
| P1 Regime Structure | 11 | -0.698 | -1.426 | 0.914 |
| P2 Liquidity Flow | 8 | -3.149 | -3.641 | 0.541 |
| P3 Conservative Confluence | 5 | -5.793 | -6.133 | 0.000 |

Relaxing the gate did not reveal an edge, so V1 was rejected rather than tuned
on validation.

## V2 result

V2 calibrated actionable frequency, made risk flags true blockers, increased
structured-output capacity, and added one bounded format retry. All 720 model
decisions were valid and no response failure remained.

| Prompt | Trades | WR | Baseline R | Stress R | PF | Stress PF | Max DD | Stress DD |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| P4 Long Regime Pullback | 63 | 31.7% | -13.754 | -17.412 | 0.719 | 0.662 | 15.649R | 19.262R |
| P5 Balanced Trend Continuation | 21 | 23.8% | -8.881 | -10.116 | 0.513 | 0.473 | 9.683R | 10.833R |
| P6 Range Absorption Reversal | 25 | 40.0% | -1.158 | -2.739 | 0.928 | 0.840 | 5.266R | 6.001R |

P6 was closest to break-even but remained negative after both baseline and
stress costs. Removing its best stress trade reduced the result to -4.636R.
Its 2023 segment was also negative. No confidence/quality threshold with at
least eight trades improved the frozen result.

A post-hoc BTC/ETH/SOL-only slice had only 11 trades. It is too small, was
discovered after outcomes were known, and is not admissible evidence.

## Repeatability audit

An interrupted parent runner left one Python child alive. The overlap created
duplicate responses for many identical snapshots before the child was stopped.
Those duplicates were not used as extra historical samples, but they allowed a
repeatability audit:

| Prompt | Repeated snapshots | Same action | Same action/pair/side |
| --- | ---: | ---: | ---: |
| P5 | 194 | 92.3% | 91.2% |
| P6 | 197 | 88.8% | 87.3% |

Action instability of roughly 8 to 11 percent is too high for direct automatic
execution without additional deterministic controls. Full explanatory text was
not identical, which is expected from a generative model.

A cross-process file lock is now enforced by the replay tool. A second runner
using the same cache fails before making an API request.

## API usage

- Unique V1 and V2 research decisions: 1,440.
- Logged cost for unique experiment reports: approximately USD 1.290.
- Duplicate logged responses from the orphan overlap: approximately USD 0.188.
- Total logged API cost: approximately USD 1.478.

These values use the configured model rates and recorded API usage. Failed retry
attempts without usage metadata may make provider billing slightly different.

## Promotion state

- Development winner: none.
- Validation calls: zero.
- `AI_SIGNAL`: locked.
- `AI_APPROVAL`: locked.
- `AI_LIVE`: locked.
- Production bot and VPS order behavior: unchanged.

## Recommended next architecture

Do not continue blind prompt wording iterations on the same development set.
The defensible next architecture is a deterministic, independently validated
candidate generator followed by an AI context reviewer in shadow mode. The AI
may veto or rank candidates, while deterministic code owns side, geometry,
sizing, credentials, and every order.

Any future direct-scanner hypothesis must be preregistered as a new candidate
family, use a new development period or forward data, pass repeatability checks,
and preserve the untouched 2024 validation set.

## Evidence artifacts

```text
.audit/2026-08-05-ai-market-scanner/openai_market_prompt_development.json
.audit/2026-08-05-ai-market-scanner/openai_market_prompt_v2_development.json
.audit/2026-08-05-ai-market-scanner/development_prompt_v2_gate.json
.audit/2026-08-05-ai-market-scanner/openai_market_prompt_cache.jsonl
```

Regression verification: 258 tests passed.

