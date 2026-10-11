#!/usr/bin/env python3
"""Chronological, cost-aware research for frozen Strategy E scalping ideas."""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
import math
from pathlib import Path
from statistics import mean, median


BAR_MS = 15 * 60 * 1000
DEVELOPMENT_END = int(datetime(2025, 9, 1, tzinfo=timezone.utc).timestamp() * 1000) - 1
VALIDATION_START = DEVELOPMENT_END + 1
VALIDATION_END = int(datetime(2026, 3, 1, tzinfo=timezone.utc).timestamp() * 1000) - 1
HOLDOUT_START = VALIDATION_END + 1
BASELINE_COST_PCT = 0.0014
STRESS_COST_PCT = 0.0020
SYMBOLS = ("BTCUSDT", "ETHUSDT", "SOLUSDT")
SESSION_WINDOWS = {
    "E5_ASIA_ORB_15R": (0, 1, 7),
    "E5_EUROPE_ORB_15R": (7, 8, 13),
    "E5_US_ORB_15R": (13, 14, 21),
}


@dataclass(frozen=True)
class Candidate:
    name: str
    family: str
    lookback: int
    volume_ratio: float
    body_or_wick_ratio: float
    flow_ratio: float
    compression_max: float
    stop_atr: float
    target_r: float
    max_hold_bars: int
    regime: str
    min_risk_pct: float


CANDIDATES = (
    Candidate("E1_BALANCED_15R", "EXPANSION", 16, 1.30, 0.55, 0.54, 1.00, 1.20, 1.50, 12, "TREND", 0.0025),
    Candidate("E1_STRICT_15R", "EXPANSION", 20, 1.50, 0.60, 0.56, 0.90, 1.20, 1.50, 12, "TREND", 0.0025),
    Candidate("E1_STRICT_20R", "EXPANSION", 20, 1.50, 0.60, 0.56, 0.90, 1.20, 2.00, 12, "TREND", 0.0025),
    Candidate("E2_RANGE_RECLAIM_12R", "RECLAIM", 20, 1.50, 0.50, 0.56, 99.0, 0.15, 1.20, 8, "RANGE", 0.0025),
    Candidate("E2_TREND_RECLAIM_15R", "RECLAIM", 20, 1.40, 0.45, 0.55, 99.0, 0.15, 1.50, 10, "TREND", 0.0025),
    Candidate("E3_FAILED_RANGE_15R", "FAILED_EXPANSION", 20, 1.50, 0.55, 0.55, 99.0, 0.10, 1.50, 12, "RANGE", 0.0025),
    Candidate("E3_FAILED_ANY_20R", "FAILED_EXPANSION", 20, 1.50, 0.55, 0.55, 99.0, 0.10, 2.00, 12, "ANY", 0.0025),
    Candidate("E4_JUMP_REVERSAL_15R", "JUMP_REVERSAL", 20, 2.00, 0.65, 0.55, 99.0, 0.10, 1.50, 12, "ANY", 0.0025),
    Candidate("E3_FAILED_WIDE_15R", "FAILED_EXPANSION", 20, 1.50, 0.55, 0.55, 99.0, 0.10, 1.50, 16, "ANY", 0.0080),
    Candidate("E4_JUMP_WIDE_125R", "JUMP_REVERSAL", 20, 2.00, 0.65, 0.55, 99.0, 0.10, 1.25, 16, "ANY", 0.0080),
    Candidate("E4_JUMP_WIDE_15R", "JUMP_REVERSAL", 20, 2.00, 0.65, 0.55, 99.0, 0.10, 1.50, 24, "ANY", 0.0080),
    Candidate("E5_ASIA_ORB_15R", "SESSION_ORB", 4, 1.20, 0.50, 0.52, 99.0, 0.10, 1.50, 24, "TREND", 0.0080),
    Candidate("E5_EUROPE_ORB_15R", "SESSION_ORB", 4, 1.20, 0.50, 0.52, 99.0, 0.10, 1.50, 24, "TREND", 0.0080),
    Candidate("E5_US_ORB_15R", "SESSION_ORB", 4, 1.20, 0.50, 0.52, 99.0, 0.10, 1.50, 24, "TREND", 0.0080),
)


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def load_symbol(cache_root: Path, symbol: str) -> list[dict]:
    patterns = (
        cache_root / "market_cache_b4_stress365",
        cache_root / "market_cache_b4_270d",
    )
    files = []
    for directory in patterns:
        files.extend(sorted(directory.glob(f"{symbol}_15m_*.json")))
    if not files:
        raise FileNotFoundError(f"no 15m cache files for {symbol}")
    deduped = {}
    for path in files:
        for row in read_json(path):
            deduped[int(row["open_time"])] = row
    rows = [deduped[key] for key in sorted(deduped)]
    return rows


def ema_series(values: list[float], period: int) -> list[float | None]:
    output = [None] * len(values)
    if len(values) < period:
        return output
    current = sum(values[:period]) / period
    output[period - 1] = current
    alpha = 2.0 / (period + 1.0)
    for index in range(period, len(values)):
        current = alpha * values[index] + (1.0 - alpha) * current
        output[index] = current
    return output


def rolling_mean(values: list[float | None], period: int) -> list[float | None]:
    output = [None] * len(values)
    window = []
    total = 0.0
    for index, value in enumerate(values):
        if value is None:
            window.append(None)
        else:
            numeric = float(value)
            window.append(numeric)
            total += numeric
        if len(window) > period:
            removed = window.pop(0)
            if removed is not None:
                total -= removed
        if len(window) == period and all(item is not None for item in window):
            output[index] = total / period
    return output


def atr_series(candles: list[dict], period: int = 14) -> list[float | None]:
    true_ranges = [None]
    for previous, current in zip(candles, candles[1:]):
        true_ranges.append(max(
            float(current["high"]) - float(current["low"]),
            abs(float(current["high"]) - float(previous["close"])),
            abs(float(current["low"]) - float(previous["close"])),
        ))
    return rolling_mean(true_ranges, period)


def prepare_indicators(candles: list[dict]) -> dict:
    closes = [float(row["close"]) for row in candles]
    volumes = [float(row["volume"]) for row in candles]
    atr = atr_series(candles)
    return {
        "ema_fast": ema_series(closes, 96),
        "ema_slow": ema_series(closes, 384),
        "atr": atr,
        "atr_mean": rolling_mean(atr, 96),
        "volume_mean": rolling_mean(volumes, 40),
    }


def candle_shape(candle: dict) -> tuple[float, float, float, float]:
    high = float(candle["high"])
    low = float(candle["low"])
    open_price = float(candle["open"])
    close = float(candle["close"])
    span = high - low
    if span <= 0:
        return 0.0, 0.0, 0.0, 0.0
    body = abs(close - open_price) / span
    lower_wick = (min(open_price, close) - low) / span
    upper_wick = (high - max(open_price, close)) / span
    close_location = (close - low) / span
    return body, lower_wick, upper_wick, close_location


def trend_side(indicators: dict, index: int) -> str | None:
    fast = indicators["ema_fast"][index]
    slow = indicators["ema_slow"][index]
    old_fast = indicators["ema_fast"][index - 16] if index >= 16 else None
    if None in (fast, slow, old_fast):
        return None
    if fast > slow and fast > old_fast:
        return "LONG"
    if fast < slow and fast < old_fast:
        return "SHORT"
    return None


def detect_signal(candles: list[dict], indicators: dict, index: int, candidate: Candidate):
    if index < max(400, candidate.lookback + 1):
        return None
    candle = candles[index]
    atr = indicators["atr"][index]
    volume_mean = indicators["volume_mean"][index - 1]
    if not atr or not volume_mean or atr <= 0 or volume_mean <= 0:
        return None
    body, lower_wick, upper_wick, close_location = candle_shape(candle)
    volume_ratio = float(candle["volume"]) / volume_mean
    volume = float(candle["volume"])
    buy_share = float(candle.get("taker_buy", 0) or 0) / volume if volume > 0 else 0.5
    sell_share = 1.0 - buy_share
    prior = candles[index - candidate.lookback:index]
    prior_high = max(float(row["high"]) for row in prior)
    prior_low = min(float(row["low"]) for row in prior)
    close = float(candle["close"])
    trend = trend_side(indicators, index)

    if candidate.family == "SESSION_ORB":
        range_start_hour, range_end_hour, trade_end_hour = SESSION_WINDOWS[candidate.name]
        open_time = int(candle["open_time"])
        day_ms = 24 * 60 * 60 * 1000
        day_start = open_time - (open_time % day_ms)
        range_start = day_start + range_start_hour * 60 * 60 * 1000
        range_end = day_start + range_end_hour * 60 * 60 * 1000
        trade_end = day_start + trade_end_hour * 60 * 60 * 1000
        if open_time < range_end or open_time >= trade_end:
            return None
        opening_rows = [
            row for row in candles[max(0, index - 96):index]
            if range_start <= int(row["open_time"]) < range_end
        ]
        if len(opening_rows) != 4:
            return None
        if body < candidate.body_or_wick_ratio or volume_ratio < candidate.volume_ratio:
            return None
        opening_high = max(float(row["high"]) for row in opening_rows)
        opening_low = min(float(row["low"]) for row in opening_rows)
        buffer_value = 0.05 * atr
        session_id = f"{candidate.name}:{day_start}"
        if (
            trend == "LONG"
            and close > opening_high + buffer_value
            and buy_share >= candidate.flow_ratio
        ):
            return {
                "side": "LONG",
                "atr": atr,
                "extreme": opening_low,
                "session_id": session_id,
            }
        if (
            trend == "SHORT"
            and close < opening_low - buffer_value
            and sell_share >= candidate.flow_ratio
        ):
            return {
                "side": "SHORT",
                "atr": atr,
                "extreme": opening_high,
                "session_id": session_id,
            }
        return None

    if candidate.family == "EXPANSION":
        atr_mean = indicators["atr_mean"][index - 1]
        if not atr_mean or atr / atr_mean > candidate.compression_max:
            return None
        if body < candidate.body_or_wick_ratio or volume_ratio < candidate.volume_ratio:
            return None
        buffer_value = 0.05 * atr
        if (
            trend == "LONG"
            and close > prior_high + buffer_value
            and buy_share >= candidate.flow_ratio
        ):
            return {"side": "LONG", "atr": atr, "extreme": float(candle["low"])}
        if (
            trend == "SHORT"
            and close < prior_low - buffer_value
            and sell_share >= candidate.flow_ratio
        ):
            return {"side": "SHORT", "atr": atr, "extreme": float(candle["high"])}
        return None

    range_gap = abs(
        float(indicators["ema_fast"][index]) - float(indicators["ema_slow"][index])
    ) / close

    if candidate.family in ("FAILED_EXPANSION", "JUMP_REVERSAL"):
        expansion = candles[index - 1]
        confirmation = candle
        expansion_atr = indicators["atr"][index - 1]
        expansion_volume_mean = indicators["volume_mean"][index - 2]
        ema_fast = indicators["ema_fast"][index - 1]
        if not expansion_atr or not expansion_volume_mean or ema_fast is None:
            return None
        exp_body, _, _, exp_close_location = candle_shape(expansion)
        confirm_body, _, _, _ = candle_shape(confirmation)
        exp_volume = float(expansion["volume"])
        exp_volume_ratio = exp_volume / expansion_volume_mean
        exp_buy_share = float(expansion.get("taker_buy", 0) or 0) / exp_volume if exp_volume > 0 else 0.5
        exp_sell_share = 1.0 - exp_buy_share
        confirm_volume = float(confirmation["volume"])
        confirm_buy_share = (
            float(confirmation.get("taker_buy", 0) or 0) / confirm_volume
            if confirm_volume > 0 else 0.5
        )
        confirm_sell_share = 1.0 - confirm_buy_share
        exp_open = float(expansion["open"])
        exp_close = float(expansion["close"])
        exp_high = float(expansion["high"])
        exp_low = float(expansion["low"])
        exp_mid = (exp_open + exp_close) / 2.0
        prior_two_stage = candles[index - 1 - candidate.lookback:index - 1]
        two_stage_high = max(float(row["high"]) for row in prior_two_stage)
        two_stage_low = min(float(row["low"]) for row in prior_two_stage)
        confirm_open = float(confirmation["open"])

        if candidate.family == "FAILED_EXPANSION":
            if candidate.regime == "RANGE" and range_gap > 0.015:
                return None
            up_failure = (
                exp_close > two_stage_high + 0.05 * expansion_atr
                and exp_body >= candidate.body_or_wick_ratio
                and exp_volume_ratio >= candidate.volume_ratio
                and exp_buy_share >= candidate.flow_ratio
                and close < two_stage_high
                and close < exp_mid
                and close < confirm_open
                and confirm_body >= 0.35
                and confirm_sell_share >= 0.52
            )
            down_failure = (
                exp_close < two_stage_low - 0.05 * expansion_atr
                and exp_body >= candidate.body_or_wick_ratio
                and exp_volume_ratio >= candidate.volume_ratio
                and exp_sell_share >= candidate.flow_ratio
                and close > two_stage_low
                and close > exp_mid
                and close > confirm_open
                and confirm_body >= 0.35
                and confirm_buy_share >= 0.52
            )
            if up_failure:
                return {"side": "SHORT", "atr": expansion_atr, "extreme": exp_high}
            if down_failure:
                return {"side": "LONG", "atr": expansion_atr, "extreme": exp_low}
            return None

        expansion_range = exp_high - exp_low
        extended = abs(exp_close - float(ema_fast)) >= 1.5 * expansion_atr
        up_jump = (
            exp_close > exp_open
            and exp_body >= candidate.body_or_wick_ratio
            and expansion_range >= 2.0 * expansion_atr
            and exp_volume_ratio >= candidate.volume_ratio
            and exp_buy_share >= candidate.flow_ratio
            and exp_close_location >= 0.80
            and close < exp_mid
            and close < confirm_open
            and confirm_sell_share >= 0.52
        )
        down_jump = (
            exp_close < exp_open
            and exp_body >= candidate.body_or_wick_ratio
            and expansion_range >= 2.0 * expansion_atr
            and exp_volume_ratio >= candidate.volume_ratio
            and exp_sell_share >= candidate.flow_ratio
            and exp_close_location <= 0.20
            and close > exp_mid
            and close > confirm_open
            and confirm_buy_share >= 0.52
        )
        if extended and up_jump:
            return {"side": "SHORT", "atr": expansion_atr, "extreme": exp_high}
        if extended and down_jump:
            return {"side": "LONG", "atr": expansion_atr, "extreme": exp_low}
        return None

    if candidate.regime == "RANGE" and range_gap > 0.015:
        return None
    if volume_ratio < candidate.volume_ratio:
        return None
    sweep_buffer = 0.05 * atr
    long_reclaim = (
        float(candle["low"]) < prior_low - sweep_buffer
        and close > prior_low
        and lower_wick >= candidate.body_or_wick_ratio
        and close_location >= 0.60
        and sell_share >= candidate.flow_ratio
    )
    short_reclaim = (
        float(candle["high"]) > prior_high + sweep_buffer
        and close < prior_high
        and upper_wick >= candidate.body_or_wick_ratio
        and close_location <= 0.40
        and buy_share >= candidate.flow_ratio
    )
    if long_reclaim and (candidate.regime != "TREND" or trend == "LONG"):
        return {"side": "LONG", "atr": atr, "extreme": float(candle["low"])}
    if short_reclaim and (candidate.regime != "TREND" or trend == "SHORT"):
        return {"side": "SHORT", "atr": atr, "extreme": float(candle["high"])}
    return None


def simulate_trade(candles: list[dict], signal_index: int, signal: dict, candidate: Candidate):
    entry_index = signal_index + 1
    if entry_index >= len(candles):
        return None
    entry = float(candles[entry_index]["open"])
    atr = float(signal["atr"])
    side = signal["side"]
    if candidate.family == "EXPANSION":
        if side == "LONG":
            stop = min(float(signal["extreme"]) - 0.10 * atr, entry - candidate.stop_atr * atr)
        else:
            stop = max(float(signal["extreme"]) + 0.10 * atr, entry + candidate.stop_atr * atr)
    else:
        stop = (
            float(signal["extreme"]) - candidate.stop_atr * atr
            if side == "LONG"
            else float(signal["extreme"]) + candidate.stop_atr * atr
        )
    risk = abs(entry - stop)
    minimum_risk = entry * candidate.min_risk_pct
    if risk < minimum_risk:
        stop = entry - minimum_risk if side == "LONG" else entry + minimum_risk
        risk = minimum_risk
    risk_pct = risk / entry if entry > 0 else 0.0
    if risk <= 0 or risk_pct < candidate.min_risk_pct or risk_pct > 0.02:
        return None
    if (side == "LONG" and entry <= stop) or (side == "SHORT" and entry >= stop):
        return None
    target = entry + candidate.target_r * risk if side == "LONG" else entry - candidate.target_r * risk
    final_index = min(len(candles) - 1, entry_index + candidate.max_hold_bars - 1)
    exit_price = float(candles[final_index]["close"])
    exit_reason = "TIMEOUT"
    exit_index = final_index
    gross_r = ((exit_price - entry) / risk) if side == "LONG" else ((entry - exit_price) / risk)
    for index in range(entry_index, final_index + 1):
        candle = candles[index]
        hit_stop = float(candle["low"]) <= stop if side == "LONG" else float(candle["high"]) >= stop
        hit_target = float(candle["high"]) >= target if side == "LONG" else float(candle["low"]) <= target
        if hit_stop:
            exit_price = stop
            exit_reason = "STOP"
            exit_index = index
            gross_r = -1.0
            break
        if hit_target:
            exit_price = target
            exit_reason = "TARGET"
            exit_index = index
            gross_r = candidate.target_r
            break
    return {
        "side": side,
        "signal_time": int(candles[signal_index]["open_time"]),
        "entry_time": int(candles[entry_index]["open_time"]),
        "exit_time": int(candles[exit_index]["close_time"]),
        "entry": entry,
        "stop": stop,
        "target": target,
        "risk_pct": risk_pct,
        "gross_r": gross_r,
        "baseline_net_r": gross_r - BASELINE_COST_PCT / risk_pct,
        "stress_net_r": gross_r - STRESS_COST_PCT / risk_pct,
        "exit_reason": exit_reason,
        "exit_index": exit_index,
        "exit_price": exit_price,
    }


def run_candidate(candles: list[dict], candidate: Candidate, start_ms: int, end_ms: int) -> list[dict]:
    indicators = prepare_indicators(candles)
    records = []
    next_available = 0
    used_sessions = set()
    for index in range(400, len(candles) - 1):
        timestamp = int(candles[index]["open_time"])
        if timestamp < start_ms or timestamp > end_ms or index < next_available:
            continue
        signal = detect_signal(candles, indicators, index, candidate)
        if not signal:
            continue
        if signal.get("session_id") in used_sessions:
            continue
        trade = simulate_trade(candles, index, signal, candidate)
        if trade:
            records.append(trade)
            next_available = int(trade["exit_index"]) + 1
            if signal.get("session_id"):
                used_sessions.add(signal["session_id"])
    return records


def max_drawdown(values: list[float]) -> float:
    equity = peak = drawdown = 0.0
    for value in values:
        equity += value
        peak = max(peak, equity)
        drawdown = max(drawdown, peak - equity)
    return drawdown


def performance(records: list[dict], key: str) -> dict:
    ordered = sorted(records, key=lambda row: row["entry_time"])
    values = [float(row[key]) for row in ordered]
    gains = sum(value for value in values if value > 0)
    losses = abs(sum(value for value in values if value < 0))
    return {
        "trades": len(values),
        "win_rate_pct": sum(1 for value in values if value > 0) / len(values) * 100 if values else 0.0,
        "total_r": sum(values),
        "avg_r": mean(values) if values else 0.0,
        "profit_factor": gains / losses if losses else (math.inf if gains else 0.0),
        "max_drawdown_r": max_drawdown(values),
    }


def summarize_candidate(records_by_symbol: dict[str, list[dict]]) -> dict:
    combined = []
    pair_metrics = {}
    month_totals = defaultdict(float)
    for symbol, records in records_by_symbol.items():
        combined.extend({**row, "symbol": symbol} for row in records)
        pair_metrics[symbol] = performance(records, "baseline_net_r")
        for row in records:
            month = datetime.fromtimestamp(row["entry_time"] / 1000, timezone.utc).strftime("%Y-%m")
            month_totals[month] += float(row["baseline_net_r"])
    combined.sort(key=lambda row: row["entry_time"])
    gross = performance(combined, "gross_r")
    baseline = performance(combined, "baseline_net_r")
    stress = performance(combined, "stress_net_r")
    positive_pairs = sum(1 for value in pair_metrics.values() if value["total_r"] > 0)
    positive_months = sum(1 for value in month_totals.values() if value > 0)
    month_ratio = positive_months / len(month_totals) if month_totals else 0.0
    checks = {
        "minimum_trades": baseline["trades"] >= 120,
        "baseline_positive": baseline["total_r"] > 0,
        "baseline_pf": baseline["profit_factor"] >= 1.15,
        "stress_positive": stress["total_r"] > 0,
        "stress_pf": stress["profit_factor"] >= 1.05,
        "pair_breadth": positive_pairs >= 2,
        "month_breadth": month_ratio >= 0.55,
        "max_drawdown": baseline["max_drawdown_r"] <= 20.0,
    }
    return {
        "gross": gross,
        "baseline": baseline,
        "stress": stress,
        "pairs": pair_metrics,
        "monthly_r": dict(sorted(month_totals.items())),
        "positive_pairs": positive_pairs,
        "positive_month_ratio": month_ratio,
        "exit_reasons": dict(Counter(row["exit_reason"] for row in combined)),
        "side_baseline": {
            side: performance(
                [row for row in combined if row["side"] == side],
                "baseline_net_r",
            )
            for side in ("LONG", "SHORT")
        },
        "median_risk_pct": median(
            [float(row["risk_pct"]) for row in combined]
        ) if combined else 0.0,
        "gate": {"passed": all(checks.values()), "checks": checks},
    }


def json_safe(value):
    if isinstance(value, dict):
        return {key: json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [json_safe(item) for item in value]
    if isinstance(value, float) and not math.isfinite(value):
        return "INF" if value > 0 else "-INF"
    return value


def period_bounds(stage: str, all_rows: dict[str, list[dict]]) -> tuple[int, int]:
    first = max(int(rows[0]["open_time"]) for rows in all_rows.values())
    last = min(int(rows[-1]["open_time"]) for rows in all_rows.values())
    if stage == "development":
        return first, min(DEVELOPMENT_END, last)
    if stage == "validation":
        return max(VALIDATION_START, first), min(VALIDATION_END, last)
    return max(HOLDOUT_START, first), last


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache-root", type=Path, default=Path(".audit/2026-07-22"))
    parser.add_argument("--stage", choices=("development", "validation", "holdout"), default="development")
    parser.add_argument("--candidate", choices=tuple(item.name for item in CANDIDATES))
    parser.add_argument("--output", required=True, type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.stage != "development" and not args.candidate:
        raise ValueError("--candidate is required for validation and holdout")
    candles = {symbol: load_symbol(args.cache_root, symbol) for symbol in SYMBOLS}
    start_ms, end_ms = period_bounds(args.stage, candles)
    candidates = [item for item in CANDIDATES if not args.candidate or item.name == args.candidate]
    results = {}
    for candidate in candidates:
        records_by_symbol = {
            symbol: run_candidate(rows, candidate, start_ms, end_ms)
            for symbol, rows in candles.items()
        }
        results[candidate.name] = {
            "parameters": asdict(candidate),
            "summary": summarize_candidate(records_by_symbol),
        }
    passed = [
        name for name, result in results.items()
        if result["summary"]["gate"]["passed"]
    ]
    selected = max(
        passed,
        key=lambda name: results[name]["summary"]["stress"]["total_r"],
        default=None,
    )
    payload = {
        "engine": "STRATEGY_E_SCALPING_RESEARCH_V1",
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
