import argparse
import bisect
import importlib.util
import json
import math
import pathlib
import statistics
import time
import urllib.parse
import urllib.request
from collections import Counter, defaultdict
from datetime import datetime, timezone


ROOT = pathlib.Path(__file__).resolve().parents[1]
BINANCE_FUTURES = "https://fapi.binance.com"


def load_bot():
    spec = importlib.util.spec_from_file_location("kt_bot_audit", ROOT / "v3_swing_bot_fixed.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


BOT = load_bot()


def read_json(path):
    with open(path, "r", encoding="utf-8-sig") as handle:
        return json.load(handle)


def write_json(path, value):
    path = pathlib.Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2)


def parse_timestamp(value):
    text = value.strip().replace("Z", "+00:00")
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return int(parsed.timestamp() * 1000)


def parse_kline(row):
    volume = float(row[5])
    taker_buy = float(row[9])
    return {
        "open_time": int(row[0]),
        "open": float(row[1]),
        "high": float(row[2]),
        "low": float(row[3]),
        "close": float(row[4]),
        "volume": volume,
        "close_time": int(row[6]),
        "quote_volume": float(row[7]),
        "taker_buy": taker_buy,
        "taker_sell": max(0.0, volume - taker_buy),
    }


class MarketData:
    def __init__(self, cache_dir):
        self.cache_dir = pathlib.Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def klines(self, symbol, interval, start_ms, end_ms):
        cache_path = self.cache_dir / f"{symbol}_{interval}_{start_ms}_{end_ms}.json"
        if cache_path.exists():
            return read_json(cache_path)

        rows = []
        cursor = start_ms
        while cursor <= end_ms:
            params = urllib.parse.urlencode({
                "symbol": symbol,
                "interval": interval,
                "startTime": cursor,
                "endTime": end_ms,
                "limit": 1500,
            })
            url = f"{BINANCE_FUTURES}/fapi/v1/klines?{params}"
            payload = None
            last_error = None
            for attempt in range(4):
                try:
                    request = urllib.request.Request(url, headers={"User-Agent": "KT-Strategy-Audit/1.0"})
                    with urllib.request.urlopen(request, timeout=25) as response:
                        payload = json.loads(response.read().decode("utf-8"))
                    break
                except Exception as exc:
                    last_error = exc
                    time.sleep(1.0 + attempt)
            if payload is None:
                raise RuntimeError(f"market_data_error {symbol} {interval}: {last_error}")
            if not payload:
                break
            rows.extend(parse_kline(row) for row in payload)
            next_cursor = int(payload[-1][6]) + 1
            if next_cursor <= cursor or len(payload) < 1500:
                break
            cursor = next_cursor
            time.sleep(0.06)

        deduped = {row["open_time"]: row for row in rows}
        result = [deduped[key] for key in sorted(deduped)]
        write_json(cache_path, result)
        return result


def ema(values, period):
    if len(values) < period:
        return None
    alpha = 2.0 / (period + 1.0)
    result = sum(values[:period]) / period
    for value in values[period:]:
        result = alpha * value + (1.0 - alpha) * result
    return result


def rsi(values, period=14):
    if len(values) <= period:
        return None
    gains = []
    losses = []
    for previous, current in zip(values[-(period + 1):-1], values[-period:]):
        change = current - previous
        gains.append(max(0.0, change))
        losses.append(max(0.0, -change))
    avg_gain = sum(gains) / period
    avg_loss = sum(losses) / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100.0 - (100.0 / (1.0 + rs))


def true_range_average(candles, period=14):
    if len(candles) < period + 1:
        return None
    ranges = []
    for previous, current in zip(candles[-(period + 1):-1], candles[-period:]):
        ranges.append(max(
            current["high"] - current["low"],
            abs(current["high"] - previous["close"]),
            abs(current["low"] - previous["close"]),
        ))
    return sum(ranges) / len(ranges)


def pivot_structure(candles):
    window = candles[-50:]
    highs = BOT._smc_pivot_levels(window, "HIGH", left=2, right=2)
    lows = BOT._smc_pivot_levels(window, "LOW", left=2, right=2)
    if len(highs) < 2 or len(lows) < 2:
        return "UNKNOWN"
    higher_high = highs[-1]["level"] > highs[-2]["level"]
    higher_low = lows[-1]["level"] > lows[-2]["level"]
    if higher_high and higher_low:
        return "BULLISH"
    if not higher_high and not higher_low:
        return "BEARISH"
    return "MIXED"


def four_hour_context(candles):
    if len(candles) < 60:
        return None
    closes = [c["close"] for c in candles]
    close = closes[-1]
    fast = ema(closes, 21)
    slow = ema(closes, 55)
    atr_value = true_range_average(candles)
    window = candles[-30:]
    range_low = min(c["low"] for c in window)
    range_high = max(c["high"] for c in window)
    range_position = (close - range_low) / (range_high - range_low) if range_high > range_low else 0.5
    ret_12h = close / closes[-4] - 1.0 if len(closes) >= 4 else 0.0
    ret_24h = close / closes[-7] - 1.0 if len(closes) >= 7 else 0.0
    return {
        "close": close,
        "ema21": fast,
        "ema55": slow,
        "ema_alignment": "BULLISH" if fast > slow else "BEARISH",
        "structure": pivot_structure(candles),
        "range_position": max(0.0, min(1.0, range_position)),
        "rsi14": rsi(closes),
        "atr_pct": atr_value / close if atr_value and close else None,
        "ret_12h": ret_12h,
        "ret_24h": ret_24h,
    }


def candle_slice_at(candles, close_times, timestamp_ms, minimum=0):
    end = bisect.bisect_right(close_times, timestamp_ms)
    if end < minimum:
        return []
    return candles[:end]


def side_matches(value, side, neutral=0.0):
    return value >= neutral if side == "LONG" else value <= -neutral


def first_touch_outcome(candles, entry_time, side, entry, sl, tp, horizon_hours=96):
    risk = abs(entry - sl)
    if risk <= 0:
        return {"outcome": "INVALID"}
    horizon_ms = horizon_hours * 3600 * 1000
    future = [c for c in candles if c["open_time"] >= entry_time and c["open_time"] <= entry_time + horizon_ms]
    mfe = 0.0
    mae = 0.0
    for candle in future:
        if side == "LONG":
            mfe = max(mfe, (candle["high"] - entry) / risk)
            mae = max(mae, (entry - candle["low"]) / risk)
            hit_sl = candle["low"] <= sl
            hit_tp = candle["high"] >= tp
        else:
            mfe = max(mfe, (entry - candle["low"]) / risk)
            mae = max(mae, (candle["high"] - entry) / risk)
            hit_sl = candle["high"] >= sl
            hit_tp = candle["low"] <= tp
        if hit_sl and hit_tp:
            return {"outcome": "LOSS", "result_R": -1.0, "mfe_R": mfe, "mae_R": mae, "exit_time": candle["close_time"]}
        if hit_sl:
            return {"outcome": "LOSS", "result_R": -1.0, "mfe_R": mfe, "mae_R": mae, "exit_time": candle["close_time"]}
        if hit_tp:
            reward_r = abs(tp - entry) / risk
            return {"outcome": "WIN", "result_R": reward_r, "mfe_R": mfe, "mae_R": mae, "exit_time": candle["close_time"]}
    return {"outcome": "OPEN", "result_R": 0.0, "mfe_R": mfe, "mae_R": mae, "exit_time": None}


def summarize_records(records, result_key="result_R"):
    closed = [record for record in records if record.get("outcome") in ("WIN", "LOSS")]
    wins = [record for record in closed if record["outcome"] == "WIN"]
    results = [float(record.get(result_key, 0.0) or 0.0) for record in closed]
    positive = sum(value for value in results if value > 0)
    negative = -sum(value for value in results if value < 0)
    return {
        "signals": len(records),
        "closed": len(closed),
        "wins": len(wins),
        "losses": len(closed) - len(wins),
        "winrate_pct": round(100.0 * len(wins) / len(closed), 2) if closed else 0.0,
        "total_R": round(sum(results), 3),
        "avg_R": round(statistics.mean(results), 3) if results else 0.0,
        "profit_factor": round(positive / negative, 3) if negative > 0 else None,
    }


def audit_real_trades(journal, market, start_ms, end_ms, warmup_ms):
    trades = [
        trade for trade in journal
        if start_ms <= int(trade.get("timestamp", 0) or 0) <= end_ms
        and trade.get("status") in ("WIN", "LOSS")
    ]
    symbols = sorted({trade["pair"] for trade in trades} | {"BTCUSDT"})
    data_4h = {}
    data_15m = {}
    for index, symbol in enumerate(symbols, 1):
        print(f"market real {index}/{len(symbols)} {symbol}", flush=True)
        data_4h[symbol] = market.klines(symbol, "4h", start_ms - warmup_ms, end_ms + 2 * 86400000)
        data_15m[symbol] = market.klines(symbol, "15m", start_ms - 86400000, end_ms + 4 * 86400000)

    close_times_4h = {symbol: [c["close_time"] for c in candles] for symbol, candles in data_4h.items()}
    records = []
    for trade in trades:
        symbol = trade["pair"]
        timestamp = int(trade["timestamp"])
        candles = candle_slice_at(data_4h[symbol], close_times_4h[symbol], timestamp, 60)
        btc_candles = candle_slice_at(data_4h["BTCUSDT"], close_times_4h["BTCUSDT"], timestamp, 60)
        context = four_hour_context(candles)
        btc_context = four_hour_context(btc_candles)
        if not context or not btc_context:
            continue
        side = trade["side"]
        structure_match = context["structure"] == ("BULLISH" if side == "LONG" else "BEARISH")
        ema_match = context["ema_alignment"] == ("BULLISH" if side == "LONG" else "BEARISH")
        location_ok = context["range_position"] <= 0.72 if side == "LONG" else context["range_position"] >= 0.28
        rsi_ok = context["rsi14"] <= 66.0 if side == "LONG" else context["rsi14"] >= 34.0
        momentum_ok = side_matches(context["ret_12h"], side)
        btc_ok = True
        if symbol != "BTCUSDT":
            btc_ok = btc_context["ret_12h"] >= -0.01 if side == "LONG" else btc_context["ret_12h"] <= 0.01

        entry = float(trade["entry"])
        sl = float(trade["sl"])
        tp_1r = entry + abs(entry - sl) if side == "LONG" else entry - abs(entry - sl)
        path = first_touch_outcome(data_15m[symbol], timestamp, side, entry, sl, tp_1r)
        records.append({
            "timestamp": timestamp,
            "pair": symbol,
            "side": side,
            "status": trade["status"],
            "journal_result_R": float(trade.get("result_R") or 0.0),
            "path_1R_outcome": path["outcome"],
            "path_mfe_R": round(float(path.get("mfe_R", 0.0)), 3),
            "path_mae_R": round(float(path.get("mae_R", 0.0)), 3),
            "context": {
                **{key: (round(value, 5) if isinstance(value, float) else value) for key, value in context.items()},
                "btc_ret_12h": round(btc_context["ret_12h"], 5),
            },
            "guards": {
                "strict_structure": structure_match,
                "ema21_55_alignment": ema_match,
                "location_not_exhausted": location_ok,
                "rsi_not_exhausted": rsi_ok,
                "momentum_12h_alignment": momentum_ok,
                "btc_regime_not_opposite": btc_ok,
                "quality_v2": structure_match and ema_match and location_ok and rsi_ok and btc_ok,
            },
        })

    guard_stats = {}
    guard_names = sorted({name for record in records for name in record["guards"]})
    for name in guard_names:
        selected = [record for record in records if record["guards"][name]]
        normalized = [
            {"outcome": record["status"], "result_R": record["journal_result_R"]}
            for record in selected
        ]
        guard_stats[name] = summarize_records(normalized)

    base = [
        {"outcome": record["status"], "result_R": record["journal_result_R"]}
        for record in records
    ]
    return {
        "summary": summarize_records(base),
        "by_side": {
            side: summarize_records([
                {"outcome": record["status"], "result_R": record["journal_result_R"]}
                for record in records if record["side"] == side
            ])
            for side in ("LONG", "SHORT")
        },
        "guard_stats": guard_stats,
        "records": records,
    }


def synthetic_current(last_closed):
    item = dict(last_closed)
    item["open_time"] = last_closed["close_time"] + 1
    item["close_time"] = item["open_time"] + 4 * 3600 * 1000 - 1
    item["open"] = last_closed["close"]
    item["high"] = last_closed["close"]
    item["low"] = last_closed["close"]
    item["volume"] = 0.0
    item["taker_buy"] = 0.0
    item["taker_sell"] = 0.0
    return item


def c2_retest_diagnostic(candles_15m, sweep, mss, location, side):
    closed = candles_15m[:-1]
    latest_idx = len(closed) - 1
    if latest_idx <= mss["idx"]:
        return "retest_not_after_mss"
    if latest_idx - sweep["idx"] > BOT.SMC_SETUP_MAX_AGE_15M:
        return "setup_stale"

    after_sweep = closed[sweep["idx"] + 1:latest_idx + 1]
    if side == "LONG" and any(c["low"] < sweep["extreme"] for c in after_sweep):
        return "sweep_invalidated"
    if side == "SHORT" and any(c["high"] > sweep["extreme"] for c in after_sweep):
        return "sweep_invalidated"

    impulse = closed[sweep["idx"]:mss["idx"] + 1]
    opposite = [
        candle for candle in impulse
        if (candle["close"] < candle["open"] if side == "LONG" else candle["close"] > candle["open"])
    ]
    order_block = opposite[-1] if opposite else sweep["candle"]
    ob_low = min(order_block["open"], order_block["close"])
    ob_high = max(order_block["open"], order_block["close"])
    fvg = BOT._smc_find_fvg(closed, sweep["idx"], mss["idx"], side)
    if BOT.SMC_REQUIRE_FVG and not fvg:
        return "fvg_missing"
    if fvg:
        overlap_low = max(ob_low, fvg["area_low"])
        overlap_high = min(ob_high, fvg["area_high"])
        if overlap_low < overlap_high:
            area_low, area_high = overlap_low, overlap_high
        else:
            area_low, area_high = fvg["area_low"], fvg["area_high"]
    else:
        area_low, area_high = ob_low, ob_high

    zone_mid = (area_low + area_high) / 2.0
    if zone_mid <= 0 or area_high <= area_low:
        return "zone_invalid"
    if (area_high - area_low) / zone_mid > BOT.SMC_MAX_ZONE_WIDTH_PCT:
        return "zone_too_wide"

    retest = closed[-1]
    tolerance = zone_mid * BOT.SMC_RETEST_TOLERANCE_PCT
    touched = retest["low"] <= area_high + tolerance and retest["high"] >= area_low - tolerance
    if not touched:
        return "retest_not_touched"
    if not area_low - tolerance <= retest["close"] <= area_high + tolerance:
        return "retest_close_outside"

    metrics = BOT._smc_candle_metrics(retest, side)
    if side == "LONG":
        reaction_ok = retest["close"] >= zone_mid and (metrics["direction_ok"] or metrics["wick_ratio"] >= 0.25)
        sl = sweep["extreme"] * (1.0 - BOT.SMC_SL_BUFFER_PCT)
        targets = sorted(level for level in location["target_levels"] if level > retest["close"])
    else:
        reaction_ok = retest["close"] <= zone_mid and (metrics["direction_ok"] or metrics["wick_ratio"] >= 0.25)
        sl = sweep["extreme"] * (1.0 + BOT.SMC_SL_BUFFER_PCT)
        targets = sorted((level for level in location["target_levels"] if level < retest["close"]), reverse=True)
    if not reaction_ok:
        return "retest_no_reaction"
    if not targets:
        return "target_missing"

    target = targets[0]
    tp = target * (1.0 - BOT.SMC_TARGET_BUFFER_PCT) if side == "LONG" else target * (1.0 + BOT.SMC_TARGET_BUFFER_PCT)
    risk = retest["close"] - sl if side == "LONG" else sl - retest["close"]
    reward = tp - retest["close"] if side == "LONG" else retest["close"] - tp
    if risk <= 0 or reward <= 0:
        return "risk_reward_invalid"
    if reward / risk < BOT.SMC_MIN_RR:
        return "rr_too_low"
    return "pass"


def c2_stage_audit(symbols, market, start_ms, end_ms, warmup_ms):
    stage_sets = defaultdict(set)
    retest_reasons = defaultdict(set)
    signals = []
    errors = []
    for symbol_index, symbol in enumerate(symbols, 1):
        print(f"market c2 {symbol_index}/{len(symbols)} {symbol}", flush=True)
        try:
            candles_15m = market.klines(symbol, "15m", start_ms - 14 * 3600 * 1000, end_ms + 3600 * 1000)
            candles_4h = market.klines(symbol, "4h", start_ms - warmup_ms, end_ms + 4 * 3600 * 1000)
        except Exception as exc:
            errors.append(f"{symbol}: {exc}")
            continue
        close_times_4h = [c["close_time"] for c in candles_4h]
        for idx, latest in enumerate(candles_15m[:-1]):
            scan_time = latest["close_time"]
            if scan_time < start_ms or scan_time > end_ms or idx < 45:
                continue
            closed_4h = candle_slice_at(candles_4h, close_times_4h, scan_time, 60)
            if len(closed_4h) < 60:
                continue
            input_4h = closed_4h[-199:] + [synthetic_current(closed_4h[-1])]
            input_15m = candles_15m[max(0, idx - 198):idx + 2]
            closes_4h = [c["close"] for c in input_4h]
            trend_ema, slope = BOT.ema_slope(closes_4h, BOT.EMA_SLOW)
            bullish = closes_4h[-2] > trend_ema and slope > 0
            bearish = closes_4h[-2] < trend_ema and slope < 0
            trend = "BULLISH" if bullish else ("BEARISH" if bearish else "SIDEWAYS")

            for side in ("LONG", "SHORT"):
                stage_sets["scans"].add((symbol, side, latest["open_time"]))
                sweep = BOT._smc_find_liquidity_sweep(input_15m, side)
                if not sweep:
                    continue
                sweep_time = input_15m[:-1][sweep["idx"]]["open_time"]
                key = (symbol, side, sweep_time)
                stage_sets["sweep"].add(key)
                allowed = not ((side == "LONG" and trend == "BEARISH") or (side == "SHORT" and trend == "BULLISH"))
                if allowed:
                    stage_sets["trend_allowed"].add(key)
                else:
                    stage_sets["trend_blocked"].add(key)
                location = BOT._smc_find_4h_location(input_4h, side, sweep["extreme"])
                if not location:
                    continue
                stage_sets["location"].add(key)
                mss = BOT._smc_find_mss(input_15m, sweep, side)
                if not mss:
                    continue
                stage_sets["mss"].add(key)
                closed_15m = input_15m[:-1]
                fvg = BOT._smc_find_fvg(closed_15m, sweep["idx"], mss["idx"], side)
                if fvg:
                    stage_sets["fvg"].add(key)
                diagnostic = c2_retest_diagnostic(input_15m, sweep, mss, location, side)
                retest_reasons[diagnostic].add(key)
                area = BOT._smc_retest_area(input_15m, sweep, mss, location, side)
                if not area:
                    continue
                signal_key = (symbol, side, sweep_time, latest["open_time"])
                stage_sets["full_without_trend"].add(signal_key)
                outcome = first_touch_outcome(
                    candles_15m,
                    latest["close_time"] + 1,
                    side,
                    area["entry"],
                    area["sl"],
                    area["tp"],
                )
                signal = {
                    "pair": symbol,
                    "side": side,
                    "sweep_time": sweep_time,
                    "signal_time": latest["close_time"],
                    "trend": trend,
                    "trend_allowed": allowed,
                    "entry": area["entry"],
                    "sl": area["sl"],
                    "tp": area["tp"],
                    "planned_RR": round(area["rr"], 3),
                    **outcome,
                }
                signals.append(signal)
                if allowed:
                    stage_sets["full_current_rules"].add(signal_key)

    deduped_signals = {}
    for signal in signals:
        key = (signal["pair"], signal["side"], signal["sweep_time"])
        deduped_signals.setdefault(key, signal)
    unique_signals = list(deduped_signals.values())
    current_signals = [signal for signal in unique_signals if signal["trend_allowed"]]
    return {
        "stages": {key: len(value) for key, value in sorted(stage_sets.items())},
        "retest_reasons": {key: len(value) for key, value in sorted(retest_reasons.items())},
        "without_trend_gate": summarize_records(unique_signals),
        "current_rules": summarize_records(current_signals),
        "signals": unique_signals,
        "errors": errors,
    }


def build_live_a_setup(candles_15m, candles_4h):
    if len(candles_15m) < 35 or len(candles_4h) < 110:
        return None
    current_4h = candles_4h[-199:] + [synthetic_current(candles_4h[-1])]
    current_15m = candles_15m[-199:] + [synthetic_current(candles_15m[-1])]
    current_15m[-1]["close_time"] = current_15m[-1]["open_time"] + 15 * 60 * 1000 - 1

    closes_15m = [c["close"] for c in current_15m]
    highs_15m = [c["high"] for c in current_15m]
    lows_15m = [c["low"] for c in current_15m]
    closes_4h = [c["close"] for c in current_4h]
    highs_4h = [c["high"] for c in current_4h]
    lows_4h = [c["low"] for c in current_4h]
    atr_15m = BOT.atr(highs_15m, lows_15m, closes_15m, BOT.ATR_PERIOD)
    trend_ema, slope = BOT.ema_slope(closes_4h, BOT.EMA_SLOW)
    if atr_15m is None or trend_ema is None or slope is None:
        return None
    if BOT.ENABLE_REGIME_FILTER and not BOT.regime_ok_4h(closes_4h, highs_4h, lows_4h):
        return None
    if BOT.ENABLE_SWEEP_DETECTION and BOT.is_liquidity_sweep(current_4h):
        return None

    latest = current_15m[-2]
    previous = current_15m[-3]
    bullish = closes_4h[-2] > trend_ema and slope > 0
    bearish = closes_4h[-2] < trend_ema and slope < 0
    if not bullish and not bearish:
        return None
    side = "LONG" if bullish else "SHORT"
    if not BOT.market_structure_ok(current_4h, side):
        return None

    support, resistance = BOT.support_resistance_multi(
        current_4h,
        min_touches=BOT.SR_MIN_TOUCHES,
        lookback=BOT.SR_LOOKBACK,
    )
    average_volume = BOT.avg_volume(current_4h, BOT.VOLUME_AVG_LOOKBACK, exclude_last=2)
    volume_ratio = current_4h[-2]["volume"] / average_volume if average_volume else 0.0
    if volume_ratio >= BOT.JALUR_A_MAX_VOL_RATIO:
        return None
    close = latest["close"]
    if side == "LONG":
        if not BOT.near_level(close, support) or close <= support * (1.0 - BOT.SR_BUF_SL):
            return None
    else:
        if not BOT.near_level(close, resistance) or close >= resistance * (1.0 + BOT.SR_BUF_SL):
            return None
    if not (BOT.is_rejection_candle(latest, side) or BOT.is_rejection_candle(previous, side)):
        return None

    if BOT.ENABLE_ORDERFLOW_CONFIRM:
        buy_ratio, sell_ratio, _, _ = BOT.taker_ratio(current_15m, BOT.ORDERFLOW_LOOKBACK)
        baseline = current_15m[-(BOT.ORDERFLOW_LOOKBACK + BOT.ORDERFLOW_BASELINE_LOOKBACK):-BOT.ORDERFLOW_LOOKBACK]
        average_buy = sum(c["taker_buy"] for c in baseline) / max(1, len(baseline))
        average_sell = sum(c["taker_sell"] for c in baseline) / max(1, len(baseline))
        if side == "LONG" and (
            buy_ratio < BOT.ORDERFLOW_MIN_RATIO
            or latest["taker_buy"] < average_buy * BOT.ORDERFLOW_SPIKE_MULT
        ):
            return None
        if side == "SHORT" and (
            sell_ratio < BOT.ORDERFLOW_MIN_RATIO
            or latest["taker_sell"] < average_sell * BOT.ORDERFLOW_SPIKE_MULT
        ):
            return None

    recent_low = min(c["low"] for c in current_15m[-21:-1])
    recent_high = max(c["high"] for c in current_15m[-21:-1])
    entry = close
    if side == "LONG":
        sl_sr = support * (1.0 - BOT.SR_BUF_SL)
        sl_atr = entry - BOT.ATR_MULT * atr_15m
        distance_sr = abs(entry - sl_sr)
        if entry * BOT.MIN_STOP_PCT <= distance_sr <= entry * 0.05:
            sl = sl_sr
        else:
            sl = min(sl_atr, support * (1.0 - BOT.SR_BUF_SL))
        sl = min(sl, recent_low * (1.0 - 0.002))
    else:
        sl_sr = resistance * (1.0 + BOT.SR_BUF_SL)
        sl_atr = entry + BOT.ATR_MULT * atr_15m
        distance_sr = abs(entry - sl_sr)
        if entry * BOT.MIN_STOP_PCT <= distance_sr <= entry * 0.05:
            sl = sl_sr
        else:
            sl = max(sl_atr, resistance * (1.0 + BOT.SR_BUF_SL))
        sl = max(sl, recent_high * (1.0 + 0.002))
    risk = abs(entry - sl)
    if risk < entry * BOT.MIN_STOP_PCT:
        risk = entry * BOT.MIN_STOP_PCT
        sl = entry - risk if side == "LONG" else entry + risk
    if risk > entry * 0.05:
        return None

    context = four_hour_context(candles_4h)
    if not context:
        return None
    expected_structure = "BULLISH" if side == "LONG" else "BEARISH"
    strict_structure = context["structure"] == expected_structure
    momentum_alignment = side_matches(context["ret_12h"], side)
    ema_alignment = context["ema_alignment"] == expected_structure
    score = sum((strict_structure, momentum_alignment, ema_alignment))
    return {
        "side": side,
        "entry": entry,
        "sl": sl,
        "tp_1R": entry + risk if side == "LONG" else entry - risk,
        "volume_ratio_4h": volume_ratio,
        "context": context,
        "guards": {
            "strict_structure": strict_structure,
            "momentum_12h_alignment": momentum_alignment,
            "ema21_55_alignment": ema_alignment,
            "strict_and_momentum": strict_structure and momentum_alignment,
            "strict_or_momentum": strict_structure or momentum_alignment,
            "quality_score_2_of_3": score >= 2,
            "quality_score_3_of_3": score == 3,
        },
    }


def live_a_backtest(symbols, market, start_ms, end_ms, warmup_ms):
    records = []
    errors = []
    core_symbols = [symbol for symbol in ("BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT") if symbol in symbols]
    core_4h = {}
    core_close_times = {}
    for symbol in core_symbols:
        core_4h[symbol] = market.klines(symbol, "4h", start_ms - warmup_ms, end_ms + 4 * 3600 * 1000)
        core_close_times[symbol] = [c["close_time"] for c in core_4h[symbol]]
    regime_cache = {}

    def market_regime(timestamp):
        cache_key = timestamp // (4 * 3600 * 1000)
        if cache_key in regime_cache:
            return regime_cache[cache_key]
        fast_votes = []
        slow_votes = []
        details = {}
        for core_symbol in core_symbols:
            closed = candle_slice_at(core_4h[core_symbol], core_close_times[core_symbol], timestamp, 60)
            context = four_hour_context(closed)
            if not context:
                continue
            fast_parts = (
                context["close"] > context["ema21"],
                context["ret_12h"] > 0,
                context["ret_24h"] > 0,
            )
            slow_parts = (
                context["close"] > context["ema21"],
                context["ema21"] > context["ema55"],
                context["ret_24h"] > 0,
            )
            fast_vote = 1 if sum(fast_parts) >= 2 else -1
            slow_vote = 1 if sum(slow_parts) >= 2 else -1
            fast_votes.append(fast_vote)
            slow_votes.append(slow_vote)
            details[core_symbol] = {"fast": fast_vote, "slow": slow_vote}
        fast_score = sum(fast_votes)
        slow_score = sum(slow_votes)
        threshold = max(1, math.ceil(len(fast_votes) * 0.4))
        fast = "BULLISH" if fast_score >= threshold else ("BEARISH" if fast_score <= -threshold else "NEUTRAL")
        slow = "BULLISH" if slow_score >= threshold else ("BEARISH" if slow_score <= -threshold else "NEUTRAL")
        result = {
            "fast": fast,
            "slow": slow,
            "fast_score": fast_score,
            "slow_score": slow_score,
            "core_count": len(fast_votes),
            "details": details,
        }
        regime_cache[cache_key] = result
        return result

    for symbol_index, symbol in enumerate(symbols, 1):
        print(f"market live-a {symbol_index}/{len(symbols)} {symbol}", flush=True)
        try:
            candles_15m = market.klines(symbol, "15m", start_ms - 14 * 3600 * 1000, end_ms + 4 * 86400000)
            candles_4h = market.klines(symbol, "4h", start_ms - warmup_ms, end_ms + 4 * 3600 * 1000)
        except Exception as exc:
            errors.append(f"{symbol}: {exc}")
            continue
        close_times_4h = [c["close_time"] for c in candles_4h]
        next_allowed = start_ms
        index = 35
        while index < len(candles_15m) - 1:
            latest = candles_15m[index]
            scan_time = latest["close_time"]
            if scan_time < start_ms or scan_time > end_ms or scan_time < next_allowed:
                index += 1
                continue
            closed_4h = candle_slice_at(candles_4h, close_times_4h, scan_time, 110)
            if len(closed_4h) < 110:
                index += 1
                continue
            setup = build_live_a_setup(candles_15m[max(0, index - 198):index + 1], closed_4h)
            if not setup:
                index += 1
                continue
            regime = market_regime(scan_time)
            expected_regime = "BULLISH" if setup["side"] == "LONG" else "BEARISH"
            fast_aligned = regime["fast"] == expected_regime
            slow_aligned = regime["slow"] == expected_regime
            fast_not_opposite = regime["fast"] in ("NEUTRAL", expected_regime)
            setup["guards"].update({
                "market_fast_aligned": fast_aligned,
                "market_slow_aligned": slow_aligned,
                "market_fast_not_opposite": fast_not_opposite,
                "market_fast_aligned_local_ema": fast_aligned and setup["guards"]["ema21_55_alignment"],
                "market_fast_not_opposite_local_ema": fast_not_opposite and setup["guards"]["ema21_55_alignment"],
            })
            outcome = first_touch_outcome(
                candles_15m,
                latest["close_time"] + 1,
                setup["side"],
                setup["entry"],
                setup["sl"],
                setup["tp_1R"],
            )
            record = {
                "pair": symbol,
                "signal_time": scan_time,
                "market_regime": regime,
                **setup,
                **outcome,
            }
            records.append(record)
            if outcome.get("exit_time"):
                cooldown = 4 * 3600 * 1000 if outcome["outcome"] == "LOSS" else 30 * 60 * 1000
                next_allowed = outcome["exit_time"] + cooldown
                index = max(index + 1, bisect.bisect_left([c["close_time"] for c in candles_15m], next_allowed))
            else:
                break

    guard_stats = {"baseline": summarize_records(records)}
    guard_names = sorted({name for record in records for name in record["guards"]})
    for name in guard_names:
        guard_stats[name] = summarize_records([record for record in records if record["guards"][name]])
    return {"summary": summarize_records(records), "guard_stats": guard_stats, "records": records, "errors": errors}


def markdown_report(result):
    real = result["real_trades"]
    replay = result["live_a_replay"]
    c2 = result["strategy_c_v2"]
    lines = [
        "# KT Strategy Evidence Audit",
        "",
        f"Period: {result['period']['start']} to {result['period']['end']}",
        "",
        "## Real Trades",
        "",
        f"- Closed: {real['summary']['closed']}",
        f"- Winrate: {real['summary']['winrate_pct']}%",
        f"- Total R: {real['summary']['total_R']:+.3f}R",
        f"- Average R: {real['summary']['avg_R']:+.3f}R",
        f"- Profit factor: {real['summary']['profit_factor']}",
        "",
        "### Candidate Guard Retention",
        "",
        "| Guard | Closed | WR | Total R | Avg R |",
        "|---|---:|---:|---:|---:|",
    ]
    for name, stats in real["guard_stats"].items():
        lines.append(
            f"| {name} | {stats['closed']} | {stats['winrate_pct']:.2f}% | "
            f"{stats['total_R']:+.3f} | {stats['avg_R']:+.3f} |"
        )
    lines.extend([
        "",
        "## Jalur A Market Replay",
        "",
        "| Guard | Closed | WR | Total R | Avg R |",
        "|---|---:|---:|---:|---:|",
    ])
    for name, stats in replay["guard_stats"].items():
        lines.append(
            f"| {name} | {stats['closed']} | {stats['winrate_pct']:.2f}% | "
            f"{stats['total_R']:+.3f} | {stats['avg_R']:+.3f} |"
        )
    lines.extend([
        "",
        "## Strategy C v2 Funnel",
        "",
        "| Stage | Unique events |",
        "|---|---:|",
    ])
    for name, count in c2["stages"].items():
        lines.append(f"| {name} | {count} |")
    lines.extend([
        "",
        "### Retest Failure Reasons",
        "",
        "| Reason | Unique events |",
        "|---|---:|",
    ])
    for name, count in c2["retest_reasons"].items():
        lines.append(f"| {name} | {count} |")
    lines.extend([
        "",
        f"Current-rule C2 signals: {c2['current_rules']['signals']}",
        f"C2 sequences before trend gate: {c2['without_trend_gate']['signals']}",
        "",
    ])
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Evidence-based audit for KT live strategy and C2 funnel")
    parser.add_argument("--journal", required=True)
    parser.add_argument("--pairs-cache", required=True)
    parser.add_argument("--start", required=True, help="ISO-8601 timestamp")
    parser.add_argument("--end", required=True, help="ISO-8601 timestamp")
    parser.add_argument("--cache-dir", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--max-pairs", type=int, default=0)
    parser.add_argument("--replay-only", action="store_true")
    args = parser.parse_args()

    start_ms = parse_timestamp(args.start)
    end_ms = parse_timestamp(args.end)
    warmup_ms = 25 * 86400000
    journal = read_json(args.journal)
    pair_data = read_json(args.pairs_cache)
    symbols = list(pair_data.get("pairs", []))
    if args.max_pairs > 0:
        symbols = symbols[:args.max_pairs]
    market = MarketData(args.cache_dir)

    if args.replay_only:
        result = {
            "period": {"start": args.start, "end": args.end},
            "live_a_replay": live_a_backtest(symbols, market, start_ms, end_ms, warmup_ms),
        }
        write_json(args.output, result)
        print(json.dumps({
            "live_a_replay": result["live_a_replay"]["guard_stats"],
            "output": args.output,
        }, indent=2))
        return

    result = {
        "period": {"start": args.start, "end": args.end},
        "real_trades": audit_real_trades(journal, market, start_ms, end_ms, warmup_ms),
        "live_a_replay": live_a_backtest(symbols, market, start_ms, end_ms, warmup_ms),
        "strategy_c_v2": c2_stage_audit(symbols, market, start_ms, end_ms, warmup_ms),
    }
    write_json(args.output, result)
    markdown_path = str(pathlib.Path(args.output).with_suffix(".md"))
    pathlib.Path(markdown_path).write_text(markdown_report(result), encoding="utf-8")
    print(json.dumps({
        "real": result["real_trades"]["summary"],
        "guards": result["real_trades"]["guard_stats"],
        "live_a_replay": result["live_a_replay"]["guard_stats"],
        "c2_stages": result["strategy_c_v2"]["stages"],
        "c2_retest_reasons": result["strategy_c_v2"]["retest_reasons"],
        "c2_current": result["strategy_c_v2"]["current_rules"],
        "c2_without_trend": result["strategy_c_v2"]["without_trend_gate"],
        "output": args.output,
    }, indent=2))


if __name__ == "__main__":
    main()
