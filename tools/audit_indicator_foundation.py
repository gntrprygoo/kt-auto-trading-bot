import argparse
import bisect
import json
import pathlib
import statistics
from collections import Counter
from dataclasses import asdict, dataclass

import research_strategy_bc_v2 as common
import strategy_evidence_audit as audit


BOT = audit.BOT
MS_HOUR = 60 * 60 * 1000
MS_DAY = 24 * MS_HOUR


@dataclass(frozen=True)
class FoundationVariant:
    name: str
    sr_mode: str
    trend_mode: str
    scale_invariant_near: bool
    require_level_touch: bool
    require_15m_ema_pullback: bool


# Frozen before either development or prior-period replay is opened.
FOUNDATION_VARIANTS = (
    FoundationVariant(
        "A0_LEGACY_PARITY",
        "LEGACY",
        "LEGACY",
        False,
        False,
        False,
    ),
    FoundationVariant(
        "A1_SCALE_INVARIANT",
        "LEGACY",
        "LEGACY",
        True,
        False,
        False,
    ),
    FoundationVariant(
        "A2_LEVEL_TOUCH",
        "LEGACY",
        "LEGACY",
        True,
        True,
        False,
    ),
    FoundationVariant(
        "A3_CLUSTERED_SR",
        "CLUSTERED",
        "LEGACY",
        True,
        True,
        False,
    ),
    FoundationVariant(
        "A4_CLUSTERED_SR_TREND",
        "CLUSTERED",
        "CONFIRMED",
        True,
        True,
        False,
    ),
    FoundationVariant(
        "A5_CLUSTERED_SR_TREND_PULLBACK",
        "CLUSTERED",
        "CONFIRMED",
        True,
        True,
        True,
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


def price_invariant_near(price, level, tolerance):
    if price is None or level is None or price <= 0 or level <= 0:
        return False
    return abs(float(price) - float(level)) / float(level) <= float(tolerance)


def legacy_near_level(price, level, tolerance):
    if price is None or level is None or price <= 0 or level <= 0:
        return False
    effective_tolerance = tolerance * 3 if price < 0.001 else tolerance
    return abs(float(price) - float(level)) / float(price) <= effective_tolerance


def confirmed_pivot_events(candles, lookback=100, left=2, right=2):
    chunk = list(candles[-lookback:])
    events = []
    if len(chunk) < left + right + 1:
        return events
    for index in range(left, len(chunk) - right):
        candle = chunk[index]
        high = float(candle["high"])
        low = float(candle["low"])
        left_slice = chunk[index - left:index]
        right_slice = chunk[index + 1:index + right + 1]
        if (
            all(high > float(item["high"]) for item in left_slice)
            and all(high > float(item["high"]) for item in right_slice)
        ):
            events.append({"index": index, "level": high, "kind": "HIGH"})
        if (
            all(low < float(item["low"]) for item in left_slice)
            and all(low < float(item["low"]) for item in right_slice)
        ):
            events.append({"index": index, "level": low, "kind": "LOW"})
    return events


def _distinct_events(events, minimum_gap=3):
    selected = []
    for event in sorted(events, key=lambda item: item["index"]):
        if not selected or event["index"] - selected[-1]["index"] >= minimum_gap:
            selected.append(event)
    return selected


def clustered_support_resistance(candles, lookback=100, min_touches=2):
    chunk = list(candles[-lookback:])
    if len(chunk) < 20:
        return None, None, {"zones": [], "zone_width_pct": None}
    close = float(chunk[-1]["close"])
    atr_4h = common.atr_value(chunk[-40:])
    if close <= 0 or atr_4h is None or atr_4h <= 0:
        return None, None, {"zones": [], "zone_width_pct": None}

    # One zone is at least 0.25%, adapts to 20% of 4H ATR, and is capped at
    # 1.20%. This keeps the same definition across high- and low-priced pairs.
    zone_width = min(close * 0.012, max(close * 0.0025, atr_4h * 0.20))
    events = confirmed_pivot_events(chunk, lookback=lookback)
    clusters = []
    for event in sorted(events, key=lambda item: item["level"]):
        nearest = None
        nearest_distance = None
        for cluster in clusters:
            center = statistics.median(item["level"] for item in cluster)
            distance = abs(event["level"] - center)
            if distance <= zone_width and (
                nearest_distance is None or distance < nearest_distance
            ):
                nearest = cluster
                nearest_distance = distance
        if nearest is None:
            clusters.append([event])
        else:
            nearest.append(event)

    zones = []
    for cluster in clusters:
        distinct = _distinct_events(cluster)
        if len(distinct) < min_touches:
            continue
        levels = [item["level"] for item in distinct]
        zones.append({
            "level": statistics.median(levels),
            "touches": len(distinct),
            "last_index": max(item["index"] for item in distinct),
            "kinds": sorted({item["kind"] for item in distinct}),
        })

    supports = [zone for zone in zones if zone["level"] < close]
    resistances = [zone for zone in zones if zone["level"] > close]
    support = max(supports, key=lambda zone: zone["level"], default=None)
    resistance = min(resistances, key=lambda zone: zone["level"], default=None)
    return support, resistance, {
        "zones": zones,
        "zone_width_pct": zone_width / close,
    }


def rejection_metrics(candle, side):
    high = float(candle["high"])
    low = float(candle["low"])
    open_price = float(candle["open"])
    close = float(candle["close"])
    candle_range = high - low
    if candle_range <= 0:
        return {"valid": False, "wick_ratio": 0.0}
    wick = (
        min(open_price, close) - low
        if side == "LONG"
        else high - max(open_price, close)
    )
    ratio = max(0.0, wick / candle_range)
    return {
        "valid": ratio >= BOT.REJECTION_WICK_MIN_RATIO,
        "wick_ratio": ratio,
    }


def rejection_touches_level(candle, side, level, touch_tolerance):
    metrics = rejection_metrics(candle, side)
    if not metrics["valid"] or level is None or level <= 0:
        return False
    if side == "LONG":
        return float(candle["low"]) <= level * (1.0 + touch_tolerance)
    return float(candle["high"]) >= level * (1.0 - touch_tolerance)


def structure_or_gate(closed_4h, side):
    if len(closed_4h) < 10:
        return True
    recent = closed_4h[-10:]
    first = recent[:5]
    second = recent[5:]
    high_first = max(float(candle["high"]) for candle in first)
    high_second = max(float(candle["high"]) for candle in second)
    low_first = min(float(candle["low"]) for candle in first)
    low_second = min(float(candle["low"]) for candle in second)
    if side == "LONG":
        return high_second > high_first or low_second > low_first
    return low_second < low_first or high_second < high_first


def is_latest_liquidity_sweep(closed_4h):
    if len(closed_4h) < 6:
        return False
    last = closed_4h[-1]
    previous = closed_4h[-6:-1]
    swing_high = max(float(candle["high"]) for candle in previous)
    swing_low = min(float(candle["low"]) for candle in previous)
    average_volume = statistics.mean(float(candle["volume"]) for candle in previous)
    swept = float(last["high"]) > swing_high or float(last["low"]) < swing_low
    return swept and float(last["volume"]) > average_volume * BOT.SWEEP_VOLUME_MULT


def build_4h_context(closed_4h):
    if len(closed_4h) < 100:
        return None
    window = list(closed_4h[-199:])
    closes = [float(candle["close"]) for candle in window]
    highs = [float(candle["high"]) for candle in window]
    lows = [float(candle["low"]) for candle in window]
    ema21 = BOT.ema(closes, 21)
    ema55, slope_1 = BOT.ema_slope(closes, 55)
    ema55_old = BOT.ema(closes[:-3], 55)
    atr_4h = BOT.atr(highs, lows, closes, BOT.ATR_PERIOD)
    quality = BOT.quality_context_4h(window, exclude_incomplete=False)
    if (
        ema21 is None
        or ema55 is None
        or ema55_old is None
        or slope_1 is None
        or atr_4h is None
        or quality is None
    ):
        return None
    average_volume = BOT.avg_volume(window, BOT.VOLUME_AVG_LOOKBACK, exclude_last=1)
    volume_ratio = (
        float(window[-1].get("volume", 0.0)) / average_volume
        if average_volume
        else None
    )
    return {
        "closed": window,
        "close": closes[-1],
        "ema21": ema21,
        "ema55": ema55,
        "ema55_slope_1": slope_1,
        "ema55_slope_3": (ema55 - ema55_old) / ema55_old,
        "atr_4h": atr_4h,
        "quality": quality,
        "regime_ok": BOT.regime_ok_4h(closes, highs, lows),
        "sweep": is_latest_liquidity_sweep(window),
        "volume_ratio": volume_ratio,
        "legacy_sr": None,
        "clustered_sr": None,
    }


def trend_side(context, mode):
    close = context["close"]
    if mode == "LEGACY":
        if close > context["ema55"] and context["ema55_slope_1"] > 0:
            return "LONG"
        if close < context["ema55"] and context["ema55_slope_1"] < 0:
            return "SHORT"
        return None
    if (
        close > context["ema21"] > context["ema55"]
        and context["ema55_slope_3"] > 0
    ):
        return "LONG"
    if (
        close < context["ema21"] < context["ema55"]
        and context["ema55_slope_3"] < 0
    ):
        return "SHORT"
    return None


def quality_gate(context, side):
    expected = "BULLISH" if side == "LONG" else "BEARISH"
    quality = context["quality"]
    if quality["ema_alignment"] != expected:
        return False
    if side == "LONG" and quality["structure"] != "BULLISH":
        return False
    if side == "SHORT" and quality["range_position"] < BOT.QUALITY_SHORT_MIN_RANGE_POSITION:
        return False
    return True


def resolve_levels(context, variant):
    if variant.sr_mode == "LEGACY":
        if context["legacy_sr"] is None:
            support, resistance = BOT.support_resistance_multi(
                context["closed"],
                lookback=BOT.SR_LOOKBACK,
                min_touches=BOT.SR_MIN_TOUCHES,
            )
            context["legacy_sr"] = (
                {"level": support, "touches": None},
                {"level": resistance, "touches": None},
                {"zone_width_pct": BOT.SR_TOUCH_TOL},
            )
        return context["legacy_sr"]
    if context["clustered_sr"] is None:
        context["clustered_sr"] = clustered_support_resistance(
            context["closed"],
            lookback=BOT.SR_LOOKBACK,
            min_touches=2,
        )
    return context["clustered_sr"]


def adaptive_tolerances(context, variant):
    if variant.sr_mode == "LEGACY":
        return BOT.NEAR_LEVEL_TOLERANCE, BOT.SR_TOUCH_TOL
    atr_pct = context["atr_4h"] / context["close"]
    near_tolerance = min(0.025, max(0.008, atr_pct * 0.50))
    touch_tolerance = min(0.012, max(0.0025, atr_pct * 0.20))
    return near_tolerance, touch_tolerance


def orderflow_pass(closed_15m, side):
    required = BOT.ORDERFLOW_LOOKBACK + BOT.ORDERFLOW_BASELINE_LOOKBACK
    if len(closed_15m) < required:
        return False
    buy_ratio, sell_ratio, _, _ = BOT.taker_ratio(
        closed_15m, BOT.ORDERFLOW_LOOKBACK
    )
    baseline = closed_15m[-required:-BOT.ORDERFLOW_LOOKBACK]
    average_buy = statistics.mean(float(candle["taker_buy"]) for candle in baseline)
    average_sell = statistics.mean(float(candle["taker_sell"]) for candle in baseline)
    latest = closed_15m[-1]
    if side == "LONG":
        return (
            buy_ratio >= BOT.ORDERFLOW_MIN_RATIO
            and float(latest["taker_buy"])
            >= average_buy * BOT.ORDERFLOW_SPIKE_MULT
        )
    return (
        sell_ratio >= BOT.ORDERFLOW_MIN_RATIO
        and float(latest["taker_sell"])
        >= average_sell * BOT.ORDERFLOW_SPIKE_MULT
    )


def structural_stop(closed_15m, side, entry, level, atr_15m):
    recent = closed_15m[-20:]
    if len(recent) < 20:
        return None
    if side == "LONG":
        stop_sr = level * (1.0 - BOT.SR_BUF_SL)
        stop_atr = entry - BOT.ATR_MULT * atr_15m
        distance_sr = abs(entry - stop_sr)
        if entry * BOT.MIN_STOP_PCT <= distance_sr <= entry * 0.05:
            stop = stop_sr
        else:
            stop = min(stop_atr, stop_sr)
        stop = min(stop, min(float(candle["low"]) for candle in recent) * 0.998)
    else:
        stop_sr = level * (1.0 + BOT.SR_BUF_SL)
        stop_atr = entry + BOT.ATR_MULT * atr_15m
        distance_sr = abs(entry - stop_sr)
        if entry * BOT.MIN_STOP_PCT <= distance_sr <= entry * 0.05:
            stop = stop_sr
        else:
            stop = max(stop_atr, stop_sr)
        stop = max(stop, max(float(candle["high"]) for candle in recent) * 1.002)
    distance = abs(entry - stop)
    if distance < entry * BOT.MIN_STOP_PCT:
        distance = entry * BOT.MIN_STOP_PCT
        stop = entry - distance if side == "LONG" else entry + distance
    if distance / entry >= BOT.QUALITY_MAX_SL_PCT:
        return None
    return stop


def simulate_live_management(
    candles,
    signal_index,
    side,
    stop,
    cost_pct,
    horizon_bars=384,
):
    entry_index = signal_index + 1
    if entry_index >= len(candles):
        return None
    entry = float(candles[entry_index]["open"])
    risk = entry - stop if side == "LONG" else stop - entry
    if entry <= 0 or risk <= 0:
        return None
    risk_pct = risk / entry
    if risk_pct < BOT.MIN_STOP_PCT or risk_pct >= BOT.QUALITY_MAX_SL_PCT:
        return None

    tp1 = entry + risk if side == "LONG" else entry - risk
    tp2 = entry + 2.0 * risk if side == "LONG" else entry - 2.0 * risk
    trigger = (
        entry * (1.0 + BOT.PROFIT_SL_PLUS_TRIGGER_PCT)
        if side == "LONG"
        else entry * (1.0 - BOT.PROFIT_SL_PLUS_TRIGGER_PCT)
    )
    lock = (
        entry * (1.0 + BOT.PROFIT_SL_PLUS_LOCK_PCT)
        if side == "LONG"
        else entry * (1.0 - BOT.PROFIT_SL_PLUS_LOCK_PCT)
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
        tp1_hit_now = (
            float(candle["high"]) >= tp1
            if side == "LONG"
            else float(candle["low"]) <= tp1
        )
        trigger_hit = (
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
                gross_r += 0.5
                remaining -= 0.5
                tp1_hit = True
            gross_r += remaining * 2.0
            remaining = 0.0
            outcome = "TP2"
            exit_index = index
            exit_time = int(candle["close_time"])
            break
        if tp1_hit_now and not tp1_hit:
            gross_r += 0.5
            remaining -= 0.5
            tp1_hit = True
        if trigger_hit or (tp1_hit and lock_reached):
            active_stop = (
                max(active_stop, lock)
                if side == "LONG"
                else min(active_stop, lock)
            )
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
        "risk_pct": risk_pct,
        "gross_R_live": gross_r,
        "cost_R_live": cost_r,
        "net_R_live": gross_r - cost_r,
        "outcome_live": outcome,
        "exit_time_live": exit_time,
        "exit_index_live": exit_index,
    }


def evaluate_signal(
    pair,
    candles_15m,
    signal_index,
    context,
    variant,
    cost_pct,
    funnel,
):
    funnel["evaluations"] += 1
    if not context["regime_ok"] or context["sweep"]:
        return None
    funnel["regime_pass"] += 1

    side = trend_side(context, variant.trend_mode)
    if side is None:
        return None
    funnel["trend_pass"] += 1
    if not structure_or_gate(context["closed"], side):
        return None
    funnel["structure_pass"] += 1
    if not quality_gate(context, side):
        return None
    funnel["quality_pass"] += 1
    if (
        context["volume_ratio"] is not None
        and context["volume_ratio"] >= BOT.JALUR_A_MAX_VOL_RATIO
    ):
        return None
    funnel["volume_pass"] += 1

    closed_15m = candles_15m[max(0, signal_index - 198):signal_index + 1]
    if len(closed_15m) < 60:
        return None
    latest = closed_15m[-1]
    previous = closed_15m[-2]
    rejection_candidates = [
        candle
        for candle in (latest, previous)
        if rejection_metrics(candle, side)["valid"]
    ]
    if not rejection_candidates:
        return None
    funnel["rejection_pass"] += 1

    support, resistance, sr_meta = resolve_levels(context, variant)
    selected = support if side == "LONG" else resistance
    if not selected:
        return None
    level = float(selected["level"])
    funnel["sr_available"] += 1
    near_tolerance, touch_tolerance = adaptive_tolerances(context, variant)
    close = float(latest["close"])
    if variant.scale_invariant_near:
        near = price_invariant_near(close, level, near_tolerance)
    else:
        near = legacy_near_level(close, level, near_tolerance)
    correct_side = (
        close > level * (1.0 - BOT.SR_BUF_SL)
        if side == "LONG"
        else close < level * (1.0 + BOT.SR_BUF_SL)
    )
    if not near or not correct_side:
        return None
    funnel["near_pass"] += 1

    if variant.require_level_touch and not any(
        rejection_touches_level(
            candle,
            side,
            level,
            touch_tolerance,
        )
        for candle in rejection_candidates
    ):
        return None
    funnel["touch_pass"] += 1

    closes_15m = [float(candle["close"]) for candle in closed_15m]
    highs_15m = [float(candle["high"]) for candle in closed_15m]
    lows_15m = [float(candle["low"]) for candle in closed_15m]
    atr_15m = BOT.atr(
        highs_15m,
        lows_15m,
        closes_15m,
        BOT.ATR_PERIOD,
    )
    ema21_15m = BOT.ema(closes_15m, 21)
    if atr_15m is None or ema21_15m is None or atr_15m <= 0:
        return None
    if (
        variant.require_15m_ema_pullback
        and abs(close - ema21_15m) / atr_15m > 1.0
    ):
        return None
    funnel["pullback_pass"] += 1

    if BOT.ENABLE_ORDERFLOW_CONFIRM and not orderflow_pass(closed_15m, side):
        return None
    funnel["orderflow_pass"] += 1
    stop = structural_stop(closed_15m, side, close, level, atr_15m)
    if stop is None:
        return None
    funnel["risk_pass"] += 1

    live = simulate_live_management(
        candles_15m,
        signal_index,
        side,
        stop,
        cost_pct,
    )
    if live is None:
        return None
    funnel["trades"] += 1
    return {
        "strategy": variant.name,
        "pair": pair,
        "side": side,
        "signal_time": int(latest["close_time"]),
        "sr_mode": variant.sr_mode,
        "level": level,
        "level_touches": selected.get("touches"),
        "near_distance_pct": abs(close - level) / level,
        "near_tolerance_pct": near_tolerance,
        "touch_tolerance_pct": touch_tolerance,
        "zone_width_pct": sr_meta.get("zone_width_pct"),
        "ema21_4h": context["ema21"],
        "ema55_4h": context["ema55"],
        "ema55_slope_1": context["ema55_slope_1"],
        "ema55_slope_3": context["ema55_slope_3"],
        "ema21_distance_atr_15m": abs(close - ema21_15m) / atr_15m,
        "volume_ratio_4h": context["volume_ratio"],
        "range_position_4h": context["quality"]["range_position"],
        **live,
    }


def simulate_variant(
    pair,
    candles_15m,
    candles_4h,
    start_ms,
    end_ms,
    variant,
    cost_pct,
    context_cache=None,
):
    close_times_15m = [int(candle["close_time"]) for candle in candles_15m]
    close_times_4h = [int(candle["close_time"]) for candle in candles_4h]
    records = []
    funnel = Counter()
    context_cache = context_cache if context_cache is not None else {}
    index = max(60, bisect.bisect_left(close_times_15m, start_ms))
    while index < len(candles_15m) - 1:
        signal_time = close_times_15m[index]
        if signal_time > end_ms:
            break
        end_4h = bisect.bisect_right(close_times_4h, signal_time)
        if end_4h < 100:
            index += 1
            continue
        if end_4h not in context_cache:
            context_cache[end_4h] = build_4h_context(
                candles_4h[max(0, end_4h - 199):end_4h]
            )
        context = context_cache[end_4h]
        if context is None:
            index += 1
            continue
        record = evaluate_signal(
            pair,
            candles_15m,
            index,
            context,
            variant,
            cost_pct,
            funnel,
        )
        if record:
            records.append(record)
            cooldown_bars = (
                16 if record["outcome_live"] == "SL" else 2
            )
            index = int(record["exit_index_live"]) + cooldown_bars
        else:
            index += 1
    return records, funnel


def pair_breakdown(records):
    result = {}
    for pair in sorted({record["pair"] for record in records}):
        selected = [record for record in records if record["pair"] == pair]
        result[pair] = common.summarize(selected, "net_R_live")
    return result


def build_report(records, funnel, start_ms, end_ms):
    return {
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
        "funnel": dict(sorted(funnel.items())),
        "pairs": pair_breakdown(records),
        "records": sorted(
            records,
            key=lambda item: (item["signal_time"], item["pair"]),
        ),
    }


def main():
    parser = argparse.ArgumentParser(
        description="Leakage-controlled audit of live Strategy A S/R and EMA foundations"
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
    all_records = {variant.name: [] for variant in FOUNDATION_VARIANTS}
    all_funnels = {variant.name: Counter() for variant in FOUNDATION_VARIANTS}
    errors = []

    for pair_number, pair in enumerate(pairs, 1):
        print(f"load {pair_number}/{len(pairs)} {pair}", flush=True)
        try:
            candles_15m = market.klines(
                pair,
                "15m",
                start_ms - 4 * MS_DAY,
                end_ms + 5 * MS_DAY,
            )
            candles_4h = market.klines(
                pair,
                "4h",
                start_ms - 60 * MS_DAY,
                end_ms + 4 * MS_HOUR,
            )
        except Exception as exc:
            errors.append(f"{pair}: {type(exc).__name__}: {exc}")
            continue
        pair_context_cache = {}
        for variant in FOUNDATION_VARIANTS:
            print(f"  simulate {variant.name}", flush=True)
            records, funnel = simulate_variant(
                pair,
                candles_15m,
                candles_4h,
                start_ms,
                end_ms,
                variant,
                args.cost_pct,
                context_cache=pair_context_cache,
            )
            all_records[variant.name].extend(records)
            all_funnels[variant.name].update(funnel)

    result = {
        "engine": "A_FOUNDATION_SR_EMA_PARITY_AUDIT_V1",
        "protocol": {
            "variants_frozen_before_replay": True,
            "confirmed_candles_only": True,
            "entry": "next_15m_open",
            "same_candle_ordering": "active_stop_first",
            "live_management": "TP1_1R_50pct_TP2_2R_50pct_SLplus_1pct",
            "round_trip_fee_plus_slippage_pct": args.cost_pct,
            "timeout_hours": 96,
        },
        "period": {"start": args.start, "end": args.end},
        "pair_count_requested": len(pairs),
        "variants": [asdict(variant) for variant in FOUNDATION_VARIANTS],
        "results": {},
        "errors": errors,
    }
    for variant in FOUNDATION_VARIANTS:
        result["results"][variant.name] = build_report(
            all_records[variant.name],
            all_funnels[variant.name],
            start_ms,
            end_ms,
        )
    write_json(args.output, result)
    summary = {
        name: report["overall"]
        for name, report in result["results"].items()
    }
    print(json.dumps({
        "output": args.output,
        "errors": len(errors),
        "summary": summary,
    }, indent=2), flush=True)


if __name__ == "__main__":
    main()
