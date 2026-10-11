import argparse
import json
import pathlib

import research_strategy_bc_v2 as common


BASELINE = "A0_LEGACY_PARITY"
CANDIDATE = "A2_LEVEL_TOUCH"
REJECTED_STRUCTURAL_VARIANTS = (
    "A3_CLUSTERED_SR",
    "A4_CLUSTERED_SR_TREND",
    "A5_CLUSTERED_SR_TREND_PULLBACK",
)


def read_json(path):
    with pathlib.Path(path).open("r", encoding="utf-8-sig") as handle:
        return json.load(handle)


def write_json(path, value):
    path = pathlib.Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(value, handle, ensure_ascii=True, indent=2)
        handle.write("\n")


def _records(report, variant):
    return list(report["results"][variant]["records"])


def _period_metrics(report, variant):
    result = report["results"][variant]
    folds = result["folds_30d"]
    return {
        "overall": result["overall"],
        "long": result["long"],
        "short": result["short"],
        "worst_fold_R": min(
            (float(fold["total_net_R"]) for fold in folds),
            default=0.0,
        ),
        "positive_folds": sum(
            float(fold["total_net_R"]) > 0 for fold in folds
        ),
        "fold_count": len(folds),
    }


def _combined_metrics(records, start_ms, end_ms):
    folds = common.fold_summaries(
        records,
        "net_R_live",
        start_ms,
        end_ms,
    )
    active_pairs = sorted({record["pair"] for record in records})
    positive_pairs = 0
    for pair in active_pairs:
        pair_records = [
            record for record in records if record["pair"] == pair
        ]
        if common.summarize(pair_records, "net_R_live")["total_net_R"] > 0:
            positive_pairs += 1
    return {
        "overall": common.summarize(records, "net_R_live"),
        "long": common.summarize(
            [record for record in records if record["side"] == "LONG"],
            "net_R_live",
        ),
        "short": common.summarize(
            [record for record in records if record["side"] == "SHORT"],
            "net_R_live",
        ),
        "worst_fold_R": min(
            (float(fold["total_net_R"]) for fold in folds),
            default=0.0,
        ),
        "positive_pairs": positive_pairs,
        "active_pairs": len(active_pairs),
    }


def evaluate(development, validation):
    development_start = common.audit.parse_timestamp(
        development["period"]["start"]
    )
    development_end = common.audit.parse_timestamp(
        development["period"]["end"]
    )
    validation_start = common.audit.parse_timestamp(
        validation["period"]["start"]
    )
    validation_end = common.audit.parse_timestamp(
        validation["period"]["end"]
    )
    combined_start = min(development_start, validation_start)
    combined_end = max(development_end, validation_end)

    baseline_development = _period_metrics(development, BASELINE)
    baseline_validation = _period_metrics(validation, BASELINE)
    candidate_development = _period_metrics(development, CANDIDATE)
    candidate_validation = _period_metrics(validation, CANDIDATE)
    candidate_records = (
        _records(development, CANDIDATE)
        + _records(validation, CANDIDATE)
    )
    baseline_records = (
        _records(development, BASELINE)
        + _records(validation, BASELINE)
    )
    candidate_combined = _combined_metrics(
        candidate_records,
        combined_start,
        combined_end,
    )
    baseline_combined = _combined_metrics(
        baseline_records,
        combined_start,
        combined_end,
    )

    gates = {
        "development_net_positive": (
            candidate_development["overall"]["total_net_R"] > 0
        ),
        "validation_net_nonnegative": (
            candidate_validation["overall"]["total_net_R"] >= 0
        ),
        "validation_pf_gte_1": (
            candidate_validation["overall"]["profit_factor"] is not None
            and candidate_validation["overall"]["profit_factor"] >= 1.0
        ),
        "validation_improves_baseline_by_3R": (
            candidate_validation["overall"]["total_net_R"]
            - baseline_validation["overall"]["total_net_R"]
            >= 3.0
        ),
        "combined_pf_gte_1_10": (
            candidate_combined["overall"]["profit_factor"] is not None
            and candidate_combined["overall"]["profit_factor"] >= 1.10
        ),
        "combined_trades_gte_200": (
            candidate_combined["overall"]["trades"] >= 200
        ),
        "worst_period_fold_gte_minus_5R": (
            min(
                candidate_development["worst_fold_R"],
                candidate_validation["worst_fold_R"],
            )
            >= -5.0
        ),
        "validation_long_pf_gte_1": (
            candidate_validation["long"]["profit_factor"] is not None
            and candidate_validation["long"]["profit_factor"] >= 1.0
        ),
        "validation_short_pf_gte_0_95": (
            candidate_validation["short"]["profit_factor"] is not None
            and candidate_validation["short"]["profit_factor"] >= 0.95
        ),
    }
    passed = all(gates.values())
    structural_results = {}
    for name in REJECTED_STRUCTURAL_VARIANTS:
        structural_results[name] = {
            "development": _period_metrics(development, name),
            "validation": _period_metrics(validation, name),
        }
    return {
        "engine": "A_FOUNDATION_SR_EMA_GATE_V1",
        "baseline": BASELINE,
        "candidate": CANDIDATE,
        "baseline_metrics": {
            "development": baseline_development,
            "validation": baseline_validation,
            "combined": baseline_combined,
        },
        "candidate_metrics": {
            "development": candidate_development,
            "validation": candidate_validation,
            "combined": candidate_combined,
        },
        "gates": gates,
        "gate_passed": passed,
        "decision": (
            "APPROVE_NARROW_SR_TOUCH_SAFETY_FIX"
            if passed
            else "KEEP_LIVE_UNCHANGED"
        ),
        "rejected_structural_variants": structural_results,
        "limitations": [
            "This gate compares indicator foundations, not guaranteed future profit.",
            "Spread, funding availability, global concurrency, and exact limit fills are not replayed.",
            "Validation short PF remains below 1.0 and requires forward monitoring.",
        ],
    }


def main():
    parser = argparse.ArgumentParser(
        description="Evaluate the frozen Strategy A indicator-foundation gate"
    )
    parser.add_argument("--development", required=True)
    parser.add_argument("--validation", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    result = evaluate(
        read_json(args.development),
        read_json(args.validation),
    )
    write_json(args.output, result)
    print(json.dumps({
        "output": args.output,
        "decision": result["decision"],
        "gate_passed": result["gate_passed"],
        "gates": result["gates"],
        "candidate_combined": result["candidate_metrics"]["combined"],
    }, indent=2))


if __name__ == "__main__":
    main()
