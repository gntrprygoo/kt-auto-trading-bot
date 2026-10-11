import argparse
import bisect
import json
import pathlib
import statistics
from dataclasses import asdict, dataclass
from datetime import datetime, timezone

import strategy_evidence_audit as audit


BOT = audit.BOT
MS_HOUR = 60 * 60 * 1000
MS_DAY = 24 * MS_HOUR


@dataclass(frozen=True)
class B2Variant:
    name: str
    c1_volume_min: float
    c2_volume_min: float
    c1_body_min: float
    flow_min: float
    retest_hours: int


@dataclass(frozen=True)
class C4Variant:
    name: str
    absorption_min: float
    continuation_flow_min: float
    mss_body_min: float
    location_limit: float


@dataclass(frozen=True)
class B3Variant:
    name: str
    c1_volume_min: float
    c2_volume_min: float
    c1_body_min: float
    retest_absorption_min: float
    confirmation_flow_min: float
    confirmation_body_min: float
    confirmation_bars: int
    retest_hours: int


@dataclass(frozen=True)
class C5Variant:
    name: str
    absorption_min: float
    continuation_flow_min: float
    mss_body_min: float
    max_fast_distance_atr: float
    sweep_lookback: int
    search_bars: int
    market_guard: bool = False


B2_VARIANTS = (
    B2Variant("B2_BALANCED", 1.20, 0.80, 0.55, 0.52, 16),
    B2Variant("B2_STRICT", 1.50, 1.00, 0.60, 0.54, 12),
    B2Variant("B2_NO_FLOW", 1.20, 0.80, 0.55, 0.00, 16),
)

C4_VARIANTS = (
    C4Variant("C4_ABSORPTION", 0.54, 0.52, 0.55, 0.55),
    C4Variant("C4_STRICT", 0.56, 0.54, 0.60, 0.45),
    C4Variant("C4_NO_ABSORPTION", 0.00, 0.52, 0.55, 0.55),
)

B3_VARIANTS = (
    B3Variant("B3_ABSORB_CONFIRM", 1.20, 0.75, 0.52, 0.52, 0.50, 0.45, 4, 20),
    B3Variant("B3_STRICT", 1.35, 0.85, 0.58, 0.55, 0.52, 0.52, 3, 16),
    B3Variant("B3_PRICE_ONLY", 1.20, 0.75, 0.52, 0.00, 0.00, 0.45, 4, 20),
)

C5_VARIANTS = (
    C5Variant("C5_PULLBACK_FLOW", 0.52, 0.50, 0.48, 0.80, 20, 24),
    C5Variant("C5_STRICT", 0.55, 0.52, 0.55, 0.60, 24, 20),
    C5Variant("C5_PRICE_ONLY", 0.00, 0.00, 0.48, 0.80, 20, 24),
)

C6_VARIANTS = (
    C5Variant("C6_MARKET_FLOW", 0.52, 0.50, 0.48, 0.80, 20, 24, True),
    C5Variant("C6_MARKET_STRICT", 0.55, 0.52, 0.55, 0.60, 24, 20, True),
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


def ema(values, period):
    if len(values) < period:
        return None
    alpha = 2.0 / (period + 1.0)
    result = sum(values[:period]) / period
    for value in values[period:]:
        result = alpha * value + (1.0 - alpha) * result
    return result


def atr_value(candles, period=14):
    if len(candles) < period + 1:
        return None
    values = []
    sample = candles[-(period + 1):]
    for previous, current in zip(sample[:-1], sample[1:]):
        values.append(max(
            current["high"] - current["low"],
            abs(current["high"] - previous["close"]),
            abs(current["low"] - previous["close"]),
        ))
    return sum(values) / len(values) if values else None


def candle_metrics(candle, side):
    high = float(candle["high"])
    low = float(candle["low"])
    open_price = float(candle["open"])
    close = float(candle["close"])
    candle_range = high - low
    if candle_range <= 0:
        return {
            "body_ratio": 0.0,
            "close_position": 0.5,
            "direction_ok": False,
            "wick_ratio": 0.0,
        }
    if side == "LONG":
        close_position = (close - low) / candle_range
        wick_ratio = (min(open_price, close) - low) / candle_range
        direction_ok = close > open_price
    else:
        close_position = (high - close) / candle_range
        wick_ratio = (high - max(open_price, close)) / candle_range
        direction_ok = close < open_price
    return {
        "body_ratio": abs(close - open_price) / candle_range,
        "close_position": close_position,
        "direction_ok": direction_ok,
        "wick_ratio": max(0.0, wick_ratio),
    }


def directional_flow_ratio(candles, side, lookback=1):
    sample = candles[-lookback:]
    buy = sum(float(c.get("taker_buy", 0.0)) for c in sample)
    sell = sum(float(c.get("taker_sell", 0.0)) for c in sample)
    total = buy + sell
    if total <= 0:
        return 0.5
    return buy / total if side == "LONG" else sell / total


def opposing_absorption_ratio(candle, side):
    volume = float(candle.get("taker_buy", 0.0)) + float(candle.get("taker_sell", 0.0))
    if volume <= 0:
        return 0.5
    if side == "LONG":
        return float(candle.get("taker_sell", 0.0)) / volume
    return float(candle.get("taker_buy", 0.0)) / volume


def trend_context(candles_4h):
    if len(candles_4h) < 60:
        return None
    closes = [float(candle["close"]) for candle in candles_4h]
    fast = ema(closes, 21)
    slow = ema(closes, 55)
    atr_4h = atr_value(candles_4h)
    _, slow_slope = BOT.ema_slope(closes, 55)
    if fast is None or slow is None or atr_4h is None or slow_slope is None:
        return None
    if fast > slow and closes[-1] > slow and slow_slope > 0:
        side = "LONG"
    elif fast < slow and closes[-1] < slow and slow_slope < 0:
        side = "SHORT"
    else:
        side = None
    window = candles_4h[-30:]
    range_low = min(float(candle["low"]) for candle in window)
    range_high = max(float(candle["high"]) for candle in window)
    return {
        "side": side,
        "fast": fast,
        "slow": slow,
        "atr": atr_4h,
        "range_low": range_low,
        "range_high": range_high,
    }


def btc_market_guard(side, btc_candles_4h, context=None):
    if len(btc_candles_4h) < 60:
        return {"passed": False, "trend_ok": False, "return_ok": False, "return_12h": 0.0}
    context = context if context is not None else trend_context(btc_candles_4h)
    if not context or len(btc_candles_4h) < 4:
        return {"passed": False, "trend_ok": False, "return_ok": False, "return_12h": 0.0}
    return_12h = (
        float(btc_candles_4h[-1]["close"])
        / float(btc_candles_4h[-4]["close"])
        - 1.0
    )
    trend_ok = context["side"] != "SHORT" if side == "LONG" else context["side"] != "LONG"
    return_ok = return_12h >= -0.01 if side == "LONG" else return_12h <= 0.01
    return {
        "passed": trend_ok and return_ok,
        "trend_ok": trend_ok,
        "return_ok": return_ok,
        "return_12h": return_12h,
    }


def first_touch_net(candles, signal_index, side, stop, reward_r, cost_pct, horizon_bars=384):
    entry_index = signal_index + 1
    if entry_index >= len(candles):
        return None
    entry = float(candles[entry_index]["open"])
    risk = entry - stop if side == "LONG" else stop - entry
    if entry <= 0 or risk <= 0:
        return None
    risk_pct = risk / entry
    if risk_pct < 0.004 or risk_pct > 0.03:
        return None
    target = entry + reward_r * risk if side == "LONG" else entry - reward_r * risk
    end = min(len(candles), entry_index + horizon_bars)
    gross_r = 0.0
    outcome = "TIMEOUT"
    exit_time = int(candles[end - 1]["close_time"])
    exit_index = end - 1
    for index in range(entry_index, end):
        candle = candles[index]
        if side == "LONG":
            hit_sl = float(candle["low"]) <= stop
            hit_tp = float(candle["high"]) >= target
        else:
            hit_sl = float(candle["high"]) >= stop
            hit_tp = float(candle["low"]) <= target
        if hit_sl:
            gross_r = -1.0
            outcome = "LOSS"
            exit_time = int(candle["close_time"])
            exit_index = index
            break
        if hit_tp:
            gross_r = reward_r
            outcome = "WIN"
            exit_time = int(candle["close_time"])
            exit_index = index
            break
    else:
        final_close = float(candles[end - 1]["close"])
        gross_r = (
            (final_close - entry) / risk
            if side == "LONG"
            else (entry - final_close) / risk
        )
        gross_r = max(-1.0, min(reward_r, gross_r))

    cost_r = cost_pct / risk_pct
    return {
        "entry": entry,
        "stop": stop,
        "target": target,
        "risk_pct": risk_pct,
        "gross_R": gross_r,
        "cost_R": cost_r,
        "net_R": gross_r - cost_r,
        "outcome": outcome,
        "exit_time": exit_time,
        "exit_index": exit_index,
    }


def max_drawdown(values):
    equity = 0.0
    peak = 0.0
    drawdown = 0.0
    for value in values:
        equity += value
        peak = max(peak, equity)
        drawdown = max(drawdown, peak - equity)
    return drawdown


def summarize(records, result_key):
    ordered = sorted(records, key=lambda item: (item["signal_time"], item["pair"]))
    values = [float(record[result_key]) for record in ordered]
    positive = sum(value for value in values if value > 0)
    negative = -sum(value for value in values if value < 0)
    wins = sum(1 for value in values if value > 0)
    return {
        "trades": len(values),
        "wins": wins,
        "loss_or_timeout": len(values) - wins,
        "winrate_pct": round(100.0 * wins / len(values), 2) if values else 0.0,
        "total_net_R": round(sum(values), 3),
        "avg_net_R": round(statistics.mean(values), 4) if values else 0.0,
        "profit_factor": round(positive / negative, 3) if negative else None,
        "max_drawdown_R": round(max_drawdown(values), 3),
    }


def fold_summaries(records, result_key, start_ms, end_ms, fold_days=30):
    folds = []
    cursor = start_ms
    number = 1
    while cursor < end_ms:
        fold_end = min(end_ms + 1, cursor + fold_days * MS_DAY)
        selected = [
            record for record in records
            if cursor <= record["signal_time"] < fold_end
        ]
        result = summarize(selected, result_key)
        result.update({
            "fold": number,
            "start": datetime.fromtimestamp(cursor / 1000, timezone.utc).date().isoformat(),
            "end": datetime.fromtimestamp((fold_end - 1) / 1000, timezone.utc).date().isoformat(),
        })
        folds.append(result)
        cursor = fold_end
        number += 1
    return folds


def attach_outcomes(candles, signal_index, setup, cost_pct):
    outcomes = {}
    for reward_r, suffix in ((1.5, "1_5R"), (2.0, "2R")):
        result = first_touch_net(
            candles,
            signal_index,
            setup["side"],
            setup["stop"],
            reward_r,
            cost_pct,
        )
        if result is None:
            return None
        outcomes[f"net_R_{suffix}"] = round(result["net_R"], 5)
        outcomes[f"gross_R_{suffix}"] = round(result["gross_R"], 5)
        outcomes[f"outcome_{suffix}"] = result["outcome"]
        outcomes[f"target_{suffix}"] = result["target"]
        outcomes[f"exit_time_{suffix}"] = result["exit_time"]
        outcomes[f"exit_index_{suffix}"] = result["exit_index"]
        outcomes["entry"] = result["entry"]
        outcomes["risk_pct"] = result["risk_pct"]
        outcomes["cost_R"] = result["cost_R"]
    return outcomes


def detect_b2_breakout(closed_4h, variant):
    if len(closed_4h) < 105:
        return None
    c1 = closed_4h[-2]
    c2 = closed_4h[-1]
    history = closed_4h[:-2]
    support, resistance = BOT.support_resistance_multi(
        history,
        min_touches=BOT.SR_MIN_TOUCHES,
        lookback=BOT.SR_LOOKBACK,
    )
    average_volume = statistics.mean(
        float(candle.get("volume", 0.0)) for candle in history[-20:]
    )
    atr_4h = atr_value(history)
    context = trend_context(closed_4h[-199:])
    if average_volume <= 0 or not atr_4h or not context or not context["side"]:
        return None
    side = context["side"]
    level = resistance if side == "LONG" else support
    metrics = candle_metrics(c1, side)
    c1_volume = float(c1.get("volume", 0.0)) / average_volume
    c2_volume = float(c2.get("volume", 0.0)) / average_volume
    if side == "LONG":
        break_distance = (float(c1["close"]) - level) / atr_4h
        price_ok = (
            float(c1["close"]) > level
            and float(c2["close"]) > level
            and float(c2["low"]) >= level - 0.35 * atr_4h
        )
    else:
        break_distance = (level - float(c1["close"])) / atr_4h
        price_ok = (
            float(c1["close"]) < level
            and float(c2["close"]) < level
            and float(c2["high"]) <= level + 0.35 * atr_4h
        )
    if not (
        price_ok
        and 0.10 <= break_distance <= 1.50
        and metrics["direction_ok"]
        and metrics["body_ratio"] >= variant.c1_body_min
        and metrics["close_position"] >= 0.70
        and c1_volume >= variant.c1_volume_min
        and c2_volume >= variant.c2_volume_min
    ):
        return None
    return {
        "side": side,
        "level": level,
        "atr_4h": atr_4h,
        "detected_time": int(c2["close_time"]),
        "expires_time": int(c2["close_time"]) + variant.retest_hours * MS_HOUR,
        "c1_volume_ratio": c1_volume,
        "c2_volume_ratio": c2_volume,
        "break_distance_atr": break_distance,
    }


def simulate_b2(pair, candles_15m, candles_4h, start_ms, end_ms, variant, cost_pct):
    close_times_4h = [int(candle["close_time"]) for candle in candles_4h]
    records = []
    pending = None
    last_4h_count = None
    index = max(60, bisect.bisect_left(
        [int(candle["close_time"]) for candle in candles_15m],
        start_ms,
    ))
    while index < len(candles_15m) - 1:
        candle = candles_15m[index]
        scan_time = int(candle["close_time"])
        if scan_time > end_ms:
            break
        end_4h = bisect.bisect_right(close_times_4h, scan_time)
        if end_4h >= 105 and end_4h != last_4h_count:
            candidate = detect_b2_breakout(candles_4h[:end_4h], variant)
            if candidate and pending is None:
                pending = candidate
            last_4h_count = end_4h
        if not pending or scan_time <= pending["detected_time"]:
            index += 1
            continue
        if scan_time > pending["expires_time"]:
            pending = None
            index += 1
            continue

        side = pending["side"]
        level = pending["level"]
        atr_15m = atr_value(candles_15m[max(0, index - 30):index + 1])
        if not atr_15m:
            index += 1
            continue
        close = float(candle["close"])
        invalid = (
            close < level - 0.35 * atr_15m
            if side == "LONG"
            else close > level + 0.35 * atr_15m
        )
        if invalid:
            pending = None
            index += 1
            continue
        tolerance = 0.20 * atr_15m
        touched = (
            float(candle["low"]) <= level + tolerance
            if side == "LONG"
            else float(candle["high"]) >= level - tolerance
        )
        metrics = candle_metrics(candle, side)
        reclaimed = close > level if side == "LONG" else close < level
        not_extended = abs(close - level) <= 0.60 * atr_15m
        flow = directional_flow_ratio(
            candles_15m[max(0, index - 3):index + 1],
            side,
            lookback=min(4, index + 1),
        )
        if not (
            touched
            and reclaimed
            and not_extended
            and metrics["close_position"] >= 0.65
            and (metrics["direction_ok"] or metrics["wick_ratio"] >= 0.30)
            and flow >= variant.flow_min
        ):
            index += 1
            continue
        stop = (
            min(float(candle["low"]) - 0.10 * atr_15m, level - 0.25 * atr_15m)
            if side == "LONG"
            else max(float(candle["high"]) + 0.10 * atr_15m, level + 0.25 * atr_15m)
        )
        setup = {"side": side, "stop": stop}
        outcomes = attach_outcomes(candles_15m, index, setup, cost_pct)
        if outcomes:
            records.append({
                "strategy": variant.name,
                "pair": pair,
                "side": side,
                "signal_time": scan_time,
                "level": level,
                "flow_ratio": flow,
                "c1_volume_ratio": pending["c1_volume_ratio"],
                "c2_volume_ratio": pending["c2_volume_ratio"],
                "break_distance_atr": pending["break_distance_atr"],
                "stop": stop,
                **outcomes,
            })
            index = max(index, outcomes["exit_index_1_5R"])
        pending = None
        index += 1
    return records


def simulate_b3(pair, candles_15m, candles_4h, start_ms, end_ms, variant, cost_pct):
    close_times_4h = [int(candle["close_time"]) for candle in candles_4h]
    close_times_15m = [int(candle["close_time"]) for candle in candles_15m]
    records = []
    pending = None
    retest_state = None
    last_4h_count = None
    index = max(60, bisect.bisect_left(close_times_15m, start_ms))
    while index < len(candles_15m) - 1:
        candle = candles_15m[index]
        scan_time = int(candle["close_time"])
        if scan_time > end_ms:
            break
        end_4h = bisect.bisect_right(close_times_4h, scan_time)
        if end_4h >= 105 and end_4h != last_4h_count:
            candidate = detect_b2_breakout(candles_4h[:end_4h], variant)
            if candidate and pending is None:
                pending = candidate
                retest_state = None
            last_4h_count = end_4h
        if not pending or scan_time <= pending["detected_time"]:
            index += 1
            continue
        if scan_time > pending["expires_time"]:
            pending = None
            retest_state = None
            index += 1
            continue

        side = pending["side"]
        level = pending["level"]
        atr_15m = atr_value(candles_15m[max(0, index - 30):index + 1])
        if not atr_15m:
            index += 1
            continue
        close = float(candle["close"])
        invalid = (
            close < level - 0.35 * atr_15m
            if side == "LONG"
            else close > level + 0.35 * atr_15m
        )
        if invalid:
            pending = None
            retest_state = None
            index += 1
            continue

        if retest_state is not None:
            age = index - retest_state["idx"]
            broke_retest = (
                float(candle["low"]) < retest_state["extreme"]
                if side == "LONG"
                else float(candle["high"]) > retest_state["extreme"]
            )
            if broke_retest:
                retest_state = None
                index += 1
                continue
            if age > variant.confirmation_bars:
                retest_state = None
                index += 1
                continue
            if age <= 0:
                index += 1
                continue
            metrics = candle_metrics(candle, side)
            confirmed = (
                close > retest_state["high"]
                if side == "LONG"
                else close < retest_state["low"]
            )
            confirmation_flow = directional_flow_ratio([candle], side)
            if not (
                confirmed
                and metrics["direction_ok"]
                and metrics["body_ratio"] >= variant.confirmation_body_min
                and metrics["close_position"] >= 0.65
                and confirmation_flow >= variant.confirmation_flow_min
            ):
                index += 1
                continue
            stop = (
                min(
                    retest_state["extreme"] - 0.10 * retest_state["atr"],
                    level - 0.25 * retest_state["atr"],
                )
                if side == "LONG"
                else max(
                    retest_state["extreme"] + 0.10 * retest_state["atr"],
                    level + 0.25 * retest_state["atr"],
                )
            )
            setup = {"side": side, "stop": stop}
            outcomes = attach_outcomes(candles_15m, index, setup, cost_pct)
            if outcomes:
                records.append({
                    "strategy": variant.name,
                    "pair": pair,
                    "side": side,
                    "signal_time": scan_time,
                    "level": level,
                    "retest_absorption_ratio": retest_state["absorption"],
                    "confirmation_flow_ratio": confirmation_flow,
                    "confirmation_bars": age,
                    "c1_volume_ratio": pending["c1_volume_ratio"],
                    "c2_volume_ratio": pending["c2_volume_ratio"],
                    "break_distance_atr": pending["break_distance_atr"],
                    "stop": stop,
                    **outcomes,
                })
                index = max(index, outcomes["exit_index_1_5R"])
                pending = None
            retest_state = None
            index += 1
            continue

        tolerance = 0.25 * atr_15m
        touched = (
            float(candle["low"]) <= level + tolerance
            if side == "LONG"
            else float(candle["high"]) >= level - tolerance
        )
        metrics = candle_metrics(candle, side)
        reclaimed = close > level if side == "LONG" else close < level
        not_extended = abs(close - level) <= 0.70 * atr_15m
        absorption = opposing_absorption_ratio(candle, side)
        if (
            touched
            and reclaimed
            and not_extended
            and metrics["wick_ratio"] >= 0.20
            and metrics["close_position"] >= 0.55
            and absorption >= variant.retest_absorption_min
        ):
            retest_state = {
                "idx": index,
                "high": float(candle["high"]),
                "low": float(candle["low"]),
                "extreme": float(candle["low"] if side == "LONG" else candle["high"]),
                "atr": atr_15m,
                "absorption": absorption,
            }
        index += 1
    return records


def detect_c4_setup(candles_15m, closed_4h, variant, context=None):
    latest_idx = len(candles_15m) - 1
    if latest_idx < 45 or len(closed_4h) < 60:
        return None
    context = context if context is not None else trend_context(closed_4h)
    if not context or not context["side"]:
        return None
    side = context["side"]
    range_size = context["range_high"] - context["range_low"]
    if range_size <= 0:
        return None
    search_start = max(32, latest_idx - 16)
    search_end = latest_idx - 2
    for sweep_idx in range(search_end, search_start - 1, -1):
        sweep = candles_15m[sweep_idx]
        previous = candles_15m[sweep_idx - 32:sweep_idx]
        atr_15m = atr_value(candles_15m[max(0, sweep_idx - 30):sweep_idx])
        if len(previous) < 32 or not atr_15m:
            continue
        level = (
            min(float(candle["low"]) for candle in previous)
            if side == "LONG"
            else max(float(candle["high"]) for candle in previous)
        )
        extreme = float(sweep["low"] if side == "LONG" else sweep["high"])
        penetration_atr = (
            (level - extreme) / atr_15m
            if side == "LONG"
            else (extreme - level) / atr_15m
        )
        metrics = candle_metrics(sweep, side)
        reclaimed = float(sweep["close"]) > level if side == "LONG" else float(sweep["close"]) < level
        absorption = opposing_absorption_ratio(sweep, side)
        range_position = (extreme - context["range_low"]) / range_size
        location_ok = (
            range_position <= variant.location_limit
            if side == "LONG"
            else range_position >= 1.0 - variant.location_limit
        )
        if not (
            reclaimed
            and 0.08 <= penetration_atr <= 0.90
            and metrics["wick_ratio"] >= 0.25
            and metrics["close_position"] >= 0.60
            and absorption >= variant.absorption_min
            and location_ok
        ):
            continue

        pre_structure = candles_15m[max(0, sweep_idx - 10):sweep_idx]
        mss_level = (
            max(float(candle["high"]) for candle in pre_structure)
            if side == "LONG"
            else min(float(candle["low"]) for candle in pre_structure)
        )
        mss = None
        mss_end = min(latest_idx, sweep_idx + 7)
        for mss_idx in range(sweep_idx + 1, mss_end):
            candidate = candles_15m[mss_idx]
            candidate_metrics = candle_metrics(candidate, side)
            candidate_atr = atr_value(candles_15m[max(0, mss_idx - 30):mss_idx + 1])
            if not candidate_atr:
                continue
            broke = (
                float(candidate["close"]) > mss_level
                if side == "LONG"
                else float(candidate["close"]) < mss_level
            )
            body_atr = abs(float(candidate["close"]) - float(candidate["open"])) / candidate_atr
            flow = directional_flow_ratio([candidate], side)
            if (
                broke
                and candidate_metrics["direction_ok"]
                and candidate_metrics["body_ratio"] >= variant.mss_body_min
                and body_atr >= 0.50
                and flow >= variant.continuation_flow_min
            ):
                mss = {
                    "idx": mss_idx,
                    "atr": candidate_atr,
                    "flow": flow,
                    "body_atr": body_atr,
                }
                break
        if not mss or latest_idx <= mss["idx"] or latest_idx - mss["idx"] > 6:
            continue

        after_sweep = candles_15m[sweep_idx + 1:latest_idx + 1]
        breached = (
            any(float(candle["low"]) < extreme for candle in after_sweep)
            if side == "LONG"
            else any(float(candle["high"]) > extreme for candle in after_sweep)
        )
        if breached:
            continue
        retest = candles_15m[latest_idx]
        tolerance = 0.20 * mss["atr"]
        touched = (
            float(retest["low"]) <= mss_level + tolerance
            if side == "LONG"
            else float(retest["high"]) >= mss_level - tolerance
        )
        retest_metrics = candle_metrics(retest, side)
        reclaimed_mss = (
            float(retest["close"]) > mss_level
            if side == "LONG"
            else float(retest["close"]) < mss_level
        )
        retest_flow = directional_flow_ratio(
            candles_15m[max(0, latest_idx - 1):latest_idx + 1],
            side,
            lookback=2,
        )
        if not (
            touched
            and reclaimed_mss
            and retest_metrics["close_position"] >= 0.60
            and (retest_metrics["direction_ok"] or retest_metrics["wick_ratio"] >= 0.25)
            and retest_flow >= 0.50
        ):
            continue
        stop = (
            extreme - 0.15 * atr_15m
            if side == "LONG"
            else extreme + 0.15 * atr_15m
        )
        return {
            "side": side,
            "stop": stop,
            "sweep_time": int(sweep["open_time"]),
            "sweep_level": level,
            "sweep_extreme": extreme,
            "penetration_atr": penetration_atr,
            "absorption_ratio": absorption,
            "mss_level": mss_level,
            "mss_flow_ratio": mss["flow"],
            "mss_body_atr": mss["body_atr"],
            "retest_flow_ratio": retest_flow,
            "range_position": range_position,
        }
    return None


def build_trend_context_cache(candles_4h):
    return {
        count: trend_context(candles_4h[max(0, count - 199):count])
        for count in range(60, len(candles_4h) + 1)
    }


def simulate_c4(
    pair,
    candles_15m,
    candles_4h,
    start_ms,
    end_ms,
    variant,
    cost_pct,
    context_cache=None,
):
    close_times_4h = [int(candle["close_time"]) for candle in candles_4h]
    close_times_15m = [int(candle["close_time"]) for candle in candles_15m]
    records = []
    seen_sweeps = set()
    index = max(80, bisect.bisect_left(close_times_15m, start_ms))
    while index < len(candles_15m) - 1:
        signal_time = int(candles_15m[index]["close_time"])
        if signal_time > end_ms:
            break
        end_4h = bisect.bisect_right(close_times_4h, signal_time)
        if end_4h < 60:
            index += 1
            continue
        setup = detect_c4_setup(
            candles_15m[max(0, index - 198):index + 1],
            candles_4h[:end_4h],
            variant,
            context=(context_cache or {}).get(end_4h),
        )
        if not setup:
            index += 1
            continue
        event_key = (setup["side"], setup["sweep_time"])
        if event_key in seen_sweeps:
            index += 1
            continue
        seen_sweeps.add(event_key)
        outcomes = attach_outcomes(candles_15m, index, setup, cost_pct)
        if outcomes:
            records.append({
                "strategy": variant.name,
                "pair": pair,
                "side": setup["side"],
                "signal_time": signal_time,
                **{key: value for key, value in setup.items() if key != "side"},
                **outcomes,
            })
            index = max(index, outcomes["exit_index_1_5R"])
        index += 1
    return records


def detect_c5_setup(candles_15m, closed_4h, variant, context=None):
    latest_idx = len(candles_15m) - 1
    minimum_history = variant.sweep_lookback + 15
    if latest_idx < minimum_history or len(closed_4h) < 60:
        return None
    context = context if context is not None else trend_context(closed_4h)
    if not context or not context["side"] or context["atr"] <= 0:
        return None
    side = context["side"]
    search_start = max(variant.sweep_lookback, latest_idx - variant.search_bars)
    search_end = latest_idx - 2
    for sweep_idx in range(search_end, search_start - 1, -1):
        sweep = candles_15m[sweep_idx]
        previous = candles_15m[
            sweep_idx - variant.sweep_lookback:sweep_idx
        ]
        atr_15m = atr_value(candles_15m[max(0, sweep_idx - 30):sweep_idx])
        if len(previous) < variant.sweep_lookback or not atr_15m:
            continue
        level = (
            min(float(candle["low"]) for candle in previous)
            if side == "LONG"
            else max(float(candle["high"]) for candle in previous)
        )
        extreme = float(sweep["low"] if side == "LONG" else sweep["high"])
        penetration_atr = (
            (level - extreme) / atr_15m
            if side == "LONG"
            else (extreme - level) / atr_15m
        )
        metrics = candle_metrics(sweep, side)
        reclaimed = (
            float(sweep["close"]) > level
            if side == "LONG"
            else float(sweep["close"]) < level
        )
        absorption = opposing_absorption_ratio(sweep, side)
        if side == "LONG":
            location_ok = (
                context["slow"] - 0.50 * context["atr"]
                <= extreme
                <= context["fast"] + variant.max_fast_distance_atr * context["atr"]
            )
            fast_distance_atr = (extreme - context["fast"]) / context["atr"]
        else:
            location_ok = (
                context["fast"] - variant.max_fast_distance_atr * context["atr"]
                <= extreme
                <= context["slow"] + 0.50 * context["atr"]
            )
            fast_distance_atr = (context["fast"] - extreme) / context["atr"]
        if not (
            reclaimed
            and 0.05 <= penetration_atr <= 0.85
            and metrics["wick_ratio"] >= 0.20
            and metrics["close_position"] >= 0.55
            and absorption >= variant.absorption_min
            and location_ok
        ):
            continue

        pre_structure = candles_15m[max(0, sweep_idx - 8):sweep_idx]
        mss_level = (
            max(float(candle["high"]) for candle in pre_structure)
            if side == "LONG"
            else min(float(candle["low"]) for candle in pre_structure)
        )
        mss = None
        mss_end = min(latest_idx, sweep_idx + 9)
        for mss_idx in range(sweep_idx + 1, mss_end):
            candidate = candles_15m[mss_idx]
            candidate_metrics = candle_metrics(candidate, side)
            candidate_atr = atr_value(
                candles_15m[max(0, mss_idx - 30):mss_idx + 1]
            )
            if not candidate_atr:
                continue
            broke = (
                float(candidate["close"]) > mss_level
                if side == "LONG"
                else float(candidate["close"]) < mss_level
            )
            body_atr = (
                abs(float(candidate["close"]) - float(candidate["open"]))
                / candidate_atr
            )
            flow = directional_flow_ratio([candidate], side)
            if (
                broke
                and candidate_metrics["direction_ok"]
                and candidate_metrics["body_ratio"] >= variant.mss_body_min
                and body_atr >= 0.40
                and flow >= variant.continuation_flow_min
            ):
                mss = {
                    "idx": mss_idx,
                    "atr": candidate_atr,
                    "flow": flow,
                    "body_atr": body_atr,
                }
                break
        if not mss or latest_idx <= mss["idx"] or latest_idx - mss["idx"] > 8:
            continue

        after_sweep = candles_15m[sweep_idx + 1:latest_idx + 1]
        breached = (
            any(float(candle["low"]) < extreme for candle in after_sweep)
            if side == "LONG"
            else any(float(candle["high"]) > extreme for candle in after_sweep)
        )
        if breached:
            continue
        retest = candles_15m[latest_idx]
        tolerance = 0.25 * mss["atr"]
        touched = (
            float(retest["low"]) <= mss_level + tolerance
            if side == "LONG"
            else float(retest["high"]) >= mss_level - tolerance
        )
        retest_metrics = candle_metrics(retest, side)
        reclaimed_mss = (
            float(retest["close"]) > mss_level
            if side == "LONG"
            else float(retest["close"]) < mss_level
        )
        retest_flow = directional_flow_ratio(
            candles_15m[max(0, latest_idx - 1):latest_idx + 1],
            side,
            lookback=2,
        )
        if not (
            touched
            and reclaimed_mss
            and retest_metrics["close_position"] >= 0.55
            and (
                retest_metrics["direction_ok"]
                or retest_metrics["wick_ratio"] >= 0.20
            )
            and retest_flow >= 0.48
        ):
            continue
        stop = (
            extreme - 0.12 * atr_15m
            if side == "LONG"
            else extreme + 0.12 * atr_15m
        )
        return {
            "side": side,
            "stop": stop,
            "sweep_time": int(sweep["open_time"]),
            "sweep_level": level,
            "sweep_extreme": extreme,
            "penetration_atr": penetration_atr,
            "absorption_ratio": absorption,
            "mss_level": mss_level,
            "mss_flow_ratio": mss["flow"],
            "mss_body_atr": mss["body_atr"],
            "retest_flow_ratio": retest_flow,
            "fast_distance_atr": fast_distance_atr,
        }
    return None


def simulate_c5(
    pair,
    candles_15m,
    candles_4h,
    start_ms,
    end_ms,
    variant,
    cost_pct,
    context_cache=None,
    btc_candles_4h=None,
    btc_context_cache=None,
):
    close_times_4h = [int(candle["close_time"]) for candle in candles_4h]
    close_times_15m = [int(candle["close_time"]) for candle in candles_15m]
    btc_close_times = [int(candle["close_time"]) for candle in (btc_candles_4h or [])]
    records = []
    seen_sweeps = set()
    index = max(80, bisect.bisect_left(close_times_15m, start_ms))
    while index < len(candles_15m) - 1:
        signal_time = int(candles_15m[index]["close_time"])
        if signal_time > end_ms:
            break
        end_4h = bisect.bisect_right(close_times_4h, signal_time)
        if end_4h < 60:
            index += 1
            continue
        setup = detect_c5_setup(
            candles_15m[max(0, index - 198):index + 1],
            candles_4h[:end_4h],
            variant,
            context=(context_cache or {}).get(end_4h),
        )
        if not setup:
            index += 1
            continue
        event_key = (setup["side"], setup["sweep_time"])
        if event_key in seen_sweeps:
            index += 1
            continue
        market = {"passed": True, "trend_ok": True, "return_ok": True, "return_12h": 0.0}
        if variant.market_guard:
            btc_end = bisect.bisect_right(btc_close_times, signal_time)
            btc_slice = (btc_candles_4h or [])[:btc_end]
            market = btc_market_guard(
                setup["side"],
                btc_slice,
                context=(btc_context_cache or {}).get(btc_end),
            )
            if not market["passed"]:
                seen_sweeps.add(event_key)
                index += 1
                continue
        seen_sweeps.add(event_key)
        outcomes = attach_outcomes(candles_15m, index, setup, cost_pct)
        if outcomes:
            records.append({
                "strategy": variant.name,
                "pair": pair,
                "side": setup["side"],
                "signal_time": signal_time,
                "btc_return_12h": market["return_12h"],
                "btc_trend_ok": market["trend_ok"],
                **{key: value for key, value in setup.items() if key != "side"},
                **outcomes,
            })
            index = max(index, outcomes["exit_index_1_5R"])
        index += 1
    return records


def variant_report(records, start_ms, end_ms):
    report = {"records": records}
    for suffix in ("1_5R", "2R"):
        key = f"net_R_{suffix}"
        report[suffix] = {
            "overall": summarize(records, key),
            "long": summarize([r for r in records if r["side"] == "LONG"], key),
            "short": summarize([r for r in records if r["side"] == "SHORT"], key),
            "folds_30d": fold_summaries(records, key, start_ms, end_ms),
        }
    return report


def main():
    parser = argparse.ArgumentParser(description="Leakage-safe B3/C5 research replay")
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
    warmup_4h = 45 * MS_DAY
    for number, pair in enumerate(pairs, 1):
        print(f"load {number}/{len(pairs)} {pair}", flush=True)
        try:
            data[pair] = {
                "15m": market.klines(pair, "15m", start_ms - 3 * MS_DAY, end_ms + 5 * MS_DAY),
                "4h": market.klines(pair, "4h", start_ms - warmup_4h, end_ms + 4 * MS_HOUR),
            }
            data[pair]["context_4h"] = build_trend_context_cache(data[pair]["4h"])
        except Exception as exc:
            errors.append(f"{pair}: {type(exc).__name__}: {exc}")

    result = {
        "engine": "B3_C6_RESEARCH",
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
        "strategy_c": {},
        "errors": errors,
    }

    for variant in B3_VARIANTS:
        print(f"simulate {variant.name}", flush=True)
        records = []
        for pair, candles in data.items():
            records.extend(simulate_b3(
                pair,
                candles["15m"],
                candles["4h"],
                start_ms,
                end_ms,
                variant,
                args.cost_pct,
            ))
        report = variant_report(records, start_ms, end_ms)
        report["parameters"] = asdict(variant)
        result["strategy_b"][variant.name] = report

    btc_data = data.get("BTCUSDT", {})
    for variant in C6_VARIANTS:
        print(f"simulate {variant.name}", flush=True)
        records = []
        for pair, candles in data.items():
            records.extend(simulate_c5(
                pair,
                candles["15m"],
                candles["4h"],
                start_ms,
                end_ms,
                variant,
                args.cost_pct,
                candles["context_4h"],
                btc_data.get("4h", []),
                btc_data.get("context_4h", {}),
            ))
        report = variant_report(records, start_ms, end_ms)
        report["parameters"] = asdict(variant)
        result["strategy_c"][variant.name] = report

    write_json(args.output, result)
    concise = {
        group: {
            name: {
                "1_5R": item["1_5R"]["overall"],
                "2R": item["2R"]["overall"],
            }
            for name, item in result[group].items()
        }
        for group in ("strategy_b", "strategy_c")
    }
    print(json.dumps({"results": concise, "errors": errors, "output": args.output}, indent=2))


if __name__ == "__main__":
    main()
