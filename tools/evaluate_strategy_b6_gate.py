import argparse
import json
import pathlib
from collections import defaultdict
from datetime import datetime

import research_strategy_bc_v2 as common


PRIMARY = "B6_EXPANSION_ACCEPTANCE"
NEIGHBOR = "B6_EXPANSION_ACCEPTANCE_NEIGHBOR"
RESULT_KEY = "net_R_live"
STRESS_KEY = "net_R_live_cost_0_20"


def read_json(path):
    with pathlib.Path(path).open("r", encoding="utf-8-sig") as handle:
        return json.load(handle)


def write_json(path, value):
    path = pathlib.Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(value, handle, ensure_ascii=True, indent=2)
        handle.write("\n")


def records(report, candidate):
    return list(report["strategy_b"][candidate]["records"])


def report_days(report):
    start = datetime.fromisoformat(report["period"]["start"])
    end = datetime.fromisoformat(report["period"]["end"])
    return max(1.0, (end - start).total_seconds() / 86400.0)


def annualized_frequency(items, days):
    return round(len(items) * 365.25 / days, 2)


def profit_factor_at_least(metrics, threshold):
    value = metrics["profit_factor"]
    if value is None:
        return metrics["trades"] > 0 and metrics["total_net_R"] > 0
    return value >= threshold


def fold_stats(report, candidate):
    folds = report["strategy_b"][candidate]["LIVE_MANAGEMENT"]["folds_30d"]
    nonempty = [fold for fold in folds if int(fold["trades"]) > 0]
    positive = [fold for fold in nonempty if float(fold["total_net_R"]) > 0]
    return {
        "nonempty": len(nonempty),
        "positive": len(positive),
        "positive_ratio": len(positive) / len(nonempty) if nonempty else 0.0,
        "worst_net_R": min(
            (float(fold["total_net_R"]) for fold in nonempty),
            default=0.0,
        ),
    }


def combine_fold_stats(*items):
    nonempty = sum(item["nonempty"] for item in items)
    positive = sum(item["positive"] for item in items)
    return {
        "nonempty": nonempty,
        "positive": positive,
        "positive_ratio": positive / nonempty if nonempty else 0.0,
        "worst_net_R": min(
            (item["worst_net_R"] for item in items),
            default=0.0,
        ),
    }


def pair_concentration(items):
    by_pair = defaultdict(float)
    for item in items:
        by_pair[item["pair"]] += max(0.0, float(item[RESULT_KEY]))
    total = sum(by_pair.values())
    top_pair, top_value = max(
        by_pair.items(),
        key=lambda pair: pair[1],
        default=(None, 0.0),
    )
    return {
        "pair_count": len({item["pair"] for item in items}),
        "top_positive_pair": top_pair,
        "top_positive_pair_share": top_value / total if total > 0 else 1.0,
    }


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


def side_passed(metrics, minimum_trades, require_positive=True):
    if metrics["trades"] < minimum_trades:
        return False
    if require_positive and metrics["total_net_R"] <= 0:
        return False
    return profit_factor_at_least(metrics, 1.05)


def development_evaluation(recent, prior, require_long=True):
    recent_records = records(recent, PRIMARY)
    prior_records = records(prior, PRIMARY)
    combined_records = sorted(
        recent_records + prior_records,
        key=lambda item: (item["signal_time"], item["pair"]),
    )
    recent_bundle = metrics_bundle(recent_records)
    prior_bundle = metrics_bundle(prior_records)
    combined_bundle = metrics_bundle(combined_records)
    days = report_days(recent) + report_days(prior)
    folds = combine_fold_stats(
        fold_stats(recent, PRIMARY),
        fold_stats(prior, PRIMARY),
    )
    concentration = pair_concentration(combined_records)

    neighbor_recent = common.summarize(records(recent, NEIGHBOR), RESULT_KEY)
    neighbor_prior = common.summarize(records(prior, NEIGHBOR), RESULT_KEY)
    neighbor_combined = common.summarize(
        records(recent, NEIGHBOR) + records(prior, NEIGHBOR),
        RESULT_KEY,
    )

    checks = {
        "recent_trades_gte_30": recent_bundle["overall"]["trades"] >= 30,
        "prior_trades_gte_40": prior_bundle["overall"]["trades"] >= 40,
        "combined_trades_gte_85": combined_bundle["overall"]["trades"] >= 85,
        "annualized_frequency_gte_45": (
            annualized_frequency(combined_records, days) >= 45.0
        ),
        "recent_net_positive": recent_bundle["overall"]["total_net_R"] > 0,
        "prior_net_positive": prior_bundle["overall"]["total_net_R"] > 0,
        "recent_pf_gte_1_25": profit_factor_at_least(
            recent_bundle["overall"],
            1.25,
        ),
        "prior_pf_gte_1_20": profit_factor_at_least(
            prior_bundle["overall"],
            1.20,
        ),
        "combined_pf_gte_1_30": profit_factor_at_least(
            combined_bundle["overall"],
            1.30,
        ),
        "combined_avg_R_gte_0_10": (
            combined_bundle["overall"]["avg_net_R"] >= 0.10
        ),
        "recent_dd_lte_10R": (
            recent_bundle["overall"]["max_drawdown_R"] <= 10.0
        ),
        "prior_dd_lte_10R": (
            prior_bundle["overall"]["max_drawdown_R"] <= 10.0
        ),
        "positive_folds_gte_55pct": folds["positive_ratio"] >= 0.55,
        "worst_fold_gte_minus_4R": folds["worst_net_R"] >= -4.0,
        "pair_count_gte_15": concentration["pair_count"] >= 15,
        "top_pair_share_lte_30pct": (
            concentration["top_positive_pair_share"] <= 0.30
        ),
        "short_side_valid": side_passed(combined_bundle["short"], 20),
        "cost_stress_net_positive": (
            combined_bundle["cost_stress_0_20"]["total_net_R"] > 0
        ),
        "cost_stress_pf_gte_1_15": profit_factor_at_least(
            combined_bundle["cost_stress_0_20"],
            1.15,
        ),
        "neighbor_recent_positive": neighbor_recent["total_net_R"] > 0,
        "neighbor_prior_positive": neighbor_prior["total_net_R"] > 0,
        "neighbor_combined_pf_gte_1_15": profit_factor_at_least(
            neighbor_combined,
            1.15,
        ),
    }
    if require_long:
        checks["long_side_valid"] = side_passed(combined_bundle["long"], 20)
    return {
        "recent": recent_bundle,
        "prior": prior_bundle,
        "combined": combined_bundle,
        "annualized_frequency": annualized_frequency(combined_records, days),
        "folds": folds,
        "concentration": concentration,
        "neighbor": {
            "recent": neighbor_recent,
            "prior": neighbor_prior,
            "combined": neighbor_combined,
        },
        "checks": checks,
        "failed_checks": [
            name for name, passed in checks.items() if not passed
        ],
        "passed": all(checks.values()),
        "records": combined_records,
    }


def holdout_evaluation(holdout, require_long=True):
    holdout_records = records(holdout, PRIMARY)
    bundle = metrics_bundle(holdout_records)
    days = report_days(holdout)
    folds = fold_stats(holdout, PRIMARY)
    concentration = pair_concentration(holdout_records)
    neighbor = common.summarize(records(holdout, NEIGHBOR), RESULT_KEY)
    checks = {
        "holdout_trades_gte_40": bundle["overall"]["trades"] >= 40,
        "holdout_annualized_frequency_gte_35": (
            annualized_frequency(holdout_records, days) >= 35.0
        ),
        "holdout_net_positive": bundle["overall"]["total_net_R"] > 0,
        "holdout_pf_gte_1_20": profit_factor_at_least(
            bundle["overall"],
            1.20,
        ),
        "holdout_avg_R_gte_0_08": bundle["overall"]["avg_net_R"] >= 0.08,
        "holdout_dd_lte_9R": bundle["overall"]["max_drawdown_R"] <= 9.0,
        "holdout_positive_folds_gte_50pct": folds["positive_ratio"] >= 0.50,
        "holdout_worst_fold_gte_minus_4R": folds["worst_net_R"] >= -4.0,
        "holdout_pair_count_gte_10": concentration["pair_count"] >= 10,
        "holdout_top_pair_share_lte_35pct": (
            concentration["top_positive_pair_share"] <= 0.35
        ),
        "holdout_short_nonnegative": (
            bundle["short"]["trades"] >= 10
            and bundle["short"]["total_net_R"] >= 0
        ),
        "holdout_cost_stress_positive": (
            bundle["cost_stress_0_20"]["total_net_R"] > 0
        ),
        "holdout_neighbor_positive": neighbor["total_net_R"] > 0,
    }
    if require_long:
        checks["holdout_long_nonnegative"] = (
            bundle["long"]["trades"] >= 10
            and bundle["long"]["total_net_R"] >= 0
        )
    return {
        "metrics": bundle,
        "annualized_frequency": annualized_frequency(holdout_records, days),
        "folds": folds,
        "concentration": concentration,
        "neighbor": neighbor,
        "checks": checks,
        "failed_checks": [
            name for name, passed in checks.items() if not passed
        ],
        "passed": all(checks.values()),
        "records": holdout_records,
    }


def evaluate(recent, prior, holdout=None, require_long=True):
    development = development_evaluation(
        recent,
        prior,
        require_long=require_long,
    )
    result = {
        "candidate": PRIMARY,
        "neighbor": NEIGHBOR,
        "result_model": "LIVE_MANAGEMENT_TP1_TP2_SL_PLUS",
        "development": {
            key: value
            for key, value in development.items()
            if key != "records"
        },
        "holdout_opened": holdout is not None,
        "historical_shadow_admission": False,
        "live_approved": False,
    }
    if not development["passed"]:
        result.update({
            "decision": "PAUSED_DEVELOPMENT_FAILED",
            "live_blocker": "development_gate_failed",
        })
        return result
    if holdout is None:
        result.update({
            "decision": "READY_FOR_UNTOUCHED_HOLDOUT",
            "live_blocker": "untouched_holdout_not_evaluated",
        })
        return result

    holdout_result = holdout_evaluation(
        holdout,
        require_long=require_long,
    )
    all_records = sorted(
        development["records"] + holdout_result["records"],
        key=lambda item: (item["signal_time"], item["pair"]),
    )
    combined = metrics_bundle(all_records)
    combined_checks = {
        "all_trades_gte_125": combined["overall"]["trades"] >= 125,
        "all_net_positive": combined["overall"]["total_net_R"] > 0,
        "all_pf_gte_1_25": profit_factor_at_least(
            combined["overall"],
            1.25,
        ),
        "all_avg_R_gte_0_10": combined["overall"]["avg_net_R"] >= 0.10,
        "all_dd_lte_14R": combined["overall"]["max_drawdown_R"] <= 14.0,
        "all_cost_stress_positive": (
            combined["cost_stress_0_20"]["total_net_R"] > 0
        ),
        "all_short_positive": combined["short"]["total_net_R"] > 0,
    }
    if require_long:
        combined_checks["all_long_positive"] = (
            combined["long"]["total_net_R"] > 0
        )
    historical_passed = holdout_result["passed"] and all(
        combined_checks.values()
    )
    result["holdout"] = {
        key: value
        for key, value in holdout_result.items()
        if key != "records"
    }
    result["all_periods"] = combined
    result["combined_checks"] = combined_checks
    result["combined_failed_checks"] = [
        name for name, passed in combined_checks.items() if not passed
    ]
    result["historical_shadow_admission"] = historical_passed
    if historical_passed:
        result.update({
            "decision": "FORWARD_SHADOW",
            "live_blocker": "requires_50_closed_forward_shadow_trades",
        })
    else:
        result.update({
            "decision": "PAUSED_HOLDOUT_FAILED",
            "live_blocker": "untouched_holdout_gate_failed",
        })
    return result


def main():
    parser = argparse.ArgumentParser(
        description="Evaluate frozen Strategy B6 promotion gate"
    )
    parser.add_argument("--development-recent", required=True)
    parser.add_argument("--development-prior", required=True)
    parser.add_argument("--holdout")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    result = evaluate(
        read_json(args.development_recent),
        read_json(args.development_prior),
        read_json(args.holdout) if args.holdout else None,
    )
    write_json(args.output, result)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
