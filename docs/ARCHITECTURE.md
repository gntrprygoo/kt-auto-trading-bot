# Architecture

The core `v3_swing_bot_fixed.py` coordinates scanning, rule-based decisions, exchange request signing, execution, Telegram commands, persistent state, and reconciliation. It remains a large integrated module; AI and research extensions are separate modules.

| Component | Responsibility |
| --- | --- |
| Core bot | Candidates, sizing, orders, position protection, account state, and reports |
| hybrid_ai_engine.py | Structured AI review, proposals, risk gateway, and live eligibility |
| ai_market_scanner.py | Market analysis request and response contract |
| ai_range_setup.py | Setup schema, levels, and reward/risk validation |
| live_ai_market.py | Snapshots, scheduling, and shadow research orchestration |
| range_setup_shadow.py | Confirmed-candle setup progression |
| tools/ | Replay, strategy evaluation, audits, and deployment checks |

## Boundaries and recovery

Local configuration contains credentials and environment-specific state paths and is excluded from Git. Journals, account registries, worker configurations, and private reports should remain outside the public repository.

The hybrid AI contract excludes exchange credentials and account identifiers from model input. The reviewer cannot redefine order levels or sizing. Structured validation and live eligibility checks control use of its output. Independent market analysis remains shadow research.

Startup reconciliation compares exchange state with local records. Protective-order audits and journal backups support recovery. Research tools evaluate candidates separately from the running bot.

## Tradeoffs

The integrated core increases maintenance cost. Extracting exchange, persistence, and Telegram adapters is a future improvement. Simulation uses configured services; unit tests are the starting point for offline review.
