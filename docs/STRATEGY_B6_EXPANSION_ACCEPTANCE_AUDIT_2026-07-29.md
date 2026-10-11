# KT Strategy B6 Expansion-Acceptance Audit - 2026-07-29

## Executive Decision

- Strategy B remains `PAUSED_NO_VALIDATED_EDGE`.
- B6.0, B6.1, and B6.2 are rejected before prior validation.
- The 2024-2025 validation and 2023-2024 final holdout were not opened for
  B6.2 because its recent-design gate failed.
- No Strategy B detector, shadow event, Telegram command, live order path, or
  VPS file was changed.
- Strategy A V8.2, Strategy C6 shadow, existing positions, SL, TP, and profit
  protection are unchanged.

No system can know future market direction with certainty or guarantee
consistent profit. The professional result of this audit is a fail-closed
decision, not a profitable-looking backtest created by repeated tuning.

## B6.0: Symmetric 2H Expansion-Acceptance

B6.0 introduced:

- five-core 4-hour market breadth;
- 2-hour Donchian structure;
- pre-break compression;
- range and participation expansion;
- multi-candle 15-minute acceptance;
- cost-aware structural stops; and
- cross-pair concurrency and same-side cluster controls.

Recent development, 30 pairs:

| Candidate | Trades | Net R | PF | Max DD |
|---|---:|---:|---:|---:|
| B6.0 Primary | 9 | +0.581R | 1.126 | 2.729R |
| B6.0 Neighbor | 28 | -4.872R | 0.707 | 6.346R |

The funnel contained 97 armed expansions, 17 accepted events, and only 9
primary trades with valid natural stops. The primary was too sparse and the
neighbor exposed negative LONG expectancy.

## B6.1: Asymmetric 1H SHORT Continuation

B6.1 changed the hypothesis before validation:

- SHORT only;
- 1-hour expansion trigger;
- bearish five-core breadth;
- BTC 12-hour return at most zero;
- 15-minute acceptance; and
- the same cost and portfolio controls.

Recent development:

| Candidate | Trades | Net R | PF | Max DD | Cost-stress R |
|---|---:|---:|---:|---:|---:|
| B6.1 Primary | 14 | -1.026R | 0.848 | 4.505R | -1.677R |
| B6.1 Neighbor | 23 | +1.961R | 1.213 | 5.658R | +0.809R |

The frozen primary failed. The positive neighbor could not replace it after
inspection and was not taken to validation as a promoted rule.

## B6.2: Trend-Runner Exit

B6.2 tested whether the prior fixed TP2 mismatched a continuation signal:

- the B6.1 neighbor signal was frozen as the design-period signal;
- 35% TP1 at 1R;
- no fixed TP2;
- existing +1.5% trigger and +1% SL lock;
- 1-hour Chandelier trailing after +2R;
- 2.0, 2.5, and 3.0 ATR frozen trail distances; and
- five-day maximum holding period.

Recent development:

| Trail | Trades | Net R | PF | Avg R | Max DD | Cost-stress R |
|---|---:|---:|---:|---:|---:|---:|
| 2.5 ATR primary | 23 | +1.546R | 1.155 | +0.0672R | 5.658R | +0.394R |
| 2.0 ATR neighbor | 23 | +0.027R | 1.003 | +0.0012R | 5.658R | -1.126R |
| 3.0 ATR neighbor | 23 | +1.115R | 1.112 | +0.0485R | 5.658R | -0.037R |

The primary remained below minimum sample, PF, average R, and cost-stress
requirements. Both exit neighbors demonstrated that the result was fragile,
not a broad parameter plateau.

## Interpretation

B6 corrected several real weaknesses in B4/B5, but the evidence still shows:

1. multi-candle acceptance reduces false breaks but does not create enough
   expectancy by itself;
2. the usable signal remains concentrated in bearish phases;
3. transaction cost consumes most of the small edge;
4. the continuation sample becomes sparse when broad-market alignment is
   made strict enough to avoid correlated losses; and
5. uncapping TP2 helps selected winners but does not produce robust results
   across nearby trail distances.

This is evidence against promoting this breakout-continuation family with the
available OHLCV and taker-flow features. Another threshold iteration on the
same recent period would be data mining.

## Operational Outcome

- Strategy B stays paused in production.
- No deployment or service restart is required.
- The 2023-2024 holdout remains reserved for a materially different hypothesis.
- B6 research code and fail-closed gates remain available for reproducibility.
- Any next Strategy B project should add genuinely new information, such as
  funding, open interest, basis, liquidation activity, or cross-sectional
  relative strength, before consuming the final holdout.

## Evidence

- `docs/STRATEGY_B6_FROZEN_SPEC_2026-07-29.md`
- `docs/STRATEGY_B61_FROZEN_SPEC_2026-07-29.md`
- `docs/STRATEGY_B62_FROZEN_SPEC_2026-07-29.md`
- `.audit/2026-07-29-strategy-b6/strategy_b6_development270.json`
- `.audit/2026-07-29-strategy-b6/strategy_b61_development270.json`
- `.audit/2026-07-29-strategy-b6/strategy_b62_development270.json`
- `.audit/2026-07-29-strategy-b6/strategy_b62_design_gate.json`
- `tools/research_strategy_b6.py`
- `tools/research_strategy_b61.py`
- `tools/research_strategy_b62.py`

## Research Basis

- Binance USD-M Futures kline fields:
  https://developers.binance.com/en/docs/products/derivatives-trading-usds-futures/market-data/rest-api/Kline-Candlestick-Data
- Regime-aware crypto trend following and asymmetric long-short construction:
  https://arxiv.org/abs/2602.11708
- Donchian ensemble and transaction-cost-aware crypto trend following:
  https://papers.ssrn.com/sol3/papers.cfm?abstract_id=5209907
- Cost-aware walk-forward forecasting:
  https://papers.ssrn.com/sol3/papers.cfm?abstract_id=6795938
- Cross-cryptocurrency return predictability:
  https://papers.ssrn.com/sol3/papers.cfm?abstract_id=3974583

These references motivated the architecture and testing protocol. They do not
validate this implementation or promise future profitability.

