import argparse
import json
import pathlib
from collections import defaultdict
from datetime import datetime

import research_strategy_bc_v2 as common


PRIMARY = "B51_MATURE_SHORT_STRICT"
NEIGHBOR = "B51_MATURE_SHORT"
RESULT_KEY = "net_R_live"


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


def evaluate(development_recent, development_prior, holdout):
    recent_records = records(development_recent, PRIMARY)
    prior_records = records(development_prior, PRIMARY)
    holdout_records = records(holdout, PRIMARY)
    development_records = sorted(
        recent_records + prior_records,
        key=lambda item: (item["signal_time"], item["pair"]),
    )
    all_records = sorted(
        development_records + holdout_records,
        key=lambda item: (item["signal_time"], item["pair"]),
    )

    recent_metrics = common.summarize(recent_records, RESULT_KEY)
    prior_metrics = common.summarize(prior_records, RESULT_KEY)
    development_metrics = common.summarize(development_records, RESULT_KEY)
    holdout_metrics = common.summarize(holdout_records, RESULT_KEY)
    all_metrics = common.summarize(all_records, RESULT_KEY)

    development_days = report_days(development_recent) + report_days(development_prior)
    holdout_days = report_days(holdout)
    development_frequency = annualized_frequency(
        development_records,
        development_days,
    )
    holdout_frequency = annualized_frequency(holdout_records, holdout_days)

    folds_recent = fold_stats(development_recent, PRIMARY)
    folds_prior = fold_stats(development_prior, PRIMARY)
    folds_development = combine_fold_stats(folds_recent, folds_prior)
    folds_holdout = fold_stats(holdout, PRIMARY)
    development_concentration = pair_concentration(development_records)
    holdout_concentration = pair_concentration(holdout_records)

    neighbor_recent_records = records(development_recent, NEIGHBOR)
    neighbor_prior_records = records(development_prior, NEIGHBOR)
    neighbor_holdout_records = records(holdout, NEIGHBOR)
    neighbor_recent = common.summarize(neighbor_recent_records, RESULT_KEY)
    neighbor_prior = common.summarize(neighbor_prior_records, RESULT_KEY)
    neighbor_development = common.summarize(
        neighbor_recent_records + neighbor_prior_records,
        RESULT_KEY,
    )
    neighbor_holdout = common.summarize(neighbor_holdout_records, RESULT_KEY)

    development_checks = {
        "recent_trades_gte_25": recent_metrics["trades"] >= 25,
        "prior_trades_gte_35": prior_metrics["trades"] >= 35,
        "combined_trades_gte_70": development_metrics["trades"] >= 70,
        "annualized_frequency_gte_40": development_frequency >= 40.0,
        "recent_net_positive": recent_metrics["total_net_R"] > 0,
        "prior_net_positive": prior_metrics["total_net_R"] > 0,
        "recent_pf_gte_1_20": profit_factor_at_least(recent_metrics, 1.20),
        "prior_pf_gte_1_15": profit_factor_at_least(prior_metrics, 1.15),
        "combined_pf_gte_1_30": profit_factor_at_least(
            development_metrics,
            1.30,
        ),
        "combined_avg_R_gte_0_10": development_metrics["avg_net_R"] >= 0.10,
        "recent_dd_lte_10R": recent_metrics["max_drawdown_R"] <= 10.0,
        "prior_dd_lte_10R": prior_metrics["max_drawdown_R"] <= 10.0,
        "positive_folds_gte_50pct": folds_development["positive_ratio"] >= 0.50,
        "worst_fold_gte_minus_4R": folds_development["worst_net_R"] >= -4.0,
        "pair_count_gte_15": development_concentration["pair_count"] >= 15,
        "top_pair_share_lte_30pct": (
            development_concentration["top_positive_pair_share"] <= 0.30
        ),
        "neighbor_recent_positive": neighbor_recent["total_net_R"] > 0,
        "neighbor_prior_positive": neighbor_prior["total_net_R"] > 0,
        "neighbor_combined_pf_gte_1_20": profit_factor_at_least(
            neighbor_development,
            1.20,
        ),
    }

    holdout_checks = {
        "holdout_trades_gte_35": holdout_metrics["trades"] >= 35,
        "holdout_annualized_frequency_gte_35": holdout_frequency >= 35.0,
        "holdout_net_positive": holdout_metrics["total_net_R"] > 0,
        "holdout_pf_gte_1_20": profit_factor_at_least(holdout_metrics, 1.20),
        "holdout_avg_R_gte_0_08": holdout_metrics["avg_net_R"] >= 0.08,
        "holdout_dd_lte_8R": holdout_metrics["max_drawdown_R"] <= 8.0,
        "holdout_positive_folds_gte_50pct": folds_holdout["positive_ratio"] >= 0.50,
        "holdout_worst_fold_gte_minus_4R": folds_holdout["worst_net_R"] >= -4.0,
        "holdout_pair_count_gte_10": holdout_concentration["pair_count"] >= 10,
        "holdout_top_pair_share_lte_35pct": (
            holdout_concentration["top_positive_pair_share"] <= 0.35
        ),
        "neighbor_holdout_positive": neighbor_holdout["total_net_R"] > 0,
    }

    combined_checks = {
        "all_trades_gte_105": all_metrics["trades"] >= 105,
        "all_net_positive": all_metrics["total_net_R"] > 0,
        "all_pf_gte_1_25": profit_factor_at_least(all_metrics, 1.25),
        "all_avg_R_gte_0_10": all_metrics["avg_net_R"] >= 0.10,
        "all_dd_lte_12R": all_metrics["max_drawdown_R"] <= 12.0,
    }

    development_passed = all(development_checks.values())
    holdout_passed = all(holdout_checks.values())
    combined_passed = all(combined_checks.values())
    historical_passed = (
        development_passed
        and holdout_passed
        and combined_passed
    )
    if not development_passed:
        decision = "PAUSED_DEVELOPMENT_FAILED"
        live_blocker = "development_gate_failed"
    elif not holdout_passed or not combined_passed:
        decision = "PAUSED_HOLDOUT_FAILED"
        live_blocker = "untouched_holdout_gate_failed"
    else:
        decision = "FORWARD_SHADOW"
        live_blocker = "requires_50_closed_forward_shadow_trades"

    return {
        "candidate": PRIMARY,
        "neighbor": NEIGHBOR,
        "result_model": "LIVE_MANAGEMENT_TP1_TP2_SL_PLUS",
        "development_recent": recent_metrics,
        "development_prior": prior_metrics,
        "development_combined": development_metrics,
        "development_annualized_frequency": development_frequency,
        "untouched_holdout": holdout_metrics,
        "holdout_annualized_frequency": holdout_frequency,
        "all_periods": all_metrics,
        "folds_development": folds_development,
        "folds_holdout": folds_holdout,
        "concentration_development": development_concentration,
        "concentration_holdout": holdout_concentration,
        "neighbor_metrics": {
            "development_recent": neighbor_recent,
            "development_prior": neighbor_prior,
            "development_combined": neighbor_development,
            "untouched_holdout": neighbor_holdout,
        },
        "checks": {
            "development": development_checks,
            "holdout": holdout_checks,
            "combined": combined_checks,
        },
        "failed_checks": {
            "development": [
                name for name, passed in development_checks.items() if not passed
            ],
            "holdout": [
                name for name, passed in holdout_checks.items() if not passed
            ],
            "combined": [
                name for name, passed in combined_checks.items() if not passed
            ],
        },
        "historical_shadow_admission": historical_passed,
        "decision": decision,
        "live_approved": False,
        "live_blocker": live_blocker,
    }


def main():
    parser = argparse.ArgumentParser(
        description="Evaluate frozen Strategy B5.1 promotion gate"
    )
    parser.add_argument("--development-recent", required=True)
    parser.add_argument("--development-prior", required=True)
    parser.add_argument("--holdout", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    result = evaluate(
        read_json(args.development_recent),
        read_json(args.development_prior),
        read_json(args.holdout),
    )
    write_json(args.output, result)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
