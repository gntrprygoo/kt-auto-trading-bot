#!/usr/bin/env python3
"""Build point-in-time cross-market snapshots and sealed future outcomes."""

from __future__ import annotations

import argparse
from collections import defaultdict, deque
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import sys

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ai_market_scanner import SCANNER_SCHEMA, assert_snapshot_has_no_future_data
from tools.research_strategy_f_intraday import align_symbols, load_symbol


DATASET_SCHEMA = "KT_AI_MARKET_DATASET_V1"
FEATURE_SET = "OHLCV_TAKER_CROSS_MARKET_V1"
BAR_MS = 15 * 60 * 1000
HOUR_MS = 60 * 60 * 1000
BASELINE_COST_PCT = 0.0014
STRESS_COST_PCT = 0.0020
DEFAULT_SYMBOLS = ("BTCUSDT", "ETHUSDT", "SOLUSDT", "ADAUSDT", "DOGEUSDT", "XRPUSDT")


def feature_contract_sha256(contract: dict) -> str:
    if not isinstance(contract, dict) or not contract:
        raise ValueError("feature contract must be a non-empty object")
    return hashlib.sha256(
        json.dumps(contract, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def parse_utc(value: str, end_of_day: bool = False) -> int:
    text = str(value).strip()
    if len(text) == 10:
        text += "T23:59:59.999+00:00" if end_of_day else "T00:00:00+00:00"
    elif text.endswith("Z"):
        text = text[:-1] + "+00:00"
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return int(parsed.timestamp() * 1000)


def safe_number(value, digits: int = 8):
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number):
        return None
    return round(number, digits)


def ema(values: list[float], span: int) -> list[float]:
    if not values:
        return []
    alpha = 2.0 / (span + 1.0)
    result = [float(values[0])]
    for value in values[1:]:
        result.append(alpha * float(value) + (1.0 - alpha) * result[-1])
    return result


def rolling_sum(values: list[float], window: int) -> list[float | None]:
    result: list[float | None] = [None] * len(values)
    total = 0.0
    for index, value in enumerate(values):
        total += float(value)
        if index >= window:
            total -= float(values[index - window])
        if index + 1 >= window:
            result[index] = total
    return result


def rolling_mean(values: list[float], window: int) -> list[float | None]:
    sums = rolling_sum(values, window)
    return [None if value is None else value / window for value in sums]


def rolling_extreme(values: list[float], window: int, maximum: bool) -> list[float | None]:
    result: list[float | None] = [None] * len(values)
    queue: deque[int] = deque()
    for index, value in enumerate(values):
        while queue and queue[0] <= index - window:
            queue.popleft()
        while queue:
            previous = values[queue[-1]]
            if (maximum and previous >= value) or (not maximum and previous <= value):
                break
            queue.pop()
        queue.append(index)
        if index + 1 >= window:
            result[index] = float(values[queue[0]])
    return result


def point_return(closes: list[float], index: int, bars: int):
    if index < bars or closes[index - bars] <= 0:
        return None
    return closes[index] / closes[index - bars] - 1.0


def prepare_symbol(candles: list[dict]) -> dict:
    closes = [float(row["close"]) for row in candles]
    highs = [float(row["high"]) for row in candles]
    lows = [float(row["low"]) for row in candles]
    volumes = [float(row.get("volume", 0) or 0) for row in candles]
    buys = [float(row.get("taker_buy", 0) or 0) for row in candles]
    sells = [float(row.get("taker_sell", 0) or 0) for row in candles]
    true_ranges = []
    for index, row in enumerate(candles):
        previous = closes[index - 1] if index else float(row["open"])
        true_ranges.append(
            max(
                highs[index] - lows[index],
                abs(highs[index] - previous),
                abs(lows[index] - previous),
            )
        )
    return {
        "closes": closes,
        "highs": highs,
        "lows": lows,
        "volumes": volumes,
        "buys": buys,
        "sells": sells,
        "ema_fast": ema(closes, 48),
        "ema_slow": ema(closes, 192),
        "atr": rolling_mean(true_ranges, 56),
        "volume_1h": rolling_sum(volumes, 4),
        "volume_20h": rolling_sum(volumes, 80),
        "buy_1h": rolling_sum(buys, 4),
        "sell_1h": rolling_sum(sells, 4),
        "buy_4h": rolling_sum(buys, 16),
        "sell_4h": rolling_sum(sells, 16),
        "high_24h": rolling_extreme(highs, 96, True),
        "low_24h": rolling_extreme(lows, 96, False),
        "high_7d": rolling_extreme(highs, 672, True),
        "low_7d": rolling_extreme(lows, 672, False),
    }


def flow_ratio(buy, sell):
    if buy is None or sell is None or float(buy) + float(sell) <= 0:
        return None
    return (float(buy) - float(sell)) / (float(buy) + float(sell))


def range_position(close, low, high):
    if low is None or high is None or float(high) <= float(low):
        return None
    return (float(close) - float(low)) / (float(high) - float(low))


def hourly_sequence(feature: dict, index: int, periods: int = 8) -> dict:
    returns = []
    flows = []
    volumes = []
    for offset in range(periods - 1, -1, -1):
        point = index - 4 * offset
        returns.append(safe_number(point_return(feature["closes"], point, 4), 6))
        flows.append(safe_number(flow_ratio(feature["buy_1h"][point], feature["sell_1h"][point]), 5))
        current_volume = feature["volume_1h"][point]
        long_volume = feature["volume_20h"][point]
        ratio = (
            float(current_volume) / (float(long_volume) / 20.0)
            if current_volume is not None and long_volume and float(long_volume) > 0
            else None
        )
        volumes.append(safe_number(ratio, 4))
    return {
        "hourly_returns": returns,
        "hourly_taker_flow": flows,
        "hourly_volume_ratio": volumes,
    }


def market_features(symbol: str, candles: list[dict], feature: dict, index: int, btc: dict) -> dict:
    close = feature["closes"][index]
    fast = feature["ema_fast"][index]
    slow = feature["ema_slow"][index]
    atr = feature["atr"][index]
    volume_1h = feature["volume_1h"][index]
    volume_20h = feature["volume_20h"][index]
    volume_ratio = (
        float(volume_1h) / (float(volume_20h) / 20.0)
        if volume_1h is not None and volume_20h and float(volume_20h) > 0
        else None
    )
    candle = candles[index]
    candle_range = float(candle["high"]) - float(candle["low"])
    return_4h = point_return(feature["closes"], index, 16)
    btc_return_4h = point_return(btc["closes"], index, 16)
    return {
        "last_close": safe_number(close),
        "return_1h": safe_number(point_return(feature["closes"], index, 4), 6),
        "return_4h": safe_number(return_4h, 6),
        "return_12h": safe_number(point_return(feature["closes"], index, 48), 6),
        "return_24h": safe_number(point_return(feature["closes"], index, 96), 6),
        "relative_strength_vs_btc_4h": safe_number(
            None if return_4h is None or btc_return_4h is None else return_4h - btc_return_4h,
            6,
        ),
        "ema_fast_above_slow": bool(fast > slow),
        "ema_fast_distance_pct": safe_number((close - fast) / close if close > 0 else None, 6),
        "ema_spread_pct": safe_number((fast - slow) / close if close > 0 else None, 6),
        "atr_pct": safe_number(float(atr) / close if atr is not None and close > 0 else None, 6),
        "volume_ratio_1h": safe_number(volume_ratio, 4),
        "taker_flow_1h": safe_number(
            flow_ratio(feature["buy_1h"][index], feature["sell_1h"][index]), 5
        ),
        "taker_flow_4h": safe_number(
            flow_ratio(feature["buy_4h"][index], feature["sell_4h"][index]), 5
        ),
        "range_position_24h": safe_number(
            range_position(close, feature["low_24h"][index], feature["high_24h"][index]), 4
        ),
        "range_position_7d": safe_number(
            range_position(close, feature["low_7d"][index], feature["high_7d"][index]), 4
        ),
        "last_15m_direction": (
            "UP" if float(candle["close"]) > float(candle["open"]) else
            "DOWN" if float(candle["close"]) < float(candle["open"]) else "FLAT"
        ),
        "last_15m_body_ratio": safe_number(
            abs(float(candle["close"]) - float(candle["open"])) / candle_range
            if candle_range > 0 else 0,
            4,
        ),
        "last_15m_close_location": safe_number(
            (float(candle["close"]) - float(candle["low"])) / candle_range
            if candle_range > 0 else 0.5,
            4,
        ),
        **hourly_sequence(feature, index),
    }


def classify_bucket(btc_features: dict, decision_time_ms: int) -> str:
    return_24h = float(btc_features.get("return_24h") or 0)
    trend_up = bool(btc_features.get("ema_fast_above_slow"))
    if return_24h >= 0.015 and trend_up:
        regime = "UP"
    elif return_24h <= -0.015 and not trend_up:
        regime = "DOWN"
    else:
        regime = "RANGE"
    volatility = "HIGH_VOL" if float(btc_features.get("atr_pct") or 0) >= 0.006 else "NORMAL_VOL"
    month = datetime.fromtimestamp(decision_time_ms / 1000, timezone.utc).strftime("%Y-%m")
    return f"{month}|{regime}|{volatility}"


def simulate_outcome(
    candles: list[dict],
    signal_index: int,
    atr_pct: float,
    side: str,
    stop_atr: float,
    target_r: float,
    max_hold_bars: int,
    min_risk_pct: float,
    max_risk_pct: float,
) -> dict | None:
    entry_index = signal_index + 1
    if entry_index >= len(candles):
        return None
    entry = float(candles[entry_index]["open"])
    risk_pct = max(float(min_risk_pct), float(stop_atr) * float(atr_pct))
    if not math.isfinite(risk_pct) or risk_pct <= 0 or risk_pct > max_risk_pct:
        return None
    risk = entry * risk_pct
    stop = entry - risk if side == "LONG" else entry + risk
    target = entry + target_r * risk if side == "LONG" else entry - target_r * risk
    final_index = min(len(candles) - 1, entry_index + max_hold_bars - 1)
    exit_index = final_index
    exit_price = float(candles[final_index]["close"])
    reason = "TIMEOUT"
    gross_r = (exit_price - entry) / risk if side == "LONG" else (entry - exit_price) / risk
    for index in range(entry_index, final_index + 1):
        row = candles[index]
        hit_stop = float(row["low"]) <= stop if side == "LONG" else float(row["high"]) >= stop
        hit_target = float(row["high"]) >= target if side == "LONG" else float(row["low"]) <= target
        # Pessimistic same-bar handling: stop wins when both levels are touched.
        if hit_stop:
            exit_index = index
            exit_price = stop
            reason = "STOP"
            gross_r = -1.0
            break
        if hit_target:
            exit_index = index
            exit_price = target
            reason = "TARGET"
            gross_r = target_r
            break
    return {
        "entry_time": int(candles[entry_index]["open_time"]),
        "exit_time": int(candles[exit_index]["close_time"]),
        "entry": safe_number(entry),
        "stop": safe_number(stop),
        "target": safe_number(target),
        "risk_pct": safe_number(risk_pct, 8),
        "gross_r": safe_number(gross_r, 8),
        "baseline_net_r": safe_number(gross_r - BASELINE_COST_PCT / risk_pct, 8),
        "stress_net_r": safe_number(gross_r - STRESS_COST_PCT / risk_pct, 8),
        "exit_reason": reason,
        "exit_price": safe_number(exit_price),
    }


def stratified_sample(records: list[dict], maximum: int) -> list[dict]:
    if maximum <= 0 or len(records) <= maximum:
        return records
    groups: dict[str, list[dict]] = defaultdict(list)
    for record in records:
        groups[str(record["sample_bucket"])].append(record)
    for key in groups:
        groups[key].sort(
            key=lambda item: hashlib.sha256(item["snapshot"]["snapshot_id"].encode("utf-8")).hexdigest()
        )
    selected = []
    keys = sorted(groups)
    cursor = 0
    while len(selected) < maximum and keys:
        key = keys[cursor % len(keys)]
        group = groups[key]
        if group:
            selected.append(group.pop(0))
        if not group:
            keys.remove(key)
            if not keys:
                break
            cursor %= len(keys)
        else:
            cursor += 1
    return sorted(selected, key=lambda item: int(item["snapshot"]["decision_time_ms"]))


def build_dataset(args: argparse.Namespace) -> dict:
    symbols = tuple(str(item).upper() for item in args.symbols)
    if "BTCUSDT" not in symbols:
        raise ValueError("BTCUSDT must be present as market context")
    loaded = {
        symbol: load_symbol(Path(".__no_cache__"), symbol, args.market_cache)
        for symbol in symbols
    }
    aligned = align_symbols(loaded)
    features = {symbol: prepare_symbol(aligned[symbol]) for symbol in symbols}
    start_ms = parse_utc(args.start)
    end_ms = parse_utc(args.end, end_of_day=True)
    warmup = 700
    records = []
    btc_feature = features["BTCUSDT"]
    for index in range(warmup, len(aligned["BTCUSDT"]) - args.max_hold_bars - 1):
        row = aligned["BTCUSDT"][index]
        open_time = int(row["open_time"])
        if open_time < start_ms or open_time > end_ms:
            continue
        if open_time % HOUR_MS != 45 * 60 * 1000:
            continue
        decision_hour = (open_time + BAR_MS) // HOUR_MS
        if decision_hour % args.interval_hours != 0:
            continue
        decision_time = int(row.get("close_time") or (open_time + BAR_MS - 1))
        market = {
            symbol: market_features(
                symbol, aligned[symbol], features[symbol], index, btc_feature
            )
            for symbol in symbols
        }
        snapshot_id = "MS-" + hashlib.sha256(
            f"{SCANNER_SCHEMA}|{decision_time}|{'|'.join(symbols)}".encode("utf-8")
        ).hexdigest()[:18].upper()
        snapshot = {
            "schema": SCANNER_SCHEMA,
            "snapshot_id": snapshot_id,
            "decision_time_ms": decision_time,
            "decision_time_utc": datetime.fromtimestamp(
                decision_time / 1000, timezone.utc
            ).isoformat().replace("+00:00", "Z"),
            "universe": list(symbols),
            "market": market,
            "execution_contract": {
                "entry": "NEXT_15M_OPEN",
                "stop": f"MAX_{args.min_risk_pct:.4f}_OR_{args.stop_atr:.2f}_ATR",
                "target_r": args.target_r,
                "max_hold_hours": args.max_hold_bars / 4,
                "max_simultaneous_positions": 1,
                "model_must_not_size_or_set_geometry": True,
            },
        }
        assert_snapshot_has_no_future_data(snapshot)
        outcomes = {}
        for symbol in symbols:
            atr_pct = float(market[symbol].get("atr_pct") or 0)
            pair_outcomes = {}
            for side in ("LONG", "SHORT"):
                outcome = simulate_outcome(
                    aligned[symbol],
                    index,
                    atr_pct,
                    side,
                    args.stop_atr,
                    args.target_r,
                    args.max_hold_bars,
                    args.min_risk_pct,
                    args.max_risk_pct,
                )
                if outcome is not None:
                    pair_outcomes[side] = outcome
            outcomes[symbol] = pair_outcomes
        records.append(
            {
                "sample_bucket": classify_bucket(market["BTCUSDT"], decision_time),
                "snapshot": snapshot,
                "outcomes": outcomes,
            }
        )
    sampled = stratified_sample(records, args.max_snapshots)
    if not sampled:
        raise ValueError("no eligible market snapshots were generated")
    first_market = sampled[0]["snapshot"]["market"]
    first_symbol = sorted(first_market)[0]
    market_fields = sorted(first_market[first_symbol])
    for record in sampled:
        for symbol, values in record["snapshot"]["market"].items():
            if sorted(values) != market_fields:
                raise ValueError(f"inconsistent market feature fields for {symbol}")
    feature_contract = {
        "feature_set": FEATURE_SET,
        "snapshot_schema": SCANNER_SCHEMA,
        "symbols": list(symbols),
        "decision_interval": "1h_confirmed_close",
        "source_interval": "15m",
        "history_sequence_hours": 8,
        "market_fields": market_fields,
        "uses_only_confirmed_bars": True,
        "includes_open_interest": False,
        "includes_funding": False,
        "includes_order_book": False,
    }
    feature_contract_hash = feature_contract_sha256(feature_contract)
    return {
        "schema": DATASET_SCHEMA,
        "status": "RESEARCH_ONLY_NO_ORDERS",
        "stage": args.stage,
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "source": str(args.market_cache),
        "period": {"start": args.start, "end": args.end},
        "symbols": list(symbols),
        "feature_contract": feature_contract,
        "feature_contract_sha256": feature_contract_hash,
        "sampling": {
            "eligible_snapshots": len(records),
            "selected_snapshots": len(sampled),
            "method": "MONTH_REGIME_VOLATILITY_STRATIFIED_HASH_V1",
            "interval_hours": args.interval_hours,
            "outcome_independent": True,
        },
        "execution_model": {
            "entry": "NEXT_15M_OPEN",
            "stop_atr": args.stop_atr,
            "target_r": args.target_r,
            "max_hold_bars_15m": args.max_hold_bars,
            "min_risk_pct": args.min_risk_pct,
            "max_risk_pct": args.max_risk_pct,
            "baseline_cost_pct": BASELINE_COST_PCT,
            "stress_cost_pct": STRESS_COST_PCT,
            "same_bar_policy": "STOP_FIRST",
        },
        "records": sampled,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--market-cache", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--stage", choices=("development", "validation"), required=True)
    parser.add_argument("--start", required=True)
    parser.add_argument("--end", required=True)
    parser.add_argument("--symbols", nargs="+", default=list(DEFAULT_SYMBOLS))
    parser.add_argument("--interval-hours", type=int, default=1)
    parser.add_argument("--max-snapshots", type=int, default=240)
    parser.add_argument("--stop-atr", type=float, default=1.5)
    parser.add_argument("--target-r", type=float, default=2.0)
    parser.add_argument("--max-hold-bars", type=int, default=48)
    parser.add_argument("--min-risk-pct", type=float, default=0.0075)
    parser.add_argument("--max-risk-pct", type=float, default=0.03)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    result = build_dataset(args)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "stage": result["stage"],
                "eligible": result["sampling"]["eligible_snapshots"],
                "selected": result["sampling"]["selected_snapshots"],
                "output": str(args.output),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
