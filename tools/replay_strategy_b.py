import argparse
import bisect
import json
import pathlib
import statistics
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone

import strategy_evidence_audit as audit


BOT = audit.BOT


@dataclass(frozen=True)
class Variant:
    name: str
    anchored_levels: bool = True
    exempt_breakout_from_sweep: bool = False
    c1_volume_min: float = 1.5
    c2_volume_min: float = 1.2
    breakout_buffer_pct: float = 0.003
    retest_tolerance_pct: float = 0.01
    rejection_wick_min: float = 0.38
    orderflow_mode: str = "full"


VARIANTS = (
    Variant("current_level_bug", anchored_levels=False),
    Variant("anchored_with_sweep_guard"),
    Variant("anchored_sweep_exempt", exempt_breakout_from_sweep=True),
    Variant(
        "anchored_sweep_exempt_retest_1_5pct",
        exempt_breakout_from_sweep=True,
        retest_tolerance_pct=0.015,
    ),
    Variant(
        "anchored_sweep_exempt_relaxed_volume",
        exempt_breakout_from_sweep=True,
        c1_volume_min=1.3,
        c2_volume_min=1.0,
    ),
    Variant(
        "anchored_with_sweep_ratio_only",
        orderflow_mode="ratio_only",
    ),
    Variant(
        "anchored_with_sweep_no_orderflow",
        orderflow_mode="off",
    ),
    Variant(
        "anchored_sweep_exempt_ratio_only",
        exempt_breakout_from_sweep=True,
        orderflow_mode="ratio_only",
    ),
    Variant(
        "anchored_sweep_exempt_no_orderflow",
        exempt_breakout_from_sweep=True,
        orderflow_mode="off",
    ),
)


def read_json(path):
    with open(path, "r", encoding="utf-8-sig") as handle:
        return json.load(handle)


def write_json(path, value):
    path = pathlib.Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(value, handle, ensure_ascii=True, indent=2)
        handle.write("\n")


def breakout_reference_window(candles_4h, anchored=True):
    if len(candles_4h) < BOT.VOLUME_AVG_LOOKBACK + 4:
        return []
    # Full live input ends with: [... history, C1, C2, incomplete]. Levels for
    # breakout validation must be frozen before C1 and C2 occur.
    return candles_4h[:-3] if anchored else candles_4h[:-1]


def breakout_candidate(candles_4h, variant):
    history = breakout_reference_window(candles_4h, variant.anchored_levels)
    if not history:
        return None
    support, resistance = BOT.support_resistance_multi(
        history,
        min_touches=BOT.SR_MIN_TOUCHES,
        lookback=BOT.SR_LOOKBACK,
    )
    c1 = candles_4h[-3]
    c2 = candles_4h[-2]
    volume_window = candles_4h[:-3][-BOT.VOLUME_AVG_LOOKBACK:]
    average_volume = (
        sum(float(c.get("volume", 0.0)) for c in volume_window) / len(volume_window)
        if volume_window else 0.0
    )
    if average_volume <= 0:
        return None
    c1_ratio = float(c1.get("volume", 0.0)) / average_volume
    c2_ratio = float(c2.get("volume", 0.0)) / average_volume
    bullish_price = (
        c1["close"] > resistance * (1.0 + variant.breakout_buffer_pct)
        and c2["close"] > resistance
    )
    bearish_price = (
        c1["close"] < support * (1.0 - variant.breakout_buffer_pct)
        and c2["close"] < support
    )
    side = "LONG" if bullish_price else ("SHORT" if bearish_price else None)
    level = resistance if side == "LONG" else (support if side == "SHORT" else None)
    return {
        "side": side,
        "support": support,
        "resistance": resistance,
        "level": level,
        "c1": c1,
        "c2": c2,
        "c1_volume_ratio": c1_ratio,
        "c2_volume_ratio": c2_ratio,
        "volume_ok": (
            c1_ratio >= variant.c1_volume_min
            and c2_ratio >= variant.c2_volume_min
        ),
    }


def rejection_ok(candle, side, minimum):
    high = float(candle["high"])
    low = float(candle["low"])
    open_price = float(candle["open"])
    close = float(candle["close"])
    candle_range = high - low
    if candle_range <= 0:
        return False
    if side == "LONG":
        ratio = (min(open_price, close) - low) / candle_range
    else:
        ratio = (high - max(open_price, close)) / candle_range
    return ratio >= minimum


def orderflow_ok(candles_15m, side, mode="full"):
    if mode == "off" or not BOT.ENABLE_ORDERFLOW_CONFIRM:
        return True
    required = BOT.ORDERFLOW_LOOKBACK + BOT.ORDERFLOW_BASELINE_LOOKBACK
    if len(candles_15m) < required:
        return False
    buy_ratio, sell_ratio, _, _ = BOT.taker_ratio(candles_15m, BOT.ORDERFLOW_LOOKBACK)
    baseline = candles_15m[-required:-BOT.ORDERFLOW_LOOKBACK]
    average_buy = sum(c["taker_buy"] for c in baseline) / max(1, len(baseline))
    average_sell = sum(c["taker_sell"] for c in baseline) / max(1, len(baseline))
    latest = candles_15m[-1]
    if side == "LONG":
        ratio_ok = buy_ratio >= BOT.ORDERFLOW_MIN_RATIO
        spike_ok = latest["taker_buy"] >= average_buy * BOT.ORDERFLOW_SPIKE_MULT
    else:
        ratio_ok = sell_ratio >= BOT.ORDERFLOW_MIN_RATIO
        spike_ok = latest["taker_sell"] >= average_sell * BOT.ORDERFLOW_SPIKE_MULT
    return ratio_ok if mode == "ratio_only" else ratio_ok and spike_ok


def compute_breakout_stop(candles_15m, side, entry, level):
    if len(candles_15m) < 21:
        return None
    closes = [c["close"] for c in candles_15m]
    highs = [c["high"] for c in candles_15m]
    lows = [c["low"] for c in candles_15m]
    atr_value = BOT.atr(highs, lows, closes, BOT.ATR_PERIOD)
    if atr_value is None:
        return None
    recent_low = min(c["low"] for c in candles_15m[-20:])
    recent_high = max(c["high"] for c in candles_15m[-20:])
    if side == "LONG":
        sl_level = level * (1.0 - BOT.BREAKOUT_SL_BUFFER_PCT)
        sl_atr = entry - BOT.ATR_MULT * atr_value
        distance_level = abs(entry - sl_level)
        if entry * BOT.MIN_STOP_PCT <= distance_level <= entry * 0.05:
            stop = sl_level
        else:
            stop = min(sl_atr, sl_level)
        stop = min(stop, recent_low * (1.0 - 0.002))
    else:
        sl_level = level * (1.0 + BOT.BREAKOUT_SL_BUFFER_PCT)
        sl_atr = entry + BOT.ATR_MULT * atr_value
        distance_level = abs(entry - sl_level)
        if entry * BOT.MIN_STOP_PCT <= distance_level <= entry * 0.05:
            stop = sl_level
        else:
            stop = max(sl_atr, sl_level)
        stop = max(stop, recent_high * (1.0 + 0.002))
    risk = abs(entry - stop)
    if risk < entry * BOT.MIN_STOP_PCT:
        risk = entry * BOT.MIN_STOP_PCT
        stop = entry - risk if side == "LONG" else entry + risk
    if risk <= 0 or risk > entry * 0.05:
        return None
    return stop, risk


def quality_gates(candles_4h, side):
    closed = candles_4h[:-1]
    closes = [c["close"] for c in closed]
    highs = [c["high"] for c in closed]
    lows = [c["low"] for c in closed]
    trend_ema, slope = BOT.ema_slope(closes, BOT.EMA_SLOW)
    if trend_ema is None or slope is None:
        return {"trend": False, "regime": False, "quality": False, "structure": False}
    expected_side = (
        "LONG" if closes[-1] > trend_ema and slope > 0
        else ("SHORT" if closes[-1] < trend_ema and slope < 0 else None)
    )
    trend_ok = expected_side == side
    regime_ok = BOT.regime_ok_4h(closes, highs, lows)
    snapshot = BOT.quality_local_snapshot(candles_4h, side)
    quality_ok = BOT.quality_live_gate_decision(snapshot, side)[0]
    structure_ok = BOT.market_structure_ok(candles_4h, side)
    return {
        "trend": trend_ok,
        "regime": regime_ok,
        "quality": quality_ok,
        "structure": structure_ok,
        "snapshot": snapshot,
    }


def summarize(records, target="1R"):
    outcome_key = f"outcome_{target}"
    result_key = f"result_R_{target}"
    closed = [record for record in records if record.get(outcome_key) in ("WIN", "LOSS")]
    wins = [record for record in closed if record[outcome_key] == "WIN"]
    values = [float(record.get(result_key, 0.0) or 0.0) for record in closed]
    positive = sum(value for value in values if value > 0)
    negative = -sum(value for value in values if value < 0)
    return {
        "signals": len(records),
        "closed": len(closed),
        "wins": len(wins),
        "losses": len(closed) - len(wins),
        "winrate_pct": round(100.0 * len(wins) / len(closed), 2) if closed else 0.0,
        "total_R": round(sum(values), 3),
        "avg_R": round(statistics.mean(values), 3) if values else 0.0,
        "profit_factor": round(positive / negative, 3) if negative else None,
    }


def segmented_summary(records, split_ms, target="1R"):
    return {
        "train": summarize([r for r in records if r["signal_time"] < split_ms], target),
        "validation": summarize([r for r in records if r["signal_time"] >= split_ms], target),
        "all": summarize(records, target),
    }


def simulate_symbol(symbol, candles_15m, candles_4h, start_ms, end_ms, variant):
    close_times_4h = [c["close_time"] for c in candles_4h]
    close_times_15m = [c["close_time"] for c in candles_15m]
    stages = defaultdict(set)
    records = []
    pending = {"LONG": None, "SHORT": None}
    expiry_count = 0
    next_allowed = start_ms
    index = bisect.bisect_left(close_times_15m, start_ms)
    last_4h_key = None
    cached = None

    while index < len(candles_15m):
        latest = candles_15m[index]
        scan_time = latest["close_time"]
        if scan_time > end_ms:
            break
        if scan_time < start_ms or scan_time < next_allowed:
            index += 1
            continue
        end_4h = bisect.bisect_right(close_times_4h, scan_time)
        if end_4h < 110 or index < 35:
            index += 1
            continue
        current_4h_key = int(candles_4h[end_4h - 1]["open_time"])
        is_new_4h = current_4h_key != last_4h_key
        if is_new_4h:
            closed_4h = candles_4h[max(0, end_4h - 199):end_4h]
            current_4h = closed_4h[-199:] + [audit.synthetic_current(closed_4h[-1])]
            candidate = breakout_candidate(current_4h, variant)
            closes = [c["close"] for c in current_4h[:-1]]
            trend_ema, slope = BOT.ema_slope(closes, BOT.EMA_SLOW)
            target_side = None
            if trend_ema is not None and slope is not None:
                if closes[-1] > trend_ema and slope > 0:
                    target_side = "LONG"
                elif closes[-1] < trend_ema and slope < 0:
                    target_side = "SHORT"
            cached = {
                "current_4h": current_4h,
                "candidate": candidate,
                "target_side": target_side,
                "target_gates": quality_gates(current_4h, target_side) if target_side else None,
                "sweep_blocked": BOT.is_liquidity_sweep(current_4h),
                "last_closed_open_time": int(closed_4h[-1]["open_time"]),
            }
            last_4h_key = current_4h_key
        else:
            current_4h = cached["current_4h"]
            candidate = cached["candidate"]
            target_side = cached["target_side"]

        if is_new_4h and candidate and candidate["side"]:
            candidate_side = candidate["side"]
            event_key = (symbol, candidate_side, int(candidate["c1"]["open_time"]))
            stages["price_break"].add(event_key)
            if candidate["c1_volume_ratio"] >= variant.c1_volume_min:
                stages["c1_volume"].add(event_key)
            if candidate["volume_ok"]:
                stages["c2_volume"].add(event_key)

        for side in ("LONG", "SHORT"):
            item = pending[side]
            if not item:
                continue
            elapsed = (
                cached["last_closed_open_time"] - item["detected_open_time"]
            ) / (4 * 3600 * 1000)
            if elapsed > BOT.RETEST_MAX_CANDLES_4H:
                pending[side] = None
                expiry_count += 1

        if is_new_4h and candidate and candidate["side"] and candidate["volume_ok"]:
            side = candidate["side"]
            event_key = (symbol, side, int(candidate["c1"]["open_time"]))
            gates = quality_gates(current_4h, side)
            if gates["trend"]:
                stages["trend_aligned"].add(event_key)
            if gates["trend"] and gates["regime"]:
                stages["regime"].add(event_key)
            sweep_blocked = cached["sweep_blocked"]
            sweep_allowed = variant.exempt_breakout_from_sweep or not sweep_blocked
            if gates["trend"] and gates["regime"] and sweep_allowed:
                stages["sweep_guard"].add(event_key)
            if gates["trend"] and gates["regime"] and sweep_allowed and gates["quality"]:
                stages["quality"].add(event_key)
            if (
                gates["trend"] and gates["regime"] and sweep_allowed
                and gates["quality"] and gates["structure"]
            ):
                stages["structure"].add(event_key)
                if pending[side] is None:
                    pending[side] = {
                        "event_key": event_key,
                        "side": side,
                        "level": candidate["level"],
                        "detected_open_time": int(candidate["c2"]["open_time"]),
                        "detected_scan_time": scan_time,
                        "c1_volume_ratio": candidate["c1_volume_ratio"],
                        "c2_volume_ratio": candidate["c2_volume_ratio"],
                        "snapshot": gates["snapshot"],
                    }
                    stages["detected"].add(event_key)

        item = pending.get(target_side) if target_side else None
        if item and scan_time > item["detected_scan_time"]:
            gates = cached["target_gates"]
            sweep_allowed = (
                variant.exempt_breakout_from_sweep
                or not cached["sweep_blocked"]
            )
            if gates["regime"] and gates["quality"] and gates["structure"] and sweep_allowed:
                level = item["level"]
                close = latest["close"]
                touched = abs(close - level) / level <= variant.retest_tolerance_pct
                if touched:
                    stages["retest_touch"].add(item["event_key"])
                    previous = candles_15m[index - 1]
                    rejected = (
                        rejection_ok(latest, target_side, variant.rejection_wick_min)
                        or rejection_ok(previous, target_side, variant.rejection_wick_min)
                    )
                    if rejected:
                        stages["rejection"].add(item["event_key"])
                        current_15m = candles_15m[max(0, index - 198):index + 1]
                        if orderflow_ok(current_15m, target_side, variant.orderflow_mode):
                            stages["orderflow"].add(item["event_key"])
                            stop_data = compute_breakout_stop(current_15m, target_side, close, level)
                            if stop_data:
                                stop, risk = stop_data
                                risk_pct = risk / close
                                if risk_pct < BOT.QUALITY_MAX_SL_PCT:
                                    stages["risk"].add(item["event_key"])
                                    tp_1r = close + risk if target_side == "LONG" else close - risk
                                    tp_2r = close + 2.0 * risk if target_side == "LONG" else close - 2.0 * risk
                                    out_1r = audit.first_touch_outcome(
                                        candles_15m, scan_time + 1, target_side,
                                        close, stop, tp_1r,
                                    )
                                    out_2r = audit.first_touch_outcome(
                                        candles_15m, scan_time + 1, target_side,
                                        close, stop, tp_2r,
                                    )
                                    record = {
                                        "pair": symbol,
                                        "side": target_side,
                                        "signal_time": scan_time,
                                        "detected_time": item["detected_scan_time"],
                                        "wait_hours": round(
                                            (scan_time - item["detected_scan_time"]) / 3600000,
                                            2,
                                        ),
                                        "entry": close,
                                        "sl": stop,
                                        "risk_pct": risk_pct,
                                        "level": level,
                                        "c1_volume_ratio": item["c1_volume_ratio"],
                                        "c2_volume_ratio": item["c2_volume_ratio"],
                                        "range_position": gates["snapshot"].get("range_position"),
                                        "outcome_1R": out_1r["outcome"],
                                        "result_R_1R": out_1r["result_R"],
                                        "exit_time_1R": out_1r["exit_time"],
                                        "mfe_R": out_1r["mfe_R"],
                                        "mae_R": out_1r["mae_R"],
                                        "outcome_2R": out_2r["outcome"],
                                        "result_R_2R": out_2r["result_R"],
                                        "exit_time_2R": out_2r["exit_time"],
                                    }
                                    records.append(record)
                                    stages["setup"].add(item["event_key"])
                                    pending[target_side] = None
                                    exit_time = out_1r.get("exit_time")
                                    if exit_time:
                                        cooldown = 4 * 3600000 if out_1r["outcome"] == "LOSS" else 30 * 60000
                                        next_allowed = exit_time + cooldown
                                        index = max(index, bisect.bisect_left(close_times_15m, next_allowed) - 1)
                                    else:
                                        next_allowed = scan_time + 96 * 3600000
        index += 1

    return {
        "stages": {name: len(values) for name, values in sorted(stages.items())},
        "expired": expiry_count,
        "pending_end": sum(1 for value in pending.values() if value),
        "records": records,
    }


def merge_variant_results(symbol_results, split_ms):
    records = [record for result in symbol_results for record in result["records"]]
    stages = defaultdict(int)
    for result in symbol_results:
        for name, count in result["stages"].items():
            stages[name] += count
    return {
        "stages": dict(sorted(stages.items())),
        "expired": sum(result["expired"] for result in symbol_results),
        "pending_end": sum(result["pending_end"] for result in symbol_results),
        "target_1R": segmented_summary(records, split_ms, "1R"),
        "target_2R": segmented_summary(records, split_ms, "2R"),
        "by_side_1R": {
            side: segmented_summary([r for r in records if r["side"] == side], split_ms, "1R")
            for side in ("LONG", "SHORT")
        },
        "records": records,
    }


def journal_b_summary(journal):
    trades = [trade for trade in journal if trade.get("entry_path") == "B"]
    closed = [trade for trade in trades if trade.get("status") in ("WIN", "LOSS")]
    normalized = [
        {
            "outcome_1R": trade.get("status"),
            "result_R_1R": float(trade.get("result_R", 0.0) or 0.0),
        }
        for trade in closed
    ]
    statuses = defaultdict(int)
    for trade in trades:
        statuses[str(trade.get("status", "UNKNOWN"))] += 1
    return {
        "all_records": len(trades),
        "statuses": dict(sorted(statuses.items())),
        "closed_performance": summarize(normalized, "1R"),
        "closed_trades": [
            {
                "pair": trade.get("pair"),
                "side": trade.get("side"),
                "status": trade.get("status"),
                "timestamp": trade.get("timestamp"),
                "result_R": trade.get("result_R"),
                "realized_pnl": trade.get("realized_pnl"),
            }
            for trade in closed
        ],
    }


def main():
    parser = argparse.ArgumentParser(description="Replay and funnel audit for KT Strategy B")
    parser.add_argument("--journal", required=True)
    parser.add_argument("--pairs-cache", required=True)
    parser.add_argument("--cache-dir", required=True)
    parser.add_argument("--start", required=True)
    parser.add_argument("--end", required=True)
    parser.add_argument("--split", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--max-pairs", type=int, default=30)
    parser.add_argument(
        "--variants",
        help="Comma-separated variant names; default runs all variants.",
    )
    args = parser.parse_args()

    start_ms = audit.parse_timestamp(args.start)
    end_ms = audit.parse_timestamp(args.end)
    split_ms = audit.parse_timestamp(args.split)
    symbols = read_json(args.pairs_cache).get("pairs", [])[:args.max_pairs]
    journal = read_json(args.journal)
    market = audit.MarketData(args.cache_dir)
    warmup_ms = 25 * 86400000
    result = {
        "period": {"start": args.start, "split": args.split, "end": args.end},
        "journal_b": journal_b_summary(journal),
        "variants": {},
        "errors": [],
    }

    data = {}
    for index, symbol in enumerate(symbols, 1):
        print(f"load {index}/{len(symbols)} {symbol}", flush=True)
        try:
            data[symbol] = {
                "15m": market.klines(
                    symbol, "15m", start_ms - 14 * 3600000, end_ms + 4 * 86400000
                ),
                "4h": market.klines(
                    symbol, "4h", start_ms - warmup_ms, end_ms + 4 * 3600000
                ),
            }
        except Exception as exc:
            result["errors"].append(f"{symbol}: {exc}")

    selected_names = {
        name.strip() for name in (args.variants or "").split(",") if name.strip()
    }
    variants = [
        variant for variant in VARIANTS
        if not selected_names or variant.name in selected_names
    ]
    missing_names = selected_names - {variant.name for variant in variants}
    if missing_names:
        raise SystemExit(f"unknown variants: {sorted(missing_names)}")

    for variant in variants:
        print(f"variant {variant.name}", flush=True)
        per_symbol = []
        for symbol in symbols:
            if symbol not in data:
                continue
            per_symbol.append(simulate_symbol(
                symbol,
                data[symbol]["15m"],
                data[symbol]["4h"],
                start_ms,
                end_ms,
                variant,
            ))
        result["variants"][variant.name] = merge_variant_results(per_symbol, split_ms)

    write_json(args.output, result)
    concise = {
        name: {
            "stages": item["stages"],
            "1R": item["target_1R"],
            "2R": item["target_2R"],
        }
        for name, item in result["variants"].items()
    }
    print(json.dumps({
        "journal_b": result["journal_b"],
        "variants": concise,
        "errors": result["errors"],
        "output": args.output,
    }, indent=2))


if __name__ == "__main__":
    main()
