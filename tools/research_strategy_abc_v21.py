import argparse
import json
import pathlib
from collections import Counter, defaultdict
from dataclasses import asdict

import abc_structure_engine_v2 as engine
import research_strategy_abc_v2 as v2
import research_strategy_bc_v2 as common
import strategy_evidence_audit as audit


CALIBRATION_START = "2024-10-25"
CALIBRATION_END = "2025-10-24"
VALIDATION_START = "2025-10-25"
VALIDATION_END = "2026-07-22"


def write_json(path, value):
    output = pathlib.Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(value, handle, ensure_ascii=True, indent=2)
        handle.write("\n")


def _profit_factor_at_least(summary, minimum):
    value = summary.get("profit_factor")
    return value is None and summary.get("trades", 0) > 0 or (
        value is not None and float(value) >= minimum
    )


def _positive_fold_ratio(folds):
    non_empty = [
        item for item in folds
        if int(item.get("trades", 0)) > 0
    ]
    positive = sum(
        float(item.get("total_net_R", 0.0)) > 0
        for item in non_empty
    )
    return {
        "positive": positive,
        "non_empty": len(non_empty),
        "ratio": (
            round(positive / len(non_empty), 4)
            if non_empty
            else 0.0
        ),
    }


def _group_summary(records, key, result_key):
    grouped = defaultdict(list)
    for record in records:
        grouped[str(record.get(key, "n/a"))].append(record)
    return {
        name: common.summarize(rows, result_key)
        for name, rows in sorted(grouped.items())
    }


def period_report(records, start_text, end_text):
    start_ms = audit.parse_timestamp(start_text)
    end_ms = audit.parse_timestamp(end_text)
    selected = [
        item
        for item in records
        if start_ms <= int(item["signal_time"]) <= end_ms
    ]
    folds = common.fold_summaries(
        selected,
        "net_R_live",
        start_ms,
        end_ms,
        fold_days=60,
    )
    return {
        "period": {"start": start_text, "end": end_text},
        "baseline": common.summarize(
            selected,
            "net_R_live",
        ),
        "stress": common.summarize(
            selected,
            "net_R_live_cost_0_20",
        ),
        "structural_target": common.summarize(
            selected,
            "net_R_structure",
        ),
        "positive_60d_folds": _positive_fold_ratio(folds),
        "folds_60d": folds,
        "paths": _group_summary(
            selected,
            "path",
            "net_R_live",
        ),
        "sides": _group_summary(
            selected,
            "side",
            "net_R_live",
        ),
        "transitions": _group_summary(
            selected,
            "transition",
            "net_R_live",
        ),
    }


def period_gate(report):
    baseline = report["baseline"]
    stress = report["stress"]
    fold = report["positive_60d_folds"]
    checks = {
        "minimum_trades": int(baseline["trades"]) >= 15,
        "positive_net_R": float(baseline["total_net_R"]) > 0,
        "profit_factor": _profit_factor_at_least(
            baseline,
            1.10,
        ),
        "positive_stress_R": float(stress["total_net_R"]) > 0,
        "stress_profit_factor": _profit_factor_at_least(
            stress,
            1.00,
        ),
        "max_drawdown": (
            float(baseline["max_drawdown_R"]) <= 12.0
        ),
        "positive_fold_ratio": (
            int(fold["non_empty"]) >= 3
            and float(fold["ratio"]) >= 0.50
        ),
    }
    return {
        "passed": all(checks.values()),
        "checks": checks,
    }


def variant_report(
    params,
    events,
    controls,
    records,
    diagnostics,
):
    calibration = period_report(
        records,
        CALIBRATION_START,
        CALIBRATION_END,
    )
    validation = period_report(
        records,
        VALIDATION_START,
        VALIDATION_END,
    )
    calibration_gate = period_gate(calibration)
    validation_gate = period_gate(validation)
    full_baseline = common.summarize(records, "net_R_live")
    full_stress = common.summarize(
        records,
        "net_R_live_cost_0_20",
    )
    full_stress_positive = (
        float(full_stress["total_net_R"]) > 0
        and _profit_factor_at_least(full_stress, 1.00)
    )
    passed = (
        calibration_gate["passed"]
        and validation_gate["passed"]
        and full_stress_positive
    )
    insufficient_sample = (
        int(calibration["baseline"]["trades"]) < 15
        or int(validation["baseline"]["trades"]) < 15
    )
    return {
        "parameters": asdict(params),
        "event_count": len(events),
        "control_count": len(controls),
        "trade_count": len(records),
        "event_paths": dict(sorted(Counter(
            item["path"] for item in events
        ).items())),
        "lineage": v2._lineage_diagnostics(events),
        "calibration": calibration,
        "validation": validation,
        "full_period": {
            "baseline": full_baseline,
            "stress": full_stress,
        },
        "gate": {
            "calibration": calibration_gate,
            "validation": validation_gate,
            "full_stress_positive": full_stress_positive,
            "passed": passed,
            "decision": (
                "OUTCOME_SCREEN_PASS"
                if passed
                else "INSUFFICIENT_SAMPLE"
                if insufficient_sample
                else "REJECT"
            ),
            "human_label_gate_still_required": True,
        },
        "diagnostics": dict(sorted(diagnostics.items())),
        "records": records,
    }


def main():
    parser = argparse.ArgumentParser(
        description="Frozen BTC ABC v2.1 variant replay"
    )
    parser.add_argument("--output", required=True)
    parser.add_argument("--candles-15m", action="append")
    parser.add_argument("--candles-4h", action="append")
    parser.add_argument("--cache-dir")
    parser.add_argument("--cost-pct", type=float, default=0.0014)
    args = parser.parse_args()
    args.start = CALIBRATION_START
    args.end = VALIDATION_END

    start_ms = audit.parse_timestamp(CALIBRATION_START)
    end_ms = audit.parse_timestamp(VALIDATION_END)
    candles_15m, candles_4h, data_source = v2._load_market_data(
        args,
        start_ms,
        end_ms,
    )
    structure_cache = {}
    reports = {}
    for params in engine.V21_VARIANTS:
        print(f"simulate {params.name}", flush=True)
        events, controls, records, diagnostics = v2.simulate(
            candles_15m,
            candles_4h,
            start_ms,
            end_ms,
            params,
            args.cost_pct,
            structure_cache=structure_cache,
        )
        reports[params.name] = variant_report(
            params,
            events,
            controls,
            records,
            diagnostics,
        )

    result = {
        "engine": "ABC_V21_FROZEN_HYPOTHESIS_REPLAY",
        "status": "RESEARCH_ONLY",
        "spec": (
            "docs/"
            "STRATEGY_ABC_V21_FROZEN_HYPOTHESES_2026-07-30.md"
        ),
        "data_source": data_source,
        "cost_model": {
            "base_round_trip_pct": args.cost_pct,
            "stress_round_trip_pct": v2.COST_STRESS_PCT,
            "management": (
                "TP1 1R/50%, TP2 2R/50%, "
                "+1.5% trigger moves SL to +1%"
            ),
        },
        "variants": reports,
        "accepted_variants": [
            name
            for name, report in reports.items()
            if report["gate"]["passed"]
        ],
        "production_changed": False,
    }
    write_json(args.output, result)
    print(json.dumps({
        "variants": {
            name: {
                "calibration": report["calibration"]["baseline"],
                "validation": report["validation"]["baseline"],
                "full_stress": report["full_period"]["stress"],
                "decision": report["gate"]["decision"],
            }
            for name, report in reports.items()
        },
        "accepted_variants": result["accepted_variants"],
        "output": str(pathlib.Path(args.output).resolve()),
    }, indent=2))


if __name__ == "__main__":
    main()
