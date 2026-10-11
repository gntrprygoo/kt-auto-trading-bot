import argparse
import bisect
import json
import pathlib
import statistics
from collections import Counter
from dataclasses import asdict, dataclass

import research_strategy_bc_v2 as common
import strategy_evidence_audit as audit


MS_HOUR = 60 * 60 * 1000
MS_DAY = 24 * MS_HOUR


@dataclass(frozen=True)
class B4Variant:
    name: str
    side_mode: str
    channel_lookback: int
    min_level_age: int
    breakout_buffer_atr: float
    max_break_distance_atr: float
    breakout_range_atr_min: float
    breakout_range_atr_max: float
    breakout_body_min: float
    breakout_close_position_min: float
    breakout_volume_min: float
    breakout_flow_min: float
    max_ema_distance_atr: float
    retest_hours: int
    retest_tolerance_atr: float
    retest_max_penetration_atr: float
    retest_max_distance_atr: float
    retest_volume_max: float
    confirmation_bars: int
    confirmation_body_min: float
    confirmation_flow_min: float
    max_entry_distance_atr: float
    confirmation_mode: str


# These candidates are frozen before the untouched stress period is loaded.
# Only the LONG variants are eligible for promotion. The short variant is an
# explicit diagnostic after the prior B3 audit found severe downside asymmetry.
B4_VARIANTS = (
    B4Variant(
        "B4_RECLAIM_LONG", "LONG", 42, 4, 0.12, 1.20, 0.50, 2.50,
        0.50, 0.65, 0.80, 0.50, 3.00, 24, 0.30, 0.60, 0.90,
        1.50, 8, 0.35, 0.50, 1.30, "LEVEL_RECLAIM",
    ),
    B4Variant(
        "B4_RECLAIM_NEIGHBOR_LONG", "LONG", 48, 5, 0.15, 1.00, 0.60, 2.30,
        0.55, 0.70, 1.00, 0.51, 2.50, 24, 0.25, 0.50, 0.80,
        1.25, 6, 0.40, 0.51, 1.10, "LEVEL_RECLAIM",
    ),
    B4Variant(
        "B4_RETEST_CLOSE_LONG", "LONG", 42, 4, 0.12, 1.20, 0.50, 2.50,
        0.50, 0.65, 0.80, 0.50, 3.00, 24, 0.30, 0.60, 0.90,
        1.50, 0, 0.00, 0.00, 1.30, "RETEST_CLOSE",
    ),
    B4Variant(
        "B4_RETEST_CLOSE_NEIGHBOR_LONG", "LONG", 36, 3, 0.10, 1.30, 0.45, 2.70,
        0.48, 0.63, 0.75, 0.49, 3.25, 28, 0.35, 0.65, 1.00,
        1.60, 0, 0.00, 0.00, 1.45, "RETEST_CLOSE",
    ),
    B4Variant(
        "B4_PRICE_RECLAIM_LONG", "LONG", 42, 4, 0.12, 1.20, 0.50, 2.50,
        0.50, 0.65, 0.00, 0.00, 3.00, 24, 0.30, 0.60, 0.90,
        99.00, 8, 0.35, 0.00, 1.30, "LEVEL_RECLAIM",
    ),
    B4Variant(
        "B4_RECLAIM_SHORT_DIAGNOSTIC", "SHORT", 42, 4, 0.12, 1.20, 0.50, 2.50,
        0.50, 0.65, 0.80, 0.50, 3.00, 24, 0.30, 0.60, 0.90,
        1.50, 8, 0.35, 0.50, 1.30, "LEVEL_RECLAIM",
    ),
)


def read_json(path):
    with pathlib.Path(path).open("r", encoding="utf-8-sig") as handle:
        return json.load(handle)


def write_json(path, value):
    path = pathlib.Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(value, handle, ensure_ascii=True, indent=2)
        handle.write("\n")


def median_volume(candles, lookback=20):
    sample = candles[-lookback:]
    values = [float(candle.get("volume", 0.0)) for candle in sample]
    values = [value for value in values if value > 0]
    return statistics.median(values) if values else None


def prior_atr(candles, index, lookback=30):
    return common.atr_value(candles[max(0, index - lookback):index])


def advance_past_live_trade(index, record):
    return max(index, int(record["exit_index_live"]))


def donchian_level(history, side, lookback):
    if len(history) < lookback:
        return None
    window = history[-lookback:]
    field = "high" if side == "LONG" else "low"
    values = [float(candle[field]) for candle in window]
    level = max(values) if side == "LONG" else min(values)
    last_index = max(index for index, value in enumerate(values) if value == level)
    age = len(window) - 1 - last_index
    return {"level": level, "age": age, "source_time": int(window[last_index]["open_time"])}


def evaluate_b4_breakout(closed_4h, variant):
    minimum = max(70, variant.channel_lookback + 20)
    if len(closed_4h) < minimum:
        return None, "insufficient_history"
    breakout = closed_4h[-1]
    history = closed_4h[:-1]
    context = common.trend_context(history[-199:])
    if not context or context["side"] != variant.side_mode:
        return None, "trend_mismatch"
    side = variant.side_mode
    channel = donchian_level(history, side, variant.channel_lookback)
    atr_4h = common.atr_value(history)
    volume_baseline = median_volume(history, 20)
    if not channel or not atr_4h or atr_4h <= 0 or not volume_baseline:
        return None, "missing_baseline"
    if channel["age"] < variant.min_level_age:
        return None, "level_too_recent"

    level = channel["level"]
    close = float(breakout["close"])
    candle_range = float(breakout["high"]) - float(breakout["low"])
    range_atr = candle_range / atr_4h
    metrics = common.candle_metrics(breakout, side)
    volume_ratio = float(breakout.get("volume", 0.0)) / volume_baseline
    flow_ratio = common.directional_flow_ratio([breakout], side)
    ema_distance_atr = abs(close - float(context["fast"])) / atr_4h
    break_distance_atr = (
        (close - level) / atr_4h
        if side == "LONG"
        else (level - close) / atr_4h
    )
    price_break = (
        close > level + variant.breakout_buffer_atr * atr_4h
        if side == "LONG"
        else close < level - variant.breakout_buffer_atr * atr_4h
    )
    checks = (
        (price_break, "no_price_break"),
        (break_distance_atr <= variant.max_break_distance_atr, "break_too_extended"),
        (
            variant.breakout_range_atr_min <= range_atr <= variant.breakout_range_atr_max,
            "breakout_range_rejected",
        ),
        (metrics["direction_ok"], "wrong_candle_direction"),
        (metrics["body_ratio"] >= variant.breakout_body_min, "breakout_body_weak"),
        (
            metrics["close_position"] >= variant.breakout_close_position_min,
            "breakout_close_weak",
        ),
        (volume_ratio >= variant.breakout_volume_min, "breakout_volume_weak"),
        (flow_ratio >= variant.breakout_flow_min, "breakout_flow_weak"),
        (ema_distance_atr <= variant.max_ema_distance_atr, "ema_too_extended"),
    )
    for passed, reason in checks:
        if not passed:
            return None, reason
    detected_time = int(breakout["close_time"])
    return {
        "side": side,
        "level": level,
        "level_age_4h": channel["age"],
        "level_source_time": channel["source_time"],
        "detected_time": detected_time,
        "expires_time": detected_time + variant.retest_hours * MS_HOUR,
        "atr_4h": atr_4h,
        "breakout_extreme": float(breakout["low"] if side == "LONG" else breakout["high"]),
        "break_distance_atr": break_distance_atr,
        "breakout_range_atr": range_atr,
        "breakout_volume_ratio": volume_ratio,
        "breakout_flow_ratio": flow_ratio,
        "ema_distance_atr": ema_distance_atr,
    }, "detected"


def detect_b4_breakout(closed_4h, variant):
    setup, _ = evaluate_b4_breakout(closed_4h, variant)
    return setup


def evaluate_first_retest(candle, previous_candles, pending, atr_15m, variant):
    side = pending["side"]
    level = float(pending["level"])
    tolerance = variant.retest_tolerance_atr * atr_15m
    touched = (
        float(candle["low"]) <= level + tolerance
        if side == "LONG"
        else float(candle["high"]) >= level - tolerance
    )
    if not touched:
        return None
    close = float(candle["close"])
    extreme = float(candle["low"] if side == "LONG" else candle["high"])
    penetration = (
        max(0.0, level - extreme) / atr_15m
        if side == "LONG"
        else max(0.0, extreme - level) / atr_15m
    )
    held = (
        close >= level - 0.20 * atr_15m
        if side == "LONG"
        else close <= level + 0.20 * atr_15m
    )
    distance = abs(close - level) / atr_15m
    metrics = common.candle_metrics(candle, side)
    volume_baseline = median_volume(previous_candles, 20)
    volume_ratio = (
        float(candle.get("volume", 0.0)) / volume_baseline
        if volume_baseline
        else 99.0
    )
    checks = (
        (penetration <= variant.retest_max_penetration_atr, "deep_penetration"),
        (held, "level_failed"),
        (distance <= variant.retest_max_distance_atr, "close_too_extended"),
        (volume_ratio <= variant.retest_volume_max, "retest_volume_high"),
    )
    reason = "valid"
    for passed, failed_reason in checks:
        if not passed:
            reason = failed_reason
            break
    valid = reason == "valid"
    return {
        "valid": valid,
        "reason": reason,
        "high": float(candle["high"]),
        "low": float(candle["low"]),
        "extreme": extreme,
        "penetration_atr": penetration,
        "distance_atr": distance,
        "volume_ratio": volume_ratio,
        "close_position": metrics["close_position"],
        "wick_ratio": metrics["wick_ratio"],
    }


def confirm_retest(candle, retest, pending, atr_15m, variant):
    side = pending["side"]
    close = float(candle["close"])
    if variant.confirmation_mode == "LEVEL_RECLAIM":
        confirmed = (
            close > float(pending["level"]) + 0.05 * atr_15m
            if side == "LONG"
            else close < float(pending["level"]) - 0.05 * atr_15m
        )
    else:
        confirmed = close > retest["high"] if side == "LONG" else close < retest["low"]
    reclaimed = close > float(pending["level"]) if side == "LONG" else close < float(pending["level"])
    metrics = common.candle_metrics(candle, side)
    flow_ratio = common.directional_flow_ratio([candle], side)
    entry_distance_atr = abs(close - float(pending["level"])) / atr_15m
    checks = (
        (confirmed, "no_structure_break"),
        (reclaimed, "level_not_reclaimed"),
        (metrics["direction_ok"], "wrong_direction"),
        (metrics["body_ratio"] >= variant.confirmation_body_min, "body_weak"),
        (metrics["close_position"] >= 0.65, "close_weak"),
        (flow_ratio >= variant.confirmation_flow_min, "flow_weak"),
        (entry_distance_atr <= variant.max_entry_distance_atr, "entry_extended"),
    )
    reason = "valid"
    for passed, failed_reason in checks:
        if not passed:
            reason = failed_reason
            break
    valid = reason == "valid"
    return {
        "valid": valid,
        "reason": reason,
        "flow_ratio": flow_ratio,
        "body_ratio": metrics["body_ratio"],
        "close_position": metrics["close_position"],
        "entry_distance_atr": entry_distance_atr,
    }


def simulate_live_management(
    candles,
    signal_index,
    side,
    stop,
    cost_pct,
    horizon_bars=384,
    tp1_fraction=0.50,
    profit_trigger_pct=0.015,
    profit_lock_pct=0.010,
):
    entry_index = signal_index + 1
    if entry_index >= len(candles):
        return None
    entry = float(candles[entry_index]["open"])
    risk = entry - stop if side == "LONG" else stop - entry
    if entry <= 0 or risk <= 0:
        return None
    risk_pct = risk / entry
    if not 0.004 <= risk_pct <= 0.03:
        return None
    tp1 = entry + risk if side == "LONG" else entry - risk
    tp2 = entry + 2.0 * risk if side == "LONG" else entry - 2.0 * risk
    trigger = (
        entry * (1.0 + profit_trigger_pct)
        if side == "LONG"
        else entry * (1.0 - profit_trigger_pct)
    )
    lock = (
        entry * (1.0 + profit_lock_pct)
        if side == "LONG"
        else entry * (1.0 - profit_lock_pct)
    )
    active_stop = stop
    remaining = 1.0
    gross_r = 0.0
    tp1_hit = False
    sl_plus_active = False
    outcome = "TIMEOUT"
    end = min(len(candles), entry_index + horizon_bars)
    exit_index = end - 1
    exit_time = int(candles[exit_index]["close_time"])

    for index in range(entry_index, end):
        candle = candles[index]
        stop_hit = (
            float(candle["low"]) <= active_stop
            if side == "LONG"
            else float(candle["high"]) >= active_stop
        )
        # Conservative bar ordering: an already-active stop wins over any target
        # touched in the same candle.
        if stop_hit:
            stop_r = (
                (active_stop - entry) / risk
                if side == "LONG"
                else (entry - active_stop) / risk
            )
            gross_r += remaining * stop_r
            remaining = 0.0
            outcome = "SL_PLUS" if sl_plus_active else "SL"
            exit_index = index
            exit_time = int(candle["close_time"])
            break

        tp2_hit = (
            float(candle["high"]) >= tp2
            if side == "LONG"
            else float(candle["low"]) <= tp2
        )
        tp1_touched = (
            float(candle["high"]) >= tp1
            if side == "LONG"
            else float(candle["low"]) <= tp1
        )
        trigger_touched = (
            float(candle["high"]) >= trigger
            if side == "LONG"
            else float(candle["low"]) <= trigger
        )
        lock_reached = (
            float(candle["high"]) >= lock
            if side == "LONG"
            else float(candle["low"]) <= lock
        )

        if tp2_hit:
            if not tp1_hit:
                gross_r += tp1_fraction
                remaining -= tp1_fraction
                tp1_hit = True
            gross_r += remaining * 2.0
            remaining = 0.0
            outcome = "TP2"
            exit_index = index
            exit_time = int(candle["close_time"])
            break
        if tp1_touched and not tp1_hit:
            gross_r += tp1_fraction
            remaining -= tp1_fraction
            tp1_hit = True
        if trigger_touched or (tp1_hit and lock_reached):
            active_stop = max(active_stop, lock) if side == "LONG" else min(active_stop, lock)
            sl_plus_active = True
    else:
        final_close = float(candles[end - 1]["close"])
        mark_r = (
            (final_close - entry) / risk
            if side == "LONG"
            else (entry - final_close) / risk
        )
        gross_r += remaining * max(-1.0, min(2.0, mark_r))

    cost_r = cost_pct / risk_pct
    return {
        "entry": entry,
        "stop": stop,
        "tp1": tp1,
        "tp2": tp2,
        "risk_pct": risk_pct,
        "gross_R_live": gross_r,
        "cost_R_live": cost_r,
        "net_R_live": gross_r - cost_r,
        "outcome_live": outcome,
        "exit_time_live": exit_time,
        "exit_index_live": exit_index,
    }


def attach_b4_trade(
    pair,
    candles_15m,
    signal_index,
    signal_time,
    pending,
    retest,
    confirmation,
    variant,
    cost_pct,
):
    side = pending["side"]
    level = float(pending["level"])
    stop = (
        min(retest["extreme"] - 0.10 * retest["atr"], level - 0.25 * retest["atr"])
        if side == "LONG"
        else max(retest["extreme"] + 0.10 * retest["atr"], level + 0.25 * retest["atr"])
    )
    outcomes = common.attach_outcomes(
        candles_15m,
        signal_index,
        {"side": side, "stop": stop},
        cost_pct,
    )
    if not outcomes:
        return None
    live = simulate_live_management(
        candles_15m,
        signal_index,
        side,
        stop,
        cost_pct,
    )
    if not live:
        return None
    return {
        "strategy": variant.name,
        "pair": pair,
        "side": side,
        "signal_time": signal_time,
        "level": level,
        "level_age_4h": pending["level_age_4h"],
        "level_source_time": pending["level_source_time"],
        "break_distance_atr": pending["break_distance_atr"],
        "breakout_range_atr": pending["breakout_range_atr"],
        "breakout_volume_ratio": pending["breakout_volume_ratio"],
        "breakout_flow_ratio": pending["breakout_flow_ratio"],
        "ema_distance_atr": pending["ema_distance_atr"],
        "btc_return_12h": pending["btc_return_12h"],
        "retest_penetration_atr": retest["penetration_atr"],
        "retest_volume_ratio": retest["volume_ratio"],
        "confirmation_mode": variant.confirmation_mode,
        "confirmation_bars": signal_index - retest["index"],
        "confirmation_flow_ratio": confirmation["flow_ratio"],
        "confirmation_body_ratio": confirmation["body_ratio"],
        "entry_distance_atr": confirmation["entry_distance_atr"],
        "stop": stop,
        **outcomes,
        **live,
    }


def simulate_b4(
    pair,
    candles_15m,
    candles_4h,
    btc_candles_4h,
    start_ms,
    end_ms,
    variant,
    cost_pct,
):
    close_times_15m = [int(candle["close_time"]) for candle in candles_15m]
    close_times_4h = [int(candle["close_time"]) for candle in candles_4h]
    btc_close_times = [int(candle["close_time"]) for candle in btc_candles_4h]
    records = []
    stages = Counter()
    pending = None
    retest = None
    last_4h_count = None
    index = max(60, bisect.bisect_left(close_times_15m, start_ms))
    while index < len(candles_15m) - 1:
        candle = candles_15m[index]
        signal_time = int(candle["close_time"])
        if signal_time > end_ms:
            break
        end_4h = bisect.bisect_right(close_times_4h, signal_time)
        if end_4h >= 70 and end_4h != last_4h_count:
            stages["4h_evaluated"] += 1
            candidate, reason = evaluate_b4_breakout(candles_4h[:end_4h], variant)
            stages[f"breakout_{reason}"] += 1
            if candidate and pending is None:
                stages["breakout_detected_while_idle"] += 1
                btc_end = bisect.bisect_right(btc_close_times, candidate["detected_time"])
                market = common.btc_market_guard(
                    candidate["side"],
                    btc_candles_4h[:btc_end],
                )
                if market["passed"]:
                    stages["btc_guard_passed"] += 1
                    candidate["btc_return_12h"] = market["return_12h"]
                    pending = candidate
                    retest = None
                else:
                    stages["btc_guard_blocked"] += 1
            last_4h_count = end_4h
        if not pending or signal_time <= pending["detected_time"]:
            index += 1
            continue
        if signal_time > pending["expires_time"]:
            stages["pending_expired"] += 1
            pending = None
            retest = None
            index += 1
            continue

        atr_15m = prior_atr(candles_15m, index)
        if not atr_15m:
            index += 1
            continue
        side = pending["side"]
        level = float(pending["level"])
        close = float(candle["close"])
        invalid_close = (
            close < level - 0.35 * atr_15m
            if side == "LONG"
            else close > level + 0.35 * atr_15m
        )
        if invalid_close:
            stages["pending_invalid_close"] += 1
            pending = None
            retest = None
            index += 1
            continue

        if retest is None:
            evaluated = evaluate_first_retest(
                candle,
                candles_15m[max(0, index - 20):index],
                pending,
                atr_15m,
                variant,
            )
            if evaluated is None:
                index += 1
                continue
            stages["first_retest_touched"] += 1
            if not evaluated["valid"]:
                stages["first_retest_rejected"] += 1
                stages[f"first_retest_rejected_{evaluated['reason']}"] += 1
                pending = None
                index += 1
                continue
            stages["first_retest_valid"] += 1
            retest = {**evaluated, "index": index, "atr": atr_15m}
            if variant.confirmation_mode == "RETEST_CLOSE":
                metrics = common.candle_metrics(candle, side)
                confirmation = {
                    "flow_ratio": common.directional_flow_ratio([candle], side),
                    "body_ratio": metrics["body_ratio"],
                    "entry_distance_atr": abs(close - level) / atr_15m,
                }
                record = attach_b4_trade(
                    pair,
                    candles_15m,
                    index,
                    signal_time,
                    pending,
                    retest,
                    confirmation,
                    variant,
                    cost_pct,
                )
                if record:
                    stages["outcome_attached"] += 1
                    stages["retest_close_entry"] += 1
                    records.append(record)
                    index = advance_past_live_trade(index, record)
                pending = None
                retest = None
            index += 1
            continue

        age = index - retest["index"]
        if age > variant.confirmation_bars:
            stages["confirmation_window_failed"] += 1
            pending = None
            retest = None
            index += 1
            continue
        retest["extreme"] = (
            min(retest["extreme"], float(candle["low"]))
            if side == "LONG"
            else max(retest["extreme"], float(candle["high"]))
        )
        confirmation = confirm_retest(candle, retest, pending, atr_15m, variant)
        if not confirmation["valid"]:
            stages[f"confirmation_rejected_{confirmation['reason']}"] += 1
            index += 1
            continue
        stages["confirmation_valid"] += 1
        record = attach_b4_trade(
            pair,
            candles_15m,
            index,
            signal_time,
            pending,
            retest,
            confirmation,
            variant,
            cost_pct,
        )
        if record:
            stages["outcome_attached"] += 1
            records.append(record)
            index = advance_past_live_trade(index, record)
        pending = None
        retest = None
        index += 1
    return records, stages


def main():
    parser = argparse.ArgumentParser(description="Leakage-safe Strategy B4 breakout-retest research")
    parser.add_argument("--pairs-file", required=True)
    parser.add_argument("--cache-dir", required=True)
    parser.add_argument("--start", required=True)
    parser.add_argument("--end", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--max-pairs", type=int, default=30)
    parser.add_argument("--cost-pct", type=float, default=0.0014)
    args = parser.parse_args()

    start_ms = audit.parse_timestamp(args.start)
    end_ms = audit.parse_timestamp(args.end)
    pairs = read_json(args.pairs_file).get("pairs", [])[:args.max_pairs]
    market = audit.MarketData(args.cache_dir)
    data = {}
    errors = []
    for number, pair in enumerate(pairs, 1):
        print(f"load {number}/{len(pairs)} {pair}", flush=True)
        try:
            data[pair] = {
                "15m": market.klines(pair, "15m", start_ms - 4 * MS_DAY, end_ms + 5 * MS_DAY),
                "4h": market.klines(pair, "4h", start_ms - 60 * MS_DAY, end_ms + 4 * MS_HOUR),
            }
        except Exception as exc:
            errors.append(f"{pair}: {type(exc).__name__}: {exc}")

    btc_4h = data.get("BTCUSDT", {}).get("4h", [])
    result = {
        "engine": "B4_DONCHIAN_FIRST_RETEST_RESEARCH",
        "period": {"start": args.start, "end": args.end},
        "pair_count_requested": len(pairs),
        "pair_count_loaded": len(data),
        "cost_model": {
            "round_trip_fee_plus_slippage_pct": args.cost_pct,
            "entry": "next_15m_open",
            "same_candle_sl_tp": "loss",
            "timeout": "mark_to_market_at_96h",
        },
        "strategy_b": {},
        "errors": errors,
    }
    for variant in B4_VARIANTS:
        print(f"simulate {variant.name}", flush=True)
        records = []
        stages = Counter()
        for pair, candles in data.items():
            pair_records, pair_stages = simulate_b4(
                pair,
                candles["15m"],
                candles["4h"],
                btc_4h,
                start_ms,
                end_ms,
                variant,
                args.cost_pct,
            )
            records.extend(pair_records)
            stages.update(pair_stages)
        report = common.variant_report(records, start_ms, end_ms)
        report["LIVE_MANAGEMENT"] = {
            "overall": common.summarize(records, "net_R_live"),
            "long": common.summarize(
                [record for record in records if record["side"] == "LONG"],
                "net_R_live",
            ),
            "short": common.summarize(
                [record for record in records if record["side"] == "SHORT"],
                "net_R_live",
            ),
            "folds_30d": common.fold_summaries(
                records,
                "net_R_live",
                start_ms,
                end_ms,
            ),
        }
        report["parameters"] = asdict(variant)
        report["diagnostics"] = dict(sorted(stages.items()))
        result["strategy_b"][variant.name] = report

    write_json(args.output, result)
    concise = {
        name: {
            "1_5R": report["1_5R"]["overall"],
            "2R": report["2R"]["overall"],
            "LIVE_MANAGEMENT": report["LIVE_MANAGEMENT"]["overall"],
        }
        for name, report in result["strategy_b"].items()
    }
    print(json.dumps({"results": concise, "errors": errors, "output": args.output}, indent=2))


if __name__ == "__main__":
    main()
