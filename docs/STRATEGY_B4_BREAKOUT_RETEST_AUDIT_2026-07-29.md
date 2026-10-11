# KT Strategy B4 Breakout-Retest Audit - 2026-07-29

## Executive decision

- Strategy B remains `PAUSED_NO_VALIDATED_EDGE`.
- B4 is not admitted to production forward shadow.
- B4 is not approved for live Binance orders.
- Strategy A and Strategy C are unchanged.
- Existing positions, SL, TP, and profit protection are unchanged.

The B4 hypothesis looked promising in development but failed the untouched
stress period. Enabling it would be overfitting, not a professional promotion
decision. No strategy or historical replay can guarantee consistent profit.

## B4 hypothesis

B4 tested a stricter breakout-retest sequence:

1. A mature 4-hour Donchian level exists before the breakout candle.
2. The 4-hour EMA trend, EMA slope, and BTC market regime agree with the trade.
3. The breakout has bounded ATR displacement, a strong close, and acceptable
   distance from the fast EMA.
4. Volume and taker-flow are supporting filters, not standalone proof.
5. Only the first 15-minute retest is eligible.
6. The retest must test the level without failing through it.
7. Entry occurs at the next 15-minute candle open.

Short-side B4 was retained as a diagnostic candidate only because earlier B3
research showed unstable downside behavior.

## Leakage controls and execution model

- The Donchian level excludes the breakout candle.
- Volume baselines exclude the signal candle and incomplete candle.
- Retest ATR uses only candles completed before the retest candle.
- Per-pair scanning resumes from the live-management exit, not a fixed-target
  diagnostic exit.
- Development and stress periods do not overlap.
- The stress gate was frozen before its result was inspected.
- Entry uses the next 15-minute open, not the signal close.
- Round-trip fee plus slippage estimate: 0.14%.
- Initial SL, TP1 at 1R, and TP2 at 2R follow the live management model.
- At +1.5% price movement, SL protection moves to +1% from entry.
- Existing active stop wins when stop and target are touched in one candle.
- Unclosed trades are marked to market after 96 hours.

Binance historical klines provide candle volume and taker-buy volume, not a
complete historical order book. Taker-flow is therefore treated as a proxy,
not proof of institutional order flow.

## Data periods

| Dataset | Period | Pairs | Errors |
|---|---|---:|---:|
| Development | 2025-10-25 through 2026-07-22 | 30 | 0 |
| Untouched stress | 2024-10-25 through 2025-10-24 | 30 | 0 |

The universe contains established Binance USDT perpetual pairs. Both periods
use the same code, parameters, cost model, and trade-management assumptions.

## Primary result

Selected before stress inspection: `B4_RETEST_CLOSE_LONG`.

| Period | Trades | WR | Net R | PF | Max DD |
|---|---:|---:|---:|---:|---:|
| Development | 11 | 63.64% | +3.632R | 1.938 | 1.520R |
| Untouched stress | 20 | 50.00% | -0.425R | 0.962 | 5.397R |
| Combined | 31 | 54.84% | +3.207R | 1.211 | 5.397R |

Only 7 of 15 non-empty 30-day folds were positive, or 46.67%. The worst fold
was -2.545R.

The result spans 20 pairs and is not dominated by one pair. The largest positive
pair contribution was 12.8%, so concentration is not the failure. The failure
is temporal instability: most profit came from one favorable market phase.

## Parameter-neighbor result

The nearby parameter set is a robustness check, not a replacement chosen after
seeing stress data.

| Period | Trades | WR | Net R | PF | Max DD |
|---|---:|---:|---:|---:|---:|
| Development | 14 | 57.14% | +2.142R | 1.339 | 3.850R |
| Untouched stress | 44 | 43.18% | -8.025R | 0.711 | 9.926R |
| Combined | 58 | 46.55% | -5.883R | 0.827 | 11.874R |

A small parameter change destroyed the apparent edge. This is strong evidence
that B4 is fragile rather than robust.

## Gate failures

B4 failed 7 frozen checks:

- combined sample: 31, required at least 35;
- stress net R: -0.425R, required positive;
- stress PF: 0.962, required at least 1.20;
- combined PF: 1.211, required at least 1.25;
- positive active folds: 46.67%, required at least 55%;
- neighbor stress result: -8.025R, required positive;
- neighbor combined PF: 0.827, required at least 1.10.

Passing development statistics cannot override a failed untouched period.

## Operational outcome

- No B4 detector was added to the production scan loop.
- No B4 order path was added.
- No configuration was enabled.
- VPS deployment is not required because production behavior did not change.
- Telegram `/status` must continue to show Strategy B as `PAUSED`.

The next legitimate B iteration must begin with a new market hypothesis and a
new untouched dataset. Re-tuning B4 against this stress period would invalidate
the stress period and is not an acceptable path to live trading.

## Production verification

Verified read-only on 2026-07-29:

- VPS service: `active (running)`;
- main PID: `164265`;
- systemd restarts: `0`;
- bot worker processes: `1`;
- observed memory: approximately 74 MB;
- production Strategy B new entries: disabled;
- Strategy C6 shadow: enabled;
- Strategy C order execution: disabled.

No production file was uploaded, no service was restarted, and one corrected
summary was delivered to the configured Telegram admin chat.

## Residual limitations

- Historical kline replay does not include funding payments.
- Fixed slippage cannot reproduce spread expansion, latency, partial fills, or
  rejected orders.
- The established-pair universe can contain survivorship bias.
- Candle data cannot determine the true intrabar event sequence.
- Standalone B replay does not model collisions with Strategy A positions.

Most of these limitations are optimistic relative to production. B4 already
fails before adding those frictions, which strengthens the pause decision.

## Evidence

- `.audit/2026-07-22-strategy-b-c/strategy_b4_development270.json`
- `.audit/2026-07-22-strategy-b-c/strategy_b4_stress365.json`
- `.audit/2026-07-22-strategy-b-c/strategy_b4_gate.json`
- `tools/research_strategy_b4.py`
- `tools/evaluate_strategy_b4_gate.py`
- `tests/test_strategy_b4_research.py`
- `tests/test_strategy_b4_gate.py`

## Research basis

- Binance USD-M Futures kline fields:
  https://developers.binance.com/en/docs/products/derivatives-trading-usds-futures/market-data/rest-api/Kline-Candlestick-Data
- Crypto trend-following evidence:
  https://arxiv.org/abs/2009.12155
- Transaction-cost-aware crypto strategy evaluation:
  https://arxiv.org/abs/2606.00060
- Evidence that volume/trend relationships can be weak and unstable:
  https://link.springer.com/article/10.1007/s40822-021-00166-5

These references support the testing framework, not a promise of profitability.
