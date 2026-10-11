import argparse
import bisect
import json
import pathlib
import statistics
from collections import Counter, defaultdict
from dataclasses import asdict
from datetime import datetime, timedelta, timezone

import abc_derivatives_context as derivatives
import abc_structure_engine as engine
import research_strategy_b4 as b4
import research_strategy_bc_v2 as common
import strategy_evidence_audit as audit


MS_DAY = 24 * 60 * 60 * 1000
MS_HOUR = 60 * 60 * 1000
COST_STRESS_PCT = 0.0020
PORTFOLIO_MAX_CONCURRENT = 3
SAME_SIDE_CLUSTER_MS = 60 * 60 * 1000


def read_json(path):
    with pathlib.Path(path).open("r", encoding="utf-8-sig") as handle:
        return json.load(handle)


def write_json(path, value):
    output = pathlib.Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(value, handle, ensure_ascii=True, indent=2)
        handle.write("\n")


def month_key(timestamp_ms, utc_offset_hours=7):
    local_tz = timezone(timedelta(hours=utc_offset_hours))
    local = datetime.fromtimestamp(
        timestamp_ms / 1000,
        timezone.utc,
    ).astimezone(local_tz)
    return local.year, local.month


def month_open_prices(candles, utc_offset_hours=7):
    result = {}
    for candle in candles:
        key = month_key(int(candle["open_time"]), utc_offset_hours)
        result.setdefault(key, float(candle["open"]))
    return result


def structural_target_outcome(
    candles,
    signal_index,
    side,
    stop,
    target,
    cost_pct,
    horizon_bars=384,
):
    entry_index = signal_index + 1
    if entry_index >= len(candles):
        return None
    entry = float(candles[entry_index]["open"])
    risk = entry - stop if side == "LONG" else stop - entry
    reward = target - entry if side == "LONG" else entry - target
    if entry <= 0 or risk <= 0 or reward <= 0:
        return None
    risk_pct = risk / entry
    if not 0.004 <= risk_pct <= 0.03:
        return None
    planned_rr = reward / risk
    end = min(len(candles), entry_index + horizon_bars)
    gross_r = 0.0
    outcome = "TIMEOUT"
    exit_index = end - 1
    exit_time = int(candles[exit_index]["close_time"])
    for index in range(entry_index, end):
        candle = candles[index]
        if side == "LONG":
            stop_hit = float(candle["low"]) <= stop
            target_hit = float(candle["high"]) >= target
        else:
            stop_hit = float(candle["high"]) >= stop
            target_hit = float(candle["low"]) <= target
        if stop_hit:
            gross_r = -1.0
            outcome = "SL"
            exit_index = index
            exit_time = int(candle["close_time"])
            break
        if target_hit:
            gross_r = planned_rr
            outcome = "STRUCTURE_TARGET"
            exit_index = index
            exit_time = int(candle["close_time"])
            break
    else:
        final_close = float(candles[end - 1]["close"])
        gross_r = (
            (final_close - entry) / risk
            if side == "LONG"
            else (entry - final_close) / risk
        )
        gross_r = max(-1.0, min(planned_rr, gross_r))
    cost_r = cost_pct / risk_pct
    return {
        "structure_target": target,
        "planned_structure_RR": planned_rr,
        "gross_R_structure": gross_r,
        "net_R_structure": gross_r - cost_r,
        "outcome_structure": outcome,
        "exit_time_structure": exit_time,
        "exit_index_structure": exit_index,
    }


def stop_for_event(event, params):
    if event.side == "LONG":
        return min(
            float(event.extreme) - 0.10 * float(event.atr_15m),
            float(event.level)
            - params.stop_buffer_atr * float(event.atr_15m),
        )
    return max(
        float(event.extreme) + 0.10 * float(event.atr_15m),
        float(event.level)
        + params.stop_buffer_atr * float(event.atr_15m),
    )


def attach_trade(
    pair,
    candles,
    signal_index,
    event,
    params,
    cost_pct,
):
    stop = stop_for_event(event, params)
    entry_index = signal_index + 1
    if entry_index >= len(candles):
        return None, "missing_next_open"
    entry = float(candles[entry_index]["open"])
    risk = (
        entry - stop
        if event.side == "LONG"
        else stop - entry
    )
    if entry <= 0 or risk <= 0:
        return None, "invalid_stop"
    risk_pct = risk / entry
    if not params.min_risk_pct <= risk_pct <= params.max_risk_pct:
        return None, "risk_outside_bounds"

    target = float(event.planned_target)
    if event.path == "B" and target <= 0:
        target = (
            entry + 2.0 * risk
            if event.side == "LONG"
            else entry - 2.0 * risk
        )
    reward = (
        target - entry
        if event.side == "LONG"
        else entry - target
    )
    if reward <= 0 or reward / risk < params.min_planned_rr:
        return None, "structure_rr_too_low"

    live = b4.simulate_live_management(
        candles,
        signal_index,
        event.side,
        stop,
        cost_pct,
    )
    if not live:
        return None, "live_management_invalid"
    structural = structural_target_outcome(
        candles,
        signal_index,
        event.side,
        stop,
        target,
        cost_pct,
    )
    if not structural:
        return None, "structure_management_invalid"
    record = {
        "strategy": params.name,
        "pair": pair,
        **event.to_dict(),
        "stop": stop,
        **live,
        **structural,
    }
    record["net_R_live_cost_0_20"] = (
        float(record["gross_R_live"])
        - COST_STRESS_PCT / float(record["risk_pct"])
    )
    calendar_weight = engine.calendar_risk_weight(
        float(event.calendar_score)
    )
    record["calendar_risk_weight"] = calendar_weight
    record["net_R_calendar_soft"] = (
        float(record["net_R_live"]) * calendar_weight
    )
    record["net_R_calendar_soft_cost_0_20"] = (
        float(record["net_R_live_cost_0_20"]) * calendar_weight
    )
    return record, "recorded"


def simulate_pair(
    pair,
    candles_15m,
    candles_4h,
    start_ms,
    end_ms,
    params,
    cost_pct,
):
    close_times_4h = [
        int(item["close_time"])
        for item in candles_4h
    ]
    opens = month_open_prices(candles_4h)
    machine = engine.ABCStateMachine(params)
    diagnostics = Counter()
    records = []
    dynamic_structure = None
    last_4h_count = None
    active_until_index = -1
    index = max(
        64,
        bisect.bisect_left(
            [int(item["close_time"]) for item in candles_15m],
            start_ms,
        ),
    )
    while index < len(candles_15m) - 1:
        candle = candles_15m[index]
        signal_time = int(candle["close_time"])
        if signal_time > end_ms:
            break
        diagnostics["bars_evaluated"] += 1
        count_4h = bisect.bisect_right(close_times_4h, signal_time)
        if count_4h != last_4h_count:
            dynamic_structure = engine.build_structure(
                candles_4h[:count_4h],
                params,
            )
            diagnostics[
                "structure_built"
                if dynamic_structure
                else "structure_missing"
            ] += 1
            last_4h_count = count_4h
        if dynamic_structure is None:
            index += 1
            continue

        history = candles_15m[max(0, index - 64):index]
        atr_15m = engine.atr_value(history)
        volume_baseline = engine.median_volume(history, 32)
        if not atr_15m or not volume_baseline:
            diagnostics["intraday_baseline_missing"] += 1
            index += 1
            continue
        current_close = float(candle["close"])
        open_price = opens.get(
            month_key(int(candle["open_time"])),
            current_close,
        )
        month_return = (
            current_close / open_price - 1.0
            if open_price > 0
            else 0.0
        )
        previous_mode = machine.mode
        event = machine.update(
            candle,
            index,
            dynamic_structure,
            atr_15m,
            volume_baseline,
            month_return,
        )
        diagnostics[f"state_{machine.mode.lower()}"] += 1
        if machine.mode != previous_mode:
            diagnostics[
                f"transition_{previous_mode.lower()}_to_{machine.mode.lower()}"
            ] += 1
        if event is None:
            index += 1
            continue
        diagnostics[f"event_{event.path}"] += 1
        diagnostics[f"event_{event.transition.lower()}"] += 1
        if index <= active_until_index:
            diagnostics["blocked_pair_active"] += 1
            index += 1
            continue
        record, reason = attach_trade(
            pair,
            candles_15m,
            index,
            event,
            params,
            cost_pct,
        )
        diagnostics[f"trade_{reason}"] += 1
        if record:
            records.append(record)
            active_until_index = int(record["exit_index_live"])
        index += 1
    return records, diagnostics


def portfolio_overlay(
    records,
    max_concurrent=PORTFOLIO_MAX_CONCURRENT,
    same_side_cluster_ms=SAME_SIDE_CLUSTER_MS,
):
    ordered = sorted(
        records,
        key=lambda item: (
            int(item["signal_time"]),
            item["pair"],
            item["path"],
        ),
    )
    selected = []
    active = []
    diagnostics = Counter()
    for record in ordered:
        signal_time = int(record["signal_time"])
        active = [
            item
            for item in active
            if int(item["exit_time_live"]) > signal_time
        ]
        if len(active) >= max_concurrent:
            diagnostics["blocked_max_concurrent"] += 1
            continue
        clustered = any(
            item["side"] == record["side"]
            and 0 <= signal_time - int(item["signal_time"])
            < same_side_cluster_ms
            for item in selected
        )
        if clustered:
            diagnostics["blocked_same_side_cluster"] += 1
            continue
        selected.append(record)
        active.append(record)
        diagnostics["selected"] += 1
    return selected, diagnostics


def concentration(records, result_key):
    by_pair = defaultdict(float)
    for record in records:
        value = float(record[result_key])
        if value > 0:
            by_pair[record["pair"]] += value
    positive = sum(by_pair.values())
    ordered = sorted(
        by_pair.items(),
        key=lambda item: (-item[1], item[0]),
    )
    return {
        "positive_pair_count": len(ordered),
        "top_positive_pair": ordered[0][0] if ordered else None,
        "top_positive_pair_share": (
            ordered[0][1] / positive
            if ordered and positive > 0
            else 0.0
        ),
    }


def grouped_summaries(records, key):
    return {
        "overall": common.summarize(records, key),
        "long": common.summarize(
            [item for item in records if item["side"] == "LONG"],
            key,
        ),
        "short": common.summarize(
            [item for item in records if item["side"] == "SHORT"],
            key,
        ),
        "paths": {
            path: common.summarize(
                [item for item in records if item["path"] == path],
                key,
            )
            for path in ("A", "B", "C")
        },
        "calendar_phases": {
            phase: common.summarize(
                [
                    item
                    for item in records
                    if item["calendar_phase"] == phase
                ],
                key,
            )
            for phase in (
                "D01_08",
                "D09_15",
                "D16_25",
                "D26_EOM",
            )
        },
    }


def variant_report(records, start_ms, end_ms):
    selected, overlay = portfolio_overlay(records)
    return {
        "records": selected,
        "raw": grouped_summaries(records, "net_R_live"),
        "baseline": {
            **grouped_summaries(selected, "net_R_live"),
            "cost_stress_0_20": common.summarize(
                selected,
                "net_R_live_cost_0_20",
            ),
            "folds_30d": common.fold_summaries(
                selected,
                "net_R_live",
                start_ms,
                end_ms,
            ),
            "concentration": concentration(
                selected,
                "net_R_live",
            ),
        },
        "structure_target_diagnostic": grouped_summaries(
            selected,
            "net_R_structure",
        ),
        "calendar_soft_diagnostic": {
            "enabled_for_trading": False,
            "reason": (
                "Requires independent BTC calendar audit approval "
                "for each phase"
            ),
            "overall": common.summarize(
                selected,
                "net_R_calendar_soft",
            ),
            "cost_stress_0_20": common.summarize(
                selected,
                "net_R_calendar_soft_cost_0_20",
            ),
        },
        "portfolio_overlay": dict(sorted(overlay.items())),
    }


def derivatives_ablation(records, database):
    attached = derivatives.attach_context(records, database)
    eligible = [
        item
        for item in attached
        if item["derivatives_complete"]
    ]
    hard = [
        item
        for item in eligible
        if item["oi_hard_confirmed"]
    ]
    no_crowding = [
        item
        for item in eligible
        if not item["crowding_veto"]
    ]
    pairs = sorted({item["pair"] for item in eligible})
    return {
        "scope": {
            "database": str(pathlib.Path(database).resolve()),
            "eligible_trades": len(eligible),
            "eligible_pairs": pairs,
            "warning": (
                "Compare variants only inside this identical "
                "derivatives-complete subset."
            ),
        },
        "M0_PRICE_VOLUME": {
            "overall": common.summarize(eligible, "net_R_live"),
            "cost_stress_0_20": common.summarize(
                eligible,
                "net_R_live_cost_0_20",
            ),
        },
        "M1_OI_FLOW_SOFT": {
            "overall": common.summarize(
                eligible,
                "net_R_oi_soft",
            ),
            "cost_stress_0_20": common.summarize(
                eligible,
                "net_R_oi_soft_cost_0_20",
            ),
            "trades_unchanged": True,
        },
        "M2_OI_FLOW_HARD": {
            "overall": common.summarize(hard, "net_R_live"),
            "cost_stress_0_20": common.summarize(
                hard,
                "net_R_live_cost_0_20",
            ),
            "retained_pct": (
                round(100.0 * len(hard) / len(eligible), 2)
                if eligible
                else 0.0
            ),
        },
        "M3_CROWDING_VETO": {
            "overall": common.summarize(
                no_crowding,
                "net_R_live",
            ),
            "cost_stress_0_20": common.summarize(
                no_crowding,
                "net_R_live_cost_0_20",
            ),
            "retained_pct": (
                round(
                    100.0 * len(no_crowding) / len(eligible),
                    2,
                )
                if eligible
                else 0.0
            ),
        },
        "records": attached,
    }


def main():
    parser = argparse.ArgumentParser(
        description="Unified A/B/C structure-state replay"
    )
    parser.add_argument("--pairs-file", required=True)
    parser.add_argument("--cache-dir", required=True)
    parser.add_argument("--start", required=True)
    parser.add_argument("--end", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--max-pairs", type=int, default=30)
    parser.add_argument("--cost-pct", type=float, default=0.0014)
    parser.add_argument("--derivatives-db")
    args = parser.parse_args()

    start_ms = audit.parse_timestamp(args.start)
    end_ms = audit.parse_timestamp(args.end)
    pairs = read_json(args.pairs_file).get("pairs", [])[:args.max_pairs]
    market = audit.MarketData(args.cache_dir)
    data = {}
    errors = []
    for number, pair in enumerate(pairs, 1):
        print(f"load {number}/{len(pairs)} {pair}", flush=True)
        try:
            data[pair] = {
                "15m": market.klines(
                    pair,
                    "15m",
                    start_ms - 4 * MS_DAY,
                    end_ms + 5 * MS_DAY,
                ),
                "4h": market.klines(
                    pair,
                    "4h",
                    start_ms - 60 * MS_DAY,
                    end_ms + 4 * MS_HOUR,
                ),
            }
        except Exception as exc:
            errors.append(
                f"{pair}: {type(exc).__name__}: {exc}"
            )

    result = {
        "engine": "ABC_UNIFIED_STRUCTURE_STATE_V1",
        "spec": (
            "docs/STRATEGY_ABC_UNIFIED_FROZEN_SPEC_2026-07-30.md"
        ),
        "period": {"start": args.start, "end": args.end},
        "pair_count_requested": len(pairs),
        "pair_count_loaded": len(data),
        "cost_model": {
            "round_trip_fee_plus_slippage_pct": args.cost_pct,
            "stress_cost_pct": COST_STRESS_PCT,
            "entry": "next_15m_open_after_closed_candle_signal",
            "live_management": (
                "TP1 1R/50%, TP2 2R/50%, +1.5% trigger "
                "moves SL to +1%"
            ),
            "same_candle_ordering": "active_stop_wins",
            "timeout": "96h_mark_to_market",
        },
        "portfolio_model": {
            "max_concurrent": PORTFOLIO_MAX_CONCURRENT,
            "same_side_cluster_minutes": (
                SAME_SIDE_CLUSTER_MS // (60 * 1000)
            ),
        },
        "variants": {},
        "errors": errors,
    }

    for params in engine.VARIANTS:
        print(f"simulate {params.name}", flush=True)
        records = []
        diagnostics = Counter()
        for pair, candles in data.items():
            pair_records, pair_diagnostics = simulate_pair(
                pair,
                candles["15m"],
                candles["4h"],
                start_ms,
                end_ms,
                params,
                args.cost_pct,
            )
            records.extend(pair_records)
            diagnostics.update(pair_diagnostics)
        report = variant_report(records, start_ms, end_ms)
        report["parameters"] = asdict(params)
        report["diagnostics"] = dict(sorted(diagnostics.items()))
        result["variants"][params.name] = report

    primary_records = result["variants"]["ABC_PRIMARY"]["records"]
    if args.derivatives_db:
        result["derivatives_ablation"] = derivatives_ablation(
            primary_records,
            args.derivatives_db,
        )
    else:
        result["derivatives_ablation"] = {
            "status": "NOT_RUN",
            "reason": "--derivatives-db not provided",
        }

    write_json(args.output, result)
    concise = {
        name: {
            "baseline": report["baseline"]["overall"],
            "cost_stress": report["baseline"][
                "cost_stress_0_20"
            ],
            "paths": report["baseline"]["paths"],
        }
        for name, report in result["variants"].items()
    }
    print(json.dumps({
        "results": concise,
        "derivatives_ablation": {
            key: value.get("overall")
            for key, value in result["derivatives_ablation"].items()
            if isinstance(value, dict) and "overall" in value
        },
        "errors": errors,
        "output": args.output,
    }, indent=2))


if __name__ == "__main__":
    main()
