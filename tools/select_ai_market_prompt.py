#!/usr/bin/env python3
"""Freeze a development winner and optionally evaluate its validation replay."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import sys

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ai_market_scanner import SCANNER_PROMPT_FAMILY
from tools.build_ai_market_dataset import FEATURE_SET, feature_contract_sha256
from tools.replay_ai_market_prompts import REPLAY_SCHEMA


ARTIFACT_SCHEMA = "KT_AI_MARKET_PROMPT_GATE_V1"


def read_json(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON root must be an object: {path}")
    return value


def validate_replay(result: dict, stage: str) -> None:
    contract = result.get("dataset_feature_contract")
    contract_hash = str(result.get("dataset_feature_contract_sha256") or "")
    checks = {
        "schema": result.get("schema") == REPLAY_SCHEMA,
        "research_only": result.get("status") == "RESEARCH_ONLY_NO_ORDERS",
        "provider": result.get("provider") == "openai",
        "stage": result.get("stage") == stage,
        "prompt_family": result.get("prompt_family") == SCANNER_PROMPT_FAMILY,
        "no_fatal_api_error": not result.get("fatal_api_error"),
        "future_guard": bool(result.get("settings", {}).get("future_field_guard")),
        "feature_contract": bool(
            isinstance(contract, dict)
            and contract.get("feature_set") == FEATURE_SET
            and contract_hash == feature_contract_sha256(contract)
        ),
        "single_position": result.get("settings", {}).get("max_simultaneous_positions") == 1,
        "execution_model": isinstance(result.get("dataset_execution_model"), dict),
    }
    if not all(checks.values()):
        failed = [key for key, passed in checks.items() if not passed]
        raise ValueError(f"invalid {stage} replay: {failed}")


def prompt_map(result: dict) -> dict[str, dict]:
    definitions = result.get("prompt_definitions")
    if not isinstance(definitions, list):
        return {}
    return {str(item.get("id")): item for item in definitions if isinstance(item, dict)}


def finite_metric(value) -> bool:
    try:
        return math.isfinite(float(value))
    except (TypeError, ValueError):
        return False


def complete_passing_summary(item: dict) -> bool:
    summary = item.get("summary") if isinstance(item, dict) else None
    if not isinstance(summary, dict):
        return False
    baseline = summary.get("baseline")
    stress = summary.get("stress")
    required = [
        summary.get("selection_score"),
        baseline.get("total_r") if isinstance(baseline, dict) else None,
        baseline.get("profit_factor") if isinstance(baseline, dict) else None,
        baseline.get("max_drawdown_r") if isinstance(baseline, dict) else None,
        stress.get("total_r") if isinstance(stress, dict) else None,
        stress.get("profit_factor") if isinstance(stress, dict) else None,
    ]
    return bool(summary.get("gate", {}).get("passed")) and all(
        finite_metric(value) for value in required
    )


def select_development(development: dict) -> tuple[dict | None, list[dict]]:
    results = development.get("prompt_results")
    if not isinstance(results, list):
        raise ValueError("development prompt results are missing")
    passing = [
        item
        for item in results
        if complete_passing_summary(item)
    ]
    passing.sort(
        key=lambda item: (
            float(item["summary"]["selection_score"]),
            float(item["summary"]["stress"]["profit_factor"]),
            float(item["summary"]["stress"]["total_r"]),
        ),
        reverse=True,
    )
    compact = [
        {
            "prompt_id": item.get("prompt_id"),
            "passed": bool(item.get("summary", {}).get("gate", {}).get("passed")),
            "selection_score": item.get("summary", {}).get("selection_score"),
            "trades": item.get("summary", {}).get("baseline", {}).get("trades", 0),
            "baseline_total_r": item.get("summary", {}).get("baseline", {}).get("total_r", 0),
            "baseline_profit_factor": item.get("summary", {}).get("baseline", {}).get("profit_factor", 0),
            "stress_total_r": item.get("summary", {}).get("stress", {}).get("total_r", 0),
            "stress_profit_factor": item.get("summary", {}).get("stress", {}).get("profit_factor", 0),
            "max_drawdown_r": item.get("summary", {}).get("baseline", {}).get("max_drawdown_r", 0),
        }
        for item in results
    ]
    return (passing[0] if passing else None), compact


def build_artifact(development: dict, validation: dict | None = None) -> dict:
    validate_replay(development, "development")
    winner, candidates = select_development(development)
    definitions = prompt_map(development)
    artifact = {
        "schema": ARTIFACT_SCHEMA,
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "candidate_family": "AI_MARKET_SCANNER_DIRECT_V1",
        "prompt_family": SCANNER_PROMPT_FAMILY,
        "status": "LOCKED",
        "model": development.get("model"),
        "reasoning_effort": development.get("reasoning_effort"),
        "settings": development.get("settings"),
        "feature_contract": development.get("dataset_feature_contract"),
        "feature_contract_sha256": development.get("dataset_feature_contract_sha256"),
        "execution_model": development.get("dataset_execution_model"),
        "development_candidates": candidates,
        "winner": None,
        "development_passed": False,
        "validation_passed": False,
        "ai_signal_eligible": False,
        "ai_approval_eligible": False,
        "ai_live_eligible": False,
        "decision": "NO_DEVELOPMENT_PROMPT_PASSED",
    }
    if winner is None:
        return artifact
    prompt_id = str(winner["prompt_id"])
    definition = definitions.get(prompt_id)
    if not definition or not definition.get("sha256"):
        raise ValueError("winning prompt definition is missing")
    artifact["winner"] = {
        "prompt_id": prompt_id,
        "prompt_version": definition.get("version"),
        "prompt_sha256": definition.get("sha256"),
        "development_summary": winner.get("summary"),
    }
    artifact["development_passed"] = True
    artifact["decision"] = "DEVELOPMENT_PASSED_VALIDATION_REQUIRED"
    if validation is None:
        return artifact

    validate_replay(validation, "validation")
    validation_results = validation.get("prompt_results")
    if not isinstance(validation_results, list) or len(validation_results) != 1:
        raise ValueError("validation must contain exactly one frozen prompt")
    validation_item = validation_results[0]
    validation_definitions = prompt_map(validation)
    validation_definition = validation_definitions.get(prompt_id)
    consistency = {
        "same_prompt_id": validation_item.get("prompt_id") == prompt_id,
        "same_prompt_hash": bool(
            validation_definition
            and validation_definition.get("sha256") == definition.get("sha256")
        ),
        "same_model": validation.get("model") == development.get("model"),
        "same_reasoning_effort": validation.get("reasoning_effort") == development.get("reasoning_effort"),
        "same_thresholds": {
            key: validation.get("settings", {}).get(key)
            == development.get("settings", {}).get(key)
            for key in ("min_confidence", "min_quality", "max_simultaneous_positions")
        },
        "same_execution_model": validation.get("dataset_execution_model")
        == development.get("dataset_execution_model"),
        "same_feature_contract": bool(
            development.get("dataset_feature_contract_sha256")
            and validation.get("dataset_feature_contract_sha256")
            == development.get("dataset_feature_contract_sha256")
            and validation.get("dataset_feature_contract")
            == development.get("dataset_feature_contract")
        ),
    }
    consistency_passed = all(
        value if isinstance(value, bool) else all(value.values())
        for value in consistency.values()
    )
    validation_passed = bool(
        validation_item.get("summary", {}).get("gate", {}).get("passed")
    )
    artifact["validation"] = {
        "consistency": consistency,
        "consistency_passed": consistency_passed,
        "summary": validation_item.get("summary"),
    }
    artifact["validation_passed"] = consistency_passed and validation_passed
    artifact["ai_signal_eligible"] = artifact["validation_passed"]
    artifact["status"] = "PASSED_HISTORICAL" if artifact["validation_passed"] else "LOCKED"
    artifact["decision"] = (
        "ELIGIBLE_FOR_AI_SIGNAL_ONLY"
        if artifact["validation_passed"]
        else "VALIDATION_FAILED_NO_DEPLOYMENT"
    )
    # Approval and live require separate forward-performance artifacts.
    artifact["ai_approval_eligible"] = False
    artifact["ai_live_eligible"] = False
    return artifact


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--development", type=Path, required=True)
    parser.add_argument("--validation", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    artifact = build_artifact(
        read_json(args.development),
        read_json(args.validation) if args.validation else None,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(artifact, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "status": artifact["status"],
                "winner": (artifact.get("winner") or {}).get("prompt_id"),
                "decision": artifact["decision"],
                "ai_signal_eligible": artifact["ai_signal_eligible"],
                "ai_live_eligible": artifact["ai_live_eligible"],
            },
            indent=2,
        )
    )
    required_pass = artifact["validation_passed"] if args.validation else artifact["development_passed"]
    return 0 if required_pass else 2


if __name__ == "__main__":
    raise SystemExit(main())
