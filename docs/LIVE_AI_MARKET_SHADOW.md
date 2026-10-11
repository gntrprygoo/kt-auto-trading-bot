# OpenAI Live Market Shadow

Date: 2026-08-07

Status: `RESEARCH_SHADOW_ONLY`

## Purpose

P6 is a range-only research planner. It may produce one complete shadow setup
when the market is sideways and a confirmed edge trigger exists. Otherwise it
must return `NO_TRADE`.

A complete setup contains the selected pair and side, range boundaries, entry
zone, entry trigger, structural invalidation, stop loss, TP1, TP2, expiry,
evidence, and thesis. The OpenAI model selects these levels. The application
validates the submitted levels without selecting, moving, or repairing them.

The production strategies, position sizing, SL/TP orders, and live order
lifecycle are unchanged. This subsystem contains no Binance order call and all
records contain `orders_allowed=false`.

## Evidence Boundary

The earlier direct-prompt tournament did not show a positive, cost-robust
historical edge. The active prompt is therefore
`P6_RANGE_ABSORPTION_SETUP_V1_SHADOW`, and every result remains forward research.
A complete setup format is not proof of profitability and is not an approved
trading signal.

The previous V1 and V2 records remain preserved for audit. They are excluded
from V3 statistics because they used older decision and numeric-grounding
contracts.

## Decision Sequence

1. The VPS verifies the configured Binance Futures credentials locally before
   an OpenAI scan.
2. It fetches 800 public 15-minute bars for BTC, ETH, SOL, ADA, DOGE, and XRP.
3. It selects the latest common confirmed full-hour close and rejects missing or
   non-contiguous data.
4. It builds exact price, 24-hour and 7-day range, ATR, tick-size, confirmed
   hourly swing, recent candle, volume, taker-flow, trend, and BTC-context data.
5. P6 first classifies the regime. A trend, transition, volatile market,
   mid-range location, or unconfirmed trigger must produce `NO_TRADE`.
6. For a valid range edge, P6 selects the complete setup geometry in a strict
   JSON schema.
7. The application rejects any level that is not tick-aligned, not grounded in
   the supplied structure, inconsistent with the claimed edge trigger, outside
   the selected range, or below the cost-adjusted R:R gates.
8. A validated setup enters a deterministic shadow lifecycle. No order is sent.

The conservative geometry gates include 0.20% modeled round-trip cost and
require at least 1.0R to TP1 and 1.8R to TP2. The least favorable edge of the
entry zone is used for validation.

Range-position fields end in `_pct`, use a 0-to-100 scale, and are never prices.
For example, `range_position_7d_pct=20.54` means that the close is 20.54% of the
distance from the seven-day low to the seven-day high.

## Shadow Lifecycle

While a setup is active, the worker checks only its public 15-minute candles
every five minutes. It does not call OpenAI again until the setup closes or
expires. Lifecycle states are:

- `PENDING`: entry zone has not traded.
- `ACTIVE`: shadow entry has been touched.
- `TP1_HIT`: the first 50% shadow target has been reached.
- `TP2_HIT`, `SL_HIT`, `EXPIRED`, or `TIME_EXIT`: terminal result.

Only confirmed candles are scored. If stop and target appear in the same candle,
the stop is scored first. A target on the same candle as the initial entry touch
is not awarded because OHLC data cannot prove that the target happened after
entry. This intentionally avoids optimistic backfill.

## Data Security

Binance API key, Binance secret, balances, positions, Telegram token, OpenAI
key, and user identity are never included in the OpenAI request. The OpenAI key
remains in the root-only VPS environment file:

```text
/etc/kt-auto-trading-bot/hybrid-ai.env
```

Expected variable:

```text
OPENAI_API_KEY=YOUR_OPENAI_API_KEY
```

Do not place keys in Telegram, `config.json`, source code, screenshots, or logs.

Official references:

- [OpenAI Structured Outputs](https://developers.openai.com/api/docs/guides/structured-outputs)
- [OpenAI model guidance](https://developers.openai.com/api/docs/guides/latest-model?model=gpt-5.6)
- [Binance USD-M Futures klines](https://developers.binance.com/en/docs/products/derivatives-trading-usds-futures/market-data/rest-api/Kline-Candlestick-Data)
- [Binance USD-M exchange information](https://developers.binance.com/en/docs/catalog/core-trading-derivatives-trading-usd-s-m-futures/api/rest-api/market-data#exchange-information)

## Configuration

```json
{
  "enabled": true,
  "model": "gpt-5.6-sol",
  "reasoning_effort": "low",
  "prompt_id": "P6_RANGE_ABSORPTION_SETUP",
  "scan_interval_sec": 3600,
  "setup_monitor_interval_sec": 300,
  "failure_retry_sec": 900,
  "candle_limit": 800,
  "min_closed_bars": 700,
  "require_authenticated_binance": true,
  "notify_admin_on_setup": true,
  "notify_admin_on_lifecycle": true
}
```

The maximum normal cadence is 24 OpenAI calls per day. An active setup pauses
new OpenAI decisions while its public candles are monitored, so actual usage can
be lower. Duplicate hourly snapshots are not sent again.

## Telegram

The admin command `/ai_market` shows the latest decision, exact Binance market
references, validated setup geometry, cost-aware R:R, active lifecycle, shadow
statistics, evidence, risk flags, and token usage.

Only admins receive one alert when a new setup is created and when a meaningful
lifecycle event occurs. `NO_TRADE`, empty monitor checks, startup, and debugging
messages do not notify users.

## Verification

```powershell
& "C:\Users\YOUR_WINDOWS_USER\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" `
  -m unittest tests.test_ai_range_setup tests.test_live_ai_market `
  tests.test_hybrid_ai_runtime
```

## VPS Deployment

Stage the files in `/tmp/kt-ai-market-live-upload`, then run:

```bash
cd /tmp/kt-ai-market-live-upload
bash deploy/deploy_live_ai_market_shadow.sh /tmp/kt-ai-market-live-upload
```

The deployment creates a timestamped backup, updates configuration atomically,
compiles the installed files, restarts the service, verifies the hard research
lock, and refreshes Telegram commands. A failed deployment restores the backup.

V3 runtime records:

```text
/opt/kt-auto-trading-bot/data/ai_market_live_state_v3.json
/opt/kt-auto-trading-bot/data/ai_market_live_history_v3.jsonl
```
