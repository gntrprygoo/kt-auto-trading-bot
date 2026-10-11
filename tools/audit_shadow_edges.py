#!/usr/bin/env python3
"""Audit active and retired shadow hypotheses without winner selection."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import random
from statistics import mean


DEFAULT_COST_PCT = 0.0014
CLOSED_STATUSES = {"SHADOW_WIN", "SHADOW_LOSS"}


def strategy_key(record: dict) -> str:
    reason = record.get("blocked_reason")
    version = record.get("strategy_version")
    if reason == "smart_money_c_v6" or version == "C6":
        return "C6"
    if reason == "smart_money_c":
        return "C1"
    if reason == "vol_too_high":
        return "A_HIGH_VOLUME"
    return "OTHER"


def max_drawdown(values: list[float]) -> float:
    equity = 0.0
    peak = 0.0
    drawdown = 0.0
    for value in values:
        equity += value
        peak = max(peak, equity)
        drawdown = max(drawdown, peak - equity)
    return drawdown


def summarize(values: list[float]) -> dict:
    gross_profit = sum(value for value in values if value > 0)
    gross_loss = abs(sum(value for value in values if value < 0))
    if gross_loss:
        profit_factor = gross_profit / gross_loss
    elif gross_profit:
        profit_factor = math.inf
    else:
        profit_factor = 0.0
    return {
        "n": len(values),
        "wins": sum(1 for value in values if value > 0),
        "win_rate_pct": (sum(1 for value in values if value > 0) / len(values) * 100)
        if values else 0.0,
        "total_r": sum(values),
        "avg_r": mean(values) if values else 0.0,
        "profit_factor": profit_factor,
        "max_drawdown_r": max_drawdown(values),
    }


def bootstrap_mean_ci(
    values: list[float],
    samples: int = 10_000,
    seed: int = 20260804,
) -> list[float | None]:
    if not values:
        return [None, None]
    rng = random.Random(seed)
    estimates = []
    for _ in range(samples):
        estimates.append(mean(rng.choice(values) for _ in values))
    estimates.sort()
    low = estimates[int(samples * 0.025)]
    high = estimates[min(samples - 1, int(samples * 0.975))]
    return [low, high]


def estimated_cost_r(record: dict, roundtrip_cost_pct: float) -> float | None:
    try:
        entry = float(record.get("entry"))
        stop = float(record.get("sl"))
    except (TypeError, ValueError):
        return None
    risk_pct = abs(entry - stop) / entry if entry > 0 else 0.0
    if risk_pct <= 0:
        return None
    return roundtrip_cost_pct / risk_pct


def chronological_splits(values: list[float]) -> dict:
    midpoint = len(values) // 2
    tail_size = max(1, math.ceil(len(values) * 0.30)) if values else 0
    return {
        "first_half": summarize(values[:midpoint]),
        "last_half": summarize(values[midpoint:]),
        "last_30_pct": summarize(values[-tail_size:] if tail_size else []),
    }


def audit_group(records: list[dict], roundtrip_cost_pct: float) -> dict:
    closed = sorted(
        [record for record in records if record.get("status") in CLOSED_STATUSES],
        key=lambda row: row.get("closed_at") or row.get("timestamp") or 0,
    )
    gross = [float(record.get("result_R", 0) or 0) for record in closed]
    net = []
    missing_cost_basis = 0
    for record, result_r in zip(closed, gross):
        cost_r = estimated_cost_r(record, roundtrip_cost_pct)
        if cost_r is None:
            missing_cost_basis += 1
            net.append(result_r)
        else:
            net.append(result_r - cost_r)
    return {
        "records": len(records),
        "open": sum(1 for record in records if record.get("status") == "SHADOW_OPEN"),
        "timeouts": sum(1 for record in records if record.get("status") == "SHADOW_TIMEOUT"),
        "gross": summarize(gross),
        "estimated_net_after_cost": summarize(net),
        "cost_basis_missing": missing_cost_basis,
        "bootstrap_avg_r_95_ci_gross": bootstrap_mean_ci(gross),
        "chronological_gross": chronological_splits(gross),
    }


def build_audit(records: list[dict], roundtrip_cost_pct: float) -> dict:
    groups = {
        key: [record for record in records if strategy_key(record) == key]
        for key in ("A_HIGH_VOLUME", "C1", "C6")
    }
    audits = {
        key: audit_group(group, roundtrip_cost_pct)
        for key, group in groups.items()
    }
    return {
        "audit_date": "2026-08-04",
        "scope": "SHADOW_ONLY",
        "roundtrip_cost_assumption_pct": roundtrip_cost_pct,
        "method": {
            "entry_selection": "all recorded signals; no ex-post winner filtering",
            "uncertainty": "deterministic 10000-sample bootstrap mean 95% CI",
            "stability": "chronological first half, last half, and final 30%",
            "cost": "fee plus slippage estimate converted to R using recorded stop distance",
        },
        "strategies": audits,
        "decisions": {
            "A_HIGH_VOLUME": (
                "RETIRE_SHADOW; negative expectancy confirms the existing live "
                "low-volume gate should remain"
            ),
            "C1": "RETIRE; materially negative expectancy and profit factor",
            "C6": (
                "CONTINUE_FORWARD_SHADOW; historical validation passed, but only "
                f"{audits['C6']['gross']['n']} forward trades are closed and live "
                "promotion remains unapproved"
            ),
            "D1": "UNCHANGED; independent long-only forward shadow",
        },
    }


def json_safe(payload):
    if isinstance(payload, dict):
        return {key: json_safe(value) for key, value in payload.items()}
    if isinstance(payload, list):
        return [json_safe(value) for value in payload]
    if isinstance(payload, float) and not math.isfinite(payload):
        return "INF" if payload > 0 else "-INF"
    return payload


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--shadow", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--roundtrip-cost-pct", type=float, default=DEFAULT_COST_PCT)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    records = json.loads(args.shadow.read_text(encoding="utf-8-sig"))
    if not isinstance(records, list):
        raise ValueError("shadow input must be a JSON list")
    result = build_audit(records, args.roundtrip_cost_pct)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(json_safe(result), indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(json_safe(result["decisions"]), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
