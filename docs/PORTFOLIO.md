# Engineering case study

## Problem

Automated trading must keep exchange positions, protective orders, local records, and operator expectations aligned. Entry signals alone do not solve restart recovery, partial exits, reporting, or strategy evaluation.

## Implemented approach

KT Auto Trading Bot combines rule-based execution with Telegram controls, persistent journals, position audits, and historical research. Separate AI modules provide structured review and shadow setup observation behind eligibility gates.

## Engineering decisions

- Fixed notional sizing provides a consistent exposure basis; actual loss depends on stop distance and execution.
- Dual take-profit levels support partial exits and subsequent protective-stop adjustments.
- Reconciliation and backups address interruption recovery.
- Frozen specifications, replay, and holdout reports make research decisions inspectable.
- Structured AI validation and locked live eligibility bound experimental behavior.

## Skills demonstrated

Python systems development, REST integration and request signing, concurrency, state persistence, Telegram operations, unit testing, deployment scripting, reproducible research, and technical documentation.

## Review evidence

Start with tests/test_profit_protection.py, tests/test_hybrid_ai_engine.py, and tests/test_ai_range_setup.py. Compare them with the runbooks, strategy specifications, and research result documents. Run `python -m unittest discover -s tests -v` from the repository root.

This portfolio makes no profitability, customer-count, certification, or uptime claims. Research documents include rejected candidates. GitHub CI status is available after the workflow executes.

## Future improvements

Extract adapters from the core, formalize a versioned configuration schema, add an offline demonstration, and improve deployment portability. These are proposed improvements.
