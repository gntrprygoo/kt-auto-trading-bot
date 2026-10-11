# Strategy F - Selective Intraday Edge Research

Status: `FROZEN_BEFORE_DEVELOPMENT_RUN`

This document freezes the Strategy F research protocol before any Strategy F
development result is inspected. Strategy F is research-only. It must not place
orders or alter the existing live, D1, or C6 paths.

## Objective

Find a selective intraday futures edge that remains positive after realistic
round-trip costs. "Profitable" means a positive, reproducible out-of-sample
expectancy. It does not mean guaranteed future profit.

## Research motivation

- Intraday crypto returns can show state-dependent momentum and reversal.
- Cross-cryptocurrency returns can contain spillover information.
- Taker order imbalance can contain medium-horizon information, but the raw
  quarter-hour effect is too small to trade at every boundary after fees.
- Therefore Strategy F tests only selective, high-conviction combinations of
  flow, price response, volatility, and cross-asset residual state.

Primary references:

- Kim and Hansen (2026), *The Quarter-Hour Effect: Periodic Algorithmic Trading
  and Return Predictability in Cryptocurrency Futures*.
- Guo, Sang, Tu, and Wang (2024 revision), *Cross-Cryptocurrency Return
  Predictability*.
- Wen, Bouri, Xu, and Zhao (2022), *Intraday Return Predictability in the
  Cryptocurrency Markets: Momentum, Reversal, or Both*.
- Jia, Wu, Yan, and Yin (2023 revision), *A Seesaw Effect in the Cryptocurrency
  Market*.

## Data and chronology

- Venue data: Binance USD-M perpetual 15-minute OHLCV and taker-buy volume.
- Assets: BTCUSDT, ETHUSDT, SOLUSDT.
- Common timestamps only.
- Signal is evaluated after a bar closes.
- Entry is always the next bar open.
- Same-bar stop and target collision is scored as a stop.
- A maximum of one Strategy F position may be open across all assets.

Frozen periods:

- Development: available common history through `2025-08-31 23:59:59 UTC`.
- Validation: `2025-09-01` through `2026-02-28 UTC`.
- Final holdout: `2026-03-01 UTC` onward.

Validation may be opened only for a development candidate that passes every
development gate. Holdout may be opened only after that same frozen candidate
passes validation. Failed stages must not be retuned against the next stage.

## Candidate families

Exactly 12 candidates are frozen: three variants in each family.

1. `FLOW_CONTINUATION`
   Extreme 15-minute taker imbalance, elevated volume, directional candle, and
   aligned one-hour price impulse. Trade in the flow direction.
2. `FLOW_ABSORPTION`
   Extreme taker imbalance and elevated volume fail to move price in the same
   direction. Trade in the confirmed price direction, opposite aggressive flow.
3. `RESIDUAL_REVERSION`
   ETH or SOL makes an extreme beta-adjusted four-hour move versus BTC, then
   short-term flow and price turn back toward the market factor.
4. `RESIDUAL_MOMENTUM`
   ETH or SOL makes an extreme beta-adjusted four-hour move with confirming flow
   and price. Trade continuation only while its own slow trend agrees.

Frozen parameter variants are defined in
`tools/research_strategy_f_intraday.py`; changing those values creates a new
research version and requires a new sealed protocol.

## Execution and costs

- Stop: candidate ATR multiple, with a minimum risk distance of 0.75%.
- Maximum accepted initial risk distance: 2.50%.
- Exit: stop, fixed-R target, or time stop at four/eight hours.
- Baseline round-trip cost: 0.14% of notional.
- Stress round-trip cost: 0.20% of notional.
- Costs are converted into R using each trade's actual initial risk distance.
- No breakeven, SL+, partial TP, or discretionary exit is credited in research.

## Development gate

Every condition must pass:

- At least 80 completed portfolio-level trades.
- Baseline net total R greater than zero.
- Baseline profit factor at least 1.15.
- Stress net total R greater than zero.
- Stress profit factor at least 1.05.
- At least two profitable symbols after baseline costs.
- At least 55% of active calendar months profitable.
- Baseline maximum drawdown no greater than 15R.
- At least 20 long and 20 short trades, with both sides positive after baseline
  costs.

If more than one candidate passes, select the candidate with the highest stress
total R. No other ranking rule is allowed.

## Validation and holdout gates

Validation requires at least 35 trades, positive baseline total R, baseline
profit factor at least 1.10, non-negative stress total R, at least 50% positive
active months, and maximum drawdown no greater than 12R.

Final holdout requires at least 20 trades, positive baseline total R, baseline
profit factor at least 1.05, non-negative stress total R, and maximum drawdown no
greater than 10R.

## Deployment rule

Only a candidate that passes development, validation, and final holdout without
parameter changes may be implemented as a new forward-shadow path. Forward
shadow must run without orders for at least 30 closed trades before any separate
live-release review. A failed candidate is recorded, not repaired against sealed
data.
