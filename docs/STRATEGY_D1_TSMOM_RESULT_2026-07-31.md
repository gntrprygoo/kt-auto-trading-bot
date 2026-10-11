# Strategy D1 TSMOM Research Result

Date: 2026-07-31  
Decision: **FORWARD SHADOW CANDIDATE - LONG ONLY**  
Production impact: isolated no-order VPS timer added; live bot unchanged

## Executive Decision

The combined A/B/C S/R research is closed after failing its historical and
cost-stress gates. D1 is a separate BTC time-series momentum strategy that
does not use support/resistance, EMA, OI, funding direction, chart patterns,
or the A/B/C state machine.

The frozen D1 replay found one candidate:

- LONG passes the pre-registered historical side gate;
- SHORT fails and is rejected;
- combined LONG/SHORT is not promoted;
- LONG may proceed only to forward shadow with no Binance orders.

This is evidence of a historical candidate, not proof of a persistent live
edge and not a profit guarantee.

## Research Integrity

- Frozen specification SHA-256:
  `0F7A9E627D8896036E0131F1A34E578926C689E941B56DDB03D1C79810527723`
- Final result SHA-256:
  `E21649070C2AF2883C7DC524564FFE383828D9589123243581E783C06BB68DA4`
- Replay period: 2019-09-01 through 2026-07-22.
- Development: 2019-09-01 through 2022-12-31.
- Holdout: 2023-01-01 through 2026-07-22.
- Only the frozen 7/30/90-day parameter set was accepted for this decision.
- LONG and SHORT were replayed independently as required by the frozen spec.

Two implementation audits were completed before the final result:

1. An early draft used simple ATR despite the frozen Wilder ATR requirement.
   That draft was discarded, the engine was corrected, and the complete
   replay was rerun.
2. Side filtering was moved inside independent simulations. This prevents a
   rejected SHORT lifecycle from suppressing a valid LONG state transition.

## Final Historical Result

| Run | Trades | Baseline R | Baseline PF | Baseline DD | Stress R | Stress PF | Stress DD |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Combined | 444 | +48.922 | 1.329 | 15.438R | +31.764 | 1.202 | 20.377R |
| LONG only | 238 | +57.100 | 1.771 | 10.643R | +46.904 | 1.594 | 11.625R |
| SHORT only | 206 | -8.178 | 0.890 | 18.710R | -15.140 | 0.808 | 21.869R |

Combined D1 exceeds the frozen drawdown limit. The independently replayed
LONG side passes every frozen side check. SHORT has negative expectancy before
and after stress and is permanently rejected for D1.

## LONG Development And Holdout

| Period | Trades | Baseline R | Baseline PF | Stress R | Stress PF | Stress DD |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Development | 92 | +25.275 | 1.846 | +22.129 | 1.707 | 11.625R |
| Holdout | 146 | +31.824 | 1.720 | +24.775 | 1.520 | 8.790R |

The result remains positive after the adverse stress model of 0.20% round-trip
trading cost plus 0.03% adverse funding per holding day.

## Robustness Limits

D1 LONG has the fat-tailed return profile expected from trend following:

- stress mean: +0.1971R per trade;
- stress median: -0.1709R per trade;
- naive 95% mean interval: -0.0404R to +0.4346R;
- positive years: 3 of 7 non-empty calendar years;
- result without the single best trade: +30.857R;
- result without the five best trades: -2.138R.

Stress result by signal year:

| Year | Trades | Stress R |
| --- | ---: | ---: |
| 2020 | 39 | +26.363 |
| 2021 | 48 | -0.222 |
| 2022 | 5 | -4.013 |
| 2023 | 52 | +14.398 |
| 2024 | 48 | +16.759 |
| 2025 | 42 | -3.425 |
| 2026 partial | 4 | -2.955 |

The confidence interval includes zero, and a small number of large winners
carry much of the result. This is why historical admission cannot authorize
live execution.

Additional operating characteristics:

- average initial stop distance: 3.365% of entry;
- maximum historical initial stop distance: 13.716%;
- average holding time: 1.994 days;
- maximum holding time: 19.333 days;
- 96 trailing-stop exits produced +52.269 stress R;
- 142 momentum-flip exits produced -5.365 stress R.

Position sizing must eventually be based on account risk and actual stop
distance. Reusing a fixed notional without that sizing would create materially
different risk between trades.

## Frozen Forward Gate

D1 LONG remains shadow-only until all conditions below are met:

- at least 30 genuinely unseen closed trades;
- at least 270 calendar days of monitoring;
- public realized Binance funding is recorded for every closed trade;
- the frozen 0.20% fee/slippage stress cost remains applied;
- observed-funding stress total R greater than zero;
- observed-funding stress profit factor at least 1.15;
- maximum drawdown at most 12R;
- result remains positive after removing the single best trade;
- zero duplicate events, state corruption, look-ahead entries, or missing
  protective-price calculations;
- no changes to the frozen signal, ATR, stop, trail, or exit parameters.

If the forward gate fails, D1 LONG is rejected. It must not be repaired using
the same forward sample.

## Forward Shadow Deployment

The standalone runner is:

`tools/strategy_d1_shadow.py`

It is LONG-only, uses public Binance 4H candles, creates no production orders,
stores state atomically, suppresses historical events on first start, and
deduplicates entry and close events.

Local QA replayed 15,051 candles twice:

- invalid clock windows: 0;
- invalid next-open execution clocks: 0;
- invalid ATR entries: 0;
- first run historical notifications: 0;
- second run duplicate notifications: 0;
- artificial end-of-data exits: 0;
- production orders: false.

The QA state is stored at:

`.audit/2026-07-31-strategy-d1-momentum/shadow_qa_state_v2_20260731.json`

The forward shadow was activated on the VPS at 2026-07-31 02:25 WIB:

- timer: `kt-strategy-d1-shadow.timer`;
- interval: 15 minutes;
- code: `/opt/kt-d1-shadow`;
- state: `/var/lib/kt-d1-shadow/state.json`;
- data: public Binance endpoint only;
- current position at activation: none;
- first-run historical notifications: 0;
- second poll duplicate notifications: 0.

The systemd unit cannot access `/opt/kt-auto-trading-bot`, does not load
`config.json`, and does not receive Binance or Telegram credentials. After
activation, the live worker remained active on the same PID with zero systemd
restarts.

Every new closed trade is reconciled against Binance's public funding-rate
history. A positive funding rate is treated as a cost for LONG. The state
stores `observed_funding_R` and `observed_stress_net_R`; if funding retrieval
fails, the state write fails and the timer retries the close on its next run.
This remains a shadow estimate because no real order exists from which to
measure private fee tier or realized slippage.

The production bot code, config, Telegram runtime, SL, TP, order behavior, and
risk settings were not changed.

Final verification: all 176 project tests passed. The VPS live-worker hash
still matched the untouched local production file, its PID remained unchanged,
and its systemd restart count remained zero.

## Research Basis

- Moskowitz, Ooi, and Pedersen, "Time Series Momentum":
  https://www.sciencedirect.com/science/article/pii/S0304405X11002613
- Hurst, Ooi, and Pedersen, "A Century of Evidence on Trend-Following
  Investing":
  https://www.aqr.com/insights/research/journal-article/a-century-of-evidence-on-trend-following-investing
- Han, Kang, and Ryu, "Momentum in the Cryptocurrency Market: A Comprehensive
  Analysis under Realistic Assumptions":
  https://papers.ssrn.com/sol3/papers.cfm?abstract_id=4675565
- Binance funding-rate overview:
  https://academy.binance.com/en/articles/what-are-funding-rates-in-crypto-markets
- Binance Connector funding-rate history reference:
  https://binance.github.io/binance-connector-js/classes/_binance_derivatives-trading-usds-futures.DerivativesTradingUsdsFuturesRestAPI.MarketDataApi.html#getfundingratehistory

These sources motivate the strategy family and funding treatment. They do not
validate this implementation or guarantee future returns.
