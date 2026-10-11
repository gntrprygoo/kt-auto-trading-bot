import argparse
import bisect
import json
import pathlib
from collections import defaultdict

import research_strategy_bc_v2 as common
import strategy_evidence_audit as audit


MS_DAY = 24 * 60 * 60 * 1000
MS_HOUR = 60 * 60 * 1000
CORE5 = {"BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"}


def read_json(path):
    with pathlib.Path(path).open("r", encoding="utf-8-sig") as handle:
        return json.load(handle)


def write_json(path, value):
    output = pathlib.Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(value, handle, ensure_ascii=True, indent=2)
        handle.write("\n")


def simulate_tp1_structure_runner(
    candles,
    signal_index,
    side,
    stop,
    structure_target,
    cost_pct,
    horizon_bars=384,
    tp1_fraction=0.50,
    profit_trigger_pct=0.015,
    profit_lock_pct=0.010,
):
    entry_index = signal_index + 1
    if entry_index >= len(candles):
        return None
    entry = float(candles[entry_index]["open"])
    risk = entry - stop if side == "LONG" else stop - entry
    reward = (
        structure_target - entry
        if side == "LONG"
        else entry - structure_target
    )
    if entry <= 0 or risk <= 0 or reward <= 0:
        return None
    risk_pct = risk / entry
    target_r = reward / risk
    if not 0.004 <= risk_pct <= 0.03 or target_r < 1.0:
        return None
    tp1 = entry + risk if side == "LONG" else entry - risk
    trigger = (
        entry * (1.0 + profit_trigger_pct)
        if side == "LONG"
        else entry * (1.0 - profit_trigger_pct)
    )
    lock = (
        entry * (1.0 + profit_lock_pct)
        if side == "LONG"
        else entry * (1.0 - profit_lock_pct)
    )
    active_stop = float(stop)
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

        target_hit = (
            float(candle["high"]) >= structure_target
            if side == "LONG"
            else float(candle["low"]) <= structure_target
        )
        tp1_touched = (
            float(candle["high"]) >= tp1
            if side == "LONG"
            else float(candle["low"]) <= tp1
        )
        trigger_touched = (
            float(candle["high"]) >= trigger
            if side == "LONG"
            else float(candle["low"]) <= trigger
        )
        lock_reached = (
            float(candle["high"]) >= lock
            if side == "LONG"
            else float(candle["low"]) <= lock
        )
        if target_hit:
            if not tp1_hit:
                gross_r += tp1_fraction
                remaining -= tp1_fraction
                tp1_hit = True
            gross_r += remaining * target_r
            remaining = 0.0
            outcome = "STRUCTURE_TARGET"
            exit_index = index
            exit_time = int(candle["close_time"])
            break
        if tp1_touched and not tp1_hit:
            gross_r += tp1_fraction
            remaining -= tp1_fraction
            tp1_hit = True
        if trigger_touched or (tp1_hit and lock_reached):
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
        gross_r += remaining * max(-1.0, min(target_r, mark_r))
    cost_r = cost_pct / risk_pct
    return {
        "gross_R_tp1_structure": gross_r,
        "net_R_tp1_structure": gross_r - cost_r,
        "net_R_tp1_structure_cost_0_20": (
            gross_r - 0.0020 / risk_pct
        ),
        "outcome_tp1_structure": outcome,
        "exit_time_tp1_structure": exit_time,
        "exit_index_tp1_structure": exit_index,
        "structure_target_R": target_r,
    }


def grouped_report(records, result_key, start_ms, end_ms):
    return {
        "overall": common.summarize(records, result_key),
        "long": common.summarize(
            [item for item in records if item["side"] == "LONG"],
            result_key,
        ),
        "short": common.summarize(
            [item for item in records if item["side"] == "SHORT"],
            result_key,
        ),
        "paths": {
            path: common.summarize(
                [item for item in records if item["path"] == path],
                result_key,
            )
            for path in ("A", "B", "C")
        },
        "folds_30d": common.fold_summaries(
            records,
            result_key,
            start_ms,
            end_ms,
        ),
    }


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Post-process frozen ABC signals with TP1 plus "
            "structural runner management"
        )
    )
    parser.add_argument("--replay", required=True)
    parser.add_argument("--cache-dir", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--cost-pct", type=float, default=0.0014)
    args = parser.parse_args()

    replay = read_json(args.replay)
    records = replay["variants"]["ABC_PRIMARY"]["records"]
    start_ms = audit.parse_timestamp(replay["period"]["start"])
    end_ms = audit.parse_timestamp(replay["period"]["end"])
    market = audit.MarketData(args.cache_dir)
    by_pair = defaultdict(list)
    for record in records:
        by_pair[record["pair"]].append(record)
    attached = []
    errors = []
    for number, (pair, pair_records) in enumerate(
        sorted(by_pair.items()),
        1,
    ):
        print(
            f"management {number}/{len(by_pair)} {pair}",
            flush=True,
        )
        try:
            candles = market.klines(
                pair,
                "15m",
                start_ms - 4 * MS_DAY,
                end_ms + 5 * MS_DAY,
            )
        except Exception as exc:
            errors.append(
                f"{pair}: {type(exc).__name__}: {exc}"
            )
            continue
        close_times = [int(item["close_time"]) for item in candles]
        for record in pair_records:
            index = bisect.bisect_left(
                close_times,
                int(record["signal_time"]),
            )
            if (
                index >= len(candles)
                or close_times[index] != int(record["signal_time"])
            ):
                errors.append(
                    f"{pair}: signal candle missing "
                    f"{record['signal_time']}"
                )
                continue
            target = float(record["structure_target"])
            result = simulate_tp1_structure_runner(
                candles,
                index,
                record["side"],
                float(record["stop"]),
                target,
                args.cost_pct,
            )
            if result is None:
                errors.append(
                    f"{pair}: management invalid "
                    f"{record['signal_time']}"
                )
                continue
            attached.append({**record, **result})

    universes = {
        "ALL_30": attached,
        "CORE5": [
            item for item in attached if item["pair"] in CORE5
        ],
        "BTC_ONLY": [
            item for item in attached if item["pair"] == "BTCUSDT"
        ],
        "NON_CORE": [
            item for item in attached if item["pair"] not in CORE5
        ],
    }
    result = {
        "engine": "ABC_TP1_STRUCTURE_RUNNER_DIAGNOSTIC_V1",
        "source_replay": str(pathlib.Path(args.replay).resolve()),
        "period": replay["period"],
        "management": {
            "tp1": "1R closes 50%",
            "runner": "remaining 50% to frozen structural target",
            "sl_plus": "+1.5% trigger moves stop to +1%",
            "timeout": "96h mark to market",
            "status": "diagnostic_only_not_approved",
        },
        "universes": {},
        "errors": errors,
    }
    for name, selected in universes.items():
        result["universes"][name] = {
            "base_cost": grouped_report(
                selected,
                "net_R_tp1_structure",
                start_ms,
                end_ms,
            ),
            "stress_cost_0_20": grouped_report(
                selected,
                "net_R_tp1_structure_cost_0_20",
                start_ms,
                end_ms,
            ),
        }
    write_json(args.output, result)
    print(json.dumps({
        name: {
            "base": report["base_cost"]["overall"],
            "stress": report["stress_cost_0_20"]["overall"],
            "paths": report["base_cost"]["paths"],
        }
        for name, report in result["universes"].items()
    }, indent=2))
    if errors:
        print(json.dumps({"errors": errors}, indent=2))


if __name__ == "__main__":
    main()
