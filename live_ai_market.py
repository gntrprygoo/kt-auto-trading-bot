"""Live Binance Futures snapshots for OpenAI shadow analysis.

This module intentionally has no order-placement capability. It reads confirmed
market bars through callbacks supplied by the application, sends only derived
market features to OpenAI, and stores research-only decisions.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import re
import tempfile
import threading
import time
from typing import Any, Callable

from ai_market_scanner import (
    SCANNER_SCHEMA,
    MarketScannerConfig,
    assert_snapshot_has_no_future_data,
)
from ai_range_setup import (
    RANGE_SETUP_PROMPT_ID,
    OpenAIRangeSetupClient,
    range_setup_prompt_definition,
    validate_range_setup,
)
from range_setup_shadow import (
    TERMINAL_STATUSES,
    apply_terminal_stats,
    create_shadow_setup,
    empty_setup_stats,
    update_shadow_setup,
)


LIVE_STATE_SCHEMA = "KT_AI_MARKET_LIVE_STATE_V3"
LIVE_RECORD_SCHEMA = "KT_AI_MARKET_LIVE_RECORD_V3"
LIVE_FEATURE_SET = "OHLCV_TAKER_RANGE_STRUCTURE_V3"
RESEARCH_STATUS = "REJECTED_HISTORICAL_SHADOW_OBSERVATION_ONLY"
BAR_MS = 15 * 60 * 1000
HOUR_MS = 60 * 60 * 1000
DEFAULT_SYMBOLS = (
    "BTCUSDT",
    "ETHUSDT",
    "SOLUSDT",
    "ADAUSDT",
    "DOGEUSDT",
    "XRPUSDT",
)


class LiveAIMarketError(RuntimeError):
    pass


def _atomic_json_write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, path)
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass
    except Exception:
        try:
            os.unlink(temp_name)
        except OSError:
            pass
        raise


def _safe_number(value: Any, digits: int = 8):
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number):
        return None
    return round(number, digits)


def _ema(values: list[float], span: int) -> list[float]:
    if not values:
        return []
    alpha = 2.0 / (span + 1.0)
    result = [float(values[0])]
    for value in values[1:]:
        result.append(alpha * float(value) + (1.0 - alpha) * result[-1])
    return result


def _rolling_sum(values: list[float], window: int) -> list[float | None]:
    result: list[float | None] = [None] * len(values)
    total = 0.0
    for index, value in enumerate(values):
        total += float(value)
        if index >= window:
            total -= float(values[index - window])
        if index + 1 >= window:
            result[index] = total
    return result


def _rolling_mean(values: list[float], window: int) -> list[float | None]:
    return [
        None if value is None else value / window
        for value in _rolling_sum(values, window)
    ]


def _rolling_extreme(
    values: list[float], window: int, maximum: bool
) -> list[float | None]:
    result: list[float | None] = [None] * len(values)
    for index in range(window - 1, len(values)):
        sample = values[index - window + 1:index + 1]
        result[index] = max(sample) if maximum else min(sample)
    return result


def _point_return(closes: list[float], index: int, bars: int):
    if index < bars or closes[index - bars] <= 0:
        return None
    return closes[index] / closes[index - bars] - 1.0


def _prepare_symbol(candles: list[dict]) -> dict:
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
        "ema_fast": _ema(closes, 48),
        "ema_slow": _ema(closes, 192),
        "atr": _rolling_mean(true_ranges, 56),
        "volume_1h": _rolling_sum(volumes, 4),
        "volume_20h": _rolling_sum(volumes, 80),
        "buy_1h": _rolling_sum(buys, 4),
        "sell_1h": _rolling_sum(sells, 4),
        "buy_4h": _rolling_sum(buys, 16),
        "sell_4h": _rolling_sum(sells, 16),
        "high_24h": _rolling_extreme(highs, 96, True),
        "low_24h": _rolling_extreme(lows, 96, False),
        "high_7d": _rolling_extreme(highs, 672, True),
        "low_7d": _rolling_extreme(lows, 672, False),
    }


def _flow_ratio(buy, sell):
    if buy is None or sell is None or float(buy) + float(sell) <= 0:
        return None
    return (float(buy) - float(sell)) / (float(buy) + float(sell))


def _range_position(close, low, high):
    if low is None or high is None or float(high) <= float(low):
        return None
    return (float(close) - float(low)) / (float(high) - float(low))


def _hourly_sequence(feature: dict, index: int, periods: int = 8) -> dict:
    returns = []
    flows = []
    volumes = []
    for offset in range(periods - 1, -1, -1):
        point = index - 4 * offset
        returns.append(_safe_number(_point_return(feature["closes"], point, 4), 6))
        flows.append(
            _safe_number(
                _flow_ratio(feature["buy_1h"][point], feature["sell_1h"][point]),
                5,
            )
        )
        current_volume = feature["volume_1h"][point]
        long_volume = feature["volume_20h"][point]
        ratio = (
            float(current_volume) / (float(long_volume) / 20.0)
            if current_volume is not None and long_volume and float(long_volume) > 0
            else None
        )
        volumes.append(_safe_number(ratio, 4))
    return {
        "hourly_returns": returns,
        "hourly_taker_flow": flows,
        "hourly_volume_ratio": volumes,
    }


def _aggregate_hourly_bars(candles: list[dict]) -> list[dict]:
    groups: dict[int, list[dict]] = {}
    for row in candles:
        bucket = int(row["open_time"]) // HOUR_MS
        groups.setdefault(bucket, []).append(row)
    result = []
    for bucket in sorted(groups):
        rows = sorted(groups[bucket], key=lambda item: int(item["open_time"]))
        offsets = [int(row["open_time"]) % HOUR_MS for row in rows]
        if len(rows) != 4 or offsets != [0, BAR_MS, 2 * BAR_MS, 3 * BAR_MS]:
            continue
        volume = sum(float(row.get("volume", 0) or 0) for row in rows)
        taker_buy = sum(float(row.get("taker_buy", 0) or 0) for row in rows)
        result.append(
            {
                "open_time_ms": int(rows[0]["open_time"]),
                "close_time_ms": int(rows[-1]["close_time"]),
                "open": float(rows[0]["open"]),
                "high": max(float(row["high"]) for row in rows),
                "low": min(float(row["low"]) for row in rows),
                "close": float(rows[-1]["close"]),
                "volume": volume,
                "taker_buy": taker_buy,
                "taker_sell": max(volume - taker_buy, 0.0),
            }
        )
    return result


def _recent_hourly_bars(candles: list[dict], periods: int = 4) -> tuple[list[dict], list[dict]]:
    hourly = _aggregate_hourly_bars(candles)
    public = []
    for index, row in enumerate(hourly):
        prior = hourly[max(0, index - 20):index]
        average_volume = (
            sum(float(item["volume"]) for item in prior) / len(prior)
            if prior
            else None
        )
        candle_range = float(row["high"]) - float(row["low"])
        public.append(
            {
                "close_time_ms": int(row["close_time_ms"]),
                "open": _safe_number(row["open"]),
                "high": _safe_number(row["high"]),
                "low": _safe_number(row["low"]),
                "close": _safe_number(row["close"]),
                "volume_ratio": _safe_number(
                    float(row["volume"]) / average_volume
                    if average_volume and average_volume > 0
                    else None,
                    4,
                ),
                "taker_flow": _safe_number(
                    _flow_ratio(row["taker_buy"], row["taker_sell"]), 5
                ),
                "close_location": _safe_number(
                    (float(row["close"]) - float(row["low"])) / candle_range
                    if candle_range > 0
                    else 0.5,
                    4,
                ),
            }
        )
    return hourly, public[-periods:]


def _recent_15m_bars(candles: list[dict], periods: int = 4) -> list[dict]:
    result = []
    for index in range(max(0, len(candles) - periods), len(candles)):
        row = candles[index]
        prior = candles[max(0, index - 80):index]
        average_volume = (
            sum(float(item.get("volume", 0) or 0) for item in prior) / len(prior)
            if prior
            else None
        )
        volume = float(row.get("volume", 0) or 0)
        candle_range = float(row["high"]) - float(row["low"])
        result.append(
            {
                "close_time_ms": int(row["close_time"]),
                "open": _safe_number(row["open"]),
                "high": _safe_number(row["high"]),
                "low": _safe_number(row["low"]),
                "close": _safe_number(row["close"]),
                "volume_ratio": _safe_number(
                    volume / average_volume
                    if average_volume and average_volume > 0
                    else None,
                    4,
                ),
                "taker_flow": _safe_number(
                    _flow_ratio(row.get("taker_buy", 0), row.get("taker_sell", 0)), 5
                ),
                "close_location": _safe_number(
                    (float(row["close"]) - float(row["low"])) / candle_range
                    if candle_range > 0
                    else 0.5,
                    4,
                ),
            }
        )
    return result


def _confirmed_hourly_swings(
    hourly: list[dict], left: int = 2, right: int = 2, limit: int = 4
) -> tuple[list[dict], list[dict]]:
    highs = []
    lows = []
    for index in range(left, len(hourly) - right):
        row = hourly[index]
        before = hourly[index - left:index]
        after = hourly[index + 1:index + right + 1]
        high = float(row["high"])
        low = float(row["low"])
        if all(high > float(item["high"]) for item in before + after):
            highs.append(
                {
                    "price": _safe_number(high),
                    "pivot_close_time_ms": int(row["close_time_ms"]),
                    "confirmed_time_ms": int(hourly[index + right]["close_time_ms"]),
                }
            )
        if all(low < float(item["low"]) for item in before + after):
            lows.append(
                {
                    "price": _safe_number(low),
                    "pivot_close_time_ms": int(row["close_time_ms"]),
                    "confirmed_time_ms": int(hourly[index + right]["close_time_ms"]),
                }
            )
    return lows[-limit:], highs[-limit:]


def _market_features(
    candles: list[dict], feature: dict, index: int, btc_feature: dict, tick_size: float
) -> dict:
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
    return_4h = _point_return(feature["closes"], index, 16)
    btc_return_4h = _point_return(btc_feature["closes"], index, 16)
    range_low_24h = feature["low_24h"][index]
    range_high_24h = feature["high_24h"][index]
    range_low_7d = feature["low_7d"][index]
    range_high_7d = feature["high_7d"][index]
    range_position_24h = _range_position(close, range_low_24h, range_high_24h)
    range_position_7d = _range_position(close, range_low_7d, range_high_7d)
    hourly_bars, recent_hourly = _recent_hourly_bars(candles)
    recent_swing_lows, recent_swing_highs = _confirmed_hourly_swings(hourly_bars)
    return {
        "last_close": _safe_number(close),
        "return_1h": _safe_number(_point_return(feature["closes"], index, 4), 6),
        "return_4h": _safe_number(return_4h, 6),
        "return_12h": _safe_number(_point_return(feature["closes"], index, 48), 6),
        "return_24h": _safe_number(_point_return(feature["closes"], index, 96), 6),
        "relative_strength_vs_btc_4h": _safe_number(
            None if return_4h is None or btc_return_4h is None else return_4h - btc_return_4h,
            6,
        ),
        "ema_fast_above_slow": bool(fast > slow),
        "ema_fast_distance_pct": _safe_number((close - fast) / close if close > 0 else None, 6),
        "ema_spread_pct": _safe_number((fast - slow) / close if close > 0 else None, 6),
        "atr_price": _safe_number(atr),
        "atr_pct": _safe_number(float(atr) / close if atr is not None and close > 0 else None, 6),
        "tick_size": _safe_number(tick_size),
        "volume_ratio_1h": _safe_number(volume_ratio, 4),
        "taker_flow_1h": _safe_number(
            _flow_ratio(feature["buy_1h"][index], feature["sell_1h"][index]), 5
        ),
        "taker_flow_4h": _safe_number(
            _flow_ratio(feature["buy_4h"][index], feature["sell_4h"][index]), 5
        ),
        "range_low_24h": _safe_number(range_low_24h),
        "range_high_24h": _safe_number(range_high_24h),
        "range_position_24h_pct": _safe_number(
            None if range_position_24h is None else range_position_24h * 100.0, 2
        ),
        "range_low_7d": _safe_number(range_low_7d),
        "range_high_7d": _safe_number(range_high_7d),
        "range_position_7d_pct": _safe_number(
            None if range_position_7d is None else range_position_7d * 100.0, 2
        ),
        "last_15m_direction": (
            "UP" if float(candle["close"]) > float(candle["open"]) else
            "DOWN" if float(candle["close"]) < float(candle["open"]) else "FLAT"
        ),
        "last_15m_body_ratio": _safe_number(
            abs(float(candle["close"]) - float(candle["open"])) / candle_range
            if candle_range > 0 else 0,
            4,
        ),
        "last_15m_close_location": _safe_number(
            (float(candle["close"]) - float(candle["low"])) / candle_range
            if candle_range > 0 else 0.5,
            4,
        ),
        "recent_15m_bars": _recent_15m_bars(candles),
        "recent_hourly_bars": recent_hourly,
        "recent_swing_lows_1h": recent_swing_lows,
        "recent_swing_highs_1h": recent_swing_highs,
        **_hourly_sequence(feature, index),
    }


def build_live_snapshot(
    candles_by_symbol: dict[str, list[dict]],
    symbols: tuple[str, ...] | list[str],
    symbol_rules: dict[str, dict] | None = None,
    now_ms_value: int | None = None,
    min_closed_bars: int = 700,
) -> dict:
    """Build the range-setup feature contract from the latest full-hour close."""
    current_ms = int(now_ms_value or time.time() * 1000)
    ordered_symbols = tuple(str(symbol).upper() for symbol in symbols)
    if not ordered_symbols or "BTCUSDT" not in ordered_symbols:
        raise LiveAIMarketError("BTCUSDT must be present in the live universe")

    rows_by_time: dict[str, dict[int, dict]] = {}
    for symbol in ordered_symbols:
        rows = candles_by_symbol.get(symbol)
        if not isinstance(rows, list):
            raise LiveAIMarketError(f"missing candles for {symbol}")
        confirmed = {
            int(row["open_time"]): row
            for row in rows
            if int(row.get("close_time", 0) or 0) <= current_ms
        }
        rows_by_time[symbol] = confirmed

    common_times = set(rows_by_time[ordered_symbols[0]])
    for symbol in ordered_symbols[1:]:
        common_times.intersection_update(rows_by_time[symbol])
    hourly_close_times = sorted(
        value for value in common_times if value % HOUR_MS == 45 * 60 * 1000
    )
    if not hourly_close_times:
        raise LiveAIMarketError("no common confirmed hourly close is available")
    decision_open_time = hourly_close_times[-1]
    aligned_times = sorted(value for value in common_times if value <= decision_open_time)
    if len(aligned_times) < min_closed_bars:
        raise LiveAIMarketError(
            f"insufficient common confirmed bars: {len(aligned_times)}/{min_closed_bars}"
        )
    aligned_times = aligned_times[-min_closed_bars:]
    if any(
        current - previous != BAR_MS
        for previous, current in zip(aligned_times, aligned_times[1:])
    ):
        raise LiveAIMarketError("common confirmed 15m bars contain a time gap")
    aligned = {
        symbol: [rows_by_time[symbol][value] for value in aligned_times]
        for symbol in ordered_symbols
    }
    supplied_rules = symbol_rules if isinstance(symbol_rules, dict) else {}
    tick_sizes: dict[str, float] = {}
    for symbol in ordered_symbols:
        rule = supplied_rules.get(symbol)
        tick = rule.get("tick_size") if isinstance(rule, dict) else None
        if not _safe_number(tick) or float(tick) <= 0:
            raise LiveAIMarketError(f"missing Binance tick size for {symbol}")
        tick_sizes[symbol] = float(tick)
    features = {symbol: _prepare_symbol(aligned[symbol]) for symbol in ordered_symbols}
    index = len(aligned_times) - 1
    btc_feature = features["BTCUSDT"]
    market = {
        symbol: _market_features(
            aligned[symbol], features[symbol], index, btc_feature, tick_sizes[symbol]
        )
        for symbol in ordered_symbols
    }
    decision_time = int(aligned["BTCUSDT"][index]["close_time"])
    snapshot_id = "LIVE-MS-" + hashlib.sha256(
        f"{SCANNER_SCHEMA}|{LIVE_FEATURE_SET}|{decision_time}|{'|'.join(ordered_symbols)}".encode(
            "utf-8"
        )
    ).hexdigest()[:18].upper()
    snapshot = {
        "schema": SCANNER_SCHEMA,
        "snapshot_id": snapshot_id,
        "decision_time_ms": decision_time,
        "decision_time_utc": datetime.fromtimestamp(
            decision_time / 1000, timezone.utc
        ).isoformat().replace("+00:00", "Z"),
        "universe": list(ordered_symbols),
        "market": market,
        "data_contract": {
            "source": "BINANCE_USDM_FUTURES_REST",
            "source_interval": "15m",
            "decision_interval": "1h_confirmed_close",
            "feature_set": LIVE_FEATURE_SET,
            "quote_currency": "USDT",
            "numeric_semantics": {
                "price_fields": [
                    "last_close",
                    "range_low_24h",
                    "range_high_24h",
                    "range_low_7d",
                    "range_high_7d",
                ],
                "percentage_fields": [
                    "range_position_24h_pct",
                    "range_position_7d_pct",
                ],
                "structure_fields": [
                    "recent_15m_bars",
                    "recent_hourly_bars",
            "recent_swing_lows_1h",
            "recent_swing_highs_1h",
        ],
                "percentage_scale": "0_TO_100_NOT_A_PRICE",
            },
            "confirmed_bars_only": True,
            "binance_credentials_included": False,
            "account_data_included": False,
        },
        "execution_contract": {
            "status": "RESEARCH_SHADOW_ONLY",
            "plan_type": "AI_SELECTED_RANGE_SETUP",
            "model_selects_shadow_geometry": True,
            "application_validates_without_changing_levels": True,
            "minimum_cost_adjusted_rr_tp1": 1.0,
            "minimum_cost_adjusted_rr_tp2": 1.8,
            "modeled_round_trip_cost_pct": 0.002,
            "maximum_expiry_hours": 12,
            "orders_allowed": False,
            "model_must_not_size_or_place_orders": True,
        },
    }
    assert_snapshot_has_no_future_data(snapshot)
    return snapshot


_PRICE_CLAIM_PATTERN = re.compile(
    r"\b(?:price|last\s+close|close(?:d)?|trading|trades?|"
    r"range(?:\s+(?:low|high|bottom|top|edge|boundary))?)"
    r"[^\n.;]{0,80}?\b(?:at|is)\s*\$?([+-]?\d+(?:\.\d+)?)\s*(%?)",
    re.IGNORECASE,
)


def _matches_price_reference(raw_number: str, references: list[float]) -> bool:
    value = float(raw_number)
    decimals = len(raw_number.partition(".")[2]) if "." in raw_number else 0
    rounding_tolerance = 0.51 * (10.0 ** -decimals)
    return any(
        abs(value - reference)
        <= max(rounding_tolerance, abs(reference) * 1e-9)
        for reference in references
    )


def selected_market_context(snapshot: dict, decision) -> dict | None:
    pair = str(getattr(decision, "pair", "") or "").upper()
    if pair in ("", "NONE"):
        return None
    market = snapshot.get("market") if isinstance(snapshot.get("market"), dict) else {}
    features = market.get(pair) if isinstance(market.get(pair), dict) else None
    if not features:
        raise LiveAIMarketError(f"selected pair has no market snapshot: {pair}")
    keys = (
        "last_close",
        "range_low_24h",
        "range_high_24h",
        "range_position_24h_pct",
        "range_low_7d",
        "range_high_7d",
        "range_position_7d_pct",
        "atr_price",
        "atr_pct",
        "tick_size",
        "recent_swing_lows_1h",
        "recent_swing_highs_1h",
    )
    return {
        "pair": pair,
        "quote_currency": "USDT",
        "feature_set": LIVE_FEATURE_SET,
        **{key: features.get(key) for key in keys},
    }


def assert_live_decision_grounded(snapshot: dict, decision) -> dict | None:
    """Reject narrative price claims that do not match the selected pair data."""
    context = selected_market_context(snapshot, decision)
    market = snapshot.get("market") if isinstance(snapshot.get("market"), dict) else {}
    references_by_symbol: dict[str, list[float]] = {}
    for symbol, features in market.items():
        if not isinstance(features, dict):
            continue
        references = [
            float(features[key])
            for key in (
                "last_close",
                "range_low_24h",
                "range_high_24h",
                "range_low_7d",
                "range_high_7d",
            )
            if _safe_number(features.get(key)) is not None
        ]
        for collection_key in (
            "recent_15m_bars",
            "recent_hourly_bars",
            "recent_swing_lows_1h",
            "recent_swing_highs_1h",
        ):
            collection = features.get(collection_key)
            for item in collection if isinstance(collection, list) else []:
                if not isinstance(item, dict):
                    continue
                for key in ("open", "high", "low", "close", "price"):
                    if _safe_number(item.get(key)) is not None:
                        references.append(float(item[key]))
        references_by_symbol[str(symbol).upper()] = references

    selected_pair = str(getattr(decision, "pair", "") or "").upper()
    if selected_pair in references_by_symbol:
        references_by_symbol[selected_pair].extend(
            float(getattr(decision, field))
            for field in (
                "range_low",
                "range_high",
                "entry_zone_low",
                "entry_zone_high",
                "invalidation_level",
                "stop_loss",
                "take_profit_1",
                "take_profit_2",
            )
            if _safe_number(getattr(decision, field, None)) not in (None, 0)
        )

    narrative_lines = [
        *list(getattr(decision, "evidence", ()) or ()),
        *list(getattr(decision, "risk_flags", ()) or ()),
        str(getattr(decision, "thesis", "") or ""),
        str(getattr(decision, "invalidation_reason", "") or ""),
    ]
    all_references = [
        value for references in references_by_symbol.values() for value in references
    ]
    for line in narrative_lines:
        upper_line = str(line).upper()
        mentioned = [
            symbol
            for symbol in references_by_symbol
            if re.search(
                rf"\b(?:{re.escape(symbol)}|{re.escape(symbol.removesuffix('USDT'))})\b",
                upper_line,
            )
        ]
        if mentioned:
            references = [
                value for symbol in mentioned for value in references_by_symbol[symbol]
            ]
            claim_scope = ",".join(mentioned)
        elif selected_pair in references_by_symbol:
            references = references_by_symbol[selected_pair]
            claim_scope = selected_pair
        else:
            references = all_references
            claim_scope = "live universe"
        for match in _PRICE_CLAIM_PATTERN.finditer(str(line)):
            raw_number, percent_suffix = match.groups()
            if percent_suffix:
                continue
            if not _matches_price_reference(raw_number, references):
                raise LiveAIMarketError(
                    f"ungrounded AI price claim for {claim_scope}: {raw_number}"
                )
    return context


@dataclass(frozen=True)
class LiveAIMarketConfig:
    enabled: bool = False
    model: str = "gpt-5.6-sol"
    reasoning_effort: str = "low"
    api_key_env: str = "OPENAI_API_KEY"
    prompt_id: str = RANGE_SETUP_PROMPT_ID
    scan_interval_sec: int = 3600
    setup_monitor_interval_sec: int = 300
    failure_retry_sec: int = 900
    request_timeout_sec: int = 45
    max_output_tokens: int = 1800
    candle_limit: int = 800
    min_closed_bars: int = 700
    symbols: tuple[str, ...] = DEFAULT_SYMBOLS
    require_authenticated_binance: bool = True
    notify_admin_on_setup: bool = True
    notify_admin_on_lifecycle: bool = True
    state_path: str = ""
    history_path: str = ""

    @classmethod
    def from_mapping(cls, value: Any, data_dir: str | Path) -> "LiveAIMarketConfig":
        raw = value if isinstance(value, dict) else {}
        raw_symbols = raw.get("symbols", DEFAULT_SYMBOLS)
        if not isinstance(raw_symbols, (list, tuple)):
            raw_symbols = DEFAULT_SYMBOLS
        symbols = tuple(
            dict.fromkeys(
                str(item).upper().strip()
                for item in raw_symbols
                if str(item).strip()
            )
        )
        if "BTCUSDT" not in symbols:
            symbols = ("BTCUSDT",) + symbols
        prompt_id = str(raw.get("prompt_id", RANGE_SETUP_PROMPT_ID)).upper()
        range_setup_prompt_definition(prompt_id)
        data_root = Path(data_dir)
        return cls(
            enabled=bool(raw.get("enabled", False)),
            model=str(raw.get("model", "gpt-5.6-sol")).strip() or "gpt-5.6-sol",
            reasoning_effort=str(raw.get("reasoning_effort", "low")).strip() or "low",
            api_key_env=str(raw.get("api_key_env", "OPENAI_API_KEY")).strip() or "OPENAI_API_KEY",
            prompt_id=prompt_id,
            scan_interval_sec=max(900, int(raw.get("scan_interval_sec", 3600))),
            setup_monitor_interval_sec=max(
                60, min(900, int(raw.get("setup_monitor_interval_sec", 300)))
            ),
            failure_retry_sec=max(300, int(raw.get("failure_retry_sec", 900))),
            request_timeout_sec=max(10, min(120, int(raw.get("request_timeout_sec", 45)))),
            max_output_tokens=max(800, min(4000, int(raw.get("max_output_tokens", 1800)))),
            candle_limit=max(700, min(1500, int(raw.get("candle_limit", 800)))),
            min_closed_bars=max(672, min(1000, int(raw.get("min_closed_bars", 700)))),
            symbols=symbols,
            require_authenticated_binance=bool(
                raw.get("require_authenticated_binance", True)
            ),
            notify_admin_on_setup=bool(raw.get("notify_admin_on_setup", True)),
            notify_admin_on_lifecycle=bool(
                raw.get("notify_admin_on_lifecycle", True)
            ),
            state_path=str(raw.get("state_path") or data_root / "ai_market_live_state_v3.json"),
            history_path=str(
                raw.get("history_path") or data_root / "ai_market_live_history_v3.jsonl"
            ),
        )


class LiveAIMarketStateStore:
    def __init__(self, state_path: str | Path, history_path: str | Path) -> None:
        self.state_path = Path(state_path)
        self.history_path = Path(history_path)
        self.lock = threading.RLock()

    @staticmethod
    def empty() -> dict:
        return {
            "schema": LIVE_STATE_SCHEMA,
            "research_status": RESEARCH_STATUS,
            "last_attempt_ms": 0,
            "last_success_ms": 0,
            "last_ai_scan_ms": 0,
            "last_monitor_ms": 0,
            "last_error_ms": 0,
            "last_duplicate_ms": 0,
            "last_error": None,
            "scan_count": 0,
            "monitor_count": 0,
            "decision_counts": {"SETUP": 0, "NO_TRADE": 0},
            "setup_stats": empty_setup_stats(),
            "active_setup": None,
            "last_setup": None,
            "latest": None,
        }

    def load(self) -> dict:
        with self.lock:
            if not self.state_path.exists():
                return self.empty()
            try:
                value = json.loads(self.state_path.read_text(encoding="utf-8-sig"))
            except Exception as exc:
                raise LiveAIMarketError(f"live AI state is invalid: {exc}") from exc
            if not isinstance(value, dict) or value.get("schema") != LIVE_STATE_SCHEMA:
                raise LiveAIMarketError("live AI state schema is invalid")
            return value

    def save(self, state: dict) -> None:
        with self.lock:
            _atomic_json_write(self.state_path, state)

    def append_record(self, record: dict) -> None:
        with self.lock:
            self.history_path.parent.mkdir(parents=True, exist_ok=True)
            with self.history_path.open("a", encoding="utf-8", newline="\n") as handle:
                handle.write(json.dumps(record, sort_keys=True, separators=(",", ":")))
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            try:
                os.chmod(self.history_path, 0o600)
            except OSError:
                pass


class LiveAIMarketEngine:
    def __init__(
        self,
        config: LiveAIMarketConfig,
        client: OpenAIRangeSetupClient | None = None,
        now_ms_fn: Callable[[], int] | None = None,
    ) -> None:
        self.config = config
        self.client = client or OpenAIRangeSetupClient(
            MarketScannerConfig(
                model=config.model,
                reasoning_effort=config.reasoning_effort,
                api_key_env=config.api_key_env,
                timeout_sec=config.request_timeout_sec,
                max_output_tokens=config.max_output_tokens,
            )
        )
        self.store = LiveAIMarketStateStore(config.state_path, config.history_path)
        self.now_ms_fn = now_ms_fn or (lambda: int(time.time() * 1000))
        self.scan_lock = threading.Lock()

    def due(self, now_ms_value: int | None = None) -> bool:
        if not self.config.enabled:
            return False
        current = int(now_ms_value or self.now_ms_fn())
        state = self.store.load()
        error_ms = int(state.get("last_error_ms", 0) or 0)
        success_ms = int(state.get("last_success_ms", 0) or 0)
        if error_ms > success_ms:
            return current >= error_ms + self.config.failure_retry_sec * 1000
        active = state.get("active_setup")
        if isinstance(active, dict):
            monitor_ms = int(state.get("last_monitor_ms", 0) or 0)
            if monitor_ms <= 0:
                monitor_ms = max(
                    int(active.get("created_at_ms", 0) or 0),
                    int(state.get("last_ai_scan_ms", 0) or 0),
                )
            return current >= monitor_ms + self.config.setup_monitor_interval_sec * 1000
        ai_scan_ms = int(state.get("last_ai_scan_ms", 0) or 0)
        duplicate_ms = int(state.get("last_duplicate_ms", 0) or 0)
        anchor = max(ai_scan_ms, duplicate_ms)
        if anchor <= 0:
            return True
        return current >= anchor + self.config.scan_interval_sec * 1000

    def _record_error(self, error: Exception, attempted_at: int) -> dict:
        state = self.store.load()
        state["last_attempt_ms"] = attempted_at
        state["last_error_ms"] = self.now_ms_fn()
        state["last_error"] = str(error)[:300]
        self.store.save(state)
        return {"status": "ERROR", "error": state["last_error"]}

    def run_once(
        self,
        fetch_klines: Callable[[str, str, int], list[dict]],
        binance_auth_verified: bool,
        symbol_rules: dict[str, dict] | None = None,
    ) -> dict:
        if not self.config.enabled:
            return {"status": "DISABLED"}
        if not self.scan_lock.acquire(blocking=False):
            return {"status": "BUSY"}
        attempted_at = self.now_ms_fn()
        try:
            state = self.store.load()
            state["last_attempt_ms"] = attempted_at
            self.store.save(state)
            active = state.get("active_setup") if isinstance(state.get("active_setup"), dict) else None
            if active:
                pair = str(active.get("pair", ""))
                monitor_limit = min(self.config.candle_limit, 96)
                active_candles = fetch_klines(pair, "15m", monitor_limit)
                updated, events = update_shadow_setup(
                    active,
                    active_candles,
                    attempted_at,
                )
                stored_stats = (
                    state.get("setup_stats")
                    if isinstance(state.get("setup_stats"), dict)
                    else {}
                )
                stats = {**empty_setup_stats(), **stored_stats}
                if any(event.get("event") == "FILLED" for event in events):
                    stats["filled"] = int(stats.get("filled", 0)) + 1
                for event in events:
                    self.store.append_record(
                        {
                            "schema": "KT_AI_RANGE_SETUP_EVENT_V1",
                            "research_status": RESEARCH_STATUS,
                            "orders_allowed": False,
                            "setup_id": updated.get("id"),
                            "pair": updated.get("pair"),
                            "side": updated.get("side"),
                            **event,
                        }
                    )
                state["setup_stats"] = stats
                if updated.get("status") in TERMINAL_STATUSES:
                    state["setup_stats"] = apply_terminal_stats(stats, updated)
                    updated["result_counted"] = True
                    state["last_setup"] = updated
                    state["active_setup"] = None
                else:
                    state["active_setup"] = updated
                state["last_monitor_ms"] = attempted_at
                state["last_success_ms"] = attempted_at
                state["last_error"] = None
                state["monitor_count"] = int(state.get("monitor_count", 0) or 0) + 1
                self.store.save(state)
                return {
                    "status": "MONITORED_SHADOW_SETUP",
                    "setup_id": updated.get("id"),
                    "setup_status": updated.get("status"),
                    "events": events,
                    "setup": updated,
                }
            if self.config.require_authenticated_binance and not binance_auth_verified:
                raise LiveAIMarketError("Binance Futures credentials are not verified")
            candles = {
                symbol: fetch_klines(symbol, "15m", self.config.candle_limit)
                for symbol in self.config.symbols
            }
            snapshot = build_live_snapshot(
                candles,
                self.config.symbols,
                symbol_rules=symbol_rules,
                now_ms_value=attempted_at,
                min_closed_bars=self.config.min_closed_bars,
            )
            latest = state.get("latest") if isinstance(state.get("latest"), dict) else {}
            if latest.get("snapshot_id") == snapshot["snapshot_id"]:
                state["last_duplicate_ms"] = self.now_ms_fn()
                self.store.save(state)
                return {"status": "DUPLICATE", "snapshot_id": snapshot["snapshot_id"]}
            decision, metadata = self.client.decide(snapshot, self.config.prompt_id)
            market_context = assert_live_decision_grounded(snapshot, decision)
            validated_plan = validate_range_setup(decision, snapshot)
            completed_at = self.now_ms_fn()
            record = {
                "schema": LIVE_RECORD_SCHEMA,
                "research_status": RESEARCH_STATUS,
                "orders_allowed": False,
                "captured_at_ms": attempted_at,
                "completed_at_ms": completed_at,
                "binance_auth_verified": bool(binance_auth_verified),
                "snapshot_id": snapshot["snapshot_id"],
                "decision_time_ms": snapshot["decision_time_ms"],
                "snapshot": snapshot,
                "decision": decision.as_dict(),
                "market_context": market_context,
                "validated_plan": validated_plan,
                "openai": metadata,
            }
            self.store.append_record(record)
            state = self.store.load()
            state["last_success_ms"] = completed_at
            state["last_ai_scan_ms"] = completed_at
            state["last_error"] = None
            state["scan_count"] = int(state.get("scan_count", 0) or 0) + 1
            counts = state.get("decision_counts")
            if not isinstance(counts, dict):
                counts = {"SETUP": 0, "NO_TRADE": 0}
            counts[decision.action] = int(counts.get(decision.action, 0) or 0) + 1
            state["decision_counts"] = counts
            if decision.action == "SETUP":
                shadow_setup = create_shadow_setup(
                    decision,
                    validated_plan,
                    snapshot["decision_time_ms"],
                )
                state["active_setup"] = shadow_setup
                stored_stats = (
                    state.get("setup_stats")
                    if isinstance(state.get("setup_stats"), dict)
                    else {}
                )
                stats = {**empty_setup_stats(), **stored_stats}
                stats["created"] = int(stats.get("created", 0)) + 1
                state["setup_stats"] = stats
                state["last_monitor_ms"] = completed_at
                self.store.append_record(
                    {
                        "schema": "KT_AI_RANGE_SETUP_EVENT_V1",
                        "research_status": RESEARCH_STATUS,
                        "orders_allowed": False,
                        "event": "CREATED",
                        "at_ms": snapshot["decision_time_ms"],
                        "setup_id": shadow_setup["id"],
                        "pair": shadow_setup["pair"],
                        "side": shadow_setup["side"],
                    }
                )
            state["latest"] = {
                "snapshot_id": snapshot["snapshot_id"],
                "decision_time_ms": snapshot["decision_time_ms"],
                "completed_at_ms": completed_at,
                "binance_auth_verified": bool(binance_auth_verified),
                "feature_set": LIVE_FEATURE_SET,
                "decision": decision.as_dict(),
                "market_context": market_context,
                "validated_plan": validated_plan,
                "openai": metadata,
            }
            self.store.save(state)
            return {
                "status": "RECORDED_SHADOW_ONLY",
                "snapshot_id": snapshot["snapshot_id"],
                "decision": decision.as_dict(),
                "validated_plan": validated_plan,
                "setup": state.get("active_setup"),
            }
        except Exception as exc:
            return self._record_error(exc, attempted_at)
        finally:
            self.scan_lock.release()

    def summary(self) -> dict:
        state = self.store.load()
        prompt = range_setup_prompt_definition(self.config.prompt_id)
        return {
            "enabled": self.config.enabled,
            "mode": "RESEARCH_SHADOW_ONLY",
            "research_status": RESEARCH_STATUS,
            "model": self.config.model,
            "prompt_id": self.config.prompt_id,
            "prompt_version": prompt["version"],
            "feature_set": LIVE_FEATURE_SET,
            "openai_key_present": bool(self.client.config.api_key),
            "symbols": list(self.config.symbols),
            "scan_interval_sec": self.config.scan_interval_sec,
            "setup_monitor_interval_sec": self.config.setup_monitor_interval_sec,
            "notify_admin_on_setup": self.config.notify_admin_on_setup,
            "notify_admin_on_lifecycle": self.config.notify_admin_on_lifecycle,
            "last_attempt_ms": state.get("last_attempt_ms", 0),
            "last_success_ms": state.get("last_success_ms", 0),
            "last_error_ms": state.get("last_error_ms", 0),
            "last_duplicate_ms": state.get("last_duplicate_ms", 0),
            "last_error": state.get("last_error"),
            "scan_count": state.get("scan_count", 0),
            "monitor_count": state.get("monitor_count", 0),
            "decision_counts": state.get("decision_counts", {}),
            "setup_stats": state.get("setup_stats", empty_setup_stats()),
            "active_setup": state.get("active_setup"),
            "last_setup": state.get("last_setup"),
            "latest": state.get("latest"),
            "orders_allowed": False,
        }
