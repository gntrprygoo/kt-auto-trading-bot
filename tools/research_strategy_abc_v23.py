import argparse
import json
import pathlib

import abc_structure_engine_v2 as engine
import research_strategy_abc_v2 as v2
import research_strategy_abc_v22 as v22
import research_strategy_bc_v2 as common
import strategy_evidence_audit as audit


HOLDOUT_START = "2020-10-25"
HOLDOUT_END = "2022-10-24"


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Frozen unseen holdout for BTC Balanced-Range A"
        )
    )
    parser.add_argument("--output", required=True)
    parser.add_argument("--cache-dir")
    parser.add_argument("--candles-15m", action="append")
    parser.add_argument("--candles-4h", action="append")
    parser.add_argument("--cost-pct", type=float, default=0.0014)
    args = parser.parse_args()
    args.start = HOLDOUT_START
    args.end = HOLDOUT_END

    start_ms = audit.parse_timestamp(HOLDOUT_START)
    end_ms = audit.parse_timestamp(HOLDOUT_END)
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
        engine.BALANCED_A,
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
    folds, fold_result = v22._fold_result(
        records,
        start_ms,
        end_ms,
    )
    gate = v22.evaluate_gate(
        baseline,
        stress,
        fold_result,
    )
    result = {
        "engine": "ABC_V23_BALANCED_A_HOLDOUT",
        "status": "RESEARCH_ONLY",
        "spec": (
            "docs/"
            "STRATEGY_ABC_V23_BALANCED_RANGE_SPEC_2026-07-30.md"
        ),
        "symbol": "BTCUSDT",
        "period": {
            "start": HOLDOUT_START,
            "end": HOLDOUT_END,
        },
        "data_source": data_source,
        "parameters": {
            **engine.BALANCED_A.__dict__,
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
            "HOLDOUT_PASS_LABEL_GATE_STILL_REQUIRED"
            if gate["passed"]
            else "REJECT"
        ),
        "diagnostics": dict(sorted(diagnostics.items())),
        "records": records,
        "production_changed": False,
    }
    v22.write_json(args.output, result)
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
