# Strategy D1 Frozen Specification

Date frozen: 2026-07-31  
Name: `D1_TSMOM_7_30_90`  
Status: research-only, pre-result specification  
Production impact: none

## Research Decision

The combined A/B/C research is stopped because its small positive pockets did
not survive stress costs or remain stable across years. D1 is an independent
price-momentum strategy. It does not use support/resistance, EMA, chart
patterns, OI, funding direction, or the A/B/C state machine.

## Research Basis

Time-series momentum uses an instrument's own past return to determine
direction. The broad evidence is documented by:

- Moskowitz, Ooi, and Pedersen, "Time Series Momentum":
  https://www.sciencedirect.com/science/article/pii/S0304405X11002613
- Hurst, Ooi, and Pedersen, "A Century of Evidence on Trend-Following
  Investing":
  https://www.aqr.com/insights/research/journal-article/a-century-of-evidence-on-trend-following-investing
- Han, Kang, and Ryu, "Momentum in the Cryptocurrency Market: A Comprehensive
  Analysis under Realistic Assumptions":
  https://papers.ssrn.com/sol3/papers.cfm?abstract_id=4675565

These sources motivate the research family. They do not validate this BTC
implementation or its frozen parameters.

## Market And Clock

- Instrument: BTCUSDT perpetual-futures candles.
- Signal timeframe: completed 4H candles.
- Entry: next 4H open.
- One position at a time.
- Observation period: 2019-09-01 through 2026-07-22.
- Development period: 2019-09-01 through 2022-12-31.
- Holdout period: 2023-01-01 through 2026-07-22.

Every lookback window must be contiguous. Missing 4H candles make the signal
invalid rather than shortening the window.

## Direction Signal

At each completed 4H candle, calculate the close-to-close return over:

- 7 days, or 42 completed 4H bars;
- 30 days, or 180 completed 4H bars;
- 90 days, or 540 completed 4H bars.

State:

- LONG when all three returns are greater than zero;
- SHORT when all three returns are less than zero;
- NEUTRAL otherwise.

Entry occurs only when the state newly changes into LONG or SHORT. A stop-out
does not permit re-entry while the same state remains active. The state must
first change before another entry.

## Risk And Exit

- ATR: Wilder-style 20-bar 4H ATR.
- Initial stop: 2.0 ATR from the next-open entry.
- Trailing stop: 3.0 ATR from the best completed 4H close.
- The trailing stop can only tighten and applies from the next candle.
- LONG exits on a negative 7-day return.
- SHORT exits on a positive 7-day return.
- Maximum holding time: 1,080 bars, or 180 days.
- No fixed take-profit.
- A gap through the stop exits at the worse next available open.
- A stop touched inside a candle wins all same-candle ambiguity.

## Cost Model

Baseline:

- round-trip fee and slippage: 0.14% of notional.

Stress:

- round-trip fee and slippage: 0.20% of notional;
- adverse funding proxy: 0.03% of notional per holding day.

The funding proxy is deliberately adverse for both directions. Real funding
can be paid or received and its interval can change. Binance describes
periodic funding and a standard interest component of 0.03% per day for most
contracts:
https://academy.binance.com/en/articles/what-are-funding-rates-in-crypto-markets

Actual historical funding is required before any live decision.

## Frozen Gate

The full strategy passes historical admission only when:

- at least 24 trades;
- baseline net R greater than zero;
- baseline profit factor at least 1.15;
- stress net R greater than zero;
- stress profit factor at least 1.05;
- max baseline drawdown at most 12R;
- development stress net R greater than zero;
- holdout stress net R greater than zero.

Each side is evaluated independently. A side passes only when:

- at least 12 full-period trades;
- at least 4 development trades;
- at least 4 holdout trades;
- full baseline net R greater than zero;
- full baseline profit factor at least 1.15;
- full stress net R greater than zero;
- full stress profit factor at least 1.05;
- development and holdout stress net R are both greater than zero.

Passing this gate permits only a forward-shadow candidate. It never permits
automatic live deployment.

## Anti-Overfitting Rule

- Only this one parameter set may be run.
- No neighboring lookback, ATR, stop, trail, or holding-period variant may be
  selected after seeing the result.
- LONG and SHORT may be admitted separately because that rule is frozen here,
  before the result.
- A failed result ends D1. It cannot be repaired on the same historical data.
