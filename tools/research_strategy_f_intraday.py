#!/usr/bin/env python3
"""Cost-aware, chronological research for frozen Strategy F intraday ideas."""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict, deque
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
ALT_SYMBOLS = ("ETHUSDT", "SOLUSDT")
VOLUME_WINDOW = 96
TREND_WINDOW = 96 * 20
BETA_WINDOW = 96 * 14
RESIDUAL_WINDOW = 96 * 20


@dataclass(frozen=True)
class Candidate:
    name: str
    family: str
    flow_threshold: float
    volume_ratio: float
    signal_z: float
    target_r: float
    max_hold_bars: int
    stop_atr: float
    min_risk_pct: float
    regime: str
    allowed_side: str = "BOTH"


CANDIDATES = (
    Candidate("F1_FLOW_BALANCED_4H", "FLOW_CONTINUATION", 0.18, 1.30, 0.75, 1.25, 16, 1.30, 0.0075, "ANY"),
    Candidate("F1_FLOW_STRICT_4H", "FLOW_CONTINUATION", 0.26, 1.60, 1.00, 1.50, 16, 1.40, 0.0075, "TREND"),
    Candidate("F1_FLOW_STRICT_8H", "FLOW_CONTINUATION", 0.26, 1.60, 1.00, 1.75, 32, 1.50, 0.0075, "TREND"),
    Candidate("F2_ABSORB_BALANCED_4H", "FLOW_ABSORPTION", 0.18, 1.40, 0.75, 1.25, 16, 1.30, 0.0075, "ANY"),
    Candidate("F2_ABSORB_STRICT_4H", "FLOW_ABSORPTION", 0.26, 1.70, 1.00, 1.50, 16, 1.40, 0.0075, "ANY"),
    Candidate("F2_ABSORB_STRICT_8H", "FLOW_ABSORPTION", 0.26, 1.70, 1.00, 1.75, 32, 1.50, 0.0075, "ANY"),
    Candidate("F3_RESIDUAL_REVERT_4H", "RESIDUAL_REVERSION", 0.08, 0.90, 1.75, 1.25, 16, 1.30, 0.0075, "CALM_BTC"),
    Candidate("F3_RESIDUAL_REVERT_STRICT_4H", "RESIDUAL_REVERSION", 0.12, 1.10, 2.25, 1.50, 16, 1.40, 0.0075, "CALM_BTC"),
    Candidate("F3_RESIDUAL_REVERT_STRICT_8H", "RESIDUAL_REVERSION", 0.12, 1.10, 2.25, 1.75, 32, 1.50, 0.0075, "CALM_BTC"),
    Candidate("F4_RESIDUAL_MOMENTUM_4H", "RESIDUAL_MOMENTUM", 0.10, 1.00, 1.50, 1.25, 16, 1.30, 0.0075, "TREND"),
    Candidate("F4_RESIDUAL_MOMENTUM_STRICT_4H", "RESIDUAL_MOMENTUM", 0.15, 1.20, 2.00, 1.50, 16, 1.40, 0.0075, "TREND"),
    Candidate("F4_RESIDUAL_MOMENTUM_STRICT_8H", "RESIDUAL_MOMENTUM", 0.15, 1.20, 2.00, 1.75, 32, 1.50, 0.0075, "TREND"),
)


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def load_symbol(
    cache_root: Path, symbol: str, extra_cache: Path | None = None
) -> list[dict]:
    directories = [
        cache_root / "market_cache_b4_stress365",
        cache_root / "market_cache_b4_270d",
    ]
    if extra_cache is not None:
        directories.append(extra_cache)
    files = []
    for directory in directories:
        files.extend(
            path
            for path in sorted(directory.glob(f"{symbol}_15m_*.json"))
            if not path.name.endswith(".manifest.json")
        )
    if not files:
        raise FileNotFoundError(f"no 15m cache files for {symbol}")
    deduped = {}
    for path in files:
        payload = read_json(path)
        if not isinstance(payload, list):
            raise ValueError(f"candle cache must contain a JSON array: {path}")
        for row in payload:
            deduped[int(row["open_time"])] = row
    return [deduped[key] for key in sorted(deduped)]


def align_symbols(rows_by_symbol: dict[str, list[dict]]) -> dict[str, list[dict]]:
    common = None
    indexed = {}
    for symbol, rows in rows_by_symbol.items():
        mapping = {int(row["open_time"]): row for row in rows}
        indexed[symbol] = mapping
        timestamps = set(mapping)
        common = timestamps if common is None else common & timestamps
    ordered = sorted(common or ())
    if not ordered:
        raise ValueError("symbols have no common timestamps")
    return {
        symbol: [mapping[timestamp] for timestamp in ordered]
        for symbol, mapping in indexed.items()
    }


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


def rolling_mean_prior(values: list[float | None], window: int) -> list[float | None]:
    output = [None] * len(values)
    history: deque[float] = deque()
    total = 0.0
    for index, value in enumerate(values):
        if len(history) == window:
            output[index] = total / window
        if value is not None and math.isfinite(float(value)):
            numeric = float(value)
            history.append(numeric)
            total += numeric
            if len(history) > window:
                total -= history.popleft()
        else:
            history.clear()
            total = 0.0
    return output


def rolling_mean_std_prior(
    values: list[float | None], window: int
) -> tuple[list[float | None], list[float | None]]:
    means = [None] * len(values)
    stds = [None] * len(values)
    history: deque[float] = deque()
    total = 0.0
    total_sq = 0.0
    for index, value in enumerate(values):
        if len(history) == window:
            current_mean = total / window
            variance = max(0.0, total_sq / window - current_mean * current_mean)
            means[index] = current_mean
            stds[index] = math.sqrt(variance)
        if value is not None and math.isfinite(float(value)):
            numeric = float(value)
            history.append(numeric)
            total += numeric
            total_sq += numeric * numeric
            if len(history) > window:
                removed = history.popleft()
                total -= removed
                total_sq -= removed * removed
        else:
            history.clear()
            total = 0.0
            total_sq = 0.0
    return means, stds


def rolling_beta_prior(
    market_returns: list[float | None],
    asset_returns: list[float | None],
    window: int,
) -> list[float | None]:
    if len(market_returns) != len(asset_returns):
        raise ValueError("return series length mismatch")
    output = [None] * len(market_returns)
    history: deque[tuple[float, float]] = deque()
    sum_x = sum_y = sum_xx = sum_xy = 0.0
    for index, (market, asset) in enumerate(zip(market_returns, asset_returns)):
        if len(history) == window:
            covariance = sum_xy - sum_x * sum_y / window
            variance = sum_xx - sum_x * sum_x / window
            if variance > 1e-18:
                output[index] = covariance / variance
        if market is not None and asset is not None:
            x = float(market)
            y = float(asset)
            history.append((x, y))
            sum_x += x
            sum_y += y
            sum_xx += x * x
            sum_xy += x * y
            if len(history) > window:
                old_x, old_y = history.popleft()
                sum_x -= old_x
                sum_y -= old_y
                sum_xx -= old_x * old_x
                sum_xy -= old_x * old_y
        else:
            history.clear()
            sum_x = sum_y = sum_xx = sum_xy = 0.0
    return output


def atr_series(candles: list[dict], period: int = 14) -> list[float | None]:
    true_ranges: list[float | None] = [None]
    for previous, current in zip(candles, candles[1:]):
        previous_close = float(previous["close"])
        true_ranges.append(max(
            float(current["high"]) - float(current["low"]),
            abs(float(current["high"]) - previous_close),
            abs(float(current["low"]) - previous_close),
        ))
    output = [None] * len(candles)
    history: deque[float] = deque()
    total = 0.0
    for index, value in enumerate(true_ranges):
        if value is not None:
            history.append(float(value))
            total += float(value)
            if len(history) > period:
                total -= history.popleft()
        if len(history) == period:
            output[index] = total / period
    return output


def _log_return(closes: list[float], index: int, bars: int) -> float | None:
    if index < bars or closes[index - bars] <= 0 or closes[index] <= 0:
        return None
    return math.log(closes[index] / closes[index - bars])


def _zscore(value, center, scale) -> float | None:
    if value is None or center is None or scale is None or scale <= 1e-12:
        return None
    return (float(value) - float(center)) / float(scale)


def prepare_features(aligned: dict[str, list[dict]]) -> dict[str, dict]:
    features = {}
    one_bar_returns = {}
    for symbol, rows in aligned.items():
        closes = [float(row["close"]) for row in rows]
        volumes = [float(row["volume"]) for row in rows]
        one_bar = [_log_return(closes, index, 1) for index in range(len(rows))]
        one_hour = [_log_return(closes, index, 4) for index in range(len(rows))]
        four_hour = [_log_return(closes, index, 16) for index in range(len(rows))]
        trend_mean, trend_std = rolling_mean_std_prior(one_hour, TREND_WINDOW)
        volume_mean = rolling_mean_prior(volumes, VOLUME_WINDOW)
        trend_z = [
            _zscore(value, trend_mean[index], trend_std[index])
            for index, value in enumerate(one_hour)
        ]
        flow = []
        volume_ratio = []
        for index, row in enumerate(rows):
            volume = float(row["volume"])
            taker_buy = float(row.get("taker_buy", 0.0) or 0.0)
            flow.append(2.0 * taker_buy / volume - 1.0 if volume > 0 else 0.0)
            benchmark = volume_mean[index]
            volume_ratio.append(volume / benchmark if benchmark and benchmark > 0 else None)
        features[symbol] = {
            "closes": closes,
            "one_bar_return": one_bar,
            "one_hour_return": one_hour,
            "four_hour_return": four_hour,
            "trend_z": trend_z,
            "volume_ratio": volume_ratio,
            "flow": flow,
            "atr": atr_series(rows),
            "ema_fast": ema_series(closes, 96),
            "ema_slow": ema_series(closes, 384),
        }
        one_bar_returns[symbol] = one_bar

    btc_four_hour = features["BTCUSDT"]["four_hour_return"]
    alt_symbols = tuple(symbol for symbol in aligned if symbol != "BTCUSDT")
    for symbol in alt_symbols:
        beta = rolling_beta_prior(
            one_bar_returns["BTCUSDT"], one_bar_returns[symbol], BETA_WINDOW
        )
        residual = [None] * len(beta)
        for index, current_beta in enumerate(beta):
            asset_return = features[symbol]["four_hour_return"][index]
            market_return = btc_four_hour[index]
            if current_beta is not None and asset_return is not None and market_return is not None:
                residual[index] = float(asset_return) - float(current_beta) * float(market_return)
        residual_mean, residual_std = rolling_mean_std_prior(residual, RESIDUAL_WINDOW)
        residual_z = [
            _zscore(value, residual_mean[index], residual_std[index])
            for index, value in enumerate(residual)
        ]
        features[symbol]["beta"] = beta
        features[symbol]["residual"] = residual
        features[symbol]["residual_z"] = residual_z
    return features


def candle_shape(row: dict) -> tuple[int, float, float]:
    open_price = float(row["open"])
    close = float(row["close"])
    high = float(row["high"])
    low = float(row["low"])
    span = high - low
    if span <= 0:
        return 0, 0.0, 0.5
    direction = 1 if close > open_price else -1 if close < open_price else 0
    body_ratio = abs(close - open_price) / span
    close_location = (close - low) / span
    return direction, body_ratio, close_location


def _trend_agrees(feature: dict, index: int, side_sign: int) -> bool:
    fast = feature["ema_fast"][index]
    slow = feature["ema_slow"][index]
    if fast is None or slow is None:
        return False
    return (float(fast) - float(slow)) * side_sign > 0


def detect_signal(
    symbol: str,
    index: int,
    candidate: Candidate,
    aligned: dict[str, list[dict]],
    features: dict[str, dict],
):
    feature = features[symbol]
    row = aligned[symbol][index]
    atr = feature["atr"][index]
    flow = feature["flow"][index]
    volume_ratio = feature["volume_ratio"][index]
    trend_z = feature["trend_z"][index]
    direction, body_ratio, close_location = candle_shape(row)
    if atr is None or volume_ratio is None or trend_z is None:
        return None
    if volume_ratio < candidate.volume_ratio:
        return None

    side_sign = 0
    signal_value = None
    if candidate.family == "FLOW_CONTINUATION":
        if abs(flow) < candidate.flow_threshold or abs(trend_z) < candidate.signal_z:
            return None
        flow_sign = 1 if flow > 0 else -1
        trend_sign = 1 if trend_z > 0 else -1
        if flow_sign != trend_sign or direction != flow_sign or body_ratio < 0.35:
            return None
        if (flow_sign > 0 and close_location < 0.65) or (flow_sign < 0 and close_location > 0.35):
            return None
        if candidate.regime == "TREND" and not _trend_agrees(feature, index, flow_sign):
            return None
        side_sign = flow_sign
        signal_value = trend_z

    elif candidate.family == "FLOW_ABSORPTION":
        prior_trend_z = feature["trend_z"][index - 1] if index > 0 else None
        if prior_trend_z is None or abs(flow) < candidate.flow_threshold:
            return None
        if abs(prior_trend_z) < candidate.signal_z:
            return None
        flow_sign = 1 if flow > 0 else -1
        prior_trend_sign = 1 if prior_trend_z > 0 else -1
        if flow_sign != prior_trend_sign or direction != -flow_sign or body_ratio < 0.30:
            return None
        if (direction > 0 and close_location < 0.65) or (direction < 0 and close_location > 0.35):
            return None
        side_sign = direction
        signal_value = prior_trend_z

    elif candidate.family in ("RESIDUAL_REVERSION", "RESIDUAL_MOMENTUM"):
        if symbol == "BTCUSDT":
            return None
        residual_z = feature["residual_z"][index]
        if residual_z is None or abs(residual_z) < candidate.signal_z:
            return None
        residual_sign = 1 if residual_z > 0 else -1
        side_sign = -residual_sign if candidate.family == "RESIDUAL_REVERSION" else residual_sign
        if flow * side_sign < candidate.flow_threshold:
            return None
        if direction != side_sign or body_ratio < 0.25:
            return None
        if (side_sign > 0 and close_location < 0.60) or (side_sign < 0 and close_location > 0.40):
            return None
        btc_trend_z = features["BTCUSDT"]["trend_z"][index]
        if btc_trend_z is None:
            return None
        if candidate.family == "RESIDUAL_REVERSION":
            if abs(btc_trend_z) > 1.50:
                return None
        else:
            if not _trend_agrees(feature, index, side_sign):
                return None
            if btc_trend_z * side_sign < -0.50:
                return None
        signal_value = residual_z
    else:
        raise ValueError(f"unknown family: {candidate.family}")

    side = "LONG" if side_sign > 0 else "SHORT"
    if candidate.allowed_side != "BOTH" and candidate.allowed_side != side:
        return None
    score = (
        abs(float(signal_value))
        * max(abs(float(flow)), 0.01)
        * max(float(volume_ratio), 0.01)
    )
    return {
        "side": side,
        "score": score,
        "atr": float(atr),
        "extreme": float(row["low"] if side_sign > 0 else row["high"]),
        "flow": float(flow),
        "volume_ratio": float(volume_ratio),
        "trend_z": float(trend_z),
        "signal_z": float(signal_value),
        "btc_market_trend": (
            "UP"
            if _trend_agrees(features["BTCUSDT"], index, 1)
            else "DOWN"
        ),
    }


def simulate_trade(
    candles: list[dict], signal_index: int, signal: dict, candidate: Candidate
):
    entry_index = signal_index + 1
    if entry_index >= len(candles):
        return None
    entry = float(candles[entry_index]["open"])
    atr = float(signal["atr"])
    side = signal["side"]
    minimum_risk = entry * candidate.min_risk_pct
    atr_risk = candidate.stop_atr * atr
    if candidate.family in ("FLOW_ABSORPTION", "RESIDUAL_REVERSION"):
        structure_risk = (
            entry - (float(signal["extreme"]) - 0.10 * atr)
            if side == "LONG"
            else (float(signal["extreme"]) + 0.10 * atr) - entry
        )
        risk = max(minimum_risk, atr_risk, structure_risk)
    else:
        risk = max(minimum_risk, atr_risk)
    risk_pct = risk / entry if entry > 0 else 0.0
    if risk <= 0 or risk_pct < candidate.min_risk_pct or risk_pct > 0.025:
        return None
    stop = entry - risk if side == "LONG" else entry + risk
    target = entry + candidate.target_r * risk if side == "LONG" else entry - candidate.target_r * risk
    final_index = min(len(candles) - 1, entry_index + candidate.max_hold_bars - 1)
    exit_index = final_index
    exit_price = float(candles[final_index]["close"])
    exit_reason = "TIMEOUT"
    gross_r = ((exit_price - entry) / risk) if side == "LONG" else ((entry - exit_price) / risk)
    for index in range(entry_index, final_index + 1):
        row = candles[index]
        hit_stop = float(row["low"]) <= stop if side == "LONG" else float(row["high"]) >= stop
        hit_target = float(row["high"]) >= target if side == "LONG" else float(row["low"]) <= target
        if hit_stop:
            exit_index = index
            exit_price = stop
            exit_reason = "STOP"
            gross_r = -1.0
            break
        if hit_target:
            exit_index = index
            exit_price = target
            exit_reason = "TARGET"
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
        "exit_price": exit_price,
        "exit_index": exit_index,
        "flow": signal["flow"],
        "volume_ratio": signal["volume_ratio"],
        "trend_z": signal["trend_z"],
        "signal_z": signal["signal_z"],
        "btc_market_trend": signal["btc_market_trend"],
    }


def run_candidate(
    aligned: dict[str, list[dict]],
    features: dict[str, dict],
    candidate: Candidate,
    start_ms: int,
    end_ms: int,
) -> list[dict]:
    records = []
    next_available = 0
    warmup = BETA_WINDOW + RESIDUAL_WINDOW + 32
    length = len(aligned["BTCUSDT"])
    for index in range(warmup, length - 1):
        timestamp = int(aligned["BTCUSDT"][index]["open_time"])
        if timestamp < start_ms or timestamp > end_ms or index < next_available:
            continue
        signals = []
        symbols = (
            tuple(symbol for symbol in aligned if symbol != "BTCUSDT")
            if candidate.family.startswith("RESIDUAL_")
            else tuple(aligned)
        )
        for symbol in symbols:
            signal = detect_signal(symbol, index, candidate, aligned, features)
            if signal:
                signals.append((float(signal["score"]), symbol, signal))
        if not signals:
            continue
        _, symbol, selected = max(signals, key=lambda item: (item[0], item[1]))
        trade = simulate_trade(aligned[symbol], index, selected, candidate)
        if trade:
            records.append({**trade, "symbol": symbol})
            next_available = int(trade["exit_index"]) + 1
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
        "win_rate_pct": sum(value > 0 for value in values) / len(values) * 100 if values else 0.0,
        "total_r": sum(values),
        "avg_r": mean(values) if values else 0.0,
        "profit_factor": gains / losses if losses else (math.inf if gains else 0.0),
        "max_drawdown_r": max_drawdown(values),
    }


def gate_for_stage(stage: str, summary: dict) -> dict:
    baseline = summary["baseline"]
    stress = summary["stress"]
    if stage == "development":
        checks = {
            "minimum_trades": baseline["trades"] >= 80,
            "baseline_positive": baseline["total_r"] > 0,
            "baseline_pf": baseline["profit_factor"] >= 1.15,
            "stress_positive": stress["total_r"] > 0,
            "stress_pf": stress["profit_factor"] >= 1.05,
            "pair_breadth": summary["positive_pairs"] >= 2,
            "month_breadth": summary["positive_month_ratio"] >= 0.55,
            "max_drawdown": baseline["max_drawdown_r"] <= 15.0,
            "long_sample": summary["side_baseline"]["LONG"]["trades"] >= 20,
            "short_sample": summary["side_baseline"]["SHORT"]["trades"] >= 20,
            "long_positive": summary["side_baseline"]["LONG"]["total_r"] > 0,
            "short_positive": summary["side_baseline"]["SHORT"]["total_r"] > 0,
        }
    elif stage == "validation":
        checks = {
            "minimum_trades": baseline["trades"] >= 35,
            "baseline_positive": baseline["total_r"] > 0,
            "baseline_pf": baseline["profit_factor"] >= 1.10,
            "stress_non_negative": stress["total_r"] >= 0,
            "month_breadth": summary["positive_month_ratio"] >= 0.50,
            "max_drawdown": baseline["max_drawdown_r"] <= 12.0,
        }
    else:
        checks = {
            "minimum_trades": baseline["trades"] >= 20,
            "baseline_positive": baseline["total_r"] > 0,
            "baseline_pf": baseline["profit_factor"] >= 1.05,
            "stress_non_negative": stress["total_r"] >= 0,
            "max_drawdown": baseline["max_drawdown_r"] <= 10.0,
        }
    return {"passed": all(checks.values()), "checks": checks}


def summarize(
    records: list[dict], stage: str, symbols: tuple[str, ...] = SYMBOLS
) -> dict:
    ordered = sorted(records, key=lambda row: row["entry_time"])
    pair_metrics = {
        symbol: performance([row for row in ordered if row["symbol"] == symbol], "baseline_net_r")
        for symbol in symbols
    }
    month_totals = defaultdict(float)
    for row in ordered:
        month = datetime.fromtimestamp(row["entry_time"] / 1000, timezone.utc).strftime("%Y-%m")
        month_totals[month] += float(row["baseline_net_r"])
    positive_months = sum(value > 0 for value in month_totals.values())
    summary = {
        "gross": performance(ordered, "gross_r"),
        "baseline": performance(ordered, "baseline_net_r"),
        "stress": performance(ordered, "stress_net_r"),
        "pairs": pair_metrics,
        "positive_pairs": sum(item["total_r"] > 0 for item in pair_metrics.values()),
        "monthly_r": dict(sorted(month_totals.items())),
        "positive_month_ratio": positive_months / len(month_totals) if month_totals else 0.0,
        "side_baseline": {
            side: performance([row for row in ordered if row["side"] == side], "baseline_net_r")
            for side in ("LONG", "SHORT")
        },
        "exit_reasons": dict(Counter(row["exit_reason"] for row in ordered)),
        "median_risk_pct": median([float(row["risk_pct"]) for row in ordered]) if ordered else 0.0,
    }
    summary["gate"] = gate_for_stage(stage, summary)
    return summary


def period_bounds(stage: str, aligned: dict[str, list[dict]]) -> tuple[int, int]:
    first = int(aligned["BTCUSDT"][0]["open_time"])
    last = int(aligned["BTCUSDT"][-1]["open_time"])
    if stage == "development":
        return first, min(DEVELOPMENT_END, last)
    if stage == "validation":
        return max(VALIDATION_START, first), min(VALIDATION_END, last)
    return max(HOLDOUT_START, first), last


def json_safe(value):
    if isinstance(value, dict):
        return {key: json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [json_safe(item) for item in value]
    if isinstance(value, float) and not math.isfinite(value):
        return "INF" if value > 0 else "-INF"
    return value


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache-root", type=Path, default=Path(".audit/2026-07-22"))
    parser.add_argument("--extra-cache", type=Path)
    parser.add_argument("--stage", choices=("development", "validation", "holdout"), default="development")
    parser.add_argument("--candidate", choices=tuple(item.name for item in CANDIDATES))
    parser.add_argument("--output", required=True, type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.stage != "development" and not args.candidate:
        raise ValueError("--candidate is required for validation and holdout")
    loaded = {
        symbol: load_symbol(args.cache_root, symbol, args.extra_cache)
        for symbol in SYMBOLS
    }
    aligned = align_symbols(loaded)
    features = prepare_features(aligned)
    start_ms, end_ms = period_bounds(args.stage, aligned)
    candidates = [item for item in CANDIDATES if not args.candidate or item.name == args.candidate]
    results = {}
    for candidate in candidates:
        records = run_candidate(aligned, features, candidate, start_ms, end_ms)
        results[candidate.name] = {
            "parameters": asdict(candidate),
            "summary": summarize(records, args.stage),
        }
    passed = [name for name, item in results.items() if item["summary"]["gate"]["passed"]]
    selected = max(
        passed,
        key=lambda name: results[name]["summary"]["stress"]["total_r"],
        default=None,
    )
    payload = {
        "engine": "STRATEGY_F_SELECTIVE_INTRADAY_RESEARCH_V1",
        "status": "RESEARCH_ONLY_NO_ORDERS",
        "stage": args.stage,
        "period": {"start_ms": start_ms, "end_ms": end_ms},
        "symbols": list(SYMBOLS),
        "portfolio_max_concurrent_positions": 1,
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
