import argparse
import bisect
import importlib.util
import json
import pathlib
import statistics


ROOT = pathlib.Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("kt_bot_c3_replay", ROOT / "v3_swing_bot_fixed.py")
BOT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(BOT)


def load_market_file(cache_dir, symbol, interval):
    matches = sorted(cache_dir.glob(f"{symbol}_{interval}_*.json"))
    if not matches:
        raise FileNotFoundError(f"cache missing: {symbol} {interval}")
    with matches[-1].open("r", encoding="utf-8") as handle:
        return json.load(handle)


def first_touch(candles, start_index, signal, horizon_bars=7 * 24 * 4):
    side = signal["bias"]
    sl = float(signal["sl"])
    tp = float(signal["tp"])
    end = min(len(candles), start_index + horizon_bars)
    for index in range(start_index, end):
        candle = candles[index]
        hit_tp = candle["high"] >= tp if side == "LONG" else candle["low"] <= tp
        hit_sl = candle["low"] <= sl if side == "LONG" else candle["high"] >= sl
        if hit_sl:
            return "LOSS", -1.0, int(candle["close_time"]), index
        if hit_tp:
            rr = abs(tp - float(signal["entry"])) / abs(float(signal["entry"]) - sl)
            return "WIN", rr, int(candle["close_time"]), index
    return "TIMEOUT", 0.0, int(candles[end - 1]["close_time"]), end - 1


def summarize(records):
    closed = [record for record in records if record["outcome"] in ("WIN", "LOSS")]
    wins = [record for record in closed if record["outcome"] == "WIN"]
    losses = [record for record in closed if record["outcome"] == "LOSS"]
    positive = sum(record["result_R"] for record in wins)
    negative = abs(sum(record["result_R"] for record in losses))
    return {
        "signals": len(records),
        "closed": len(closed),
        "wins": len(wins),
        "losses": len(losses),
        "timeouts": len(records) - len(closed),
        "win_rate_pct": round(len(wins) / len(closed) * 100, 2) if closed else 0.0,
        "total_R": round(sum(record["result_R"] for record in closed), 3),
        "avg_R": round(statistics.mean(record["result_R"] for record in closed), 3) if closed else 0.0,
        "profit_factor": round(positive / negative, 3) if negative else None,
        "median_planned_RR": round(statistics.median(record["planned_RR"] for record in records), 3) if records else 0.0,
    }


def replay_pair(symbol, candles_15m, candles_4h, market_regime_at, days):
    records = []
    close_times_4h = [int(candle["close_time"]) for candle in candles_4h]
    blocked_until = {"LONG": 0, "SHORT": 0}
    start_index = max(200, len(candles_15m) - days * 24 * 4)
    index = start_index
    while index < len(candles_15m) - 1:
        timestamp = int(candles_15m[index]["close_time"])
        closed_4h_count = bisect.bisect_right(close_times_4h, timestamp)
        if closed_4h_count < 60 or closed_4h_count >= len(candles_4h):
            index += 1
            continue

        window_15m = candles_15m[max(0, index - 198):index + 2]
        window_4h = candles_4h[max(0, closed_4h_count - 199):closed_4h_count + 1]
        confirmed_4h = window_4h[:-1]
        closes_4h = [candle["close"] for candle in confirmed_4h]
        ema55, slope55 = BOT.ema_slope(closes_4h, BOT.EMA_SLOW)
        if ema55 is None or slope55 is None:
            index += 1
            continue
        trend = (
            "BULLISH" if closes_4h[-1] > ema55 and slope55 > 0
            else "BEARISH" if closes_4h[-1] < ema55 and slope55 < 0
            else "SIDEWAYS"
        )
        signal = BOT.detect_smart_money_c_v3_shadow(
            symbol, window_15m, window_4h, trend, funding=None
        )
        if not signal or timestamp < blocked_until[signal["bias"]]:
            index += 1
            continue

        outcome, result_r, exit_time, exit_index = first_touch(candles_15m, index + 1, signal)
        alternative_results = {}
        entry = float(signal["entry"])
        sl = float(signal["sl"])
        risk = abs(entry - sl)
        for rr_value, key in ((1.0, "1R"), (1.5, "1_5R"), (2.0, "2R")):
            alternative_signal = dict(signal)
            alternative_signal["tp"] = (
                entry + rr_value * risk if signal["bias"] == "LONG"
                else entry - rr_value * risk
            )
            alt_outcome, alt_result_r, _, _ = first_touch(
                candles_15m, index + 1, alternative_signal
            )
            alternative_results[f"outcome_{key}"] = alt_outcome
            alternative_results[f"result_{key}"] = round(alt_result_r, 4)
        blocked_until[signal["bias"]] = exit_time
        market_regime = market_regime_at(timestamp)
        market_aligned = (
            signal["bias"] == "LONG" and market_regime["direction"] == "BULLISH"
        ) or (
            signal["bias"] == "SHORT" and market_regime["direction"] == "BEARISH"
        )
        records.append({
            "timestamp": timestamp,
            "pair": symbol,
            "side": signal["bias"],
            "outcome": outcome,
            "result_R": round(result_r, 4),
            "planned_RR": float(signal["meta"]["actual_rr"]),
            "entry": entry,
            "sl": sl,
            "tp": float(signal["tp"]),
            "countertrend": bool(signal["meta"]["smc_countertrend"]),
            "has_fvg": bool(signal["meta"]["smc_has_fvg"]),
            "zone_source": signal["meta"]["smc_zone_source"],
            "mss_score": int(signal["meta"]["smc_displacement_score"]),
            "range_position": float(signal["meta"]["smc_range_position"]),
            "sweep_wick_ratio": float(signal["meta"]["smc_sweep_wick_ratio"]),
            "sweep_vol_ratio": float(signal["meta"]["smc_sweep_vol_ratio"]),
            "entry_path": signal["meta"]["entry_path"],
            "market_direction": market_regime["direction"],
            "market_aligned": market_aligned,
            "exit_time": exit_time,
            **alternative_results,
        })
        index = max(index + 1, exit_index)
    return records


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--cache-dir", default=str(ROOT / ".audit" / "2026-07-22" / "market_cache_21d"))
    parser.add_argument("--pairs-file", default=str(ROOT / ".audit" / "2026-07-22" / "dynamic_pairs_cache.json"))
    parser.add_argument("--max-pairs", type=int, default=30)
    parser.add_argument("--days", type=int, default=21)
    parser.add_argument("--output", default=str(ROOT / ".audit" / "2026-07-22" / "strategy_c_v3_replay_21d.json"))
    args = parser.parse_args()

    cache_dir = pathlib.Path(args.cache_dir)
    with pathlib.Path(args.pairs_file).open("r", encoding="utf-8") as handle:
        pairs_data = json.load(handle)
    pairs = BOT._limit_pair_universe(pairs_data.get("pairs", []), args.max_pairs)

    core_data = {
        pair: load_market_file(cache_dir, pair, "4h")
        for pair in BOT.QUALITY_MARKET_CORE_PAIRS
    }
    core_close_times = {
        pair: [int(candle["close_time"]) for candle in candles]
        for pair, candles in core_data.items()
    }
    regime_cache = {}

    def market_regime_at(timestamp):
        cache_key = timestamp // (4 * 60 * 60 * 1000)
        if cache_key in regime_cache:
            return regime_cache[cache_key]
        windows = {}
        for pair, candles in core_data.items():
            closed_count = bisect.bisect_right(core_close_times[pair], timestamp)
            if closed_count >= 60 and closed_count < len(candles):
                windows[pair] = candles[max(0, closed_count - 79):closed_count + 1]
        regime_cache[cache_key] = BOT.classify_quality_market_regime(windows)
        return regime_cache[cache_key]

    records = []
    errors = []
    for pair in pairs:
        try:
            candles_15m = load_market_file(cache_dir, pair, "15m")
            candles_4h = load_market_file(cache_dir, pair, "4h")
            pair_records = replay_pair(pair, candles_15m, candles_4h, market_regime_at, args.days)
            records.extend(pair_records)
            print(f"{pair}: {len(pair_records)} signals", flush=True)
        except Exception as exc:
            errors.append(f"{pair}: {type(exc).__name__}: {exc}")

    timestamps = sorted(record["timestamp"] for record in records)
    split = timestamps[len(timestamps) // 2] if timestamps else 0
    result = {
        "engine": "C3_SHADOW",
        "method": "first-touch OHLC; same-candle ambiguity is counted as loss",
        "pair_count": len(pairs),
        "pairs": pairs,
        "overall": summarize(records),
        "train_half": summarize([record for record in records if record["timestamp"] < split]),
        "validation_half": summarize([record for record in records if record["timestamp"] >= split]),
        "long": summarize([record for record in records if record["side"] == "LONG"]),
        "short": summarize([record for record in records if record["side"] == "SHORT"]),
        "countertrend": summarize([record for record in records if record["countertrend"]]),
        "market_aligned": summarize([record for record in records if record["market_aligned"]]),
        "market_not_aligned": summarize([record for record in records if not record["market_aligned"]]),
        "with_fvg": summarize([record for record in records if record["has_fvg"]]),
        "without_fvg": summarize([record for record in records if not record["has_fvg"]]),
        "errors": errors,
        "records": records,
    }
    output = pathlib.Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(result, handle, indent=2, ensure_ascii=True)
        handle.write("\n")
    print(json.dumps({key: result[key] for key in (
        "overall", "train_half", "validation_half", "long", "short", "countertrend",
        "market_aligned", "market_not_aligned",
        "with_fvg", "without_fvg", "errors",
    )}, indent=2))


if __name__ == "__main__":
    main()
