import argparse
import bisect
import json
import statistics
from collections import Counter
from dataclasses import asdict, dataclass, replace

import research_strategy_b4 as b4
import research_strategy_b5 as b5
import research_strategy_bc_v2 as common
import strategy_evidence_audit as audit


MS_15M = 15 * 60 * 1000
MS_HOUR = 60 * 60 * 1000
MS_DAY = 24 * MS_HOUR
CORE_MARKETS = ("BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT")
COST_STRESS_PCT = 0.0020


@dataclass(frozen=True)
class B6Variant:
    name: str
    side_mode: str
    trigger_hours: int
    channel_lookback: int
    min_level_age: int
    max_level_age: int
    compression_fast_bars: int
    compression_slow_bars: int
    compression_max_ratio: float
    breakout_buffer_atr: float
    max_break_distance_atr: float
    breakout_range_atr_min: float
    breakout_range_atr_max: float
    breakout_body_min: float
    breakout_close_position_min: float
    breakout_volume_min: float
    breakout_flow_min: float
    local_regime_score_min: int
    market_score_min: int
    btc_return_tolerance: float
    acceptance_window_bars: int
    acceptance_min_outside: int
    acceptance_max_bars: int
    acceptance_failure_atr: float
    acceptance_progress_atr: float
    acceptance_max_distance_atr: float
    acceptance_flow_min: float
    stop_level_buffer_atr: float
    min_risk_pct: float
    max_risk_pct: float


B6_PRIMARY = B6Variant(
    name="B6_EXPANSION_ACCEPTANCE",
    side_mode="BOTH",
    trigger_hours=2,
    channel_lookback=24,
    min_level_age=3,
    max_level_age=18,
    compression_fast_bars=4,
    compression_slow_bars=20,
    compression_max_ratio=0.82,
    breakout_buffer_atr=0.08,
    max_break_distance_atr=1.10,
    breakout_range_atr_min=1.05,
    breakout_range_atr_max=2.80,
    breakout_body_min=0.48,
    breakout_close_position_min=0.67,
    breakout_volume_min=1.10,
    breakout_flow_min=0.53,
    local_regime_score_min=3,
    market_score_min=2,
    btc_return_tolerance=1.0,
    acceptance_window_bars=4,
    acceptance_min_outside=3,
    acceptance_max_bars=8,
    acceptance_failure_atr=0.30,
    acceptance_progress_atr=0.10,
    acceptance_max_distance_atr=1.20,
    acceptance_flow_min=0.51,
    stop_level_buffer_atr=0.30,
    min_risk_pct=0.008,
    max_risk_pct=0.024,
)

B6_NEIGHBOR = replace(
    B6_PRIMARY,
    name="B6_EXPANSION_ACCEPTANCE_NEIGHBOR",
    channel_lookback=28,
    max_level_age=20,
    compression_max_ratio=0.88,
    max_break_distance_atr=1.20,
    breakout_range_atr_min=0.95,
    breakout_range_atr_max=2.90,
    breakout_body_min=0.44,
    breakout_close_position_min=0.63,
    breakout_volume_min=1.05,
    breakout_flow_min=0.52,
    acceptance_max_bars=10,
    acceptance_failure_atr=0.35,
    acceptance_progress_atr=0.08,
    acceptance_max_distance_atr=1.30,
    acceptance_flow_min=0.50,
    stop_level_buffer_atr=0.35,
    max_risk_pct=0.026,
)

B6_VARIANTS = (
    B6_PRIMARY,
    B6_NEIGHBOR,
    replace(B6_PRIMARY, name="B6_LONG_DIAGNOSTIC", side_mode="LONG"),
    replace(B6_PRIMARY, name="B6_SHORT_DIAGNOSTIC", side_mode="SHORT"),
)


def aggregate_interval(candles_15m, hours):
    bucket_ms = int(hours) * MS_HOUR
    expected_count = int(hours) * 4
    grouped = {}
    for candle in candles_15m:
        bucket = int(candle["open_time"]) // bucket_ms * bucket_ms
        grouped.setdefault(bucket, []).append(candle)

    result = []
    for bucket in sorted(grouped):
        group = sorted(grouped[bucket], key=lambda item: int(item["open_time"]))
        expected = [bucket + offset * MS_15M for offset in range(expected_count)]
        if len(group) != expected_count:
            continue
        if [int(item["open_time"]) for item in group] != expected:
            continue
        result.append({
            "open_time": bucket,
            "close_time": int(group[-1]["close_time"]),
            "open": float(group[0]["open"]),
            "high": max(float(item["high"]) for item in group),
            "low": min(float(item["low"]) for item in group),
            "close": float(group[-1]["close"]),
            "volume": sum(float(item.get("volume", 0.0)) for item in group),
            "taker_buy": sum(float(item.get("taker_buy", 0.0)) for item in group),
            "taker_sell": sum(float(item.get("taker_sell", 0.0)) for item in group),
        })
    return result


def true_ranges(candles):
    values = []
    for previous, current in zip(candles[:-1], candles[1:]):
        values.append(max(
            float(current["high"]) - float(current["low"]),
            abs(float(current["high"]) - float(previous["close"])),
            abs(float(current["low"]) - float(previous["close"])),
        ))
    return values


def compression_ratio(history, fast_bars, slow_bars):
    if len(history) < slow_bars + 1 or fast_bars > slow_bars:
        return None
    values = true_ranges(history[-(slow_bars + 1):])
    slow = statistics.median(values[-slow_bars:])
    fast = statistics.median(values[-fast_bars:])
    if slow <= 0:
        return None
    return fast / slow


def combine_market_contexts(contexts):
    valid = {
        symbol: context
        for symbol, context in contexts.items()
        if context and context.get("side") in ("LONG", "SHORT")
    }
    votes = {
        symbol: 1 if context["side"] == "LONG" else -1
        for symbol, context in valid.items()
    }
    score = sum(votes.values())
    side = "LONG" if score >= 2 else "SHORT" if score <= -2 else None
    btc_context = contexts.get("BTCUSDT") or {}
    return {
        "side": side,
        "score": score,
        "valid_count": len(valid),
        "long_count": sum(1 for vote in votes.values() if vote > 0),
        "short_count": sum(1 for vote in votes.values() if vote < 0),
        "votes": votes,
        "btc_side": btc_context.get("side"),
        "btc_return_12h": btc_context.get("return_12h"),
    }


def build_market_resolver(data):
    core = {}
    for symbol in CORE_MARKETS:
        candles = data.get(symbol, {})
        candles_4h = candles.get("4h", [])
        if not candles_4h:
            continue
        core[symbol] = {
            "close_times": [int(item["close_time"]) for item in candles_4h],
            "regime_cache": candles["regime_cache"],
        }
    resolved = {}

    def resolve(timestamp):
        cache_key = int(timestamp) // (4 * MS_HOUR)
        if cache_key in resolved:
            return resolved[cache_key]
        contexts = {}
        for symbol, item in core.items():
            count = bisect.bisect_right(item["close_times"], int(timestamp))
            contexts[symbol] = item["regime_cache"].get(count)
        result = combine_market_contexts(contexts)
        resolved[cache_key] = result
        return result

    return resolve


def evaluate_expansion(closed_trigger, closed_4h, variant, local_regime=None):
    minimum = max(
        variant.channel_lookback + 1,
        variant.compression_slow_bars + 2,
    )
    if len(closed_trigger) < minimum or len(closed_4h) < 60:
        return None, "insufficient_history"

    breakout = closed_trigger[-1]
    history = closed_trigger[:-1]
    local_regime = (
        local_regime
        if local_regime is not None
        else b5.regime_context(closed_4h)
    )
    if not local_regime or not local_regime.get("side"):
        return None, "local_regime_neutral"
    side = local_regime["side"]
    if variant.side_mode != "BOTH" and side != variant.side_mode:
        return None, "side_mode_blocked"
    if int(local_regime["score"]) < variant.local_regime_score_min:
        return None, "local_regime_weak"

    channel = b4.donchian_level(history, side, variant.channel_lookback)
    atr_trigger = common.atr_value(history)
    volume_baseline = b5.median_volume(history)
    compression = compression_ratio(
        history,
        variant.compression_fast_bars,
        variant.compression_slow_bars,
    )
    if (
        not channel
        or not atr_trigger
        or atr_trigger <= 0
        or not volume_baseline
        or compression is None
    ):
        return None, "missing_baseline"
    if not variant.min_level_age <= int(channel["age"]) <= variant.max_level_age:
        return None, "level_age_rejected"
    if compression > variant.compression_max_ratio:
        return None, "not_compressed"

    level = float(channel["level"])
    close = float(breakout["close"])
    break_distance_atr = (
        (close - level) / atr_trigger
        if side == "LONG"
        else (level - close) / atr_trigger
    )
    price_break = (
        close > level + variant.breakout_buffer_atr * atr_trigger
        if side == "LONG"
        else close < level - variant.breakout_buffer_atr * atr_trigger
    )
    if not price_break:
        return None, "no_price_break"
    if break_distance_atr > variant.max_break_distance_atr:
        return None, "break_too_extended"

    candle_range = float(breakout["high"]) - float(breakout["low"])
    range_atr = candle_range / atr_trigger
    metrics = common.candle_metrics(breakout, side)
    volume_ratio = float(breakout.get("volume", 0.0)) / volume_baseline
    flow_ratio = common.directional_flow_ratio([breakout], side)
    checks = (
        (
            variant.breakout_range_atr_min
            <= range_atr
            <= variant.breakout_range_atr_max,
            "breakout_range_rejected",
        ),
        (metrics["direction_ok"], "wrong_breakout_direction"),
        (metrics["body_ratio"] >= variant.breakout_body_min, "breakout_body_weak"),
        (
            metrics["close_position"] >= variant.breakout_close_position_min,
            "breakout_close_weak",
        ),
        (
            volume_ratio >= variant.breakout_volume_min
            or flow_ratio >= variant.breakout_flow_min,
            "participation_weak",
        ),
    )
    for passed, reason in checks:
        if not passed:
            return None, reason

    detected_time = int(breakout["close_time"])
    return {
        "side": side,
        "level": level,
        "level_age_trigger": int(channel["age"]),
        "level_source_time": int(channel["source_time"]),
        "detected_time": detected_time,
        "expires_time": detected_time + variant.acceptance_max_bars * MS_15M,
        "atr_trigger": atr_trigger,
        "compression_ratio": compression,
        "break_distance_atr": break_distance_atr,
        "breakout_range_atr": range_atr,
        "breakout_body_ratio": metrics["body_ratio"],
        "breakout_close_position": metrics["close_position"],
        "breakout_volume_ratio": volume_ratio,
        "breakout_flow_ratio": flow_ratio,
        "local_regime_score": int(local_regime["score"]),
        "local_return_12h": float(local_regime["return_12h"]),
        "acceptance_candles": [],
    }, "detected"


def evaluate_acceptance(candles, pending, atr_15m, variant):
    if len(candles) < variant.acceptance_window_bars:
        return {"status": "WAIT", "reason": "acceptance_window_incomplete"}
    side = pending["side"]
    level = float(pending["level"])
    window = candles[-variant.acceptance_window_bars:]
    closes = [float(item["close"]) for item in window]
    outside = [
        close >= level if side == "LONG" else close <= level
        for close in closes
    ]
    outside_count = sum(outside)
    failed = any(
        close < level - variant.acceptance_failure_atr * atr_15m
        if side == "LONG"
        else close > level + variant.acceptance_failure_atr * atr_15m
        for close in closes
    )
    if failed:
        return {"status": "REJECT", "reason": "acceptance_level_failed"}

    final_close = closes[-1]
    progress_atr = (
        (final_close - level) / atr_15m
        if side == "LONG"
        else (level - final_close) / atr_15m
    )
    if progress_atr > variant.acceptance_max_distance_atr:
        return {"status": "REJECT", "reason": "acceptance_too_extended"}

    flow_ratio = common.directional_flow_ratio(window, side)
    checks = {
        "outside_closes": outside_count >= variant.acceptance_min_outside,
        "progress": progress_atr >= variant.acceptance_progress_atr,
        "flow": flow_ratio >= variant.acceptance_flow_min,
    }
    if not all(checks.values()):
        return {
            "status": "WAIT",
            "reason": "acceptance_not_ready",
            "outside_count": outside_count,
            "progress_atr": progress_atr,
            "flow_ratio": flow_ratio,
            "checks": checks,
        }

    extreme = (
        min(float(item["low"]) for item in window)
        if side == "LONG"
        else max(float(item["high"]) for item in window)
    )
    return {
        "status": "ACCEPT",
        "reason": "accepted",
        "outside_count": outside_count,
        "progress_atr": progress_atr,
        "flow_ratio": flow_ratio,
        "extreme": extreme,
        "atr_15m": atr_15m,
        "window": window,
        "checks": checks,
    }


def quality_score(pending, acceptance):
    market_strength = abs(float(pending["market_score"])) / 5.0
    compression_strength = max(0.0, 1.0 - float(pending["compression_ratio"]))
    participation = max(
        min(float(pending["breakout_volume_ratio"]), 2.0) / 2.0,
        float(pending["breakout_flow_ratio"]),
    )
    acceptance_strength = (
        float(acceptance["outside_count"]) / 4.0
        + min(float(acceptance["progress_atr"]), 1.0)
        + float(acceptance["flow_ratio"])
    )
    return round(
        market_strength
        + compression_strength
        + float(pending["breakout_body_ratio"])
        + float(pending["breakout_close_position"])
        + participation
        + acceptance_strength,
        6,
    )


def attach_trade(
    pair,
    candles_15m,
    signal_index,
    signal_time,
    pending,
    acceptance,
    variant,
    cost_pct,
):
    side = pending["side"]
    level = float(pending["level"])
    stop = (
        min(
            float(acceptance["extreme"]) - 0.10 * acceptance["atr_15m"],
            level - variant.stop_level_buffer_atr * pending["atr_trigger"],
        )
        if side == "LONG"
        else max(
            float(acceptance["extreme"]) + 0.10 * acceptance["atr_15m"],
            level + variant.stop_level_buffer_atr * pending["atr_trigger"],
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
    if risk_pct < variant.min_risk_pct:
        return None, "risk_too_tight"
    if risk_pct >= variant.max_risk_pct:
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

    stress_net = float(live["gross_R_live"]) - COST_STRESS_PCT / risk_pct
    record = {
        "strategy": variant.name,
        "pair": pair,
        "side": side,
        "signal_time": signal_time,
        "level": level,
        "level_age_trigger": pending["level_age_trigger"],
        "level_source_time": pending["level_source_time"],
        "compression_ratio": pending["compression_ratio"],
        "break_distance_atr": pending["break_distance_atr"],
        "breakout_range_atr": pending["breakout_range_atr"],
        "breakout_body_ratio": pending["breakout_body_ratio"],
        "breakout_close_position": pending["breakout_close_position"],
        "breakout_volume_ratio": pending["breakout_volume_ratio"],
        "breakout_flow_ratio": pending["breakout_flow_ratio"],
        "local_regime_score": pending["local_regime_score"],
        "local_return_12h": pending["local_return_12h"],
        "market_score": pending["market_score"],
        "market_valid_count": pending["market_valid_count"],
        "btc_return_12h": pending["btc_return_12h"],
        "acceptance_outside_count": acceptance["outside_count"],
        "acceptance_progress_atr": acceptance["progress_atr"],
        "acceptance_flow_ratio": acceptance["flow_ratio"],
        "acceptance_bars": len(pending["acceptance_candles"]),
        "quality_score": quality_score(pending, acceptance),
        "stop": stop,
        **outcomes,
        **live,
    }
    record["net_R_live_cost_0_20"] = round(stress_net, 6)
    return record, "attached"


def portfolio_overlay(
    records,
    max_concurrent=2,
    same_side_cluster_ms=MS_HOUR,
):
    ordered = sorted(
        records,
        key=lambda item: (
            int(item["signal_time"]),
            -float(item.get("quality_score", 0.0)),
            item["pair"],
        ),
    )
    selected = []
    active = []
    diagnostics = Counter()
    for record in ordered:
        signal_time = int(record["signal_time"])
        active = [
            item
            for item in active
            if int(item["exit_time_live"]) > signal_time
        ]
        if len(active) >= max_concurrent:
            diagnostics["blocked_max_concurrent"] += 1
            continue
        clustered = any(
            item["side"] == record["side"]
            and signal_time - int(item["signal_time"]) < same_side_cluster_ms
            for item in selected
            if signal_time >= int(item["signal_time"])
        )
        if clustered:
            diagnostics["blocked_same_side_cluster"] += 1
            continue
        selected.append(record)
        active.append(record)
        diagnostics["selected"] += 1
    return selected, diagnostics


def simulate_b6(
    pair,
    candles_15m,
    candles_4h,
    start_ms,
    end_ms,
    variant,
    cost_pct,
    market_resolver,
    candles_trigger=None,
    regime_cache=None,
    attach_trade_fn=None,
):
    candles_trigger = (
        candles_trigger
        if candles_trigger is not None
        else aggregate_interval(candles_15m, variant.trigger_hours)
    )
    regime_cache = (
        regime_cache
        if regime_cache is not None
        else b5.build_regime_context_cache(candles_4h)
    )
    close_times_15m = [int(item["close_time"]) for item in candles_15m]
    close_times_trigger = [int(item["close_time"]) for item in candles_trigger]
    close_times_4h = [int(item["close_time"]) for item in candles_4h]
    records = []
    stages = Counter()
    attach_trade_fn = attach_trade if attach_trade_fn is None else attach_trade_fn
    pending = None
    last_trigger_count = None
    index = max(60, bisect.bisect_left(close_times_15m, start_ms))

    while index < len(candles_15m) - 1:
        candle = candles_15m[index]
        signal_time = int(candle["close_time"])
        if signal_time > end_ms:
            break

        trigger_count = bisect.bisect_right(close_times_trigger, signal_time)
        if trigger_count >= 30 and trigger_count != last_trigger_count:
            stages["trigger_evaluated"] += 1
            trigger_time = close_times_trigger[trigger_count - 1]
            count_4h = bisect.bisect_right(close_times_4h, trigger_time)
            candidate, reason = evaluate_expansion(
                candles_trigger[:trigger_count],
                candles_4h[:count_4h],
                variant,
                local_regime=regime_cache.get(count_4h),
            )
            stages[f"expansion_{reason}"] += 1
            if candidate and pending is None:
                market = market_resolver(candidate["detected_time"])
                expected_score = (
                    market["score"] >= variant.market_score_min
                    if candidate["side"] == "LONG"
                    else market["score"] <= -variant.market_score_min
                )
                btc_return = market.get("btc_return_12h")
                btc_return_ok = (
                    btc_return is not None
                    and (
                        float(btc_return) >= -variant.btc_return_tolerance
                        if candidate["side"] == "LONG"
                        else float(btc_return) <= variant.btc_return_tolerance
                    )
                )
                if market["valid_count"] < 3:
                    stages["market_context_missing"] += 1
                elif market["side"] != candidate["side"] or not expected_score:
                    stages["market_breadth_mismatch"] += 1
                elif not btc_return_ok:
                    stages["btc_return_mismatch"] += 1
                else:
                    candidate["market_score"] = market["score"]
                    candidate["market_valid_count"] = market["valid_count"]
                    candidate["btc_return_12h"] = float(btc_return)
                    pending = candidate
                    stages["expansion_armed"] += 1
            last_trigger_count = trigger_count

        if not pending or signal_time <= pending["detected_time"]:
            index += 1
            continue
        if signal_time > pending["expires_time"]:
            stages["acceptance_expired"] += 1
            pending = None
            index += 1
            continue

        atr_15m = b4.prior_atr(candles_15m, index)
        if not atr_15m:
            stages["acceptance_atr_missing"] += 1
            index += 1
            continue
        pending["acceptance_candles"].append(candle)
        acceptance = evaluate_acceptance(
            pending["acceptance_candles"],
            pending,
            atr_15m,
            variant,
        )
        stages[f"acceptance_{acceptance['status'].lower()}"] += 1
        if acceptance["status"] == "REJECT":
            stages[f"acceptance_rejected_{acceptance['reason']}"] += 1
            pending = None
            index += 1
            continue
        if acceptance["status"] != "ACCEPT":
            index += 1
            continue

        record, reason = attach_trade_fn(
            pair,
            candles_15m,
            index,
            signal_time,
            pending,
            acceptance,
            variant,
            cost_pct,
        )
        stages[f"trade_{reason}"] += 1
        if record:
            records.append(record)
            index = b4.advance_past_live_trade(index, record)
        pending = None
        index += 1
    return records, stages


def variant_report(records, start_ms, end_ms):
    selected, overlay = portfolio_overlay(records)
    return {
        "records": selected,
        "RAW_LIVE_MANAGEMENT": {
            "overall": common.summarize(records, "net_R_live"),
            "long": common.summarize(
                [item for item in records if item["side"] == "LONG"],
                "net_R_live",
            ),
            "short": common.summarize(
                [item for item in records if item["side"] == "SHORT"],
                "net_R_live",
            ),
        },
        "LIVE_MANAGEMENT": {
            "overall": common.summarize(selected, "net_R_live"),
            "long": common.summarize(
                [item for item in selected if item["side"] == "LONG"],
                "net_R_live",
            ),
            "short": common.summarize(
                [item for item in selected if item["side"] == "SHORT"],
                "net_R_live",
            ),
            "cost_stress_0_20": common.summarize(
                selected,
                "net_R_live_cost_0_20",
            ),
            "folds_30d": common.fold_summaries(
                selected,
                "net_R_live",
                start_ms,
                end_ms,
            ),
        },
        "portfolio_overlay": dict(sorted(overlay.items())),
    }


def main():
    parser = argparse.ArgumentParser(
        description="Frozen Strategy B6 expansion-acceptance research"
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
    pairs = b5.read_json(args.pairs_file).get("pairs", [])[:args.max_pairs]
    market = audit.MarketData(args.cache_dir)
    data = {}
    errors = []
    trigger_hours = sorted({variant.trigger_hours for variant in B6_VARIANTS})
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
            data[pair]["regime_cache"] = b5.build_regime_context_cache(
                data[pair]["4h"]
            )
            data[pair]["trigger"] = {
                hours: aggregate_interval(data[pair]["15m"], hours)
                for hours in trigger_hours
            }
        except Exception as exc:
            errors.append(f"{pair}: {type(exc).__name__}: {exc}")

    market_resolver = build_market_resolver(data)
    result = {
        "engine": "B6_4H_BREADTH_2H_EXPANSION_15M_ACCEPTANCE",
        "spec": "docs/STRATEGY_B6_FROZEN_SPEC_2026-07-29.md",
        "period": {"start": args.start, "end": args.end},
        "pair_count_requested": len(pairs),
        "pair_count_loaded": len(data),
        "cost_model": {
            "round_trip_fee_plus_slippage_pct": args.cost_pct,
            "cost_stress_pct": COST_STRESS_PCT,
            "entry": "next_15m_open_after_acceptance",
            "same_candle_sl_tp": "active_stop_wins",
            "timeout": "mark_to_market_at_96h",
        },
        "portfolio_model": {
            "max_concurrent_b6": 2,
            "same_side_cluster_minutes": 60,
        },
        "strategy_b": {},
        "errors": errors,
    }

    for variant in B6_VARIANTS:
        print(f"simulate {variant.name}", flush=True)
        raw_records = []
        stages = Counter()
        for pair, candles in data.items():
            pair_records, pair_stages = simulate_b6(
                pair,
                candles["15m"],
                candles["4h"],
                start_ms,
                end_ms,
                variant,
                args.cost_pct,
                market_resolver,
                candles_trigger=candles["trigger"][variant.trigger_hours],
                regime_cache=candles["regime_cache"],
            )
            raw_records.extend(pair_records)
            stages.update(pair_stages)
        report = variant_report(raw_records, start_ms, end_ms)
        report["parameters"] = asdict(variant)
        report["diagnostics"] = dict(sorted(stages.items()))
        result["strategy_b"][variant.name] = report

    b5.write_json(args.output, result)
    concise = {
        name: report["LIVE_MANAGEMENT"]
        for name, report in result["strategy_b"].items()
    }
    print(json.dumps({
        "results": concise,
        "errors": errors,
        "output": args.output,
    }, indent=2))


if __name__ == "__main__":
    main()
