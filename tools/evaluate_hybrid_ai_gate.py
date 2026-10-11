#!/usr/bin/env python3
"""Create the immutable live-lock artifact from frozen AI replay results."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from hybrid_ai_engine import LIVE_GATE_SCHEMA, PROMPT_VERSION


def read_json(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise ValueError(f"result is not an object: {path}")
    return value


def compact_stage(result: dict, expected_stage: str) -> dict:
    summary = result.get("summary") if isinstance(result.get("summary"), dict) else {}
    gate = summary.get("gate") if isinstance(summary.get("gate"), dict) else {}
    decisions = result.get("decisions") if isinstance(result.get("decisions"), list) else []
    candidate_count = int(summary.get("candidate_count", 0) or 0)
    integrity = {
        "schema": result.get("schema") == "KT_HISTORICAL_AI_REPLAY_V1",
        "research_only": result.get("status") == "RESEARCH_ONLY_NO_ORDERS",
        "provider_openai": result.get("provider") == "openai",
        "stage": result.get("stage") == expected_stage,
        "prompt": result.get("prompt_version") == PROMPT_VERSION,
        "future_guard": bool(result.get("settings", {}).get("future_field_guard")),
        "no_decision_failures": int(summary.get("decision_failures", 0) or 0) == 0,
        "decision_count_complete": len(decisions) == candidate_count,
        "candidate_family_present": bool(result.get("candidate_family")),
        "candidate_definition_present": isinstance(result.get("candidate_definition"), dict),
    }
    passed = bool(gate.get("passed")) and all(integrity.values())
    return {
        "passed": passed,
        "integrity": integrity,
        "checks": gate.get("checks", {}),
        "candidate_count": summary.get("candidate_count", 0),
        "accepted_trades": summary.get("baseline", {}).get("trades", 0),
        "baseline_total_r": summary.get("baseline", {}).get("total_r", 0),
        "baseline_profit_factor": summary.get("baseline", {}).get("profit_factor"),
        "stress_total_r": summary.get("stress", {}).get("total_r", 0),
        "stress_profit_factor": summary.get("stress", {}).get("profit_factor"),
        "max_drawdown_r": summary.get("baseline", {}).get("max_drawdown_r", 0),
    }


def evaluate(development: dict, validation: dict) -> dict:
    same_model = (
        development.get("model")
        and development.get("model") == validation.get("model")
    )
    same_settings = development.get("settings") == validation.get("settings")
    same_candidate_family = (
        development.get("candidate_family")
        and development.get("candidate_family") == validation.get("candidate_family")
    )
    same_candidate_definition = (
        isinstance(development.get("candidate_definition"), dict)
        and development.get("candidate_definition") == validation.get("candidate_definition")
    )
    dev = compact_stage(development, "development")
    val = compact_stage(validation, "validation")
    passed = bool(
        same_model
        and same_settings
        and same_candidate_family
        and same_candidate_definition
        and dev["passed"]
        and val["passed"]
    )
    return {
        "schema": LIVE_GATE_SCHEMA,
        "status": "PASSED" if passed else "LOCKED",
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "model": development.get("model"),
        "prompt_version": PROMPT_VERSION,
        "same_model": bool(same_model),
        "same_settings": bool(same_settings),
        "same_candidate_family": bool(same_candidate_family),
        "same_candidate_definition": bool(same_candidate_definition),
        "development": dev,
        "validation": val,
        "live_enabled": False,
        "decision": (
            "ELIGIBLE_FOR_EXPLICIT_OPERATOR_ENABLE"
            if passed
            else "AI_LIVE_REMAINS_LOCKED"
        ),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--development", type=Path, required=True)
    parser.add_argument("--validation", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    result = evaluate(read_json(args.development), read_json(args.validation))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))
    return 0 if result["status"] == "PASSED" else 2


if __name__ == "__main__":
    raise SystemExit(main())
