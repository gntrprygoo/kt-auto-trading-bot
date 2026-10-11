import argparse
import hashlib
import json
import math
import pathlib
import time
import urllib.parse
import urllib.request

from build_btc_structure_review import read_json
from strategy_d_momentum_engine import (
    D1,
    MS_4H,
    MS_DAY,
    simulate,
)


SCHEMA = "KT_STRATEGY_D1_FORWARD_SHADOW_V1"
DEFAULT_BASE_URL = "https://fapi.binance.com"
FUNDING_SOURCE = "BINANCE_PUBLIC_FUNDING_RATE_HISTORY"


def write_json_atomic(path, value):
    output = pathlib.Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(output.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(value, handle, ensure_ascii=True, indent=2)
        handle.write("\n")
    temporary.replace(output)


def http_get_json(url, params, timeout=20):
    query = urllib.parse.urlencode(params)
    request = urllib.request.Request(
        f"{url}?{query}",
        headers={"User-Agent": "kt-strategy-d1-shadow/1.0"},
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def parse_kline(row):
    return {
        "open_time": int(row[0]),
        "close_time": int(row[6]),
        "open": float(row[1]),
        "high": float(row[2]),
        "low": float(row[3]),
        "close": float(row[4]),
        "volume": float(row[5]),
    }


def parse_funding_rate(row):
    if row.get("symbol") != "BTCUSDT":
        raise ValueError("Unexpected funding-rate symbol")
    funding_time = int(row["fundingTime"])
    funding_rate = float(row["fundingRate"])
    mark_price = float(row["markPrice"])
    if (
        not math.isfinite(funding_rate)
        or not math.isfinite(mark_price)
        or mark_price <= 0
    ):
        raise ValueError("Invalid Binance funding-rate row")
    return {
        "funding_time": funding_time,
        "funding_rate": funding_rate,
        "mark_price": mark_price,
    }


def fetch_4h_candles(
    base_url,
    start_ms,
    end_ms,
    get_json=http_get_json,
):
    rows = {}
    cursor = int(start_ms)
    while cursor <= end_ms:
        payload = get_json(
            f"{base_url.rstrip('/')}/fapi/v1/klines",
            {
                "symbol": "BTCUSDT",
                "interval": "4h",
                "startTime": cursor,
                "endTime": int(end_ms),
                "limit": 1500,
            },
            timeout=20,
        )
        if not isinstance(payload, list):
            raise RuntimeError("Unexpected Binance kline response")
        if not payload:
            break
        for raw in payload:
            candle = parse_kline(raw)
            if candle["open_time"] <= end_ms:
                rows[candle["open_time"]] = candle
        next_cursor = int(payload[-1][0]) + MS_4H
        if next_cursor <= cursor:
            raise RuntimeError("Binance pagination did not advance")
        cursor = next_cursor
        if len(payload) < 1500:
            break
    return [rows[key] for key in sorted(rows)]


def fetch_funding_rates(
    base_url,
    start_ms,
    end_ms,
    get_json=http_get_json,
):
    rows = {}
    cursor = int(start_ms)
    while cursor <= end_ms:
        payload = get_json(
            f"{base_url.rstrip('/')}/fapi/v1/fundingRate",
            {
                "symbol": "BTCUSDT",
                "startTime": cursor,
                "endTime": int(end_ms),
                "limit": 1000,
            },
            timeout=20,
        )
        if not isinstance(payload, list):
            raise RuntimeError(
                "Unexpected Binance funding-rate response"
            )
        if not payload:
            break
        parsed = [parse_funding_rate(row) for row in payload]
        for row in parsed:
            if cursor <= row["funding_time"] <= end_ms:
                rows[row["funding_time"]] = row
        next_cursor = parsed[-1]["funding_time"] + 1
        if next_cursor <= cursor:
            raise RuntimeError(
                "Binance funding pagination did not advance"
            )
        cursor = next_cursor
        if len(payload) < 1000:
            break
    return [rows[key] for key in sorted(rows)]


def merge_candles(paths):
    rows = {}
    for path in paths:
        for candle in read_json(path):
            rows[int(candle["open_time"])] = candle
    return [rows[key] for key in sorted(rows)]


def trade_id(record):
    raw = (
        f"{record['signal_time']}|{record['entry_time']}|"
        f"{record['exit_time']}|{record['side']}"
    )
    return hashlib.sha256(raw.encode("ascii")).hexdigest()[:20]


def public_position(position):
    if position is None:
        return None
    return {
        "side": position["side"],
        "signal_time": int(position["signal_time"]),
        "entry_time": int(position["entry_time"]),
        "entry": float(position["entry"]),
        "initial_stop": float(position["initial_stop"]),
        "active_stop": float(position["stop"]),
        "best_close": float(position["best_close"]),
        "signal_returns": dict(position["signal_returns"]),
    }


def public_entry_from_record(record):
    return {
        "side": record["side"],
        "signal_time": int(record["signal_time"]),
        "entry_time": int(record["entry_time"]),
        "entry": float(record["entry"]),
        "initial_stop": float(record["initial_stop"]),
        "signal_returns": dict(record["signal_returns"]),
    }


def update_shadow_state(previous, records, position, as_of_ms):
    if previous is None:
        state = {
            "schema": SCHEMA,
            "monitor_started_at": int(as_of_ms),
            "last_poll_at": int(as_of_ms),
            "last_closed_4h": None,
            "notified_entry_times": [],
            "recorded_trade_ids": [],
            "closed_trades": [],
            "current_position": public_position(position),
        }
        return state, {
            "initialized": True,
            "new_entries": [],
            "new_closed_trades": [],
        }
    if previous.get("schema") != SCHEMA:
        raise ValueError("Unsupported D1 shadow state schema")
    if int(as_of_ms) < int(previous.get("last_poll_at", 0)):
        raise ValueError("D1 shadow poll time cannot move backwards")

    state = dict(previous)
    notified = {
        int(value)
        for value in state.get("notified_entry_times", [])
    }
    recorded = set(state.get("recorded_trade_ids", []))
    started_at = int(state["monitor_started_at"])
    new_entries = []
    entry_candidates = [
        public_entry_from_record(record)
        for record in records
        if int(record["entry_time"]) > started_at
    ]
    if (
        position is not None
        and int(position["entry_time"]) > started_at
    ):
        entry_candidates.append(public_position(position))
    for entry in sorted(
        entry_candidates,
        key=lambda item: int(item["entry_time"]),
    ):
        entry_time = int(entry["entry_time"])
        if entry_time in notified:
            continue
        new_entries.append(entry)
        notified.add(entry_time)

    new_closed = []
    closed_trades = list(state.get("closed_trades", []))
    for record in records:
        if int(record["exit_time"]) <= started_at:
            continue
        identifier = trade_id(record)
        if identifier in recorded:
            continue
        item = {
            "trade_id": identifier,
            **record,
        }
        new_closed.append(item)
        closed_trades.append(item)
        recorded.add(identifier)
    state.update({
        "last_poll_at": int(as_of_ms),
        "notified_entry_times": sorted(notified),
        "recorded_trade_ids": sorted(recorded),
        "closed_trades": closed_trades,
        "current_position": public_position(position),
    })
    return state, {
        "initialized": False,
        "new_entries": new_entries,
        "new_closed_trades": new_closed,
    }


def run_shadow(candles, previous, as_of_ms):
    if not candles:
        raise ValueError("No 4H candles available")
    closed_candles = [
        candle
        for candle in candles
        if int(candle["close_time"]) <= as_of_ms
    ]
    if not closed_candles:
        raise ValueError("No closed 4H candles available")
    history_start = int(closed_candles[0]["close_time"])
    simulation_start = history_start + 90 * MS_DAY
    records, diagnostics, position = simulate(
        candles,
        simulation_start,
        int(as_of_ms),
        D1,
        allowed_sides=("LONG",),
        finalize=False,
        return_state=True,
    )
    state, changes = update_shadow_state(
        previous,
        records,
        position,
        as_of_ms,
    )
    last_closed_4h = int(closed_candles[-1]["close_time"])
    state["last_closed_4h"] = last_closed_4h
    return state, {
        **changes,
        "engine": D1.name,
        "mode": "FORWARD_SHADOW_LONG_ONLY",
        "candles": len(candles),
        "closed_candles": len(closed_candles),
        "last_closed_4h": last_closed_4h,
        "current_position": public_position(position),
        "closed_forward_trades": len(
            state["closed_trades"]
        ),
        "diagnostics": diagnostics,
        "production_orders": False,
    }


def report_has_changes(report):
    return bool(
        report["initialized"]
        or report["new_entries"]
        or report["new_closed_trades"]
    )


def enrich_trade_funding(record, funding_rows):
    entry_time = int(record["entry_time"])
    exit_time = int(record["exit_time"])
    initial_risk = float(record["initial_risk"])
    if initial_risk <= 0:
        raise ValueError("Invalid initial risk for funding reconciliation")
    applicable = [
        row
        for row in funding_rows
        if entry_time <= int(row["funding_time"]) <= exit_time
    ]
    direction = -1.0 if record["side"] == "LONG" else 1.0
    observed_funding_r = sum(
        direction
        * float(row["funding_rate"])
        * float(row["mark_price"])
        / initial_risk
        for row in applicable
    )
    record.update({
        "funding_source": FUNDING_SOURCE,
        "funding_event_count": len(applicable),
        "funding_rate_sum": sum(
            float(row["funding_rate"])
            for row in applicable
        ),
        "observed_funding_R": observed_funding_r,
        "observed_baseline_net_R": (
            float(record["gross_R"])
            - float(record["baseline_cost_R"])
            + observed_funding_r
        ),
        "observed_stress_net_R": (
            float(record["gross_R"])
            - float(record["stress_cost_R"])
            + observed_funding_r
        ),
    })
    return record


def reconcile_state_funding(
    state,
    report,
    base_url,
    as_of_ms,
    get_json=http_get_json,
):
    pending = [
        record
        for record in state.get("closed_trades", [])
        if record.get("funding_source") != FUNDING_SOURCE
    ]
    if pending:
        start_ms = min(int(row["entry_time"]) for row in pending)
        end_ms = max(int(row["exit_time"]) for row in pending)
        funding_rows = fetch_funding_rates(
            base_url,
            start_ms,
            end_ms,
            get_json=get_json,
        )
        for record in pending:
            enrich_trade_funding(record, funding_rows)
    state["funding_reconciliation"] = {
        "source": FUNDING_SOURCE,
        "last_reconciled_at": int(as_of_ms),
        "unreconciled_trades": 0,
    }
    by_id = {
        record["trade_id"]: record
        for record in state.get("closed_trades", [])
    }
    report["new_closed_trades"] = [
        by_id.get(record["trade_id"], record)
        for record in report["new_closed_trades"]
    ]
    report["funding_reconciled_trades"] = len(pending)
    return state, report


def main():
    parser = argparse.ArgumentParser(
        description="Strategy D1 LONG-only forward shadow"
    )
    parser.add_argument(
        "--state",
        default=".audit/d1_forward_shadow_state.json",
    )
    parser.add_argument("--candles-4h", action="append")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--as-of-ms", type=int)
    parser.add_argument("--history-days", type=int, default=370)
    parser.add_argument("--quiet-unchanged", action="store_true")
    args = parser.parse_args()
    as_of_ms = int(args.as_of_ms or time.time() * 1000)
    if args.candles_4h:
        candles = [
            row
            for row in merge_candles(args.candles_4h)
            if int(row["open_time"]) <= as_of_ms
        ]
    else:
        candles = fetch_4h_candles(
            args.base_url,
            as_of_ms - args.history_days * MS_DAY,
            as_of_ms,
        )
    state_path = pathlib.Path(args.state)
    previous = (
        read_json(state_path)
        if state_path.exists()
        else None
    )
    state, report = run_shadow(
        candles,
        previous,
        as_of_ms,
    )
    state, report = reconcile_state_funding(
        state,
        report,
        args.base_url,
        as_of_ms,
    )
    write_json_atomic(state_path, state)
    if not args.quiet_unchanged or report_has_changes(report):
        print(json.dumps({
            **report,
            "state": str(state_path.resolve()),
        }, indent=2))


if __name__ == "__main__":
    main()
