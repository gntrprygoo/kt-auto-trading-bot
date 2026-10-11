# Changelog

## 2026-08-07 - P6 Complete Range Setup Shadow

- Replaced the P6 summary-only decision with a strict complete setup contract:
  selected range, entry zone and trigger, invalidation, SL, TP1, TP2, and expiry.
- Added Binance tick-size, exact recent candles, and confirmed hourly swings to
  the live snapshot. Missing or non-contiguous data now fails closed.
- Added deterministic validation for price grounding, claimed edge trigger,
  range geometry, and conservative cost-adjusted R:R without changing AI levels.
- Added a confirmed-15m shadow lifecycle with conservative same-bar scoring,
  five-minute public-data monitoring, and V3 state/history isolation.
- Added admin-only Telegram alerts for setup creation and meaningful lifecycle
  events. No-trade, empty checks, startup, and debug output remain silent.
- Preserved `orders_allowed=false`; P6 still has no validated edge and cannot
  place, size, approve, or modify a Binance order.

## 2026-08-07 - OpenAI Market Numeric Grounding Fix

- Confirmed that the XRP Binance snapshot was correct (`last_close=1.0306`),
  while the model incorrectly described `range_position_7d=0.2054` as a price.
- Replaced ambiguous 0-to-1 range-position fields in live snapshots with
  explicit 0-to-100 percentage fields and added exact 24-hour/7-day USDT range
  boundaries.
- Upgraded P6 to `P6_RANGE_ABSORPTION_REVERSAL_V3_GROUNDED` without changing its
  range-absorption method; it remains rejected-gate shadow research only.
- Added a deterministic post-response grounding guard that rejects unrecognized
  narrative price claims before they can enter state or research history.
- Added Binance-sourced close and range references to `/ai_market`, and moved the
  corrected forward observations to V2 state/history files so the original 17
  scans remain preserved but excluded from the new sample.

## 2026-08-06 - OpenAI Live Market Shadow

- Added an isolated hourly worker that builds point-in-time snapshots from
  confirmed Binance USD-M Futures candles and sends only derived market data to
  OpenAI.
- Preserved the rejected historical direct-scanner gate: all decisions are
  marked research shadow-only and the module contains no order capability.
- Added local Binance-account credential verification while excluding API
  credentials, balances, positions, Telegram data, and user identity from model
  requests.
- Added atomic latest state, append-only JSONL history, hourly deduplication,
  bounded failure retries, usage metadata, and no scheduled Telegram alerts.
- Added the admin-only `/ai_market` report plus a rollback-capable VPS deployment
  script and parity tests against the historical feature contract.

## 2026-08-06 - Direct AI Prompt Tournaments Rejected

- Completed 1,440 unique OpenAI development decisions across six direct market
  scanner prompts; no prompt passed the frozen development gate.
- Rejected V1 after its 24 raw trade selections remained negative when the
  confidence, quality, and risk-flag blocks were removed offline.
- Rejected V2: long pullback lost -13.754R, balanced continuation lost -8.881R,
  and the closest range-absorption prompt still lost -1.158R baseline and
  -2.739R under stress costs.
- Kept the 2024 unseen validation set sealed, with no development winner and no
  eligibility for AI signal, approval, or live execution.
- Audited duplicate model responses and measured 87.3 to 91.2 percent agreement
  on action/pair/side, insufficient for direct autonomous execution.
- Stopped an orphan replay process, recorded approximately USD 1.478 in logged
  API usage including duplicates, and added an exclusive cross-process replay
  lock to prevent recurrence.
- Passed all 258 regression tests; production VPS and order behavior were not
  changed.

## 2026-08-05 - Direct AI Market Scanner Research Pipeline

- Added an independent six-pair market scanner that lets the model choose one
  pair and direction or return `NO_TRADE`; deterministic code retains all
  execution geometry, sizing, account risk, and order authority.
- Added three frozen prompt variants for regime/structure, liquidity/flow, and
  conservative confluence research.
- Built separate 240-snapshot development and unseen-validation datasets from
  confirmed OHLCV and taker-flow history without future outcomes, OI, funding,
  or order-book fields.
- Added strict feature-contract hashing, future-field detection, resumable API
  caching, one-position replay, pessimistic same-bar handling, and baseline plus
  stress transaction costs.
- Added fail-closed development and validation gates with no forced winner;
  historical success can unlock only `AI_SIGNAL`, never approval or live mode.
- The one-request smoke reached OpenAI but stopped on
  `credit_balance_exhausted`; no bulk tournament ran, no winner exists, and the
  production VPS bot remains unchanged.

## 2026-08-05 - Hybrid AI Trading Engine, Locked by Default

- Added a bounded OpenAI reviewer that can only return `TRADE` or `SKIP`; the
  deterministic bot retains side, prices, SL/TP, quantity, leverage, and risk.
- Added `AI_SHADOW`, admin-gated `AI_APPROVAL`, and double-locked `AI_LIVE`.
- Added atomic proposal state, expiry, deduplication, single-claim execution,
  price/account-risk revalidation, USD 10 notional cap, one-position cap, and
  daily AI stop at -1R.
- Added admin Telegram commands for status, pending proposals, mode selection,
  approval, and rejection.
- Added leakage-guarded, cost-aware historical replay with strict structured
  output, `store=false`, resumable cache, and bounded parallel requests.
- Added immutable development/validation gate evaluation and VPS shadow
  deployment/runbook files.
- Completed the 215-candidate local heuristic control replay with zero alignment
  failures; it failed the cost/stress gate as expected and cannot unlock live.
- Reached the OpenAI API in a one-event smoke test, but the account returned
  `insufficient_quota`; OpenAI replay remains incomplete and `AI_LIVE` locked.

## 2026-07-31 - Telegram D1 Forward Shadow Monitor

- Added the read-only `/d1shadow` command for admins and active managed users.
- Reported D1 worker freshness, current LONG-only shadow position, frozen-gate
  progress, observed funding, stress R, profit factor, drawdown, and the result
  without the best trade.
- Kept D1 isolated from private Binance credentials and every production order
  path; the Telegram worker only reads the public forward-shadow state.
- Synchronized the global Telegram menu from 27 to 28 commands while
  preserving every existing command.

## 2026-07-31 - Strategy D1 LONG-Only Forward Shadow Candidate

- Closed and froze combined A/B/C research after no path showed a validated,
  cost-robust entry edge.
- Pre-registered a separate BTCUSDT 4H time-series momentum strategy without
  S/R, EMA, OI direction, calendar, or A/B/C dependencies.
- Corrected Wilder ATR and independent side replay before accepting the final
  result.
- Admitted LONG-only after 238 historical trades produced `+57.100R`, PF
  `1.771`, and 10.643R drawdown; stress produced `+46.904R`, PF `1.594`, and
  11.625R drawdown.
- Rejected SHORT after `-8.178R` baseline and `-15.140R` stress.
- Added a no-order forward-shadow runner with public Binance candles, atomic
  state, first-run suppression, deduplication, and no external HTTP package.
- Replayed 15,051 candles twice with zero clock gaps, zero synthetic
  end-of-data closes, and zero duplicate events.
- Deployed a hardened 15-minute systemd timer under `/opt/kt-d1-shadow`; the
  unit cannot read the production bot directory or credentials.
- Verified two public Binance polls, a neutral initial state, zero duplicate
  events, and a successful oneshot result.
- Added public funding-rate reconciliation for every new close and passed all
  176 project tests.
- Kept the live worker on the same PID with zero restarts; production code,
  config, Telegram, SL, TP, order behavior, and risk settings were unchanged.

## 2026-07-30 - Unified A/B/C State Model Researched, Shadow Rejected

- Reframed A, B, and C as transitions of one frozen S/R structure instead of
  independent entry scanners.
- Added leakage-safe 4H structure clustering and 15m closed-candle transitions
  for range reaction, accepted breakout/retest, and failed-breakout or
  liquidity-sweep reclaim.
- Corrected Path A during smoke testing so momentum bodies cannot masquerade as
  clean S/R rejection; A now requires a balanced active range and dominant
  rejection wick.
- Replayed the frozen primary plus tight/wide neighbors over 30 pairs from
  2025-10-25 through 2026-07-22 using the production TP1/TP2 and SL+ model.
- Rejected the primary after 1,926 trades produced `-267.025R`, PF `0.758`,
  average `-0.139R`, max drawdown `267.055R`, and zero positive 30-day folds.
- Rejected every path independently: A `-95.938R`, B `-9.264R`, and C
  `-161.823R`.
- Audited the proposed monthly BTC cycle over 77 complete WIB months since
  2020. No phase passed the frozen stability and bootstrap gate; calendar
  remains metadata only.
- Ran OI, taker-flow, funding, and premium ablation on the available
  derivatives-complete subset. Every derivatives variant underperformed the
  price/volume baseline, so no OI filter or risk modifier was adopted.
- Tested TP1 plus a structural runner as a diagnostic; it also failed with the
  existing SL+ behavior.
- Kept the prior-validation period closed, did not add the unified engine to
  production or shadow, and made no live bot, VPS, order, SL, or TP changes.

## 2026-07-29 - Strategy B6 Expansion-Acceptance Rejected

- Added leakage-controlled B6 research for five-core market breadth, structural
  compression and expansion, multi-candle acceptance, cost-aware stops, and
  correlated-signal portfolio limits.
- Rejected symmetric B6.0 after the primary produced only 9 trades and its
  parameter neighbor lost `-4.872R`.
- Added asymmetric SHORT-only B6.1 with a 1H trigger and BTC direction guard;
  its frozen primary lost `-1.026R`.
- Tested B6.2 trend-specific management with partial TP1 and 1H Chandelier
  trailing instead of a fixed TP2.
- Rejected B6.2 after the 2.5 ATR primary reached only `+1.546R`, PF `1.155`,
  and 23 trades, while nearby trail settings failed robustness and cost stress.
- Preserved both validation periods by stopping at the failed recent-design
  gate.
- Kept Strategy B paused and made no production, Telegram, VPS, SL, or TP
  changes.

## 2026-07-29 - Strategy A S/R and EMA Foundation Audit

- Traced Binance klines through the production EMA, S/R, regime, and entry path.
- Confirmed that live EMA/S/R decisions use closed candles and that the EMA
  formula is standard.
- Identified and removed a dead 15m EMA21 calculation and misleading pullback
  wording; a real EMA pullback profile failed validation and remains inactive.
- Corrected nominal-price-dependent S/R tolerance.
- Required a rejection wick to interact with the selected S/R level on the
  same candle.
- Replayed six frozen variants across 30 pairs and separate 270-day and
  365-day periods with 0.14% modeled round-trip cost.
- Approved only the narrow S/R touch correction: combined 235 trades,
  `+19.009R`, PF `1.202`, and max drawdown `13.944R`.
- Rejected clustered S/R and strict EMA replacements after both lost money in
  the prior-market validation period.
- Kept Strategy B paused, Strategy C shadow-only, and SL/TP unchanged.
- Deployed `V8.2-SR-TOUCH` to the VPS with automatic rollback backup; verified
  one worker, zero restarts, live heartbeat, and preserved BCH order protection.
- Preserved the pre-existing global Telegram pause state; no new entries run
  until an explicit `/resume`.

## 2026-07-29 - Strategy B5 Structural Audit

- Diagnosed B4's sparse funnel: 48,660 4H evaluations produced only 11 trades.
- Added a research-only B5 engine using 4H regime, 1H breakout, 15m first
  retest, quality scoring, and the production live-management model.
- Increased the development sample to 626 trades and exposed a negative base
  edge of `-99.476R` after modeled fees and slippage.
- Identified structural stops below 0.8% as the main transaction-cost failure.
- Added frozen B5.1 cost-aware and mature-level SHORT candidates.
- Replayed B5.1 across separate 270-day and 365-day development periods.
- Rejected the selected candidate after its worst 30-day fold reached
  `-5.614R`, beyond the frozen `-4R` gate.
- Preserved the 2023-2024 holdout as untouched and kept Strategy B paused.
- Passed all 61 regression tests; production runtime was not modified.

## 2026-07-29 - Strategy B4 Breakout-Retest Rejected

- Added a leakage-controlled B4 Donchian first-retest research engine.
- Modeled next-candle entry, fees/slippage, TP1/TP2, SL+, and conservative
  same-candle execution.
- Tested 30 established pairs over a 270-day development period and a separate
  365-day untouched stress period.
- Rejected B4 after the primary candidate lost `-0.425R` with PF `0.962` in
  stress and its parameter neighbor lost `-8.025R`.
- Added a frozen promotion gate and regression tests for fail-closed behavior.
- Corrected retest ATR self-normalization and per-pair live-exit advancement
  before finalizing the B4 gate.
- Passed all 53 regression tests and verified one healthy VPS worker with zero
  systemd restarts.
- Kept Strategy B paused; no production or VPS order behavior was changed.

## 2026-07-22 - Strategy B Audit and Strategy C6 Forward Shadow

- Corrected Strategy B's breakout-volume baseline so C1, C2, and the incomplete
  candle cannot dilute C1's own ratio.
- Kept Strategy B paused after all B3 candidates failed the 180-day holdout.
- Added Strategy C6 Market Strict as forward-shadow only.
- Added BTC 4H trend/return guard, sweep absorption, MSS displacement, and retest
  sequence for C6.
- Matched research and runtime ATR, 199-candle history, and next-candle-open entry.
- Added persistent C6 setup IDs, 96-hour timeout, and separate `/shadow` reporting.
- Validated C6 over 90-day development plus 180-day holdout with fees/slippage.
- Verified 66/66 runtime/research signal parity and passed 42 regression tests.
- Live promotion remains blocked pending 30 closed forward C6 shadow trades.

## 2026-07-05

### Added

- Project workspace initialized for KT Auto Trading Bot.
- External config support through `config.json` or `KT_BOT_CONFIG`.
- `config.example.json` template.
- Journal backup before account sync.
- Live position audit for positions without active SL.
- Orphan SL/TP order audit.
- Audit alert throttling to reduce repeated Telegram spam.
- Binance `realized_pnl` priority for dollar P&L reports.
- Telegram command layer:
  - `/start`
  - `/status`
  - `/health`
  - `/positions`
  - `/orders`
  - `/report`
  - `/weekly`
  - `/monthly`
  - `/alltime`
  - `/pause`
  - `/resume`
  - `/risk`
  - `/help`
- Persistent pause/resume state.
- Polished Telegram command response text.
- Product documentation:
  - README
  - Binance API setup guide
  - Report guide
  - Risk disclosure
  - Runbook
- PowerShell launchers for simulate and real mode.
- Main launcher menu through `start_bot.ps1`.
- Double-click launchers:
  - `START_BOT.bat`
  - `RUN_SIMULATE.bat`
  - `RUN_REAL.bat`
- Interactive config setup script: `setup_config.ps1`.
- Professional performance analytics in reports:
  - max drawdown in R
  - best/worst pair
  - entry path performance
- Telegram `/health` command for pre-flight diagnostics.
- Telegram `/weekly` and `/monthly` performance reports.
- Private beta documentation:
  - beta readiness checklist
  - beta tester onboarding
  - bug report template
  - roadmap status
- Client onboarding package and public Telegram onboarding flow.
- Mobile-only public product architecture document.
- Public next-phase roadmap for registry, license, per-user config, and managed workers.
- Semi-SaaS foundation:
  - local user registry
  - `/register`
  - `/myaccount`
  - `/license`
  - `/onboarding`
  - admin-only approve/revoke/extend/list commands
  - trading commands restricted to admin until per-user workers exist
- Managed worker foundation:
  - per-user config/journal/log folders
  - worker manager CLI
  - PowerShell wrapper
  - worker PID status/start/stop
  - Telegram command polling disabled for worker configs
- Client command routing for managed workers:
  - `/status`
  - `/health`
  - `/positions`
  - `/orders`
  - `/report`
  - `/weekly`
  - `/monthly`
  - `/alltime`
- Reduced runtime noise and disk I/O:
  - terminal `scan_done` output is disabled by default
  - pre-sync journal backup is throttled
  - unchanged `sync_done` summaries are throttled
- Disabled orphan order audit by default for quieter 24/7 operation.
- Added automatic scan log rotation and a helper script to compact oversized logs.
- Added quiet logging mode to suppress routine scan noise and reduce laptop/disk load.
- Added optional 1% profit breakeven trigger that moves SL to entry and keeps existing TP1/TP2 unchanged.
- Added Smart Money Jalur C shadow tracking: liquidity sweep, market structure shift, and retest validation without live orders.
- Added Telegram `/shadow` command for on-demand shadow signal monitoring.
- Changed the 1% profit protection rule to move SL to SL+ 0.5% from entry, with BEP/SL+ reporting.
- Removed one manual BTCUSDT journal result from All Time data after creating a journal backup.
  - `/risk`
- Startup terminal banner so PowerShell clearly shows the bot is running.
- Cycle completion terminal line after each scan.

### Changed

- CLI defaults no longer override config values when arguments are omitted.
- Daily/all-time P&L report uses actual Binance `realized_pnl` when available, with R-based estimate as fallback.
- Replaced deprecated `datetime.utcnow()` usage with timezone-aware UTC helpers.
- Fixed duplicate TP1/breakeven Telegram notifications by persisting BE state immediately and adding an in-progress guard.

### Notes

- Web dashboard is not required yet. Telegram command menu through BotFather is enough for current product phase.
# 2026-07-16 - SL+ Profit Protection

- Changed the running-profit trigger from +1.0% to +1.5%.
- Changed the locked stop from +0.5% to +1.0% from entry, mirrored for SHORT positions.
- TP1 now moves the remaining position stop to the same +1.0% locked-profit level.
- If TP1 is reached before a +1.0% stop is valid against mark price, the original SL remains active and the monitor waits safely.
- Preserved TP1/TP2 prices and all Strategy A/B entry logic.

# 2026-07-15 - Strategy C v2

- Rebuilt Strategy C as a shadow-only 4H-location liquidity sweep engine.
- Added sweep penetration, wick, volume, displacement, MSS, FVG, and narrow-retest validation.
- Replaced mechanical 2R TP with the nearest opposing 4H liquidity target and minimum structural RR 1.7.
- Separated Telegram `/shadow` statistics into C v1 legacy and C v2.
- Added conservative candle high/low outcome tracking for C v2.
- Added focused LONG/SHORT and rejection-path unit tests.

# 2026-07-31 - Strategy ABC V2.4 Research

- Completed the 36-chart structured BTC adjudication.
- Recorded 35 accepted labels, 1 skip, and 60% minimum-rule overlap.
- Added the research-only `ABC_V24_HUMAN_EXCLUSIVE` state variant.
- Enabled failed-B to C lineage and same-level A-sweep to C promotion.
- Added explicit reclaim verification before C emission.
- Added historical regression, exact-time human-fit, and fixed-horizon
  MFE/MAE entry-edge diagnostics.
- Rejected V2.4 after 101 trades produced -6.539R and PF 0.876.
- Confirmed no statistically validated edge at 4h, 12h, or 24h horizons.
- Kept production bot, VPS, Telegram, risk, SL, and TP behavior unchanged.
