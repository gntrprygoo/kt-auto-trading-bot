# Strategy E Scalping Research Result - 2026-08-04

Status: `REJECT_NO_COST_AWARE_EDGE`

No Strategy E order path or forward-shadow worker was enabled.

## Data and controls

- BTCUSDT, ETHUSDT, and SOLUSDT perpetual 15-minute klines.
- Available development data begins in October 2024.
- Entry at the next candle open after a confirmed signal.
- Same-candle SL and TP is counted as SL.
- One position per symbol, no overlapping Strategy E trades.
- Baseline round-trip fee plus slippage: 0.14%.
- Stress round-trip cost: 0.20%.
- Development ended 2025-08-31 UTC.
- Validation from 2025-09-01 through 2026-02-28 remained unopened.
- Holdout from 2026-03-01 onward remained unopened.

## Development results

### Round 1

| Candidate | Trades | Net R | PF | Stress R | Gate |
|---|---:|---:|---:|---:|---|
| E1 Balanced Expansion 1.5R | 484 | -132.20R | 0.601 | -181.62R | Fail |
| E1 Strict Expansion 1.5R | 235 | -105.49R | 0.421 | -129.88R | Fail |
| E1 Strict Expansion 2.0R | 234 | -103.08R | 0.452 | -127.36R | Fail |
| E2 Range Reclaim 1.2R | 167 | -47.59R | 0.536 | -68.36R | Fail |
| E2 Trend Reclaim 1.5R | 73 | -26.91R | 0.477 | -35.71R | Fail |

### Round 2

| Candidate | Trades | Gross R | Net R | PF | Stress R | Gate |
|---|---:|---:|---:|---:|---:|---|
| E3 Failed Range 1.5R | 185 | +12.37R | -40.99R | 0.639 | -63.86R | Fail |
| E3 Failed Any 2.0R | 307 | +18.84R | -60.80R | 0.689 | -94.93R | Fail |
| E4 Jump Reversal 1.5R | 49 | +5.85R | -5.49R | 0.785 | -10.34R | Fail |

The two-stage patterns were positive before costs, but their roughly 0.53% to
0.64% median stop distances made turnover cost dominant.

### Round 3 cost-distance test

| Candidate | Trades | Net R | PF | Stress R | Gate |
|---|---:|---:|---:|---:|---|
| E3 Failed Wide 1.5R | 327 | -39.40R | 0.756 | -62.41R | Fail |
| E4 Jump Wide 1.25R | 52 | -1.52R | 0.928 | -5.05R | Fail |
| E4 Jump Wide 1.5R | 52 | +0.84R | 1.034 | -2.69R | Fail |

The best baseline candidate was too small, had insufficient sample size, PF
far below 1.15, and failed stress cost.

### Round 4 independent opening-range hypothesis

| Candidate | Trades | Gross R | Net R | PF | Stress R | Gate |
|---|---:|---:|---:|---:|---:|---|
| Asia ORB 1.5R | 195 | +11.32R | -12.43R | 0.852 | -22.61R | Fail |
| Europe ORB 1.5R | 259 | -5.10R | -39.77R | 0.720 | -54.63R | Fail |
| US ORB 1.5R | 251 | +2.08R | -27.73R | 0.766 | -40.51R | Fail |

## Decision

The tested 15-minute kline-only scalping families do not have a validated edge
after plausible costs. None may be deployed to forward shadow or live trading.
Opening validation or holdout to search for a favorable subset would invalidate
those periods, so they remain sealed.

The next scalping research should first collect higher-quality execution data:
real bid/ask spread, maker fill probability, order-book imbalance, and observed
slippage. Without those inputs, a small gross candle edge is not evidence of a
tradable net edge. Alternatively, a lower-turnover intraday strategy can be
specified as a new family, not as another parameter variant of Strategy E.

## Research basis

- Binance USD-M Futures kline data:
  https://developers.binance.com/en/docs/products/derivatives-trading-usds-futures/market-data/rest-api/Kline-Candlestick-Data
- Intraday high-frequency crypto patterns:
  https://arxiv.org/abs/2009.04200
- Periodicity in crypto volatility and liquidity:
  https://arxiv.org/abs/2109.12142
- State-dependent intraday momentum and reversal:
  https://papers.ssrn.com/sol3/papers.cfm?abstract_id=4080253

No historical test can guarantee future profitability.
