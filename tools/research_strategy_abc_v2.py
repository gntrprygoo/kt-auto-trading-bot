import argparse
import bisect
import hashlib
import json
import pathlib
import statistics
from collections import Counter, defaultdict
from dataclasses import asdict

import abc_structure_engine_v2 as engine
import research_strategy_b4 as b4
import research_strategy_bc_v2 as common
import research_strategy_abc as v1
import strategy_evidence_audit as audit


MS_DAY = 24 * 60 * 60 * 1000
MS_4H = 4 * 60 * 60 * 1000
COST_STRESS_PCT = 0.0020


def read_json(path):
    with pathlib.Path(path).open("r", encoding="utf-8-sig") as handle:
        return json.load(handle)


def write_json(path, value):
    output = pathlib.Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(value, handle, ensure_ascii=True, indent=2)
        handle.write("\n")


def _stop_for_event(event, params):
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
    candles,
    signal_index,
    event,
    params,
    cost_pct,
):
    entry_index = signal_index + 1
    if entry_index >= len(candles):
        return None, "missing_next_open"
    stop = _stop_for_event(event, params)
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
    structural = v1.structural_target_outcome(
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
        "pair": "BTCUSDT",
        "signal_index": int(signal_index),
        **event.to_dict(),
        "entry": entry,
        "stop": stop,
        **live,
        **structural,
    }
    record["net_R_live_cost_0_20"] = (
        float(record["gross_R_live"])
        - COST_STRESS_PCT / float(record["risk_pct"])
    )
    return record, "recorded"


def _group_summary(records, key, result_key):
    grouped = defaultdict(list)
    for record in records:
        grouped[str(record[key])].append(record)
    return {
        name: common.summarize(rows, result_key)
        for name, rows in sorted(grouped.items())
    }


def _lineage_diagnostics(events):
    result = {
        "events": len(events),
        "unique_event_ids": len({
            item["event_id"] for item in events
        }),
        "unique_level_ids": len({
            item["level_id"] for item in events
        }),
        "unique_range_ids": len({
            item["range_id"] for item in events
        }),
        "path_counts": dict(sorted(Counter(
            item["path"] for item in events
        ).items())),
        "transition_counts": dict(sorted(Counter(
            item["transition"] for item in events
        ).items())),
    }
    c_events = [item for item in events if item["path"] == "C"]
    result["c_without_parent_transition"] = sum(
        not item.get("parent_transition_id")
        for item in c_events
    )
    result["duplicate_transition_keys"] = (
        len(events)
        - len({
            (
                item["path"],
                item["transition"],
                item["range_id"],
                item["level_id"],
                item["parent_transition_id"],
            )
            for item in events
        })
    )
    return result


def simulate(
    candles_15m,
    candles_4h,
    start_ms,
    end_ms,
    params,
    cost_pct,
    structure_cache=None,
    admitted_paths=None,
):
    close_times_15m = [
        int(item["close_time"]) for item in candles_15m
    ]
    close_times_4h = [
        int(item["close_time"]) for item in candles_4h
    ]
    machine = engine.ABCStateMachineV2(params)
    diagnostics = Counter()
    events = []
    controls = []
    records = []
    active_until_index = -1
    last_control_bucket = None
    dynamic_structure = None
    if structure_cache is None:
        structure_cache = {}
    last_4h_count = None
    index = max(
        64,
        bisect.bisect_left(close_times_15m, start_ms),
    )
    while index < len(candles_15m) - 1:
        candle = candles_15m[index]
        signal_time = int(candle["close_time"])
        if signal_time > end_ms:
            break
        diagnostics["bars_evaluated"] += 1
        count_4h = bisect.bisect_right(close_times_4h, signal_time)
        if count_4h != last_4h_count:
            if count_4h not in structure_cache:
                structure_cache[count_4h] = engine.build_structure(
                    candles_4h[:count_4h],
                    params,
                )
            dynamic_structure = structure_cache[count_4h]
            diagnostics[
                "structure_built"
                if dynamic_structure
                else "structure_missing"
            ] += 1
            if dynamic_structure:
                diagnostics[
                    "structure_balance_valid"
                    if dynamic_structure.balance_valid
                    else "structure_balance_rejected"
                ] += 1
            last_4h_count = count_4h
        history = candles_15m[max(0, index - 64):index]
        atr_15m = engine.atr_value(history)
        volume_baseline = engine.median_volume(history, 32)
        if not atr_15m or not volume_baseline:
            diagnostics["intraday_baseline_missing"] += 1
            index += 1
            continue
        previous_mode = machine.mode
        event = machine.update(
            candle,
            index,
            dynamic_structure,
            atr_15m,
            volume_baseline,
            history,
        )
        diagnostics[f"state_{machine.mode.lower()}"] += 1
        if machine.mode != previous_mode:
            diagnostics[
                f"transition_{previous_mode.lower()}_to_"
                f"{machine.mode.lower()}"
            ] += 1
        if event is None:
            active_structure = machine.structure
            control_bucket = signal_time // MS_DAY
            if (
                active_structure is not None
                and active_structure.balance_valid
                and control_bucket != last_control_bucket
            ):
                close = float(candle["close"])
                boundaries = (
                    ("LONG", active_structure.support),
                    ("SHORT", active_structure.resistance),
                )
                side_hint, nearest = min(
                    boundaries,
                    key=lambda item: abs(
                        close - float(item[1].price)
                    ),
                )
                distance_atr = (
                    abs(close - float(nearest.price))
                    / float(atr_15m)
                )
                if distance_atr <= 1.0:
                    raw_id = (
                        f"CONTROL|{nearest.level_id}|{signal_time}"
                    )
                    controls.append({
                        "candidate_id": (
                            "CONTROL-"
                            + hashlib.sha1(
                                raw_id.encode("ascii")
                            ).hexdigest()[:12]
                        ),
                        "candidate_type": "NEAR_BOUNDARY_NO_EVENT",
                        "signal_time": signal_time,
                        "signal_index": int(index),
                        "side_hint": side_hint,
                        "range_id": active_structure.range_id,
                        "level_id": nearest.level_id,
                        "level": float(nearest.price),
                        "level_source_tf": nearest.source_tf,
                        "level_freshness": nearest.freshness,
                        "level_touches": int(nearest.touches),
                        "level_age_bars_4h": int(
                            nearest.age_bars_4h
                        ),
                        "level_test_count": int(
                            nearest.test_count
                        ),
                        "level_volume_ratio": float(
                            nearest.volume_at_level_ratio
                        ),
                        "level_score": float(nearest.score),
                        "distance_atr": float(distance_atr),
                        "machine_mode": machine.mode,
                        "support": float(
                            active_structure.support.price
                        ),
                        "resistance": float(
                            active_structure.resistance.price
                        ),
                        "macro_bias_context": (
                            active_structure.macro_bias
                        ),
                        "structure_efficiency_4h": float(
                            active_structure.efficiency_4h
                        ),
                        "structure_containment_ratio": float(
                            active_structure.containment_ratio
                        ),
                    })
                    last_control_bucket = control_bucket
            index += 1
            continue
        event_record = {
            **event.to_dict(),
            "signal_index": int(index),
        }
        events.append(event_record)
        diagnostics[f"event_{event.path}"] += 1
        diagnostics[f"event_{event.transition.lower()}"] += 1
        if (
            admitted_paths is not None
            and event.path not in admitted_paths
        ):
            diagnostics["trade_path_not_admitted"] += 1
            index += 1
            continue
        if index <= active_until_index:
            diagnostics["trade_blocked_existing_position"] += 1
            index += 1
            continue
        record, reason = attach_trade(
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
    return events, controls, records, diagnostics


def _load_market_data(args, start_ms, end_ms):
    if bool(args.candles_15m) != bool(args.candles_4h):
        raise SystemExit(
            "--candles-15m and --candles-4h must be used together"
        )
    if args.candles_15m:
        def merge(paths):
            rows = {}
            for path in paths:
                for candle in read_json(path):
                    rows[int(candle["open_time"])] = candle
            return [rows[key] for key in sorted(rows)]

        return (
            merge(args.candles_15m),
            merge(args.candles_4h),
            {
                "source": "explicit_files",
                "candles_15m": [
                    str(pathlib.Path(path).resolve())
                    for path in args.candles_15m
                ],
                "candles_4h": [
                    str(pathlib.Path(path).resolve())
                    for path in args.candles_4h
                ],
            },
        )
    if not args.cache_dir:
        raise SystemExit(
            "Provide explicit candle files or --cache-dir"
        )
    market = audit.MarketData(args.cache_dir)
    candles_15m = market.klines(
        "BTCUSDT",
        "15m",
        start_ms - 7 * MS_DAY,
        end_ms + 5 * MS_DAY,
    )
    candles_4h = market.klines(
        "BTCUSDT",
        "4h",
        start_ms - 210 * MS_DAY,
        end_ms + MS_4H,
    )
    return candles_15m, candles_4h, {
        "source": "market_cache",
        "cache_dir": str(pathlib.Path(args.cache_dir).resolve()),
    }


def main():
    parser = argparse.ArgumentParser(
        description=(
            "BTC-only A/B/C v2 structure lineage replay"
        )
    )
    parser.add_argument("--start", required=True)
    parser.add_argument("--end", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--cache-dir")
    parser.add_argument("--candles-15m", action="append")
    parser.add_argument("--candles-4h", action="append")
    parser.add_argument("--cost-pct", type=float, default=0.0014)
    args = parser.parse_args()

    start_ms = audit.parse_timestamp(args.start)
    end_ms = audit.parse_timestamp(args.end)
    candles_15m, candles_4h, data_source = _load_market_data(
        args,
        start_ms,
        end_ms,
    )
    events, controls, records, diagnostics = simulate(
        candles_15m,
        candles_4h,
        start_ms,
        end_ms,
        engine.PRIMARY,
        args.cost_pct,
    )
    live = common.summarize(records, "net_R_live")
    stress = common.summarize(
        records,
        "net_R_live_cost_0_20",
    )
    structural = common.summarize(
        records,
        "net_R_structure",
    )
    result = {
        "engine": "ABC_V2_BTC_STRUCTURE_LINEAGE",
        "status": "RESEARCH_ONLY_LABEL_GATE_REQUIRED",
        "production_changed": False,
        "symbol": "BTCUSDT",
        "period": {"start": args.start, "end": args.end},
        "data_source": data_source,
        "information_clock": {
            "macro_levels": "completed_1D_from_4H_aggregation",
            "structure": "completed_4H",
            "trigger": "completed_15m",
            "entry": "next_15m_open",
        },
        "context_policy": {
            "calendar": "recorded_only_not_filter_or_risk_weight",
            "open_interest": "not_joined_until_price_gate_passes",
            "funding": "not_joined_until_price_gate_passes",
        },
        "management_policy": {
            "promotion_baseline": (
                "existing TP1 1R/50%, TP2 2R/50%, "
                "+1.5% trigger moves SL to +1%"
            ),
            "structural_target": "diagnostic_only",
        },
        "parameters": asdict(engine.PRIMARY),
        "event_count": len(events),
        "control_count": len(controls),
        "trade_count": len(records),
        "lineage": _lineage_diagnostics(events),
        "outcome_diagnostic": {
            "existing_management": live,
            "cost_stress_0_20": stress,
            "structural_target_only": structural,
            "paths": _group_summary(
                records,
                "path",
                "net_R_live",
            ),
            "sides": _group_summary(
                records,
                "side",
                "net_R_live",
            ),
            "chronological_30d_folds": common.fold_summaries(
                records,
                "net_R_live",
                start_ms,
                end_ms,
            ),
        },
        "label_gate": {
            "status": "BLOCKED_PENDING_HUMAN_LABELS",
            "minimum_labels": 100,
            "minimum_per_path": 20,
            "minimum_precision": 0.70,
            "note": (
                "Outcome metrics cannot promote v2 until the "
                "structure-label gate passes."
            ),
        },
        "diagnostics": dict(sorted(diagnostics.items())),
        "events": events,
        "review_controls": controls,
        "records": records,
    }
    write_json(args.output, result)
    print(json.dumps({
        "engine": result["engine"],
        "events": len(events),
        "controls": len(controls),
        "trades": len(records),
        "lineage": result["lineage"],
        "existing_management": live,
        "label_gate": result["label_gate"]["status"],
        "output": str(pathlib.Path(args.output).resolve()),
    }, indent=2))


if __name__ == "__main__":
    main()
