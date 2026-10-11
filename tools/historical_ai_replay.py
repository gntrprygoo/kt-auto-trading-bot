#!/usr/bin/env python3
"""Replay frozen deterministic candidates through the Hybrid AI reviewer."""

from __future__ import annotations

import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import sys
import time

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from hybrid_ai_engine import (
    AITradeDecision,
    HybridAIConfig,
    HybridRiskGateway,
    OpenAIResponsesClient,
    PROMPT_VERSION,
    candidate_id,
)
from tools.research_strategy_f_intraday import (
    align_symbols,
    candle_shape,
    load_symbol,
    prepare_features,
)


FUTURE_FIELDS = {
    "exit_time",
    "exit_price",
    "exit_index",
    "exit_reason",
    "gross_r",
    "baseline_net_r",
    "stress_net_r",
    "result_r",
    "status",
}

FATAL_API_ERROR_MARKERS = (
    "insufficient_quota",
    "credit_balance_exhausted",
    "invalid_api_key",
    "authentication",
    "openai http 401",
    "openai http 403",
    "openai http 400",
    "openai http 404",
    "openai http 429",
)


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _safe(value, digits=8):
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number):
        return None
    return round(number, digits)


def _return(closes: list[float], index: int, bars: int):
    if index < bars or closes[index - bars] <= 0:
        return None
    return closes[index] / closes[index - bars] - 1.0


def build_feature_context(
    symbol: str,
    index: int,
    aligned: dict[str, list[dict]],
    features: dict[str, dict],
) -> dict:
    row = aligned[symbol][index]
    feature = features[symbol]
    btc = features["BTCUSDT"]
    direction, body_ratio, close_location = candle_shape(row)
    close = float(row["close"])
    fast = feature["ema_fast"][index]
    slow = feature["ema_slow"][index]
    atr = feature["atr"][index]
    signal_open_time = int(row["open_time"])
    candle_close_time = int(row.get("close_time") or signal_open_time)
    timestamp_dt = datetime.fromtimestamp(candle_close_time / 1000, timezone.utc)
    return {
        "last_confirmed_candle_utc": timestamp_dt.isoformat().replace("+00:00", "Z"),
        "last_confirmed_candle_close_ms": candle_close_time,
        "signal_candle_open_ms": signal_open_time,
        "utc_hour": timestamp_dt.hour,
        "utc_weekday": timestamp_dt.weekday(),
        "return_15m": _safe(_return(feature["closes"], index, 1)),
        "return_1h": _safe(_return(feature["closes"], index, 4)),
        "return_4h": _safe(_return(feature["closes"], index, 16)),
        "return_12h": _safe(_return(feature["closes"], index, 48)),
        "return_24h": _safe(_return(feature["closes"], index, 96)),
        "btc_return_4h": _safe(_return(btc["closes"], index, 16)),
        "btc_return_24h": _safe(_return(btc["closes"], index, 96)),
        "atr_pct": _safe(float(atr) / close if atr and close > 0 else None),
        "ema_fast_above_slow": bool(fast is not None and slow is not None and fast > slow),
        "ema_distance_pct": _safe((fast - slow) / close if fast is not None and slow is not None else None),
        "trend_z": _safe(feature["trend_z"][index]),
        "residual_z": _safe(feature.get("residual_z", [None] * len(aligned[symbol]))[index]),
        "volume_ratio": _safe(feature["volume_ratio"][index]),
        "taker_flow": _safe(feature["flow"][index]),
        "btc_taker_flow": _safe(btc["flow"][index]),
        "candle_direction": direction,
        "candle_body_ratio": _safe(body_ratio),
        "candle_close_location": _safe(close_location),
    }


def build_candidate(
    record: dict,
    context: dict,
    notional_usdt: float = 10.0,
    decision_time_ms: int | None = None,
) -> dict:
    entry = float(record["entry"])
    stop = float(record["stop"])
    target = float(record["target"])
    risk_pct = abs(entry - stop) / entry
    rr = abs(target - entry) / abs(entry - stop)
    return {
        "pair": str(record["symbol"]).upper(),
        "side": str(record["side"]).upper(),
        # F2 enters at the next candle open. At that instant the entry price is
        # observable and the signal candle is fully confirmed; no later candle
        # or trade outcome is included in the snapshot.
        "signal_time_ms": int(
            decision_time_ms
            or record.get("entry_time")
            or context.get("last_confirmed_candle_close_ms")
            or record["signal_time"]
        ),
        "entry": entry,
        "sl": stop,
        "tp": target,
        "tp2": target,
        "actual_rr": rr,
        "stop_pct": risk_pct,
        "notional_usdt": float(notional_usdt),
        "risk_usdt": float(notional_usdt) * risk_pct,
        "strategy": "F2_LONG_RESIDUAL_MOMENTUM_8H_FROZEN",
        "market_context": {
            **context,
            "source_flow": _safe(record.get("flow")),
            "source_volume_ratio": _safe(record.get("volume_ratio")),
            "source_trend_z": _safe(record.get("trend_z")),
            "source_signal_z": _safe(record.get("signal_z")),
            "btc_market_trend": record.get("btc_market_trend"),
        },
    }


def assert_no_future_fields(snapshot: dict) -> None:
    def walk(value, path="root"):
        if isinstance(value, dict):
            for key, child in value.items():
                if str(key).lower() in FUTURE_FIELDS:
                    raise ValueError(f"future field leaked into model input: {path}.{key}")
                walk(child, f"{path}.{key}")
        elif isinstance(value, list):
            for index, child in enumerate(value):
                walk(child, f"{path}[{index}]")

    walk(snapshot)


def replay_key(provider: str, model: str, snapshot: dict) -> str:
    payload = {
        "provider": provider,
        "model": model,
        "prompt_version": PROMPT_VERSION,
        "snapshot": snapshot,
    }
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def load_cache(path: Path) -> dict[str, dict]:
    cached: dict[str, dict] = {}
    if not path.exists():
        return cached
    with path.open("r", encoding="utf-8-sig") as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            try:
                item = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"invalid replay cache line {line_number}") from exc
            if isinstance(item, dict) and item.get("replay_key"):
                cached[str(item["replay_key"])] = item
    return cached


def append_cache(path: Path, item: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(item, sort_keys=True, separators=(",", ":")) + "\n")
        handle.flush()
        os.fsync(handle.fileno())


def is_fatal_api_error(error: str | None) -> bool:
    normalized = str(error or "").lower()
    return any(marker in normalized for marker in FATAL_API_ERROR_MARKERS)


def heuristic_decision(candidate: dict) -> AITradeDecision:
    context = candidate.get("market_context", {})
    residual = float(context.get("residual_z") or context.get("source_signal_z") or 0)
    flow = float(context.get("taker_flow") or context.get("source_flow") or 0)
    volume = float(context.get("volume_ratio") or context.get("source_volume_ratio") or 0)
    trend_ok = bool(context.get("ema_fast_above_slow"))
    accepted = residual >= 2.5 and flow >= 0.18 and volume >= 1.4 and trend_ok
    return AITradeDecision(
        action="TRADE" if accepted else "SKIP",
        confidence=0.78 if accepted else 0.76,
        regime="TREND" if trend_ok else "TRANSITION",
        setup_quality=74 if accepted else 50,
        risk_flags=() if accepted else ("heuristic_filter_not_aligned",),
        thesis="Frozen deterministic replay control decision.",
        invalidation="The supplied stop invalidates the candidate.",
    )


def profit_factor(values: list[float]):
    wins = sum(value for value in values if value > 0)
    losses = -sum(value for value in values if value < 0)
    if losses <= 1e-12:
        return 0.0 if wins <= 1e-12 else 999.0
    return wins / losses


def max_drawdown(values: list[float]) -> float:
    equity = peak = drawdown = 0.0
    for value in values:
        equity += value
        peak = max(peak, equity)
        drawdown = max(drawdown, peak - equity)
    return drawdown


def summarize_values(values: list[float]) -> dict:
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


def stage_gate(stage: str, summary: dict) -> dict:
    reviewed = summary["reviewed_candidates"]
    coverage = summary["decision_coverage"]
    baseline = summary["baseline"]
    stress = summary["stress"]
    if stage == "development":
        checks = {
            "reviewed_candidates": reviewed >= 100,
            "accepted_trades": baseline["trades"] >= 30,
            "decision_coverage": coverage >= 0.95,
            "baseline_positive": baseline["total_r"] > 0,
            "baseline_pf": (baseline["profit_factor"] or 0) >= 1.15,
            "stress_positive": stress["total_r"] > 0,
            "stress_pf": (stress["profit_factor"] or 0) >= 1.05,
            "max_drawdown": baseline["max_drawdown_r"] <= 12.0,
        }
    else:
        checks = {
            "reviewed_candidates": reviewed >= 15,
            "accepted_trades": baseline["trades"] >= 8,
            "decision_coverage": coverage >= 0.95,
            "baseline_positive": baseline["total_r"] > 0,
            "baseline_pf": (baseline["profit_factor"] or 0) >= 1.10,
            "stress_non_negative": stress["total_r"] >= 0,
            "max_drawdown": baseline["max_drawdown_r"] <= 6.0,
        }
    return {"passed": all(checks.values()), "checks": checks}


def run_replay(args: argparse.Namespace) -> dict:
    source = read_json(args.input)
    records = source.get("records") if isinstance(source, dict) else None
    if not isinstance(records, list):
        raise ValueError("input must contain a records array")
    if args.max_events:
        records = records[: args.max_events]
    symbols = sorted({str(record.get("symbol", "")).upper() for record in records} | {"BTCUSDT"})
    loaded = {
        symbol: load_symbol(args.cache_root, symbol, args.extra_cache)
        for symbol in symbols
    }
    aligned = align_symbols(loaded)
    features = prepare_features(aligned)
    timestamps = {int(row["open_time"]): index for index, row in enumerate(aligned["BTCUSDT"])}

    config = HybridAIConfig.from_mapping(
        {
            "enabled": True,
            "model": args.model,
            "reasoning_effort": args.reasoning_effort,
            "api_key_env": args.api_key_env,
            "request_timeout_sec": args.timeout,
            "min_confidence": args.min_confidence,
            "min_setup_quality": args.min_setup_quality,
            "max_notional_usdt": args.notional,
        },
        args.output.parent,
    )
    client = OpenAIResponsesClient(config)
    risk_gateway = HybridRiskGateway(config)
    cache = load_cache(args.cache)

    prepared = []
    for sequence, record in enumerate(records, 1):
        signal_time = int(record["signal_time"])
        index = timestamps.get(signal_time)
        if index is None:
            prepared.append({
                "sequence": sequence,
                "record": record,
                "signal_time": signal_time,
                "symbol": str(record.get("symbol", "")).upper(),
                "error": "timestamp_not_aligned",
            })
            continue
        symbol = str(record["symbol"]).upper()
        context = build_feature_context(symbol, index, aligned, features)
        decision_time = int(
            record.get("entry_time")
            or context.get("last_confirmed_candle_close_ms")
            or signal_time
        )
        candidate = build_candidate(
            record,
            context,
            args.notional,
            decision_time_ms=decision_time,
        )
        snapshot = {
            "schema": "KT_HYBRID_CANDIDATE_V1",
            "prompt_version": PROMPT_VERSION,
            "candidate_id": candidate_id(candidate),
            "candidate": candidate,
        }
        assert_no_future_fields(snapshot)
        prepared.append({
            "sequence": sequence,
            "record": record,
            "signal_time": signal_time,
            "decision_time_ms": decision_time,
            "symbol": symbol,
            "candidate": candidate,
            "snapshot": snapshot,
            "replay_key": replay_key(args.provider, config.model, snapshot),
        })

    resolved: dict[int, dict] = {}
    api_queue = []
    for item in prepared:
        if item.get("error"):
            resolved[item["sequence"]] = {
                "decision": None,
                "metadata": {},
                "error": item["error"],
            }
            continue
        cached = cache.get(item["replay_key"])
        decision = None
        metadata = {}
        if cached and isinstance(cached.get("decision"), dict):
            try:
                decision = AITradeDecision.from_mapping(cached["decision"])
                metadata = cached.get("openai", {})
            except Exception:
                decision = None
        if decision is not None:
            resolved[item["sequence"]] = {
                "decision": decision,
                "metadata": metadata,
                "error": None,
            }
            continue
        if args.provider == "openai":
            api_queue.append(item)
            continue

        decision = heuristic_decision(item["candidate"])
        metadata = {"model": "HEURISTIC_CONTROL_NOT_AI"}
        resolved[item["sequence"]] = {
            "decision": decision,
            "metadata": metadata,
            "error": None,
        }
        cache_item = {
            "replay_key": item["replay_key"],
            "candidate_id": item["snapshot"]["candidate_id"],
            "prompt_version": PROMPT_VERSION,
            "model": "HEURISTIC_CONTROL_NOT_AI",
            "decision": asdict(decision),
            "openai": metadata,
            "error": None,
        }
        append_cache(args.cache, cache_item)
        cache[item["replay_key"]] = cache_item

    if api_queue:
        workers = max(1, min(8, int(args.workers)))

        def call_reviewer(item):
            try:
                value, meta = client.decide(item["snapshot"])
                return value, meta, None
            except Exception as exc:
                return None, {}, str(exc)[:300]
            finally:
                if args.sleep_ms > 0:
                    time.sleep(args.sleep_ms / 1000.0)

        completed = 0
        fatal_error = None
        with ThreadPoolExecutor(max_workers=workers) as executor:
            # Submit one bounded batch at a time. Authentication, quota, or
            # rate-limit failures stop subsequent calls instead of flooding the
            # API with the entire historical sample.
            for start in range(0, len(api_queue), workers):
                batch = api_queue[start:start + workers]
                futures = {executor.submit(call_reviewer, item): item for item in batch}
                for future in as_completed(futures):
                    item = futures[future]
                    decision, metadata, error = future.result()
                    resolved[item["sequence"]] = {
                        "decision": decision,
                        "metadata": metadata,
                        "error": error,
                    }
                    # A later JSONL row supersedes an earlier failed row with
                    # the same key, so interruptions are resumable.
                    cache_item = {
                        "replay_key": item["replay_key"],
                        "candidate_id": item["snapshot"]["candidate_id"],
                        "prompt_version": PROMPT_VERSION,
                        "model": config.model,
                        "decision": asdict(decision) if decision else None,
                        "openai": metadata,
                        "error": error,
                    }
                    append_cache(args.cache, cache_item)
                    cache[item["replay_key"]] = cache_item
                    completed += 1
                    if is_fatal_api_error(error):
                        fatal_error = error
                    if args.progress_every and completed % args.progress_every == 0:
                        print(
                            f"ai_calls_completed={completed}/{len(api_queue)} workers={workers}",
                            flush=True,
                        )
                if fatal_error:
                    break
        if fatal_error:
            for item in api_queue:
                if item["sequence"] not in resolved:
                    resolved[item["sequence"]] = {
                        "decision": None,
                        "metadata": {},
                        "error": "replay_aborted_after_fatal_api_error",
                    }

    accepted_records = []
    decisions = []
    failures = 0
    action_counts = Counter()
    for sequence, item in enumerate(prepared, 1):
        result = resolved[item["sequence"]]
        decision = result["decision"]
        metadata = result["metadata"]
        error = result["error"]
        if decision is None:
            failures += 1
            failure = {
                "signal_time": item["signal_time"],
                "symbol": item["symbol"],
                "error": error or "decision_unavailable",
            }
            if item.get("snapshot"):
                failure["candidate_id"] = item["snapshot"]["candidate_id"]
            decisions.append(failure)
        else:
            candidate = item["candidate"]
            gate = risk_gateway.evaluate(
                candidate,
                decision,
                {
                    "now_ms": item["decision_time_ms"],
                    "equity": args.replay_equity,
                    "open_positions": 0,
                    "open_pairs": [],
                    "daily_r": 0.0,
                    "entry_paused": False,
                },
            )
            accepted = gate.allowed
            action_counts[decision.action] += 1
            decisions.append({
                "candidate_id": item["snapshot"]["candidate_id"],
                "decision_time_ms": item["decision_time_ms"],
                "signal_time": item["signal_time"],
                "symbol": item["symbol"],
                "accepted": accepted,
                "decision": asdict(decision),
                "risk_gate_reasons": list(gate.reasons),
                "openai": metadata,
            })
            if accepted:
                accepted_records.append(item["record"])
        if args.progress_every and sequence % args.progress_every == 0:
            print(
                f"replay_progress reviewed={sequence}/{len(records)} "
                f"accepted={len(accepted_records)} failures={failures}",
                flush=True,
            )

    baseline_values = [float(record["baseline_net_r"]) for record in accepted_records]
    stress_values = [float(record["stress_net_r"]) for record in accepted_records]
    summary = {
        "candidate_count": len(records),
        "reviewed_candidates": len(records) - failures,
        "decision_failures": failures,
        "decision_coverage": (len(records) - failures) / len(records) if records else 0.0,
        "action_counts": dict(action_counts),
        "baseline": summarize_values(baseline_values),
        "stress": summarize_values(stress_values),
    }
    summary["gate"] = stage_gate(args.stage, summary)
    return {
        "schema": "KT_HISTORICAL_AI_REPLAY_V1",
        "status": "RESEARCH_ONLY_NO_ORDERS",
        "provider": args.provider,
        "stage": args.stage,
        "model": config.model if args.provider == "openai" else "HEURISTIC_CONTROL_NOT_AI",
        "prompt_version": PROMPT_VERSION,
        "candidate_family": "F2_LONG_RESIDUAL_MOMENTUM_8H_FROZEN",
        "candidate_definition": source.get("candidate") if isinstance(source, dict) else None,
        "source": str(args.input),
        "settings": {
            "reasoning_effort": config.reasoning_effort,
            "min_confidence": config.min_confidence,
            "min_setup_quality": config.min_setup_quality,
            "min_rr": config.min_rr,
            "max_stop_pct": config.max_stop_pct,
            "max_account_risk_pct": config.max_account_risk_pct,
            "notional_usdt": args.notional,
            "future_field_guard": True,
            "decision_time": "next_candle_open_after_confirmed_signal",
        },
        "summary": summary,
        "decisions": decisions,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--stage", choices=("development", "validation"), required=True)
    parser.add_argument("--cache-root", type=Path, default=Path(".audit/2026-07-22"))
    parser.add_argument("--extra-cache", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--cache", type=Path, required=True)
    parser.add_argument("--provider", choices=("openai", "heuristic"), default="openai")
    parser.add_argument("--model", default="gpt-5.6-luna")
    parser.add_argument("--reasoning-effort", default="low")
    parser.add_argument("--api-key-env", default="OPENAI_API_KEY")
    parser.add_argument("--timeout", type=int, default=45)
    parser.add_argument("--min-confidence", type=float, default=0.72)
    parser.add_argument("--min-setup-quality", type=int, default=65)
    parser.add_argument("--notional", type=float, default=10.0)
    parser.add_argument("--replay-equity", type=float, default=1000.0)
    parser.add_argument("--max-events", type=int)
    parser.add_argument("--progress-every", type=int, default=10)
    parser.add_argument("--sleep-ms", type=int, default=0)
    parser.add_argument("--workers", type=int, default=2)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    result = run_replay(args)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result["summary"], indent=2))
    return 2 if result["summary"]["decision_failures"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
