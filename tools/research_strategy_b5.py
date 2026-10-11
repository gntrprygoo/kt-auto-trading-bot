import argparse
import bisect
import json
import pathlib
import statistics
from collections import Counter
from dataclasses import asdict, dataclass

import research_strategy_b4 as b4
import research_strategy_bc_v2 as common
import strategy_evidence_audit as audit


MS_HOUR = 60 * 60 * 1000
MS_DAY = 24 * MS_HOUR


@dataclass(frozen=True)
class B5Variant:
    name: str
    side_mode: str
    channel_lookback_1h: int
    min_level_age_1h: int
    breakout_buffer_atr: float
    max_break_distance_atr: float
    breakout_range_atr_min: float
    breakout_range_atr_max: float
    breakout_body_min: float
    breakout_close_position_min: float
    breakout_volume_min: float
    breakout_flow_min: float
    breakout_score_min: int
    retest_hours: int
    retest_tolerance_atr: float
    retest_max_penetration_atr: float
    retest_max_distance_atr: float
    retest_volume_max: float
    retest_absorption_min: float
    retest_score_min: int


# Frozen B5 development candidates. The balanced candidate replaces the sparse
# 4H breakout trigger with a 1H structural trigger while preserving 4H regime.
B5_VARIANTS = (
    B5Variant(
        "B5_BALANCED",
        "BOTH",
        36,
        2,
        0.08,
        1.25,
        0.45,
        2.50,
        0.40,
        0.60,
        1.00,
        0.52,
        4,
        16,
        0.35,
        0.70,
        0.90,
        1.35,
        0.52,
        2,
    ),
    B5Variant(
        "B5_BALANCED_NEIGHBOR",
        "BOTH",
        30,
        2,
        0.06,
        1.40,
        0.40,
        2.80,
        0.38,
        0.58,
        0.95,
        0.51,
        3,
        20,
        0.40,
        0.80,
        1.00,
        1.50,
        0.51,
        2,
    ),
    B5Variant(
        "B5_STRICT",
        "BOTH",
        48,
        3,
        0.10,
        1.10,
        0.55,
        2.30,
        0.50,
        0.68,
        1.10,
        0.53,
        4,
        12,
        0.30,
        0.60,
        0.80,
        1.20,
        0.54,
        3,
    ),
    B5Variant(
        "B5_LONG_BALANCED",
        "LONG",
        36,
        2,
        0.08,
        1.25,
        0.45,
        2.50,
        0.40,
        0.60,
        1.00,
        0.52,
        4,
        16,
        0.35,
        0.70,
        0.90,
        1.35,
        0.52,
        2,
    ),
    B5Variant(
        "B5_SHORT_DIAGNOSTIC",
        "SHORT",
        36,
        2,
        0.08,
        1.25,
        0.45,
        2.50,
        0.40,
        0.60,
        1.00,
        0.52,
        4,
        16,
        0.35,
        0.70,
        0.90,
        1.35,
        0.52,
        2,
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


def aggregate_1h(candles_15m):
    grouped = {}
    for candle in candles_15m:
        bucket = int(candle["open_time"]) // MS_HOUR * MS_HOUR
        grouped.setdefault(bucket, []).append(candle)
    candles_1h = []
    for bucket in sorted(grouped):
        group = sorted(grouped[bucket], key=lambda candle: int(candle["open_time"]))
        if len(group) != 4:
            continue
        expected = [bucket + offset * 15 * 60 * 1000 for offset in range(4)]
        if [int(candle["open_time"]) for candle in group] != expected:
            continue
        candles_1h.append({
            "open_time": bucket,
            "close_time": int(group[-1]["close_time"]),
            "open": float(group[0]["open"]),
            "high": max(float(candle["high"]) for candle in group),
            "low": min(float(candle["low"]) for candle in group),
            "close": float(group[-1]["close"]),
            "volume": sum(float(candle.get("volume", 0.0)) for candle in group),
            "taker_buy": sum(float(candle.get("taker_buy", 0.0)) for candle in group),
            "taker_sell": sum(float(candle.get("taker_sell", 0.0)) for candle in group),
        })
    return candles_1h


def median_volume(candles, lookback=20):
    values = [
        float(candle.get("volume", 0.0))
        for candle in candles[-lookback:]
        if float(candle.get("volume", 0.0)) > 0
    ]
    return statistics.median(values) if values else None


def regime_context(candles_4h):
    if len(candles_4h) < 60:
        return None
    closes = [float(candle["close"]) for candle in candles_4h]
    fast = common.ema(closes, 21)
    slow = common.ema(closes, 55)
    atr_4h = common.atr_value(candles_4h)
    _, slow_slope = common.BOT.ema_slope(closes, 55)
    if fast is None or slow is None or not atr_4h or slow_slope is None:
        return None
    return_12h = closes[-1] / closes[-4] - 1.0
    long_votes = {
        "ema": fast > slow,
        "price": closes[-1] > fast,
        "slope": slow_slope > 0,
        "momentum": return_12h > 0,
    }
    short_votes = {
        "ema": fast < slow,
        "price": closes[-1] < fast,
        "slope": slow_slope < 0,
        "momentum": return_12h < 0,
    }
    long_score = sum(long_votes.values())
    short_score = sum(short_votes.values())
    if long_score >= 3 and long_score > short_score:
        side = "LONG"
        score = long_score
    elif short_score >= 3 and short_score > long_score:
        side = "SHORT"
        score = short_score
    else:
        side = None
        score = max(long_score, short_score)
    return {
        "side": side,
        "score": score,
        "long_score": long_score,
        "short_score": short_score,
        "fast": fast,
        "slow": slow,
        "slow_slope": slow_slope,
        "atr": atr_4h,
        "return_12h": return_12h,
    }


def build_regime_context_cache(candles_4h):
    return {
        count: regime_context(candles_4h[max(0, count - 199):count])
        for count in range(60, len(candles_4h) + 1)
    }


def btc_opposition_veto(side, btc_candles_4h, context=None):
    context = context if context is not None else regime_context(btc_candles_4h)
    if not context:
        return {"passed": False, "reason": "btc_context_missing", "context": None}
    strongly_opposed = (
        context["side"] == "SHORT"
        and context["score"] == 4
        and context["return_12h"] <= -0.008
        if side == "LONG"
        else context["side"] == "LONG"
        and context["score"] == 4
        and context["return_12h"] >= 0.008
    )
    return {
        "passed": not strongly_opposed,
        "reason": "btc_strong_opposition" if strongly_opposed else "passed",
        "context": context,
    }


def evaluate_breakout(closed_1h, closed_4h, variant, regime=None):
    minimum = max(60, variant.channel_lookback_1h + 20)
    if len(closed_1h) < minimum or len(closed_4h) < 60:
        return None, "insufficient_history"
    breakout = closed_1h[-1]
    history = closed_1h[:-1]
    regime = regime if regime is not None else regime_context(closed_4h)
    if not regime or not regime["side"]:
        return None, "regime_neutral"
    side = regime["side"]
    if variant.side_mode != "BOTH" and side != variant.side_mode:
        return None, "side_mode_blocked"

    channel = b4.donchian_level(history, side, variant.channel_lookback_1h)
    atr_1h = common.atr_value(history)
    volume_baseline = median_volume(history)
    if not channel or not atr_1h or atr_1h <= 0 or not volume_baseline:
        return None, "missing_baseline"
    if channel["age"] < variant.min_level_age_1h:
        return None, "level_too_recent"

    level = float(channel["level"])
    close = float(breakout["close"])
    break_distance_atr = (
        (close - level) / atr_1h
        if side == "LONG"
        else (level - close) / atr_1h
    )
    price_break = (
        close > level + variant.breakout_buffer_atr * atr_1h
        if side == "LONG"
        else close < level - variant.breakout_buffer_atr * atr_1h
    )
    if not price_break:
        return None, "no_price_break"
    if break_distance_atr > variant.max_break_distance_atr:
        return None, "break_too_extended"

    candle_range = float(breakout["high"]) - float(breakout["low"])
    range_atr = candle_range / atr_1h
    metrics = common.candle_metrics(breakout, side)
    volume_ratio = float(breakout.get("volume", 0.0)) / volume_baseline
    flow_ratio = common.directional_flow_ratio([breakout], side)
    components = {
        "range": (
            variant.breakout_range_atr_min
            <= range_atr
            <= variant.breakout_range_atr_max
        ),
        "direction": metrics["direction_ok"],
        "body": metrics["body_ratio"] >= variant.breakout_body_min,
        "close": metrics["close_position"] >= variant.breakout_close_position_min,
        "volume": volume_ratio >= variant.breakout_volume_min,
        "flow": flow_ratio >= variant.breakout_flow_min,
    }
    score = sum(components.values())
    participation = components["volume"] or components["flow"]
    if not participation:
        return None, "participation_weak"
    if score < variant.breakout_score_min:
        return None, "breakout_score_low"

    detected_time = int(breakout["close_time"])
    return {
        "side": side,
        "level": level,
        "level_age_1h": int(channel["age"]),
        "level_source_time": int(channel["source_time"]),
        "detected_time": detected_time,
        "expires_time": detected_time + variant.retest_hours * MS_HOUR,
        "atr_1h": atr_1h,
        "break_distance_atr": break_distance_atr,
        "breakout_range_atr": range_atr,
        "breakout_volume_ratio": volume_ratio,
        "breakout_flow_ratio": flow_ratio,
        "breakout_score": score,
        "breakout_components": components,
        "regime_score": regime["score"],
        "regime_return_12h": regime["return_12h"],
    }, "detected"


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
    penetration_atr = (
        max(0.0, level - extreme) / atr_15m
        if side == "LONG"
        else max(0.0, extreme - level) / atr_15m
    )
    distance_atr = abs(close - level) / atr_15m
    held = (
        close >= level - 0.20 * atr_15m
        if side == "LONG"
        else close <= level + 0.20 * atr_15m
    )
    if penetration_atr > variant.retest_max_penetration_atr:
        return {"valid": False, "reason": "deep_penetration"}
    if not held:
        return {"valid": False, "reason": "level_failed"}
    if distance_atr > variant.retest_max_distance_atr:
        return {"valid": False, "reason": "close_too_extended"}

    metrics = common.candle_metrics(candle, side)
    volume_baseline = median_volume(previous_candles)
    volume_ratio = (
        float(candle.get("volume", 0.0)) / volume_baseline
        if volume_baseline
        else 99.0
    )
    absorption = common.opposing_absorption_ratio(candle, side)
    reclaimed = close >= level if side == "LONG" else close <= level
    components = {
        "reclaimed": reclaimed,
        "reaction": metrics["direction_ok"] and metrics["close_position"] >= 0.55,
        "wick": metrics["wick_ratio"] >= 0.15,
        "volume_contraction": volume_ratio <= variant.retest_volume_max,
        "absorption": absorption >= variant.retest_absorption_min,
    }
    score = sum(components.values())
    if score < variant.retest_score_min:
        return {"valid": False, "reason": "retest_score_low"}
    return {
        "valid": True,
        "reason": "valid",
        "extreme": extreme,
        "penetration_atr": penetration_atr,
        "distance_atr": distance_atr,
        "volume_ratio": volume_ratio,
        "absorption_ratio": absorption,
        "score": score,
        "components": components,
        "atr": atr_15m,
    }


def attach_trade(
    pair,
    candles_15m,
    signal_index,
    signal_time,
    pending,
    retest,
    variant,
    cost_pct,
    min_risk_pct=0.004,
    max_risk_pct=0.03,
):
    side = pending["side"]
    level = float(pending["level"])
    stop = (
        min(
            float(retest["extreme"]) - 0.10 * retest["atr"],
            level - 0.25 * retest["atr"],
        )
        if side == "LONG"
        else max(
            float(retest["extreme"]) + 0.10 * retest["atr"],
            level + 0.25 * retest["atr"],
        )
    )
    entry_index = signal_index + 1
    if entry_index >= len(candles_15m):
        return None, "entry_missing"
    entry = float(candles_15m[entry_index]["open"])
    risk = entry - stop if side == "LONG" else stop - entry
    risk_pct = risk / entry if entry > 0 else 0.0
    if risk <= 0:
        return None, "risk_invalid"
    if risk_pct < min_risk_pct:
        return None, "risk_too_tight"
    if risk_pct >= max_risk_pct:
        return None, "risk_too_wide"

    outcomes = common.attach_outcomes(
        candles_15m,
        signal_index,
        {"side": side, "stop": stop},
        cost_pct,
    )
    live = b4.simulate_live_management(
        candles_15m,
        signal_index,
        side,
        stop,
        cost_pct,
    )
    if not outcomes or not live:
        return None, "outcome_missing"
    return {
        "strategy": variant.name,
        "pair": pair,
        "side": side,
        "signal_time": signal_time,
        "level": level,
        "level_age_1h": pending["level_age_1h"],
        "level_source_time": pending["level_source_time"],
        "break_distance_atr": pending["break_distance_atr"],
        "breakout_range_atr": pending["breakout_range_atr"],
        "breakout_volume_ratio": pending["breakout_volume_ratio"],
        "breakout_flow_ratio": pending["breakout_flow_ratio"],
        "breakout_score": pending["breakout_score"],
        "regime_score": pending["regime_score"],
        "regime_return_12h": pending["regime_return_12h"],
        "btc_return_12h": pending["btc_return_12h"],
        "retest_penetration_atr": retest["penetration_atr"],
        "retest_volume_ratio": retest["volume_ratio"],
        "retest_absorption_ratio": retest["absorption_ratio"],
        "retest_score": retest["score"],
        "stop": stop,
        **outcomes,
        **live,
    }, "attached"


def simulate_b5(
    pair,
    candles_15m,
    candles_4h,
    btc_candles_4h,
    start_ms,
    end_ms,
    variant,
    cost_pct,
    candles_1h=None,
    regime_cache=None,
    btc_regime_cache=None,
    min_risk_pct=0.004,
    max_risk_pct=0.03,
    max_level_age_1h=None,
):
    candles_1h = candles_1h if candles_1h is not None else aggregate_1h(candles_15m)
    regime_cache = (
        regime_cache
        if regime_cache is not None
        else build_regime_context_cache(candles_4h)
    )
    btc_regime_cache = (
        btc_regime_cache
        if btc_regime_cache is not None
        else build_regime_context_cache(btc_candles_4h)
    )
    close_times_15m = [int(candle["close_time"]) for candle in candles_15m]
    close_times_1h = [int(candle["close_time"]) for candle in candles_1h]
    close_times_4h = [int(candle["close_time"]) for candle in candles_4h]
    btc_close_times = [int(candle["close_time"]) for candle in btc_candles_4h]
    records = []
    stages = Counter()
    pending = None
    last_1h_count = None
    index = max(60, bisect.bisect_left(close_times_15m, start_ms))
    while index < len(candles_15m) - 1:
        candle = candles_15m[index]
        signal_time = int(candle["close_time"])
        if signal_time > end_ms:
            break

        end_1h = bisect.bisect_right(close_times_1h, signal_time)
        if end_1h >= 60 and end_1h != last_1h_count:
            stages["1h_evaluated"] += 1
            breakout_time = close_times_1h[end_1h - 1]
            end_4h = bisect.bisect_right(close_times_4h, breakout_time)
            candidate, reason = evaluate_breakout(
                candles_1h[:end_1h],
                candles_4h[:end_4h],
                variant,
                regime=regime_cache.get(end_4h),
            )
            stages[f"breakout_{reason}"] += 1
            if candidate and pending is None:
                if (
                    max_level_age_1h is not None
                    and candidate["level_age_1h"] > max_level_age_1h
                ):
                    stages["breakout_level_too_old"] += 1
                    candidate = None
            if candidate and pending is None:
                stages["breakout_detected_while_idle"] += 1
                btc_end = bisect.bisect_right(
                    btc_close_times,
                    candidate["detected_time"],
                )
                market = btc_opposition_veto(
                    candidate["side"],
                    btc_candles_4h[:btc_end],
                    context=btc_regime_cache.get(btc_end),
                )
                if market["passed"]:
                    stages["btc_veto_passed"] += 1
                    candidate["btc_return_12h"] = market["context"]["return_12h"]
                    pending = candidate
                else:
                    stages[f"btc_veto_{market['reason']}"] += 1
            last_1h_count = end_1h

        if not pending or signal_time <= pending["detected_time"]:
            index += 1
            continue
        if signal_time > pending["expires_time"]:
            stages["pending_expired"] += 1
            pending = None
            index += 1
            continue

        atr_15m = b4.prior_atr(candles_15m, index)
        if not atr_15m:
            stages["retest_atr_missing"] += 1
            index += 1
            continue
        level = float(pending["level"])
        close = float(candle["close"])
        invalid_close = (
            close < level - 0.45 * atr_15m
            if pending["side"] == "LONG"
            else close > level + 0.45 * atr_15m
        )
        if invalid_close:
            stages["pending_invalid_close"] += 1
            pending = None
            index += 1
            continue

        retest = evaluate_first_retest(
            candle,
            candles_15m[max(0, index - 20):index],
            pending,
            atr_15m,
            variant,
        )
        if retest is None:
            index += 1
            continue
        stages["first_retest_touched"] += 1
        if not retest["valid"]:
            stages["first_retest_rejected"] += 1
            stages[f"first_retest_rejected_{retest['reason']}"] += 1
            pending = None
            index += 1
            continue

        stages["first_retest_valid"] += 1
        record, reason = attach_trade(
            pair,
            candles_15m,
            index,
            signal_time,
            pending,
            retest,
            variant,
            cost_pct,
            min_risk_pct=min_risk_pct,
            max_risk_pct=max_risk_pct,
        )
        stages[f"trade_{reason}"] += 1
        if record:
            records.append(record)
            index = b4.advance_past_live_trade(index, record)
        pending = None
        index += 1
    return records, stages


def main():
    parser = argparse.ArgumentParser(
        description="Leakage-controlled Strategy B5 multi-timeframe research"
    )
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
                "15m": market.klines(
                    pair,
                    "15m",
                    start_ms - 4 * MS_DAY,
                    end_ms + 5 * MS_DAY,
                ),
                "4h": market.klines(
                    pair,
                    "4h",
                    start_ms - 60 * MS_DAY,
                    end_ms + 4 * MS_HOUR,
                ),
            }
            data[pair]["1h"] = aggregate_1h(data[pair]["15m"])
            data[pair]["regime_cache"] = build_regime_context_cache(data[pair]["4h"])
        except Exception as exc:
            errors.append(f"{pair}: {type(exc).__name__}: {exc}")

    btc_4h = data.get("BTCUSDT", {}).get("4h", [])
    btc_regime_cache = build_regime_context_cache(btc_4h)
    result = {
        "engine": "B5_4H_REGIME_1H_BREAKOUT_15M_RETEST",
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
    for variant in B5_VARIANTS:
        print(f"simulate {variant.name}", flush=True)
        records = []
        stages = Counter()
        for pair, candles in data.items():
            pair_records, pair_stages = simulate_b5(
                pair,
                candles["15m"],
                candles["4h"],
                btc_4h,
                start_ms,
                end_ms,
                variant,
                args.cost_pct,
                candles_1h=candles["1h"],
                regime_cache=candles["regime_cache"],
                btc_regime_cache=btc_regime_cache,
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
    print(json.dumps({
        "results": concise,
        "errors": errors,
        "output": args.output,
    }, indent=2))


if __name__ == "__main__":
    main()
