# KT Strategy B/C Optimization Decision - 2026-07-22

## Executive decision

- Strategy A remains live and is not changed by this work.
- Strategy B remains `PAUSED_NO_VALIDATED_EDGE`.
- Strategy C6 Market Strict is approved for `FORWARD_SHADOW` only.
- Strategy C6 cannot create Binance orders.
- Live promotion is not approved until at least 30 C6 forward shadow trades
  have closed and pass the stated gate.

No strategy can guarantee consistent profit. This decision improves testable
robustness and blocks deployment when evidence is insufficient.

## Bugs and design faults corrected

1. Strategy B support/resistance was already anchored before C1/C2. Its volume
   baseline still included C1, which diluted C1's own volume ratio. Runtime now
   excludes C1, C2, and the incomplete candle, matching replay.
2. B's old retest order-flow check expected immediate same-direction aggression.
   B3 research tested the more coherent sequence of opposing-flow absorption
   followed by directional confirmation. It still failed holdout and remains
   paused.
3. C3 treated candle volume as proof of liquidity and permitted unstable
   countertrend reversals. C6 permits only trend-aligned pullback sweeps.
4. C6 now requires the full chronological sequence: local liquidity sweep,
   opposing-flow absorption, directional MSS displacement, MSS retest, and BTC
   market-regime agreement.
5. Runtime and replay initially differed in ATR calculation, history length,
   and entry timestamp. C6 now uses the same 14-candle true-range average,
   199 closed-candle runtime window, and next-candle open in both engines.
6. A persistent `setup_id` prevents one sweep from being recorded repeatedly.
7. C6 shadow trades use a 96-hour timeout and conservative same-candle SL/TP
   handling.

## Validation method

- Universe: 30 established Binance USDT perpetual pairs.
- Development: 2026-04-23 through 2026-07-22 (90 days).
- Holdout: 2025-10-25 through 2026-04-22 (180 days), not used to tune C6.
- Entry: next 15-minute candle open.
- Estimated round-trip fee plus slippage: 0.14%.
- Same candle touches SL and TP: counted as loss.
- Timeout: mark to market after 96 hours.
- Primary target selected before forward deployment: 1.5R.
- Runtime parity: all 66 selected C6 records matched by side and sweep ID.

Binance klines expose candle and taker-buy volume, not a full historical limit
order book. C6 therefore treats taker flow as an absorption proxy, not as true
order-book order-flow imbalance.

## Strategy B decision

### Development (90 days)

| Candidate | Trades | Net R at 1.5R | PF | Max DD |
|---|---:|---:|---:|---:|
| B3 Absorb Confirm | 12 | -1.026R | 0.869 | 3.396R |
| B3 Strict | 3 | -3.214R | 0.000 | 3.214R |
| B3 Price Only | 32 | +0.527R | 1.027 | 8.134R |

### Holdout (180 days)

| Candidate | Trades | Net R at 1.5R | PF | Max DD |
|---|---:|---:|---:|---:|
| B3 Absorb Confirm | 23 | -6.382R | 0.633 | 7.795R |
| B3 Strict | 8 | +0.693R | 1.146 | 2.415R |
| B3 Price Only | 65 | -14.137R | 0.700 | 23.897R |

No B candidate has enough stable evidence. Enabling B would be optimization by
hope, not by validation. Its corrected foundation remains in the codebase, but
`strategy_b.enable_live` remains false.

## Strategy C6 decision

### Selected candidate: C6 Market Strict, target 1.5R

| Period | Trades | WR | Net R | PF | Max DD |
|---|---:|---:|---:|---:|---:|
| Development 90d | 24 | 54.17% | +5.275R | 1.433 | 4.325R |
| Holdout 180d | 42 | 52.38% | +8.582R | 1.389 | 5.045R |
| Combined 270d | 66 | 53.03% | +13.857R | 1.405 | 5.045R |

Combined direction split:

| Side | Trades | WR | Net R | PF |
|---|---:|---:|---:|---:|
| LONG | 28 | 46.43% | +1.030R | 1.063 |
| SHORT | 38 | 57.89% | +12.827R | 1.722 |

The result spans 26 pairs. The largest pair supplied 18.1% of gross positive R,
so the total is not explained by one contract. Five of nine non-empty 30-day
folds were positive; the worst fold was -2.811R.

The LONG side is only marginally positive and is the main forward-validation
risk. This is why C6 is shadow-only despite passing the historical shadow gate.

## Promotion gate

Historical shadow admission passed all configured checks:

- development and holdout net R positive;
- development, holdout, and combined PF above 1.20;
- at least 60 combined trades;
- combined drawdown no more than 10R;
- combined LONG and SHORT net R positive;
- at least 50% positive non-empty monthly folds;
- worst monthly fold no worse than -4R;
- no pair supplies more than 35% of gross positive R.

Live promotion additionally requires at least 30 closed forward C6 shadow
trades. At that checkpoint, require PF above 1.20, positive net R, controlled
drawdown, and no negative direction bucket with an adequate sample. Until then,
the live status is `NOT_APPROVED`.

## Operational behavior

- Telegram `/status`: `A LIVE | B PAUSED | C SHADOW C6`.
- Telegram `/shadow`: C6 results remain separate from C1/C2/C3 legacy data.
- C6 records virtual entry, SL, TP, setup ID, absorption, MSS flow, and risk.
- C6 does not send a notification for every scan or near miss.
- Existing live positions and their SL/TP orders are not changed.

## Evidence artifacts

- `.audit/2026-07-22-strategy-b-c/strategy_bc_v5_recent90_livewindow.json`
- `.audit/2026-07-22-strategy-b-c/strategy_bc_v5_holdout180_livewindow.json`
- `.audit/2026-07-22-strategy-b-c/strategy_bc_v5_gate.json`
- `tools/research_strategy_bc_v2.py`
- `tools/evaluate_strategy_bc_gate.py`
- `tools/verify_c6_runtime_parity.py`

## VPS deployment verification

- Deployed at `2026-07-22 14:00 WIB` through `deploy/deploy_c6.sh`.
- Rollback snapshot: `/opt/kt-auto-trading-bot/backups/deploy-c6-20260722T070048Z`.
- Production SHA-256: `76060ddfb22b9263d71298dd5f5d0f7e1bc400e140f281829d1ab81b14dc4f0c`.
- Service state: active, PID `164265`, `NRestarts=0`, one worker process.
- First scan completed with 30 active pairs and no runtime traceback.
- Runtime verification: B v2 live disabled; C v6 shadow enabled; C order execution disabled.
- One concise audit update was delivered to the Telegram admin chat.

## Research basis

- Binance USD-M Futures kline data fields and limitations:
  https://developers.binance.com/en/docs/products/derivatives-trading-usds-futures/market-data/rest-api/Kline-Candlestick-Data
- Cont, Kukanov, and Stoikov on order-flow imbalance and short-horizon price
  impact: https://arxiv.org/abs/1011.6402
- Moskowitz, Ooi, and Pedersen on time-series momentum across futures:
  https://w4.stern.nyu.edu/facdir/lpederse/papers/TimeSeriesMomentum.pdf

Historical replay, forward shadow performance, and these references do not
guarantee future returns.
