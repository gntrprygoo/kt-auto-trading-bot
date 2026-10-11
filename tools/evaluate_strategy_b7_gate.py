import argparse
import json
import pathlib
from collections import defaultdict

import research_strategy_bc_v2 as common
import strategy_evidence_audit as audit


PRIMARY = "B7_DERIVATIVES_P20"
TIGHT = "B7_DERIVATIVES_P15"
WIDE = "B7_DERIVATIVES_P25"
RESULT_KEY = "net_R_live"
STRESS_KEY = "net_R_live_cost_0_20"


def read_json(path):
    with pathlib.Path(path).open(
        "r",
        encoding="utf-8-sig",
    ) as handle:
        return json.load(handle)


def write_json(path, value):
    output = pathlib.Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(value, handle, ensure_ascii=True, indent=2)
        handle.write("\n")


def records(report, candidate):
    return list(report["strategy_b"][candidate]["records"])


def profit_factor_at_least(metrics, threshold):
    value = metrics["profit_factor"]
    if value is None:
        return metrics["trades"] > 0 and metrics["total_net_R"] > 0
    return float(value) >= threshold


def metrics_bundle(items):
    return {
        "overall": common.summarize(items, RESULT_KEY),
        "long": common.summarize(
            [item for item in items if item["side"] == "LONG"],
            RESULT_KEY,
        ),
        "short": common.summarize(
            [item for item in items if item["side"] == "SHORT"],
            RESULT_KEY,
        ),
        "cost_stress_0_20": common.summarize(items, STRESS_KEY),
    }


def pair_concentration(items):
    positive = defaultdict(float)
    for item in items:
        positive[item["pair"]] += max(
            0.0,
            float(item[RESULT_KEY]),
        )
    total = sum(positive.values())
    top_pair, top_value = max(
        positive.items(),
        key=lambda item: item[1],
        default=(None, 0.0),
    )
    return {
        "pair_count": len({item["pair"] for item in items}),
        "top_positive_pair": top_pair,
        "top_positive_pair_share": (
            top_value / total if total > 0 else 1.0
        ),
    }


def equal_time_folds(report, candidate, count):
    start = audit.parse_timestamp(report["period"]["start"])
    end = audit.parse_timestamp(report["period"]["end"])
    width = max(1, (end - start + 1) // count)
    items = records(report, candidate)
    folds = []
    for number in range(count):
        fold_start = start + number * width
        fold_end = (
            end
            if number == count - 1
            else start + (number + 1) * width - 1
        )
        fold_items = [
            item
            for item in items
            if fold_start <= int(item["signal_time"]) <= fold_end
        ]
        metrics = common.summarize(fold_items, RESULT_KEY)
        folds.append({
            "fold": number + 1,
            "start_ms": fold_start,
            "end_ms": fold_end,
            **metrics,
        })
    positive = [
        item
        for item in folds
        if item["trades"] > 0 and item["total_net_R"] > 0
    ]
    return {
        "count": count,
        "positive": len(positive),
        "folds": folds,
    }


def side_passes(metrics, minimum_trades):
    return (
        metrics["trades"] >= minimum_trades
        and metrics["total_net_R"] > 0
        and profit_factor_at_least(metrics, 1.05)
    )


def development_evaluation(report):
    primary_items = records(report, PRIMARY)
    primary = metrics_bundle(primary_items)
    tight = metrics_bundle(records(report, TIGHT))
    wide = metrics_bundle(records(report, WIDE))
    concentration = pair_concentration(primary_items)
    folds = equal_time_folds(report, PRIMARY, 4)
    checks = {
        "trades_gte_120": primary["overall"]["trades"] >= 120,
        "net_positive": primary["overall"]["total_net_R"] > 0,
        "pf_gte_1_25": profit_factor_at_least(
            primary["overall"],
            1.25,
        ),
        "avg_R_gte_0_10": primary["overall"]["avg_net_R"] >= 0.10,
        "dd_lte_8R": primary["overall"]["max_drawdown_R"] <= 8.0,
        "positive_folds_gte_3_of_4": folds["positive"] >= 3,
        "pair_count_gte_20": concentration["pair_count"] >= 20,
        "top_pair_share_lte_25pct": (
            concentration["top_positive_pair_share"] <= 0.25
        ),
        "long_side_valid": side_passes(primary["long"], 30),
        "short_side_valid": side_passes(primary["short"], 30),
        "stress_net_positive": (
            primary["cost_stress_0_20"]["total_net_R"] > 0
        ),
        "stress_pf_gte_1_10": profit_factor_at_least(
            primary["cost_stress_0_20"],
            1.10,
        ),
        "tight_net_positive": tight["overall"]["total_net_R"] > 0,
        "tight_pf_gte_1_05": profit_factor_at_least(
            tight["overall"],
            1.05,
        ),
        "tight_stress_nonnegative": (
            tight["cost_stress_0_20"]["total_net_R"] >= 0
        ),
        "wide_net_positive": wide["overall"]["total_net_R"] > 0,
        "wide_pf_gte_1_05": profit_factor_at_least(
            wide["overall"],
            1.05,
        ),
        "wide_stress_nonnegative": (
            wide["cost_stress_0_20"]["total_net_R"] >= 0
        ),
    }
    passed = all(checks.values())
    return {
        "primary": primary,
        "tight": tight,
        "wide": wide,
        "folds": folds,
        "concentration": concentration,
        "checks": checks,
        "failed_checks": [
            name for name, value in checks.items() if not value
        ],
        "passed": passed,
    }


def validation_evaluation(report):
    items = records(report, PRIMARY)
    bundle = metrics_bundle(items)
    folds = equal_time_folds(report, PRIMARY, 5)
    checks = {
        "trades_gte_100": bundle["overall"]["trades"] >= 100,
        "net_positive": bundle["overall"]["total_net_R"] > 0,
        "pf_gte_1_10": profit_factor_at_least(
            bundle["overall"],
            1.10,
        ),
        "dd_lte_10R": bundle["overall"]["max_drawdown_R"] <= 10.0,
        "positive_folds_gte_3_of_5": folds["positive"] >= 3,
        "stress_pf_gte_1_00": profit_factor_at_least(
            bundle["cost_stress_0_20"],
            1.00,
        ),
        "long_represented": bundle["long"]["trades"] > 0,
        "short_represented": bundle["short"]["trades"] > 0,
    }
    passed = all(checks.values())
    return {
        "metrics": bundle,
        "folds": folds,
        "checks": checks,
        "failed_checks": [
            name for name, value in checks.items() if not value
        ],
        "passed": passed,
    }


def evaluate(development, validation=None):
    development_result = development_evaluation(development)
    result = {
        "candidate": PRIMARY,
        "neighbors": [TIGHT, WIDE],
        "spec": (
            "docs/STRATEGY_B7_DERIVATIVES_REGIME_"
            "FROZEN_SPEC_2026-07-29.md"
        ),
        "development": development_result,
        "validation_opened": validation is not None,
        "holdout_opened": False,
        "historical_shadow_admission": False,
        "live_approved": False,
    }
    if not development_result["passed"]:
        result.update({
            "decision": "PAUSED_DEVELOPMENT_FAILED",
            "live_blocker": "development_gate_failed",
        })
        return result
    if validation is None:
        result.update({
            "decision": "READY_FOR_PRIOR_VALIDATION",
            "live_blocker": "prior_validation_not_evaluated",
        })
        return result

    validation_result = validation_evaluation(validation)
    result["validation"] = validation_result
    if validation_result["passed"]:
        result.update({
            "decision": "READY_FOR_FINAL_HISTORICAL_HOLDOUT",
            "live_blocker": "final_historical_holdout_not_evaluated",
        })
    else:
        result.update({
            "decision": "PAUSED_VALIDATION_FAILED",
            "live_blocker": "prior_validation_gate_failed",
        })
    return result


def main():
    parser = argparse.ArgumentParser(
        description="Evaluate frozen Strategy B7 promotion gate"
    )
    parser.add_argument("--development", required=True)
    parser.add_argument("--validation")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    development = read_json(args.development)
    validation = read_json(args.validation) if args.validation else None
    result = evaluate(development, validation)
    write_json(args.output, result)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
