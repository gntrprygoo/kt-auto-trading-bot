#!/usr/bin/env python3
"""Chronological research for frozen Strategy H market-neutral candidates."""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
import math
from pathlib import Path
from statistics import mean
import sys

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.research_strategy_f_intraday import (
    BETA_WINDOW,
    BAR_MS,
    align_symbols,
    json_safe,
    load_symbol,
    period_bounds,
    performance,
    prepare_features,
)


BASELINE_COST_PCT = 0.0016
STRESS_COST_PCT = 0.0024
SYMBOLS = (
    "BTCUSDT",
    "ETHUSDT",
    "XRPUSDT",
    "SOLUSDT",
    "DOGEUSDT",
    "ADAUSDT",
)
ALT_SYMBOLS = tuple(symbol for symbol in SYMBOLS if symbol != "BTCUSDT")


@dataclass(frozen=True)
class RelativeCandidate:
    name: str
    mode: str
    lookback_bars: int
    min_dispersion: float
    schedule_hours: int
    max_hold_bars: int
    stop_pct: float
    target_pct: float
    flow_confirm: bool


CANDIDATES = (
    RelativeCandidate("H1_MOMENTUM_8H", "MOMENTUM", 96, 0.025, 8, 32, 0.010, 0.015, False),
    RelativeCandidate("H1_MOMENTUM_FLOW_8H", "MOMENTUM", 96, 0.020, 8, 32, 0.010, 0.015, True),
    RelativeCandidate("H2_REVERSAL_8H", "REVERSAL", 96, 0.025, 8, 32, 0.010, 0.015, False),
    RelativeCandidate("H2_REVERSAL_FLOW_8H", "REVERSAL", 96, 0.020, 8, 32, 0.010, 0.015, True),
    RelativeCandidate("H3_MOMENTUM_24H", "MOMENTUM", 288, 0.050, 24, 96, 0.015, 0.0225, False),
    RelativeCandidate("H3_REVERSAL_24H", "REVERSAL", 288, 0.050, 24, 96, 0.015, 0.0225, False),
)


def is_schedule_boundary(row: dict, schedule_hours: int) -> bool:
    boundary_ms = int(row["open_time"]) + BAR_MS
    return boundary_ms % (schedule_hours * 60 * 60 * 1000) == 0


def beta_adjusted_return(
    symbol: str,
    index: int,
    lookback_bars: int,
    aligned: dict[str, list[dict]],
    features: dict[str, dict],
) -> float | None:
    if index < lookback_bars:
        return None
    beta = features[symbol]["beta"][index]
    if beta is None:
        return None
    asset_now = float(aligned[symbol][index]["close"])
    asset_old = float(aligned[symbol][index - lookback_bars]["close"])
    btc_now = float(aligned["BTCUSDT"][index]["close"])
    btc_old = float(aligned["BTCUSDT"][index - lookback_bars]["close"])
    if min(asset_now, asset_old, btc_now, btc_old) <= 0:
        return None
    return math.log(asset_now / asset_old) - float(beta) * math.log(btc_now / btc_old)


def detect_pair_signal(
    index: int,
    candidate: RelativeCandidate,
    aligned: dict[str, list[dict]],
    features: dict[str, dict],
):
    if not is_schedule_boundary(aligned["BTCUSDT"][index], candidate.schedule_hours):
        return None
    residuals = {}
    for symbol in ALT_SYMBOLS:
        value = beta_adjusted_return(
            symbol, index, candidate.lookback_bars, aligned, features
        )
        if value is None:
            return None
        residuals[symbol] = value
    strongest = max(residuals, key=residuals.get)
    weakest = min(residuals, key=residuals.get)
    dispersion = residuals[strongest] - residuals[weakest]
    if dispersion < candidate.min_dispersion:
        return None
    if candidate.mode == "MOMENTUM":
        long_symbol, short_symbol = strongest, weakest
    else:
        long_symbol, short_symbol = weakest, strongest
    long_flow = float(features[long_symbol]["flow"][index])
    short_flow = float(features[short_symbol]["flow"][index])
    if candidate.flow_confirm and (long_flow < 0.08 or short_flow > -0.08):
        return None
    return {
        "long_symbol": long_symbol,
        "short_symbol": short_symbol,
        "dispersion": dispersion,
        "long_residual": residuals[long_symbol],
        "short_residual": residuals[short_symbol],
        "long_flow": long_flow,
        "short_flow": short_flow,
    }


def pair_return(
    long_price: float,
    short_price: float,
    long_entry: float,
    short_entry: float,
) -> float:
    return 0.5 * (long_price / long_entry - 1.0) + 0.5 * (1.0 - short_price / short_entry)


def simulate_pair_trade(
    aligned: dict[str, list[dict]],
    signal_index: int,
    signal: dict,
    candidate: RelativeCandidate,
):
    entry_index = signal_index + 1
    length = len(aligned["BTCUSDT"])
    if entry_index >= length:
        return None
    long_symbol = signal["long_symbol"]
    short_symbol = signal["short_symbol"]
    long_entry = float(aligned[long_symbol][entry_index]["open"])
    short_entry = float(aligned[short_symbol][entry_index]["open"])
    if long_entry <= 0 or short_entry <= 0:
        return None
    final_index = min(length - 1, entry_index + candidate.max_hold_bars - 1)
    exit_index = final_index
    exit_reason = "TIMEOUT"
    gross_return = pair_return(
        float(aligned[long_symbol][final_index]["close"]),
        float(aligned[short_symbol][final_index]["close"]),
        long_entry,
        short_entry,
    )
    for index in range(entry_index, final_index + 1):
        long_row = aligned[long_symbol][index]
        short_row = aligned[short_symbol][index]
        worst_return = pair_return(
            float(long_row["low"]),
            float(short_row["high"]),
            long_entry,
            short_entry,
        )
        best_return = pair_return(
            float(long_row["high"]),
            float(short_row["low"]),
            long_entry,
            short_entry,
        )
        if worst_return <= -candidate.stop_pct:
            exit_index = index
            exit_reason = "STOP"
            gross_return = -candidate.stop_pct
            break
        if best_return >= candidate.target_pct:
            exit_index = index
            exit_reason = "TARGET"
            gross_return = candidate.target_pct
            break
    return {
        "signal_time": int(aligned["BTCUSDT"][signal_index]["close_time"]),
        "entry_time": int(aligned["BTCUSDT"][entry_index]["open_time"]),
        "exit_time": int(aligned["BTCUSDT"][exit_index]["close_time"]),
        "exit_index": exit_index,
        "exit_reason": exit_reason,
        "long_symbol": long_symbol,
        "short_symbol": short_symbol,
        "long_entry": long_entry,
        "short_entry": short_entry,
        "dispersion": float(signal["dispersion"]),
        "long_flow": float(signal["long_flow"]),
        "short_flow": float(signal["short_flow"]),
        "gross_return_pct": gross_return,
        "gross_r": gross_return / candidate.stop_pct,
        "baseline_net_r": (gross_return - BASELINE_COST_PCT) / candidate.stop_pct,
        "stress_net_r": (gross_return - STRESS_COST_PCT) / candidate.stop_pct,
    }


def run_candidate(
    aligned: dict[str, list[dict]],
    features: dict[str, dict],
    candidate: RelativeCandidate,
    start_ms: int,
    end_ms: int,
) -> list[dict]:
    records = []
    next_available = 0
    warmup = BETA_WINDOW + max(item.lookback_bars for item in CANDIDATES) + 1
    for index in range(warmup, len(aligned["BTCUSDT"]) - 1):
        timestamp = int(aligned["BTCUSDT"][index]["open_time"])
        if timestamp < start_ms or timestamp > end_ms or index < next_available:
            continue
        signal = detect_pair_signal(index, candidate, aligned, features)
        if not signal:
            continue
        trade = simulate_pair_trade(aligned, index, signal, candidate)
        if trade:
            records.append(trade)
            next_available = int(trade["exit_index"]) + 1
    return records


def stage_gate(stage: str, summary: dict) -> dict:
    baseline = summary["baseline"]
    stress = summary["stress"]
    if stage == "development":
        checks = {
            "minimum_trades": baseline["trades"] >= 200,
            "baseline_positive": baseline["total_r"] > 0,
            "baseline_pf": baseline["profit_factor"] >= 1.15,
            "stress_positive": stress["total_r"] > 0,
            "stress_pf": stress["profit_factor"] >= 1.05,
            "month_breadth": summary["positive_month_ratio"] >= 0.55,
            "year_breadth": summary["positive_year_ratio"] >= 0.60,
            "long_asset_breadth": summary["long_asset_breadth"] >= 4,
            "short_asset_breadth": summary["short_asset_breadth"] >= 4,
            "max_drawdown": baseline["max_drawdown_r"] <= 20.0,
        }
    elif stage == "validation":
        checks = {
            "minimum_trades": baseline["trades"] >= 30,
            "baseline_positive": baseline["total_r"] > 0,
            "baseline_pf": baseline["profit_factor"] >= 1.10,
            "stress_non_negative": stress["total_r"] >= 0,
            "month_breadth": summary["positive_month_ratio"] >= 0.50,
            "max_drawdown": baseline["max_drawdown_r"] <= 10.0,
        }
    else:
        checks = {
            "minimum_trades": baseline["trades"] >= 20,
            "baseline_positive": baseline["total_r"] > 0,
            "baseline_pf": baseline["profit_factor"] >= 1.05,
            "stress_non_negative": stress["total_r"] >= 0,
            "max_drawdown": baseline["max_drawdown_r"] <= 10.0,
        }
    return {"passed": all(checks.values()), "checks": checks}


def summarize(records: list[dict], stage: str) -> dict:
    ordered = sorted(records, key=lambda row: row["entry_time"])
    month_totals = defaultdict(float)
    year_totals = defaultdict(float)
    for row in ordered:
        current = datetime.fromtimestamp(row["entry_time"] / 1000, timezone.utc)
        month_totals[current.strftime("%Y-%m")] += float(row["baseline_net_r"])
        year_totals[current.strftime("%Y")] += float(row["baseline_net_r"])
    long_usage = Counter(row["long_symbol"] for row in ordered)
    short_usage = Counter(row["short_symbol"] for row in ordered)
    summary = {
        "gross": performance(ordered, "gross_r"),
        "baseline": performance(ordered, "baseline_net_r"),
        "stress": performance(ordered, "stress_net_r"),
        "monthly_r": dict(sorted(month_totals.items())),
        "yearly_r": dict(sorted(year_totals.items())),
        "positive_month_ratio": sum(value > 0 for value in month_totals.values()) / len(month_totals) if month_totals else 0.0,
        "positive_year_ratio": sum(value > 0 for value in year_totals.values()) / len(year_totals) if year_totals else 0.0,
        "long_usage": dict(long_usage),
        "short_usage": dict(short_usage),
        "long_asset_breadth": len(long_usage),
        "short_asset_breadth": len(short_usage),
        "exit_reasons": dict(Counter(row["exit_reason"] for row in ordered)),
        "average_dispersion": mean([float(row["dispersion"]) for row in ordered]) if ordered else 0.0,
    }
    summary["gate"] = stage_gate(stage, summary)
    return summary


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", choices=("development", "validation", "holdout"), default="development")
    parser.add_argument("--candidate", choices=tuple(item.name for item in CANDIDATES))
    parser.add_argument("--cache-root", type=Path, default=Path(".audit/2026-07-22"))
    parser.add_argument("--extra-cache", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.stage != "development" and not args.candidate:
        raise ValueError("--candidate is required for validation and holdout")
    loaded = {
        symbol: load_symbol(args.cache_root, symbol, args.extra_cache)
        for symbol in SYMBOLS
    }
    aligned = align_symbols(loaded)
    features = prepare_features(aligned)
    start_ms, end_ms = period_bounds(args.stage, aligned)
    candidates = [item for item in CANDIDATES if not args.candidate or item.name == args.candidate]
    results = {}
    for candidate in candidates:
        records = run_candidate(aligned, features, candidate, start_ms, end_ms)
        results[candidate.name] = {
            "parameters": asdict(candidate),
            "summary": summarize(records, args.stage),
            "records": records,
        }
    passed = [name for name, item in results.items() if item["summary"]["gate"]["passed"]]
    selected = max(
        passed,
        key=lambda name: results[name]["summary"]["stress"]["total_r"],
        default=None,
    )
    payload = {
        "engine": "STRATEGY_H_RELATIVE_VALUE_RESEARCH_V1",
        "status": "RESEARCH_ONLY_NO_ORDERS",
        "stage": args.stage,
        "period": {"start_ms": start_ms, "end_ms": end_ms},
        "symbols": list(SYMBOLS),
        "baseline_cost_pct": BASELINE_COST_PCT,
        "stress_cost_pct": STRESS_COST_PCT,
        "results": results,
        "passed_candidates": passed,
        "selected_candidate": selected,
        "next_step": (
            "RUN_VALIDATION_WITH_FROZEN_SELECTED_CANDIDATE"
            if selected and args.stage == "development"
            else "REJECT_OR_REVIEW_STAGE_RESULT"
        ),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(json_safe(payload), indent=2) + "\n", encoding="utf-8")
    compact = {
        name: {
            "trades": item["summary"]["baseline"]["trades"],
            "net_r": round(item["summary"]["baseline"]["total_r"], 3),
            "pf": item["summary"]["baseline"]["profit_factor"],
            "stress_r": round(item["summary"]["stress"]["total_r"], 3),
            "passed": item["summary"]["gate"]["passed"],
        }
        for name, item in results.items()
    }
    print(json.dumps(json_safe({"results": compact, "selected": selected}), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
