# Strategy D1 Forward Shadow Runbook

Status: LONG-only, no orders  
Service: `kt-strategy-d1-shadow.service`  
Timer: `kt-strategy-d1-shadow.timer`

## Isolation

- Code: `/opt/kt-d1-shadow`
- State: `/var/lib/kt-d1-shadow/state.json`
- Python: `/usr/bin/python3`
- Data source: public Binance BTCUSDT 4H klines
- Funding source: public Binance BTCUSDT funding-rate history
- Binance API key: not used
- Telegram token: not used
- Production config: inaccessible to the systemd unit
- Production order path: not imported

The service is a `oneshot` job. The timer runs it every 15 minutes. Unchanged
polls are silent; initialization, new entries, and new closed trades are
written to the system journal.

Each closed trade stores observed public funding separately from the frozen
fee/slippage stress cost. A funding lookup failure makes the job fail before
state is written, so the next timer run retries reconciliation.

## Status

```bash
sudo systemctl status kt-strategy-d1-shadow.timer
sudo systemctl show kt-strategy-d1-shadow.service \
  -p Result -p ExecMainStatus -p ActiveEnterTimestamp
sudo systemctl list-timers kt-strategy-d1-shadow.timer
```

## Event Log

```bash
sudo journalctl -u kt-strategy-d1-shadow.service --since today
```

## State

```bash
sudo -u kulitrader /usr/bin/python3 -m json.tool \
  /var/lib/kt-d1-shadow/state.json
```

## Run Now

```bash
sudo systemctl start kt-strategy-d1-shadow.service
sudo systemctl show kt-strategy-d1-shadow.service \
  -p Result -p ExecMainStatus
```

## Stop Or Disable

Stopping the timer does not affect the live trading bot.

```bash
sudo systemctl disable --now kt-strategy-d1-shadow.timer
```

## Safety Check

```bash
sudo systemctl is-active kt-auto-trading-bot
sudo systemctl show kt-auto-trading-bot -p MainPID -p NRestarts
sudo systemctl cat kt-strategy-d1-shadow.service
```

The D1 unit must show:

- `InaccessiblePaths=-/opt/kt-auto-trading-bot`
- no `KT_BOT_CONFIG`
- no import or execution of `v3_swing_bot_fixed.py`
- no Binance private endpoint or API key

## Forward Gate

Do not enable live orders from this service. Review D1 only after at least 270
days and 30 genuinely unseen closed trades under the frozen gate documented
in `STRATEGY_D1_TSMOM_RESULT_2026-07-31.md`.

## Telegram Monitoring

The production Telegram worker may read this service's public state through
`/d1shadow`. The command is read-only and reports worker freshness, current
shadow position, observed-funding stress performance, and forward-gate
progress. It does not call a private Binance endpoint, write the D1 state, or
create an order.
