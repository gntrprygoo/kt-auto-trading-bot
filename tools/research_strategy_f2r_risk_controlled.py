#!/usr/bin/env python3
"""Risk-budget gate for the frozen Strategy F2 long residual candidate."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.research_strategy_f2_long_residual import evaluate as evaluate_f2
from tools.research_strategy_f_intraday import json_safe


ACCOUNT_RISK_PCT = 0.0035


def account_metrics(summary: dict) -> dict:
    return {
        "risk_per_trade_pct": ACCOUNT_RISK_PCT,
        "baseline_total_return_pct": summary["baseline"]["total_r"] * ACCOUNT_RISK_PCT * 100.0,
        "stress_total_return_pct": summary["stress"]["total_r"] * ACCOUNT_RISK_PCT * 100.0,
        "baseline_max_drawdown_pct": summary["baseline"]["max_drawdown_r"] * ACCOUNT_RISK_PCT * 100.0,
    }


def f2r_gate(stage: str, summary: dict, account: dict) -> dict:
    baseline = summary["baseline"]
    stress = summary["stress"]
    if stage == "development":
        checks = {
            "minimum_trades": baseline["trades"] >= 180,
            "baseline_positive": baseline["total_r"] > 0,
            "baseline_pf": baseline["profit_factor"] >= 1.15,
            "stress_positive": stress["total_r"] > 0,
            "stress_pf": stress["profit_factor"] >= 1.05,
            "eth_positive": summary["pairs"]["ETHUSDT"]["total_r"] > 0,
            "sol_positive": summary["pairs"]["SOLUSDT"]["total_r"] > 0,
            "month_breadth": summary["positive_month_ratio"] >= 0.55,
            "account_drawdown": account["baseline_max_drawdown_pct"] <= 8.0,
        }
    elif stage == "validation":
        checks = {
            "minimum_trades": baseline["trades"] >= 18,
            "baseline_positive": baseline["total_r"] > 0,
            "baseline_pf": baseline["profit_factor"] >= 1.10,
            "stress_non_negative": stress["total_r"] >= 0,
            "month_breadth": summary["positive_month_ratio"] >= 0.50,
            "account_drawdown": account["baseline_max_drawdown_pct"] <= 4.0,
        }
    else:
        checks = {
            "minimum_trades": baseline["trades"] >= 15,
            "baseline_positive": baseline["total_r"] > 0,
            "baseline_pf": baseline["profit_factor"] >= 1.05,
            "stress_non_negative": stress["total_r"] >= 0,
            "account_drawdown": account["baseline_max_drawdown_pct"] <= 4.0,
        }
    return {"passed": all(checks.values()), "checks": checks}


def evaluate(stage: str, cache_root: Path, extra_cache: Path | None) -> dict:
    result = evaluate_f2(stage, cache_root, extra_cache)
    result["engine"] = "STRATEGY_F2R_RISK_CONTROLLED_RESEARCH_V1"
    summary = result["summary"]
    account = account_metrics(summary)
    summary["account"] = account
    summary["gate"] = f2r_gate(stage, summary, account)
    result["account_risk_pct"] = ACCOUNT_RISK_PCT
    result["next_step"] = (
        "OPEN_NEXT_SEALED_STAGE"
        if summary["gate"]["passed"]
        else "REJECT_CANDIDATE_AND_KEEP_NEXT_STAGE_SEALED"
    )
    return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", choices=("development", "validation", "holdout"), required=True)
    parser.add_argument("--cache-root", type=Path, default=Path(".audit/2026-07-22"))
    parser.add_argument("--extra-cache", type=Path)
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
        "account_return_pct": round(summary["account"]["baseline_total_return_pct"], 3),
        "account_max_drawdown_pct": round(summary["account"]["baseline_max_drawdown_pct"], 3),
        "passed": summary["gate"]["passed"],
        "checks": summary["gate"]["checks"],
    }
    print(json.dumps(json_safe(compact), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
