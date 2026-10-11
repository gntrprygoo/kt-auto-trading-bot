import argparse
import json
import pathlib
from dataclasses import asdict

import abc_structure_engine_v2 as engine
import research_strategy_abc_v2 as v2
import research_strategy_bc_v2 as common
import strategy_evidence_audit as audit


REVIEW_START = "2019-09-01"
REVIEW_END = "2026-07-22"


def write_json(path, value):
    output = pathlib.Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(value, handle, ensure_ascii=True, indent=2)
        handle.write("\n")


def build_result(
    args,
    data_source,
    events,
    controls,
    records,
    diagnostics,
    start_ms,
    end_ms,
):
    return {
        "engine": "ABC_V24_HUMAN_EXCLUSIVE",
        "status": "RESEARCH_ONLY_TRAINING_SAMPLE",
        "validation_role": (
            "HISTORICAL_REGRESSION_NOT_PROMOTION_EVIDENCE"
        ),
        "production_changed": False,
        "symbol": "BTCUSDT",
        "period": {
            "start": args.start,
            "end": args.end,
        },
        "human_spec_dataset": "82ccd32d0703",
        "parameters": asdict(engine.HUMAN_V24),
        "data_source": data_source,
        "event_count": len(events),
        "control_count": len(controls),
        "trade_count": len(records),
        "event_paths": {
            path: sum(item["path"] == path for item in events)
            for path in ("A", "B", "C")
        },
        "lineage": v2._lineage_diagnostics(events),
        "outcome_diagnostic": {
            "existing_management": common.summarize(
                records,
                "net_R_live",
            ),
            "cost_stress_0_20": common.summarize(
                records,
                "net_R_live_cost_0_20",
            ),
            "structural_target_only": common.summarize(
                records,
                "net_R_structure",
            ),
            "paths": v2._group_summary(
                records,
                "path",
                "net_R_live",
            ),
            "sides": v2._group_summary(
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
        "diagnostics": dict(sorted(diagnostics.items())),
        "events": events,
        "review_controls": controls,
        "records": records,
    }


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Replay the research-only human-exclusive ABC V2.4 "
            "state machine"
        )
    )
    parser.add_argument("--output", required=True)
    parser.add_argument("--start", default=REVIEW_START)
    parser.add_argument("--end", default=REVIEW_END)
    parser.add_argument("--candles-15m", action="append", required=True)
    parser.add_argument("--candles-4h", action="append", required=True)
    parser.add_argument("--cost-pct", type=float, default=0.0014)
    args = parser.parse_args()
    args.cache_dir = None

    start_ms = audit.parse_timestamp(args.start)
    end_ms = audit.parse_timestamp(args.end)
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
        engine.HUMAN_V24,
        args.cost_pct,
    )
    result = build_result(
        args,
        data_source,
        events,
        controls,
        records,
        diagnostics,
        start_ms,
        end_ms,
    )
    write_json(args.output, result)
    print(json.dumps({
        "period": result["period"],
        "events": result["event_count"],
        "event_paths": result["event_paths"],
        "controls": result["control_count"],
        "trades": result["trade_count"],
        "outcome": result["outcome_diagnostic"][
            "existing_management"
        ],
        "validation_role": result["validation_role"],
        "output": str(pathlib.Path(args.output).resolve()),
    }, indent=2))


if __name__ == "__main__":
    main()
