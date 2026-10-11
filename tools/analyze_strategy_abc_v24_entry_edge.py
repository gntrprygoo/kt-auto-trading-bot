import argparse
import json
import pathlib
import statistics
from collections import defaultdict
from datetime import datetime, timezone

from build_btc_structure_review import read_json, write_json


DEFAULT_HORIZONS = (16, 48, 96)


def merge_candles(paths):
    rows = {}
    for path in paths:
        for candle in read_json(path):
            rows[int(candle["open_time"])] = candle
    return [rows[key] for key in sorted(rows)]


def event_stop(event, stop_buffer_atr):
    atr = float(event["atr_15m"])
    if event["side"] == "LONG":
        return min(
            float(event["extreme"]) - 0.10 * atr,
            float(event["level"]) - stop_buffer_atr * atr,
        )
    return max(
        float(event["extreme"]) + 0.10 * atr,
        float(event["level"]) + stop_buffer_atr * atr,
    )


def first_hit(rows, side, entry, risk, reward_r):
    reward = reward_r * risk
    for candle in rows:
        high = float(candle["high"])
        low = float(candle["low"])
        if side == "LONG":
            favorable = high >= entry + reward
            adverse = low <= entry - risk
        else:
            favorable = low <= entry - reward
            adverse = high >= entry + risk
        if favorable and adverse:
            return "BOTH_SAME_BAR"
        if favorable:
            return "FAVORABLE_FIRST"
        if adverse:
            return "ADVERSE_FIRST"
    return "UNRESOLVED"


def event_horizon_record(
    event,
    candles,
    horizon,
    stop_buffer_atr,
    cost_pct,
):
    signal_index = int(event["signal_index"])
    entry_index = signal_index + 1
    if entry_index >= len(candles):
        return None, "missing_next_open"
    if (
        int(candles[signal_index]["close_time"])
        != int(event["signal_time"])
    ):
        return None, "signal_index_mismatch"

    entry = float(candles[entry_index]["open"])
    stop = event_stop(event, stop_buffer_atr)
    risk = (
        entry - stop
        if event["side"] == "LONG"
        else stop - entry
    )
    if entry <= 0 or risk <= 0:
        return None, "invalid_risk"
    rows = candles[
        entry_index:min(len(candles), entry_index + horizon)
    ]
    if len(rows) < horizon:
        return None, "incomplete_horizon"

    if event["side"] == "LONG":
        favorable = max(
            float(candle["high"]) - entry for candle in rows
        )
        adverse = max(
            entry - float(candle["low"]) for candle in rows
        )
        close_r = (
            float(rows[-1]["close"]) - entry
        ) / risk
    else:
        favorable = max(
            entry - float(candle["low"]) for candle in rows
        )
        adverse = max(
            float(candle["high"]) - entry for candle in rows
        )
        close_r = (
            entry - float(rows[-1]["close"])
        ) / risk
    risk_pct = risk / entry
    cost_r = cost_pct / risk_pct
    return {
        "event_id": event["event_id"],
        "signal_time": int(event["signal_time"]),
        "signal_year_utc": datetime.fromtimestamp(
            int(event["signal_time"]) / 1000,
            timezone.utc,
        ).year,
        "path": event["path"],
        "side": event["side"],
        "transition": event["transition"],
        "horizon_bars": int(horizon),
        "entry": entry,
        "stop": stop,
        "risk_pct": risk_pct,
        "cost_R": cost_r,
        "MFE_R": favorable / risk,
        "MAE_R": adverse / risk,
        "close_R": close_r,
        "close_net_R": close_r - cost_r,
        "one_R_vs_stop": first_hit(
            rows,
            event["side"],
            entry,
            risk,
            1.0,
        ),
        "two_R_vs_stop": first_hit(
            rows,
            event["side"],
            entry,
            risk,
            2.0,
        ),
    }, "recorded"


def mean(rows, key):
    return sum(float(row[key]) for row in rows) / len(rows)


def summarize(rows):
    hit_keys = ("one_R_vs_stop", "two_R_vs_stop")
    net_values = [
        float(row["close_net_R"]) for row in rows
    ]
    net_mean = statistics.mean(net_values)
    net_std = (
        statistics.stdev(net_values)
        if len(net_values) > 1
        else 0.0
    )
    net_se = net_std / (len(net_values) ** 0.5)
    result = {
        "events": len(rows),
        "avg_risk_pct": round(mean(rows, "risk_pct"), 6),
        "median_risk_pct": round(statistics.median(
            float(row["risk_pct"]) for row in rows
        ), 6),
        "avg_cost_R": round(mean(rows, "cost_R"), 4),
        "avg_MFE_R": round(mean(rows, "MFE_R"), 4),
        "median_MFE_R": round(statistics.median(
            float(row["MFE_R"]) for row in rows
        ), 4),
        "avg_MAE_R": round(mean(rows, "MAE_R"), 4),
        "median_MAE_R": round(statistics.median(
            float(row["MAE_R"]) for row in rows
        ), 4),
        "avg_close_R": round(mean(rows, "close_R"), 4),
        "avg_close_net_R": round(
            net_mean,
            4,
        ),
        "median_close_net_R": round(
            statistics.median(net_values),
            4,
        ),
        "close_net_R_std": round(net_std, 4),
        "close_net_R_95pct_ci": {
            "low": round(net_mean - 1.96 * net_se, 4),
            "high": round(net_mean + 1.96 * net_se, 4),
        },
        "close_net_R_t_stat": (
            round(net_mean / net_se, 4)
            if net_se > 0 else None
        ),
        "positive_close_net": sum(
            float(row["close_net_R"]) > 0 for row in rows
        ),
    }
    for key in hit_keys:
        counts = {
            outcome: sum(
                row[key] == outcome for row in rows
            )
            for outcome in (
                "FAVORABLE_FIRST",
                "ADVERSE_FIRST",
                "BOTH_SAME_BAR",
                "UNRESOLVED",
            )
        }
        resolved = (
            counts["FAVORABLE_FIRST"]
            + counts["ADVERSE_FIRST"]
        )
        counts["favorable_rate_resolved"] = (
            round(counts["FAVORABLE_FIRST"] / resolved, 4)
            if resolved else None
        )
        result[key] = counts
    return result


def grouped_summary(rows, key):
    grouped = defaultdict(list)
    for row in rows:
        grouped[str(row[key])].append(row)
    return {
        name: summarize(values)
        for name, values in sorted(grouped.items())
    }


def evaluate(replay, candles, horizons, cost_pct):
    params = replay["parameters"]
    diagnostics = defaultdict(int)
    records = []
    for event in replay.get("events", []):
        for horizon in horizons:
            row, reason = event_horizon_record(
                event,
                candles,
                horizon,
                float(params["stop_buffer_atr"]),
                cost_pct,
            )
            diagnostics[reason] += 1
            if row:
                records.append(row)

    by_horizon = {}
    for horizon in horizons:
        rows = [
            row
            for row in records
            if row["horizon_bars"] == horizon
        ]
        by_horizon[str(horizon)] = {
            "all": summarize(rows),
            "paths": grouped_summary(rows, "path"),
            "sides": grouped_summary(rows, "side"),
            "years": grouped_summary(
                rows,
                "signal_year_utc",
            ),
            "transitions": grouped_summary(
                rows,
                "transition",
            ),
        }
    return {
        "schema": "KT_ABC_V24_ENTRY_EDGE_DIAGNOSTIC_V1",
        "engine": replay.get("engine"),
        "status": "RESEARCH_ONLY_NO_PARAMETER_SELECTION",
        "validation_role": (
            "HISTORICAL_TRAINING_SAMPLE_DIAGNOSTIC"
        ),
        "symbol": replay.get("symbol"),
        "period": replay.get("period"),
        "horizons": {
            str(value): f"{value * 15 // 60}h"
            for value in horizons
        },
        "cost_pct": cost_pct,
        "events_input": len(replay.get("events", [])),
        "diagnostics": dict(sorted(diagnostics.items())),
        "by_horizon": by_horizon,
        "production_changed": False,
        "records": records,
    }


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Measure fixed-horizon MFE/MAE for ABC V2.4 events"
        )
    )
    parser.add_argument("--replay", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument(
        "--horizon-bars",
        action="append",
        type=int,
    )
    parser.add_argument("--cost-pct", type=float, default=0.0014)
    args = parser.parse_args()
    replay = read_json(args.replay)
    paths = replay.get("data_source", {}).get("candles_15m")
    if not paths:
        raise SystemExit(
            "Replay does not contain explicit 15m candle paths"
        )
    horizons = tuple(
        args.horizon_bars or DEFAULT_HORIZONS
    )
    if any(value <= 0 for value in horizons):
        raise SystemExit("Horizon bars must be positive")
    result = evaluate(
        replay,
        merge_candles(paths),
        horizons,
        args.cost_pct,
    )
    write_json(args.output, result)
    print(json.dumps({
        "status": result["status"],
        "events_input": result["events_input"],
        "diagnostics": result["diagnostics"],
        "by_horizon": {
            key: value["all"]
            for key, value in result["by_horizon"].items()
        },
        "output": str(pathlib.Path(args.output).resolve()),
    }, indent=2))


if __name__ == "__main__":
    main()
