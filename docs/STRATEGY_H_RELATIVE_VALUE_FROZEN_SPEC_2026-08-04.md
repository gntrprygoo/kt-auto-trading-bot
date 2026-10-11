# Strategy H - Intraday Relative Value

Status: `FROZEN_BEFORE_DEVELOPMENT_RUN`

Strategy H is a market-neutral research family. It trades one long altcoin and
one short altcoin at equal notional so that broad BTC direction is not the main
source of return. It is research-only and cannot place orders.

## Data and universe

- Factor: BTCUSDT.
- Ranked assets: ETHUSDT, XRPUSDT, SOLUSDT, DOGEUSDT, ADAUSDT.
- Verified Binance USD-M 15-minute OHLCV and taker-buy volume.
- Signal after the final bar before a scheduled UTC boundary.
- Entry at the next 15-minute open.
- One equal-notional long/short pair at a time.
- Same-bar stop/target collision is scored as a stop.

## Frozen candidates

Exactly six candidates are tested:

1. `H1_MOMENTUM_8H`: rank beta-adjusted 24-hour returns; long strongest, short
   weakest; minimum cross-sectional spread 2.5%; hold up to eight hours.
2. `H1_MOMENTUM_FLOW_8H`: same, minimum spread 2.0%, with current flow aligned
   to both legs.
3. `H2_REVERSAL_8H`: rank beta-adjusted 24-hour returns; long weakest, short
   strongest; minimum spread 2.5%; hold up to eight hours.
4. `H2_REVERSAL_FLOW_8H`: same, minimum spread 2.0%, with current flow aligned
   to both legs.
5. `H3_MOMENTUM_24H`: beta-adjusted 72-hour ranking at 00:00 UTC, minimum spread
   5.0%, hold up to 24 hours.
6. `H3_REVERSAL_24H`: inverse of candidate 5.

Eight-hour candidates evaluate at 00:00, 08:00, and 16:00 UTC. The signal uses
only completed bars before that boundary. Their pair stop/target are -1.0% and
+1.5%. Twenty-four-hour candidates use -1.5% and +2.25%.

## Costs

Equal-notional pair returns average the two leg returns. A 0.14% fee on each
leg's own notional is therefore still 0.14% of pair capital, not 0.28%.
Strategy H uses a more conservative `0.16%` baseline and `0.24%` stress cost to
include possible funding and execution mismatch between legs.

## Chronology

- Development: verified common history through 2025-08-31 UTC.
- Validation: 2025-09-01 through 2026-02-28 UTC.
- Final holdout: 2026-03-01 onward.

Only a candidate passing every development gate can open validation. If several
pass, select the highest stress total R. Parameters remain frozen thereafter.

## Development gate

- At least 200 trades.
- Baseline total R positive and profit factor at least 1.15.
- Stress total R positive and profit factor at least 1.05.
- At least 55% of active months positive.
- At least 60% of active calendar years positive.
- At least four assets used on each side.
- Maximum drawdown no greater than 20R.

## Validation gate

- At least 30 trades.
- Baseline total R positive and profit factor at least 1.10.
- Stress total R non-negative.
- At least 50% of active months positive.
- Maximum drawdown no greater than 10R.

## Holdout gate

- At least 20 trades.
- Baseline total R positive and profit factor at least 1.05.
- Stress total R non-negative.
- Maximum drawdown no greater than 10R.

A full pass permits forward shadow only. It does not permit live two-leg orders.
