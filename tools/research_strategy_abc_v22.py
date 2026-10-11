import argparse
import json
import pathlib

import abc_structure_engine_v2 as engine
import research_strategy_abc_v2 as v2
import research_strategy_bc_v2 as common
import strategy_evidence_audit as audit


SECONDARY_START = "2022-10-25"
SECONDARY_END = "2024-10-24"


def write_json(path, value):
    output = pathlib.Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(value, handle, ensure_ascii=True, indent=2)
        handle.write("\n")


def _profit_factor_at_least(summary, minimum):
    value = summary.get("profit_factor")
    if value is None:
        return int(summary.get("trades", 0)) > 0
    return float(value) >= minimum


def _fold_result(records, start_ms, end_ms):
    folds = common.fold_summaries(
        records,
        "net_R_live",
        start_ms,
        end_ms,
        fold_days=90,
    )
    non_empty = [
        item for item in folds
        if int(item.get("trades", 0)) > 0
    ]
    positive = sum(
        float(item.get("total_net_R", 0.0)) > 0
        for item in non_empty
    )
    return folds, {
        "positive": positive,
        "non_empty": len(non_empty),
        "ratio": (
            round(positive / len(non_empty), 4)
            if non_empty
            else 0.0
        ),
    }


def evaluate_gate(baseline, stress, fold_result):
    checks = {
        "minimum_trades": int(baseline["trades"]) >= 15,
        "positive_base_R": float(baseline["total_net_R"]) > 0,
        "base_profit_factor": _profit_factor_at_least(
            baseline,
            1.15,
        ),
        "positive_stress_R": float(stress["total_net_R"]) > 0,
        "stress_profit_factor": _profit_factor_at_least(
            stress,
            1.05,
        ),
        "average_R": float(baseline["avg_net_R"]) >= 0.05,
        "max_drawdown": (
            float(baseline["max_drawdown_R"]) <= 10.0
        ),
        "positive_fold_ratio": (
            int(fold_result["non_empty"]) >= 4
            and float(fold_result["ratio"]) >= 0.50
        ),
    }
    return {
        "passed": all(checks.values()),
        "checks": checks,
    }


def main():
    parser = argparse.ArgumentParser(
        description="Frozen older-period test for BTC Confirmed-A"
    )
    parser.add_argument("--output", required=True)
    parser.add_argument("--cache-dir")
    parser.add_argument("--candles-15m", action="append")
    parser.add_argument("--candles-4h", action="append")
    parser.add_argument("--cost-pct", type=float, default=0.0014)
    args = parser.parse_args()
    args.start = SECONDARY_START
    args.end = SECONDARY_END

    start_ms = audit.parse_timestamp(SECONDARY_START)
    end_ms = audit.parse_timestamp(SECONDARY_END)
    candles_15m, candles_4h, data_source = v2._load_market_data(
        args,
        start_ms,
        end_ms,
    )
    events, controls, records, diagnostics = v2.simulate(
        candles_15m,
        candles_4h,
        start_ms,
        end_ms,
        engine.COMBINED,
        args.cost_pct,
        admitted_paths={"A"},
    )
    baseline = common.summarize(records, "net_R_live")
    stress = common.summarize(
        records,
        "net_R_live_cost_0_20",
    )
    structural = common.summarize(
        records,
        "net_R_structure",
    )
    folds, fold_result = _fold_result(
        records,
        start_ms,
        end_ms,
    )
    gate = evaluate_gate(baseline, stress, fold_result)
    result = {
        "engine": "ABC_V22_CONFIRMED_A_SECONDARY",
        "status": "RESEARCH_ONLY",
        "spec": (
            "docs/"
            "STRATEGY_ABC_V22_CONFIRMED_A_SPEC_2026-07-30.md"
        ),
        "symbol": "BTCUSDT",
        "period": {
            "start": SECONDARY_START,
            "end": SECONDARY_END,
        },
        "data_source": data_source,
        "parameters": {
            **engine.COMBINED.__dict__,
            "admitted_paths": ["A"],
        },
        "event_count": len(events),
        "event_paths": {
            path: sum(item["path"] == path for item in events)
            for path in ("A", "B", "C")
        },
        "trade_count": len(records),
        "baseline": baseline,
        "stress": stress,
        "structural_target": structural,
        "folds_90d": folds,
        "positive_90d_folds": fold_result,
        "gate": gate,
        "decision": (
            "SECONDARY_PASS_LABEL_GATE_STILL_REQUIRED"
            if gate["passed"]
            else "REJECT"
        ),
        "diagnostics": dict(sorted(diagnostics.items())),
        "records": records,
        "production_changed": False,
    }
    write_json(args.output, result)
    print(json.dumps({
        "period": result["period"],
        "events": result["event_count"],
        "trades": len(records),
        "baseline": baseline,
        "stress": stress,
        "positive_90d_folds": fold_result,
        "gate": gate,
        "decision": result["decision"],
        "output": str(pathlib.Path(args.output).resolve()),
    }, indent=2))


if __name__ == "__main__":
    main()
