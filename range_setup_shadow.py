#!/usr/bin/env python3
"""Deterministic lifecycle tracking for AI-generated range setups."""

from __future__ import annotations

import hashlib
from typing import Any


SHADOW_SETUP_SCHEMA = "KT_AI_RANGE_SHADOW_SETUP_V1"
TERMINAL_STATUSES = {"SL_HIT", "TP2_HIT", "EXPIRED", "TIME_EXIT"}


def empty_setup_stats() -> dict:
    return {
        "created": 0,
        "filled": 0,
        "closed": 0,
        "tp2_hit": 0,
        "sl_hit": 0,
        "expired": 0,
        "time_exit": 0,
        "wins": 0,
        "losses": 0,
        "breakeven": 0,
        "total_r": 0.0,
    }


def create_shadow_setup(decision, validation: dict, decision_time_ms: int) -> dict:
    decision_data = decision.as_dict()
    setup_id = "P6S-" + hashlib.sha256(
        (
            f"{decision_time_ms}|{decision.pair}|{decision.side}|"
            f"{decision.entry_zone_low}|{decision.entry_zone_high}|{decision.stop_loss}"
        ).encode("utf-8")
    ).hexdigest()[:14].upper()
    return {
        "schema": SHADOW_SETUP_SCHEMA,
        "id": setup_id,
        "status": "PENDING",
        "orders_allowed": False,
        "pair": decision.pair,
        "side": decision.side,
        "created_at_ms": int(decision_time_ms),
        "expires_at_ms": int(decision_time_ms + decision.expiry_hours * 3600 * 1000),
        "last_checked_ms": int(decision_time_ms),
        "filled_at_ms": 0,
        "entry_price": 0.0,
        "last_market_close_ms": 0,
        "last_market_price": 0.0,
        "tp1_hit": False,
        "tp1_hit_at_ms": 0,
        "closed_at_ms": 0,
        "exit_price": 0.0,
        "result_r": None,
        "result_counted": False,
        "decision": decision_data,
        "validation": dict(validation),
    }


def _entry_fill(row: dict, zone_low: float, zone_high: float) -> float:
    open_price = float(row["open"])
    return min(max(open_price, zone_low), zone_high)


def _leg_r(
    side: str,
    entry: float,
    exit_price: float,
    stop_loss: float,
    cost_pct: float,
) -> float:
    gross_risk = abs(entry - stop_loss)
    cost = entry * cost_pct
    denominator = gross_risk + cost
    if denominator <= 0:
        return 0.0
    direction = 1.0 if side == "LONG" else -1.0
    net_pnl = direction * (exit_price - entry) - cost
    return net_pnl / denominator


def _close_setup(
    setup: dict,
    status: str,
    row: dict,
    exit_price: float,
    closed_at_ms: int | None = None,
) -> None:
    decision = setup["decision"]
    entry = float(setup["entry_price"])
    stop = float(decision["stop_loss"])
    cost_pct = float(setup["validation"].get("round_trip_cost_pct", 0.002))
    final_leg = _leg_r(setup["side"], entry, exit_price, stop, cost_pct)
    if setup.get("tp1_hit"):
        first_leg = _leg_r(
            setup["side"], entry, float(decision["take_profit_1"]), stop, cost_pct
        )
        result_r = (first_leg + final_leg) / 2.0
    else:
        result_r = final_leg
    setup["status"] = status
    setup["closed_at_ms"] = int(closed_at_ms or row["close_time"])
    setup["exit_price"] = float(exit_price)
    setup["result_r"] = round(result_r, 6)


def update_shadow_setup(
    setup: dict,
    candles: list[dict],
    now_ms_value: int,
) -> tuple[dict, list[dict]]:
    """Advance one setup using confirmed 15-minute bars, pessimistic on ambiguity."""
    updated = dict(setup)
    updated["decision"] = dict(setup.get("decision", {}))
    updated["validation"] = dict(setup.get("validation", {}))
    events = []
    if updated.get("status") in TERMINAL_STATUSES:
        return updated, events
    last_checked = int(updated.get("last_checked_ms", updated.get("created_at_ms", 0)) or 0)
    expiry = int(updated["expires_at_ms"])
    decision = updated["decision"]
    zone_low = float(decision["entry_zone_low"])
    zone_high = float(decision["entry_zone_high"])
    stop = float(decision["stop_loss"])
    tp1 = float(decision["take_profit_1"])
    tp2 = float(decision["take_profit_2"])
    side = str(updated["side"])
    confirmed = sorted(
        (
            row
            for row in candles
            if int(row.get("close_time", 0) or 0) <= int(now_ms_value)
            and int(row.get("close_time", 0) or 0) > last_checked
            and int(row.get("open_time", 0) or 0) > int(updated["created_at_ms"])
        ),
        key=lambda row: int(row["open_time"]),
    )
    last_row = None
    for row in confirmed:
        if int(row["open_time"]) >= expiry:
            break
        last_row = row
        low = float(row["low"])
        high = float(row["high"])
        filled_this_bar = False
        if updated["status"] == "PENDING" and low <= zone_high and high >= zone_low:
            updated["status"] = "ACTIVE"
            updated["filled_at_ms"] = int(row["open_time"])
            updated["entry_price"] = _entry_fill(row, zone_low, zone_high)
            filled_this_bar = True
            events.append(
                {
                    "event": "FILLED",
                    "at_ms": int(row["open_time"]),
                    "price": updated["entry_price"],
                }
            )
        if updated["status"] not in ("ACTIVE", "TP1_HIT"):
            continue
        updated["last_market_close_ms"] = int(row["close_time"])
        updated["last_market_price"] = float(row["close"])
        stop_hit = low <= stop if side == "LONG" else high >= stop
        tp1_hit = high >= tp1 if side == "LONG" else low <= tp1
        tp2_hit = high >= tp2 if side == "LONG" else low <= tp2
        if stop_hit:
            _close_setup(updated, "SL_HIT", row, stop)
            events.append(
                {"event": "SL_HIT", "at_ms": int(row["close_time"]), "price": stop}
            )
            break
        # An OHLC bar does not reveal whether a target traded before or after
        # the first entry touch. Ignore same-bar targets instead of awarding a
        # result that may not have been attainable; same-bar stops remain valid.
        if filled_this_bar:
            continue
        if tp1_hit and not updated.get("tp1_hit"):
            updated["tp1_hit"] = True
            updated["tp1_hit_at_ms"] = int(row["close_time"])
            updated["status"] = "TP1_HIT"
            events.append(
                {"event": "TP1_HIT", "at_ms": int(row["close_time"]), "price": tp1}
            )
        if tp2_hit:
            if not updated.get("tp1_hit"):
                updated["tp1_hit"] = True
                updated["tp1_hit_at_ms"] = int(row["close_time"])
            _close_setup(updated, "TP2_HIT", row, tp2)
            events.append(
                {"event": "TP2_HIT", "at_ms": int(row["close_time"]), "price": tp2}
            )
            break
    if confirmed:
        updated["last_checked_ms"] = int(confirmed[-1]["close_time"])
    if updated["status"] not in TERMINAL_STATUSES and int(now_ms_value) >= expiry:
        if updated["status"] == "PENDING":
            updated["status"] = "EXPIRED"
            updated["closed_at_ms"] = expiry
            updated["result_r"] = 0.0
            events.append({"event": "EXPIRED", "at_ms": expiry, "price": 0.0})
        else:
            exit_row = last_row or (confirmed[-1] if confirmed else None)
            stored_price = float(updated.get("last_market_price", 0) or 0)
            if last_row is not None:
                exit_price = float(last_row["close"])
                exit_row = last_row
            elif stored_price > 0:
                exit_price = stored_price
                exit_row = {
                    "close_time": int(
                        updated.get("last_market_close_ms", expiry) or expiry
                    )
                }
            else:
                exit_price = 0.0
            if exit_row is not None and exit_price > 0:
                _close_setup(
                    updated,
                    "TIME_EXIT",
                    exit_row,
                    exit_price,
                    closed_at_ms=expiry,
                )
                events.append(
                    {
                        "event": "TIME_EXIT",
                        "at_ms": expiry,
                        "price": exit_price,
                    }
                )
    return updated, events


def apply_terminal_stats(stats: dict[str, Any], setup: dict) -> dict:
    result = {**empty_setup_stats(), **(stats if isinstance(stats, dict) else {})}
    if setup.get("status") not in TERMINAL_STATUSES or setup.get("result_counted"):
        return result
    result["closed"] = int(result.get("closed", 0)) + 1
    status = str(setup["status"])
    field = {
        "TP2_HIT": "tp2_hit",
        "SL_HIT": "sl_hit",
        "EXPIRED": "expired",
        "TIME_EXIT": "time_exit",
    }[status]
    result[field] = int(result.get(field, 0)) + 1
    value = float(setup.get("result_r", 0) or 0)
    result["total_r"] = round(float(result.get("total_r", 0) or 0) + value, 6)
    if value > 0.05:
        result["wins"] = int(result.get("wins", 0)) + 1
    elif value < -0.05:
        result["losses"] = int(result.get("losses", 0)) + 1
    else:
        result["breakeven"] = int(result.get("breakeven", 0)) + 1
    return result
