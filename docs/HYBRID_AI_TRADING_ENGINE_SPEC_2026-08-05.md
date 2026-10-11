# Hybrid AI Trading Engine Frozen Specification

Date: 2026-08-05

Status: `IMPLEMENTATION_FROZEN_DEFAULT_SHADOW`

## Objective

Add an AI review layer to a deterministic Binance Futures setup without giving
the model authority to invent a side, price, stop, target, quantity, or risk.
The engine must fail closed for approval and live execution while preserving the
existing production strategy in shadow mode.

This system does not claim or guarantee profitability. Historical replay and
forward observation are evidence gates, not optimization targets.

## Decision boundary

The deterministic bot remains responsible for:

- candidate generation;
- side selection;
- confirmed-candle features;
- entry, SL, TP1, and TP2;
- exchange precision and minimum notional;
- position sizing;
- Binance authentication and order lifecycle.

The OpenAI model may only return:

- `TRADE` or `SKIP`;
- confidence from 0 through 1;
- market regime classification;
- setup-quality score;
- concise thesis and invalidation;
- a bounded list of risk flags.

The model cannot reverse the side or modify execution parameters.

## Modes

### AI_SHADOW

- Records AI decisions and deterministic gate results.
- Sends no AI order.
- Does not block or alter the existing production strategy.
- Is the only permitted initial deployment mode.

### AI_APPROVAL

- AI `SKIP`, malformed output, timeout, or any failed risk check blocks the
  candidate.
- Passing candidates are stored as `PENDING_APPROVAL` and sent to the admin.
- The proposal expires after a short TTL.
- Approval is accepted only from an admin Telegram chat.
- Price freshness and account risk are checked again before execution.

### AI_LIVE

- Requires both `allow_live=true` in config and a valid gate artifact.
- The gate artifact must prove that frozen development and validation replays
  passed their stated thresholds.
- Any unavailable dependency, stale data, duplicate candidate, or invalid state
  results in `SKIP`.
- Live mode starts with a maximum USD 10 notional and one AI position.

## Hard safety policy

- API key comes only from the `OPENAI_API_KEY` environment variable.
- No Binance credential or Telegram token is sent to OpenAI.
- OpenAI requests use `store=false`.
- Candidate IDs are deterministic and deduplicated.
- Responses must satisfy a strict JSON schema.
- Any risk flag blocks approval and live execution.
- Minimum RR: 1.5.
- Maximum stop distance: 3 percent.
- Maximum estimated account risk: 0.25 percent.
- Maximum AI notional: USD 10.
- Maximum open AI positions: 1.
- Maximum approval age: 5 minutes.
- Maximum execution price deviation: 0.30 percent.
- Daily AI stop: -1R.
- Missing or corrupt live gate always locks AI_LIVE.

## Historical replay protocol

1. Freeze model, prompt version, schema, thresholds, and candidate family.
2. Build every model input using data available at signal time only.
3. Never send exit reason, future price, gross R, or net R to the model.
4. Cache each response by candidate ID and request hash.
5. Evaluate transaction-cost-adjusted baseline and stress R.
6. Development must pass before validation is considered.
7. Validation is evaluated once with unchanged settings.
8. A failed validation produces a locked gate artifact and cannot enable live.

Development gate:

- at least 100 reviewed candidates;
- at least 30 accepted trades;
- decision coverage at least 95 percent;
- baseline total R positive and PF at least 1.15;
- stress total R positive and PF at least 1.05;
- maximum drawdown no greater than 12R.

Validation gate:

- at least 15 reviewed candidates;
- at least 8 accepted trades;
- decision coverage at least 95 percent;
- baseline total R positive and PF at least 1.10;
- stress total R non-negative;
- maximum drawdown no greater than 6R.

## Operational controls

- `/ai_status` shows mode, key readiness, gate status, and proposal counts.
- `/ai_pending` lists unexpired proposals.
- `/ai_approve ID` approves one proposal and executes only after revalidation.
- `/ai_reject ID` rejects one proposal.
- `/ai_mode shadow|approval|live` changes mode for admins only.

Mode changes are persisted atomically. Telegram cannot bypass `allow_live` or
the replay gate.

## Initial rollout

1. Run historical replay with the frozen prompt.
2. Deploy only `AI_SHADOW`.
3. Review response validity, latency, cost, and selected-trade performance.
4. Open `AI_APPROVAL` only after operational checks pass.
5. Open `AI_LIVE` only if the immutable replay gate passes and the operator
   explicitly enables live in configuration.
