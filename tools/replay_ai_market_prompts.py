#!/usr/bin/env python3
"""Replay AI market-scanner prompts and evaluate sealed historical outcomes."""

from __future__ import annotations

import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sys
import time

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ai_market_scanner import (
    MarketScanDecision,
    MarketScannerConfig,
    OpenAIMarketScannerClient,
    PROMPT_VARIANTS,
    SCANNER_SCHEMA,
    SCANNER_PROMPT_FAMILY,
    assert_snapshot_has_no_future_data,
    prompt_definition,
)
from tools.build_ai_market_dataset import (
    DATASET_SCHEMA,
    FEATURE_SET,
    feature_contract_sha256,
)


REPLAY_SCHEMA = "KT_AI_MARKET_PROMPT_REPLAY_V1"
FATAL_API_MARKERS = (
    "insufficient_quota",
    "credit_balance_exhausted",
    "invalid_api_key",
    "authentication",
    "openai http 400",
    "openai http 401",
    "openai http 403",
    "openai http 404",
    "openai http 429",
)


@contextmanager
def exclusive_replay_lock(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = path.open("a+b")
    handle.seek(0, os.SEEK_END)
    if handle.tell() == 0:
        handle.write(b"0")
        handle.flush()
    handle.seek(0)
    try:
        if os.name == "nt":
            import msvcrt

            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl

            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except (OSError, BlockingIOError) as exc:
        handle.close()
        raise RuntimeError(
            f"another AI market replay already holds lock: {path}"
        ) from exc
    try:
        yield
    finally:
        handle.seek(0)
        if os.name == "nt":
            import msvcrt

            msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl

            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        handle.close()


def read_json(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON root must be an object: {path}")
    return value


def replay_key(config: MarketScannerConfig, prompt_id: str, snapshot: dict) -> str:
    prompt = prompt_definition(prompt_id)
    payload = {
        "model": config.model,
        "reasoning_effort": config.reasoning_effort,
        "max_output_tokens": config.max_output_tokens,
        "prompt_id": prompt["id"],
        "prompt_sha256": prompt["sha256"],
        "snapshot": snapshot,
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def load_cache(path: Path) -> dict[str, dict]:
    result: dict[str, dict] = {}
    if not path.exists():
        return result
    with path.open("r", encoding="utf-8-sig") as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            try:
                item = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"invalid cache line {line_number}: {path}") from exc
            if isinstance(item, dict) and item.get("replay_key"):
                result[str(item["replay_key"])] = item
    return result


def append_cache(path: Path, item: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(item, sort_keys=True, separators=(",", ":")) + "\n")
        handle.flush()
        os.fsync(handle.fileno())


def fatal_api_error(error: str | None) -> bool:
    normalized = str(error or "").lower()
    return any(marker in normalized for marker in FATAL_API_MARKERS)


def validate_dataset(dataset: dict, stage: str) -> list[dict]:
    checks = {
        "schema": dataset.get("schema") == DATASET_SCHEMA,
        "research_only": dataset.get("status") == "RESEARCH_ONLY_NO_ORDERS",
        "stage": dataset.get("stage") == stage,
    }
    failed = [key for key, passed in checks.items() if not passed]
    if failed:
        raise ValueError(f"invalid AI market dataset: {failed}")

    contract = dataset.get("feature_contract")
    contract_hash = str(dataset.get("feature_contract_sha256") or "")
    if not isinstance(contract, dict) or contract.get("feature_set") != FEATURE_SET:
        raise ValueError("dataset feature contract is missing or unsupported")
    if contract_hash != feature_contract_sha256(contract):
        raise ValueError("dataset feature contract hash mismatch")

    records = dataset.get("records")
    if not isinstance(records, list) or not records:
        raise ValueError("dataset records are missing")
    expected_symbols = [str(item).upper() for item in dataset.get("symbols", [])]
    if not expected_symbols or len(expected_symbols) != len(set(expected_symbols)):
        raise ValueError("dataset symbol contract is empty or duplicated")
    if [str(item).upper() for item in contract.get("symbols", [])] != expected_symbols:
        raise ValueError("dataset symbols do not match the feature contract")
    expected_fields = {str(item) for item in contract.get("market_fields", [])}
    if not expected_fields:
        raise ValueError("dataset market field contract is empty")
    for index, record in enumerate(records):
        if not isinstance(record, dict) or not isinstance(record.get("snapshot"), dict):
            raise ValueError(f"dataset record {index} has no snapshot")
        snapshot = record["snapshot"]
        if snapshot.get("schema") != SCANNER_SCHEMA:
            raise ValueError(f"dataset record {index} uses an unsupported snapshot schema")
        universe = [str(item).upper() for item in snapshot.get("universe", [])]
        if universe != expected_symbols:
            raise ValueError(f"dataset record {index} universe does not match its contract")
        market = snapshot.get("market")
        if not isinstance(market, dict) or list(market) != expected_symbols:
            raise ValueError(f"dataset record {index} market does not match its universe")
        for symbol in expected_symbols:
            fields = market.get(symbol)
            if not isinstance(fields, dict) or set(fields) != expected_fields:
                raise ValueError(
                    f"dataset record {index} fields do not match the contract for {symbol}"
                )
        execution = snapshot.get("execution_contract")
        if not isinstance(execution, dict) or not execution.get(
            "model_must_not_size_or_set_geometry"
        ):
            raise ValueError(f"dataset record {index} has an unsafe execution contract")
        if execution.get("max_simultaneous_positions") != 1:
            raise ValueError(f"dataset record {index} permits multiple positions")
        assert_snapshot_has_no_future_data(snapshot)
    return records


def profit_factor(values: list[float]):
    wins = sum(value for value in values if value > 0)
    losses = -sum(value for value in values if value < 0)
    if losses <= 1e-12:
        return 999.0 if wins > 0 else 0.0
    return wins / losses


def max_drawdown(values: list[float]) -> float:
    equity = 0.0
    peak = 0.0
    drawdown = 0.0
    for value in values:
        equity += value
        peak = max(peak, equity)
        drawdown = max(drawdown, peak - equity)
    return drawdown


def summarize_r(values: list[float]) -> dict:
    wins = sum(1 for value in values if value > 0)
    return {
        "trades": len(values),
        "wins": wins,
        "losses": sum(1 for value in values if value < 0),
        "win_rate": wins / len(values) if values else 0.0,
        "total_r": sum(values),
        "average_r": sum(values) / len(values) if values else 0.0,
        "profit_factor": profit_factor(values),
        "max_drawdown_r": max_drawdown(values),
    }


def concentration(counter: Counter) -> float:
    total = sum(counter.values())
    return max(counter.values(), default=0) / total if total else 0.0


def stage_gate(stage: str, summary: dict) -> dict:
    baseline = summary["baseline"]
    stress = summary["stress"]
    common = {
        "decision_coverage": summary["decision_coverage"] >= 0.98,
        "zero_decision_failures": summary["decision_failures"] == 0,
        "baseline_positive": baseline["total_r"] > 0,
        "stress_positive": stress["total_r"] > 0,
        "pair_concentration": summary["max_pair_concentration"] <= 0.70,
    }
    if stage == "development":
        checks = {
            "reviewed_snapshots": summary["snapshot_count"] >= 100,
            "executed_trades": baseline["trades"] >= 25,
            **common,
            "baseline_profit_factor": baseline["profit_factor"] >= 1.15,
            "stress_profit_factor": stress["profit_factor"] >= 1.05,
            "baseline_max_drawdown": baseline["max_drawdown_r"] <= 10.0,
            "stress_max_drawdown": stress["max_drawdown_r"] <= 10.0,
        }
    else:
        checks = {
            "reviewed_snapshots": summary["snapshot_count"] >= 100,
            "executed_trades": baseline["trades"] >= 20,
            **common,
            "baseline_profit_factor": baseline["profit_factor"] >= 1.10,
            "stress_profit_factor": stress["profit_factor"] >= 1.00,
            "baseline_max_drawdown": baseline["max_drawdown_r"] <= 8.0,
            "stress_max_drawdown": stress["max_drawdown_r"] <= 8.0,
        }
    return {"passed": all(checks.values()), "checks": checks}


def aggregate_usage(decisions: list[dict], input_price: float, output_price: float) -> dict:
    input_tokens = 0
    output_tokens = 0
    cached_tokens = 0
    for item in decisions:
        usage = item.get("openai", {}).get("usage", {})
        if not isinstance(usage, dict):
            continue
        input_tokens += int(usage.get("input_tokens", 0) or 0)
        output_tokens += int(usage.get("output_tokens", 0) or 0)
        details = usage.get("input_tokens_details", {})
        if isinstance(details, dict):
            cached_tokens += int(details.get("cached_tokens", 0) or 0)
    uncached = max(0, input_tokens - cached_tokens)
    estimated_cost = (
        uncached * input_price / 1_000_000
        + cached_tokens * (input_price * 0.10) / 1_000_000
        + output_tokens * output_price / 1_000_000
    )
    return {
        "input_tokens": input_tokens,
        "cached_input_tokens": cached_tokens,
        "output_tokens": output_tokens,
        "total_tokens": input_tokens + output_tokens,
        "estimated_cost_usd": estimated_cost,
        "rate_assumption_per_million": {
            "input_usd": input_price,
            "cached_input_usd": input_price * 0.10,
            "output_usd": output_price,
        },
    }


def evaluate_prompt(
    prompt_id: str,
    records: list[dict],
    decisions: list[dict],
    stage: str,
    min_confidence: float,
    min_quality: int,
    input_price: float,
    output_price: float,
) -> dict:
    record_by_id = {
        str(record["snapshot"]["snapshot_id"]): record
        for record in records
    }
    ordered = sorted(
        (item for item in decisions if item["prompt_id"] == prompt_id),
        key=lambda item: int(item["decision_time_ms"]),
    )
    failures = sum(1 for item in ordered if item.get("error"))
    valid = [item for item in ordered if isinstance(item.get("decision"), dict)]
    no_trade = 0
    risk_blocked = 0
    overlap_blocked = 0
    missing_outcome = 0
    executions = []
    next_available_ms = 0
    pairs: Counter = Counter()
    sides: Counter = Counter()
    regimes: Counter = Counter()
    for item in valid:
        decision = MarketScanDecision.from_mapping(
            item["decision"], record_by_id[item["snapshot_id"]]["snapshot"]["universe"]
        )
        if decision.action == "NO_TRADE":
            no_trade += 1
            continue
        if (
            decision.confidence < min_confidence
            or decision.setup_quality < min_quality
            or decision.risk_flags
            or decision.regime in ("TRANSITION", "UNUSABLE")
        ):
            risk_blocked += 1
            continue
        record = record_by_id[item["snapshot_id"]]
        outcome = (
            record.get("outcomes", {})
            .get(decision.pair, {})
            .get(decision.side)
        )
        if not isinstance(outcome, dict):
            missing_outcome += 1
            continue
        entry_time = int(outcome["entry_time"])
        if entry_time < next_available_ms:
            overlap_blocked += 1
            continue
        next_available_ms = int(outcome["exit_time"])
        execution = {
            "snapshot_id": item["snapshot_id"],
            "decision_time_ms": int(item["decision_time_ms"]),
            "pair": decision.pair,
            "side": decision.side,
            "confidence": decision.confidence,
            "setup_quality": decision.setup_quality,
            "regime": decision.regime,
            "entry_time": entry_time,
            "exit_time": int(outcome["exit_time"]),
            "entry": outcome["entry"],
            "stop": outcome["stop"],
            "target": outcome["target"],
            "exit_reason": outcome["exit_reason"],
            "baseline_net_r": float(outcome["baseline_net_r"]),
            "stress_net_r": float(outcome["stress_net_r"]),
        }
        executions.append(execution)
        pairs[decision.pair] += 1
        sides[decision.side] += 1
        regimes[decision.regime] += 1
    baseline = summarize_r([item["baseline_net_r"] for item in executions])
    stress = summarize_r([item["stress_net_r"] for item in executions])
    summary = {
        "snapshot_count": len(records),
        "valid_decisions": len(valid),
        "decision_failures": failures,
        "decision_coverage": len(valid) / len(records) if records else 0.0,
        "no_trade_decisions": no_trade,
        "risk_blocked": risk_blocked,
        "overlap_blocked": overlap_blocked,
        "missing_outcome": missing_outcome,
        "baseline": baseline,
        "stress": stress,
        "pair_counts": dict(sorted(pairs.items())),
        "side_counts": dict(sorted(sides.items())),
        "regime_counts": dict(sorted(regimes.items())),
        "max_pair_concentration": concentration(pairs),
        "usage": aggregate_usage(ordered, input_price, output_price),
    }
    summary["gate"] = stage_gate(stage, summary)
    summary["selection_score"] = (
        stress["total_r"]
        + max(0.0, stress["profit_factor"] - 1.0) * 2.0
        - max(baseline["max_drawdown_r"], stress["max_drawdown_r"]) * 0.25
        if summary["gate"]["passed"]
        else None
    )
    return {"prompt_id": prompt_id, "summary": summary, "executions": executions}


def run_replay(args: argparse.Namespace) -> dict:
    dataset = read_json(args.dataset)
    records = validate_dataset(dataset, args.stage)
    if args.max_snapshots:
        records = records[: args.max_snapshots]
    prompt_ids = [str(item).upper() for item in args.prompts]
    unknown = [item for item in prompt_ids if item not in PROMPT_VARIANTS]
    if unknown:
        raise ValueError(f"unknown prompts: {unknown}")
    config = MarketScannerConfig(
        model=args.model,
        reasoning_effort=args.reasoning_effort,
        api_key_env=args.api_key_env,
        timeout_sec=args.timeout,
        max_output_tokens=args.max_output_tokens,
    )
    client = OpenAIMarketScannerClient(config)
    cache = load_cache(args.cache)
    resolved: dict[tuple[str, str], dict] = {}
    queue = []
    for prompt_id in prompt_ids:
        for record in records:
            snapshot = record["snapshot"]
            key = replay_key(config, prompt_id, snapshot)
            cached = cache.get(key)
            if cached and isinstance(cached.get("decision"), dict):
                try:
                    decision = MarketScanDecision.from_mapping(
                        cached["decision"], snapshot["universe"]
                    )
                except Exception:
                    decision = None
                if decision is not None:
                    resolved[(prompt_id, snapshot["snapshot_id"])] = {
                        "decision": decision,
                        "openai": cached.get("openai", {}),
                        "error": None,
                        "cached": True,
                    }
                    continue
            queue.append(
                {
                    "prompt_id": prompt_id,
                    "snapshot": snapshot,
                    "replay_key": key,
                }
            )

    def call_one(item: dict) -> dict:
        last_error = None
        for attempt in range(1, 3):
            try:
                decision, metadata = client.decide(item["snapshot"], item["prompt_id"])
                metadata["attempt_count"] = attempt
                return {
                    "decision": decision,
                    "openai": metadata,
                    "error": None,
                    "cached": False,
                }
            except Exception as exc:
                last_error = str(exc)[:600]
                if fatal_api_error(last_error) or attempt == 2:
                    break
                time.sleep(0.5 * attempt)
        return {
            "decision": None,
            "openai": {"attempt_count": 2},
            "error": last_error,
            "cached": False,
        }

    fatal = None
    completed_calls = 0
    workers = max(1, min(4, int(args.workers)))
    for offset in range(0, len(queue), workers):
        batch = queue[offset : offset + workers]
        with ThreadPoolExecutor(max_workers=workers) as executor:
            future_map = {executor.submit(call_one, item): item for item in batch}
            for future in as_completed(future_map):
                item = future_map[future]
                result = future.result()
                completed_calls += 1
                resolved[(item["prompt_id"], item["snapshot"]["snapshot_id"])] = result
                cache_item = {
                    "replay_key": item["replay_key"],
                    "prompt_id": item["prompt_id"],
                    "snapshot_id": item["snapshot"]["snapshot_id"],
                    "decision": result["decision"].as_dict() if result["decision"] else None,
                    "openai": result["openai"],
                    "error": result["error"],
                }
                append_cache(args.cache, cache_item)
                if fatal_api_error(result["error"]):
                    fatal = result["error"]
        if completed_calls and completed_calls % args.progress_every == 0:
            print(f"api_progress={completed_calls}/{len(queue)}")
        if fatal:
            break
        if args.sleep_ms:
            time.sleep(args.sleep_ms / 1000.0)

    decisions = []
    for prompt_id in prompt_ids:
        for record in records:
            snapshot = record["snapshot"]
            result = resolved.get((prompt_id, snapshot["snapshot_id"]))
            if result is None:
                result = {
                    "decision": None,
                    "openai": {},
                    "error": "not_attempted_after_fatal_api_error" if fatal else "decision_missing",
                    "cached": False,
                }
            decisions.append(
                {
                    "prompt_id": prompt_id,
                    "snapshot_id": snapshot["snapshot_id"],
                    "decision_time_ms": int(snapshot["decision_time_ms"]),
                    "decision": result["decision"].as_dict() if result["decision"] else None,
                    "openai": result["openai"],
                    "error": result["error"],
                    "cache_hit": bool(result["cached"]),
                }
            )
    prompt_results = [
        evaluate_prompt(
            prompt_id,
            records,
            decisions,
            args.stage,
            args.min_confidence,
            args.min_quality,
            args.input_price_per_million,
            args.output_price_per_million,
        )
        for prompt_id in prompt_ids
    ]
    return {
        "schema": REPLAY_SCHEMA,
        "status": "RESEARCH_ONLY_NO_ORDERS",
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "stage": args.stage,
        "provider": "openai",
        "model": config.model,
        "reasoning_effort": config.reasoning_effort,
        "prompt_family": SCANNER_PROMPT_FAMILY,
        "prompt_definitions": [prompt_definition(item) | {"instructions": None} for item in prompt_ids],
        "dataset": str(args.dataset),
        "dataset_schema": dataset.get("schema"),
        "dataset_feature_contract": dataset.get("feature_contract"),
        "dataset_feature_contract_sha256": dataset.get("feature_contract_sha256"),
        "dataset_execution_model": dataset.get("execution_model"),
        "settings": {
            "min_confidence": args.min_confidence,
            "min_quality": args.min_quality,
            "max_parallel_calls": workers,
            "future_field_guard": True,
            "max_simultaneous_positions": 1,
        },
        "fatal_api_error": fatal,
        "prompt_results": prompt_results,
        "decisions": decisions,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--cache", type=Path, required=True)
    parser.add_argument("--stage", choices=("development", "validation"), required=True)
    parser.add_argument("--prompts", nargs="+", default=list(PROMPT_VARIANTS))
    parser.add_argument("--model", default="gpt-5.6-luna")
    parser.add_argument("--reasoning-effort", default="low")
    parser.add_argument("--api-key-env", default="OPENAI_API_KEY")
    parser.add_argument("--timeout", type=int, default=45)
    parser.add_argument("--max-output-tokens", type=int, default=1200)
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument("--sleep-ms", type=int, default=100)
    parser.add_argument("--progress-every", type=int, default=20)
    parser.add_argument("--max-snapshots", type=int)
    parser.add_argument("--min-confidence", type=float, default=0.70)
    parser.add_argument("--min-quality", type=int, default=65)
    parser.add_argument("--input-price-per-million", type=float, default=0.20)
    parser.add_argument("--output-price-per-million", type=float, default=1.20)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    lock_path = args.cache.with_suffix(args.cache.suffix + ".lock")
    with exclusive_replay_lock(lock_path):
        result = run_replay(args)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    compact = {
        item["prompt_id"]: {
            "gate": item["summary"]["gate"]["passed"],
            "trades": item["summary"]["baseline"]["trades"],
            "total_r": item["summary"]["baseline"]["total_r"],
            "stress_r": item["summary"]["stress"]["total_r"],
            "profit_factor": item["summary"]["baseline"]["profit_factor"],
            "cost_usd": item["summary"]["usage"]["estimated_cost_usd"],
        }
        for item in result["prompt_results"]
    }
    print(json.dumps(compact, indent=2))
    failures = sum(
        item["summary"]["decision_failures"] for item in result["prompt_results"]
    )
    return 2 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
