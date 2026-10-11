# Strategy ABC V2.3: Frozen Balanced-Range A

Status: research only  
Frozen: 2026-07-30, before loading the 2020-2022 holdout  
Symbol: BTCUSDT  
Execution timeframe: 15m  
Structure timeframe: 4h and 1d

## Hypothesis

Strategy A should only trade a confirmed reaction at a meaningful balance
boundary. A range narrower than 6 ATR is more likely to be local noise, while a
range wider than 10 ATR is more likely to contain multiple internal regimes
rather than one tradable balance.

The hypothesis came from structural failure attribution. It is not a guarantee
of positive performance and may be rejected by the untouched holdout.

## Frozen Candidate

- State engine: `ABC_V21_COMBINED`.
- Admitted execution path: A only.
- A requires the existing reaction plus MSS/displacement confirmation.
- A range width: 6.0 through 10.0 4h ATR, inclusive.
- Existing S/R construction remains unchanged.
- Existing B and C state tracking remains unchanged.
- Existing target, stop, cost, cooldown, and risk rules remain unchanged.
- No direction, month, session, macro-bias, or outcome filter is allowed.

The width rule gates only the start of an A setup. It does not change which
range the structure engine selects, preventing a second hidden optimization of
the S/R map.

## Final Unseen Holdout

- Start: 2020-10-25.
- End: 2022-10-24.
- This period was not used to choose the 6-10 ATR rule.
- Public Binance Futures candles are cached after the first download.

## Acceptance Gate

All checks must pass:

- At least 15 completed trades.
- Baseline total R above zero.
- Baseline profit factor at least 1.15.
- Stress-cost total R above zero.
- Stress-cost profit factor at least 1.05.
- Average baseline R at least +0.05R.
- Maximum drawdown no greater than 10R.
- At least four non-empty 90-day folds.
- At least 50% of non-empty 90-day folds positive.

A pass still does not authorize live deployment. Manual chart-label review and
forward shadow testing remain mandatory.

## Stop Rule

If the holdout fails, no further numeric filters may be selected from the same
historical records. The next valid research input must be independently labeled
chart examples or new forward data.
