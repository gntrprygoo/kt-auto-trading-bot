# Hybrid AI Trading Engine Runbook

## Current safety state

- Initial mode: `AI_SHADOW`.
- `AI_LIVE` is locked by `allow_live=false`.
- A valid development plus validation replay artifact is also mandatory.
- The AI reviewer cannot change side, entry, SL, TP, quantity, leverage, or risk.
- OpenAI never receives Binance credentials, Telegram tokens, account IDs, or balances.
- This system does not guarantee profit and is not financial advice.

As of 2026-08-05, the one-event network smoke test reached the OpenAI API but
returned `insufficient_quota`. Historical OpenAI replay therefore remains
incomplete and the live gate remains locked.

## What each mode does

`AI_SHADOW`

- Reviews only deterministic candidates that already pass the bot rules.
- Stores the decision and reason.
- Does not alter the existing production entry.
- Sends no AI approval message and sends no AI order.

`AI_APPROVAL`

- AI `SKIP`, timeout, invalid output, or failed risk checks block the candidate.
- A passing proposal is sent to the admin Telegram account.
- `/ai_approve ID` rechecks age, price, account risk, open positions, and daily AI R.
- `/ai_reject ID` closes the proposal without an order.
- Proposals expire after five minutes and execute at most once.

`AI_LIVE`

- Cannot be enabled until both historical stages pass unchanged settings.
- Also requires an explicit `allow_live=true` config change.
- Starts with at most USD 10 notional, 0.25 percent account risk, one AI position,
  and a daily AI stop at -1R.

## Fund the OpenAI API

ChatGPT subscription and OpenAI API credit are separate. Add API credit in the
OpenAI Platform billing page, then keep the key in an environment variable only.

PowerShell for the current terminal:

```powershell
$env:OPENAI_API_KEY = "YOUR_OPENAI_API_KEY"
```

Do not put this key in `config.json`, Telegram, source code, screenshots, or logs.

## Resume historical replay

From the project folder:

```powershell
.\tools\run_hybrid_ai_replay.ps1
```

The runner starts with one API/model/schema smoke event, then uses two concurrent
requests and a resumable JSONL cache. Completed responses are not requested
again. Invalid model/schema, quota, authentication, or rate-limit errors stop
later request batches. Validation stays sealed unless development passes its
frozen cost-aware gate.

Outputs:

- `.audit/2026-08-05-hybrid-ai/openai_development.json`
- `.audit/2026-08-05-hybrid-ai/openai_validation.json`
- `.audit/2026-08-05-hybrid-ai/openai_replay_cache.jsonl`
- `.audit/2026-08-05-hybrid-ai/hybrid_ai_live_gate.json`

Exit code `2` means incomplete decisions or a failed gate. It is not permission
to tune on validation; keep `AI_LIVE` locked.

## VPS secret setup

Deploy code in shadow mode first. Then edit the root-only environment file:

```bash
sudo nano /etc/kt-auto-trading-bot/hybrid-ai.env
```

Its only line is:

```text
OPENAI_API_KEY=YOUR_OPENAI_API_KEY
```

Apply and check without printing the secret:

```bash
sudo chmod 600 /etc/kt-auto-trading-bot/hybrid-ai.env
sudo systemctl restart kt-auto-trading-bot
sudo systemctl is-active kt-auto-trading-bot
journalctl -u kt-auto-trading-bot -n 80 --no-pager
```

## Telegram controls

Admin-only commands:

```text
/ai_status
/ai_pending
/ai_mode shadow
/ai_mode approval
/ai_approve AI-XXXXXXXXXXXXXXX
/ai_reject AI-XXXXXXXXXXXXXXX
```

Sync command tersebut ke menu Telegram tanpa menghapus command lama:

```bash
cd /opt/kt-auto-trading-bot
KT_BOT_CONFIG=/opt/kt-auto-trading-bot/config.json \
  .venv/bin/python tools/sync_hybrid_ai_telegram_commands.py --apply
```

`/ai_mode live` remains blocked until both independent locks pass. Use
`/ai_mode shadow` as the immediate safe fallback; this command does not require
the OpenAI key to be available.

## Promotion order

1. Complete historical development replay.
2. Stop if development fails; do not inspect AI validation for tuning.
3. Complete frozen validation only after development passes.
4. Deploy `AI_SHADOW` and check response validity, latency, usage, and errors.
5. Use `AI_APPROVAL` with manual decisions and USD 10 cap.
6. Consider `AI_LIVE` only if the immutable gate says `PASSED` and operational
   forward evidence is also acceptable.

No promotion step changes existing open positions or their SL/TP orders.
