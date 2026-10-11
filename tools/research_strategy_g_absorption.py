#!/usr/bin/env python3
"""Sealed-stage evaluator for Strategy G broad flow absorption."""

from __future__ import annotations

import argparse
from dataclasses import asdict
import json
from pathlib import Path
import sys

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.research_strategy_f_intraday import (
    BASELINE_COST_PCT,
    STRESS_COST_PCT,
    Candidate,
    align_symbols,
    json_safe,
    load_symbol,
    period_bounds,
    prepare_features,
    run_candidate,
    summarize,
)


SYMBOLS = (
    "BTCUSDT",
    "ETHUSDT",
    "XRPUSDT",
    "SOLUSDT",
    "DOGEUSDT",
    "ADAUSDT",
)
CANDIDATE = Candidate(
    "G1_BROAD_FLOW_ABSORPTION_4H",
    "FLOW_ABSORPTION",
    0.18,
    1.40,
    0.75,
    1.25,
    16,
    1.30,
    0.0075,
    "ANY",
)


def g_gate(stage: str, summary: dict) -> dict:
    baseline = summary["baseline"]
    stress = summary["stress"]
    positive_pairs = sum(
        summary["pairs"][symbol]["total_r"] > 0 for symbol in SYMBOLS
    )
    if stage == "development":
        checks = {
            "minimum_trades": baseline["trades"] >= 50,
            "baseline_positive": baseline["total_r"] > 0,
            "baseline_pf": baseline["profit_factor"] >= 1.20,
            "stress_positive": stress["total_r"] > 0,
            "stress_pf": stress["profit_factor"] >= 1.10,
            "pair_breadth": positive_pairs >= 4,
            "month_breadth": summary["positive_month_ratio"] >= 0.55,
            "max_drawdown": baseline["max_drawdown_r"] <= 10.0,
        }
    elif stage == "validation":
        checks = {
            "minimum_trades": baseline["trades"] >= 10,
            "baseline_positive": baseline["total_r"] > 0,
            "baseline_pf": baseline["profit_factor"] >= 1.15,
            "stress_non_negative": stress["total_r"] >= 0,
            "pair_breadth": positive_pairs >= 3,
            "max_drawdown": baseline["max_drawdown_r"] <= 6.0,
        }
    else:
        checks = {
            "minimum_trades": baseline["trades"] >= 8,
            "baseline_positive": baseline["total_r"] > 0,
            "baseline_pf": baseline["profit_factor"] >= 1.10,
            "stress_non_negative": stress["total_r"] >= 0,
            "max_drawdown": baseline["max_drawdown_r"] <= 6.0,
        }
    return {"passed": all(checks.values()), "checks": checks, "positive_pairs": positive_pairs}


def evaluate(stage: str, cache_root: Path, extra_cache: Path) -> dict:
    loaded = {
        symbol: load_symbol(cache_root, symbol, extra_cache)
        for symbol in SYMBOLS
    }
    aligned = align_symbols(loaded)
    features = prepare_features(aligned)
    start_ms, end_ms = period_bounds(stage, aligned)
    records = run_candidate(aligned, features, CANDIDATE, start_ms, end_ms)
    summary = summarize(records, stage, SYMBOLS)
    summary["gate"] = g_gate(stage, summary)
    return {
        "engine": "STRATEGY_G_FLOW_ABSORPTION_RESEARCH_V1",
        "status": "RESEARCH_ONLY_NO_ORDERS",
        "stage": stage,
        "period": {"start_ms": start_ms, "end_ms": end_ms},
        "symbols": list(SYMBOLS),
        "candidate": asdict(CANDIDATE),
        "baseline_cost_pct": BASELINE_COST_PCT,
        "stress_cost_pct": STRESS_COST_PCT,
        "summary": summary,
        "records": records,
        "next_step": (
            "OPEN_NEXT_SEALED_STAGE"
            if summary["gate"]["passed"]
            else "REJECT_CANDIDATE_AND_KEEP_NEXT_STAGE_SEALED"
        ),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", choices=("development", "validation", "holdout"), required=True)
    parser.add_argument("--cache-root", type=Path, default=Path(".audit/2026-07-22"))
    parser.add_argument("--extra-cache", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    result = evaluate(args.stage, args.cache_root, args.extra_cache)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(json_safe(result), indent=2) + "\n", encoding="utf-8")
    summary = result["summary"]
    compact = {
        "stage": args.stage,
        "trades": summary["baseline"]["trades"],
        "net_r": round(summary["baseline"]["total_r"], 3),
        "pf": summary["baseline"]["profit_factor"],
        "stress_r": round(summary["stress"]["total_r"], 3),
        "stress_pf": summary["stress"]["profit_factor"],
        "max_drawdown_r": round(summary["baseline"]["max_drawdown_r"], 3),
        "positive_pairs": summary["gate"]["positive_pairs"],
        "passed": summary["gate"]["passed"],
        "checks": summary["gate"]["checks"],
    }
    print(json.dumps(json_safe(compact), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
