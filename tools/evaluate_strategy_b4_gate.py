import argparse
import json
import pathlib
from collections import defaultdict

import research_strategy_bc_v2 as common


PRIMARY = "B4_RETEST_CLOSE_LONG"
NEIGHBOR = "B4_RETEST_CLOSE_NEIGHBOR_LONG"
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


def nonempty_fold_stats(report, candidate):
    folds = report["strategy_b"][candidate]["LIVE_MANAGEMENT"]["folds_30d"]
    nonempty = [fold for fold in folds if int(fold["trades"]) > 0]
    positive = [fold for fold in nonempty if float(fold["total_net_R"]) > 0]
    return {
        "nonempty": len(nonempty),
        "positive": len(positive),
        "positive_ratio": len(positive) / len(nonempty) if nonempty else 0.0,
        "worst_net_R": min((float(fold["total_net_R"]) for fold in nonempty), default=0.0),
    }


def pair_concentration(items):
    by_pair = defaultdict(float)
    for item in items:
        by_pair[item["pair"]] += max(0.0, float(item[RESULT_KEY]))
    total = sum(by_pair.values())
    top_pair, top_value = max(by_pair.items(), key=lambda pair: pair[1], default=(None, 0.0))
    return {
        "pair_count": len({item["pair"] for item in items}),
        "top_positive_pair": top_pair,
        "top_positive_pair_share": top_value / total if total > 0 else 1.0,
    }


def profit_factor_at_least(metrics, threshold):
    value = metrics["profit_factor"]
    if value is None:
        return metrics["trades"] > 0 and metrics["total_net_R"] > 0
    return value >= threshold


def evaluate(development, stress):
    dev_records = records(development, PRIMARY)
    stress_records = records(stress, PRIMARY)
    combined = sorted(dev_records + stress_records, key=lambda item: (item["signal_time"], item["pair"]))
    dev_metrics = common.summarize(dev_records, RESULT_KEY)
    stress_metrics = common.summarize(stress_records, RESULT_KEY)
    combined_metrics = common.summarize(combined, RESULT_KEY)
    folds_dev = nonempty_fold_stats(development, PRIMARY)
    folds_stress = nonempty_fold_stats(stress, PRIMARY)
    fold_count = folds_dev["nonempty"] + folds_stress["nonempty"]
    fold_positive = folds_dev["positive"] + folds_stress["positive"]
    fold_ratio = fold_positive / fold_count if fold_count else 0.0
    worst_fold = min(folds_dev["worst_net_R"], folds_stress["worst_net_R"])
    concentration = pair_concentration(combined)

    neighbor_dev_records = records(development, NEIGHBOR)
    neighbor_stress_records = records(stress, NEIGHBOR)
    neighbor_combined = neighbor_dev_records + neighbor_stress_records
    neighbor_dev = common.summarize(neighbor_dev_records, RESULT_KEY)
    neighbor_stress = common.summarize(neighbor_stress_records, RESULT_KEY)
    neighbor_all = common.summarize(neighbor_combined, RESULT_KEY)

    checks = {
        "development_trades_gte_10": dev_metrics["trades"] >= 10,
        "stress_trades_gte_15": stress_metrics["trades"] >= 15,
        "combined_trades_gte_35": combined_metrics["trades"] >= 35,
        "development_net_positive": dev_metrics["total_net_R"] > 0,
        "stress_net_positive": stress_metrics["total_net_R"] > 0,
        "development_pf_gte_1_20": profit_factor_at_least(dev_metrics, 1.20),
        "stress_pf_gte_1_20": profit_factor_at_least(stress_metrics, 1.20),
        "combined_pf_gte_1_25": profit_factor_at_least(combined_metrics, 1.25),
        "combined_avg_R_gte_0_08": combined_metrics["avg_net_R"] >= 0.08,
        "development_dd_lte_8R": dev_metrics["max_drawdown_R"] <= 8.0,
        "stress_dd_lte_8R": stress_metrics["max_drawdown_R"] <= 8.0,
        "positive_nonempty_folds_gte_55pct": fold_ratio >= 0.55,
        "worst_fold_gte_minus_3R": worst_fold >= -3.0,
        "pair_count_gte_12": concentration["pair_count"] >= 12,
        "top_pair_share_lte_30pct": concentration["top_positive_pair_share"] <= 0.30,
        "neighbor_development_positive": neighbor_dev["total_net_R"] > 0,
        "neighbor_stress_positive": neighbor_stress["total_net_R"] > 0,
        "neighbor_combined_trades_gte_20": neighbor_all["trades"] >= 20,
        "neighbor_combined_pf_gte_1_10": profit_factor_at_least(neighbor_all, 1.10),
    }
    historical_passed = all(checks.values())
    failed_checks = [name for name, passed in checks.items() if not passed]
    return {
        "candidate": PRIMARY,
        "result_model": "LIVE_MANAGEMENT_TP1_TP2_SL_PLUS",
        "development": dev_metrics,
        "stress": stress_metrics,
        "combined": combined_metrics,
        "folds": {
            "nonempty": fold_count,
            "positive": fold_positive,
            "positive_ratio": round(fold_ratio, 4),
            "worst_net_R": round(worst_fold, 4),
        },
        "concentration": concentration,
        "neighbor": {
            "candidate": NEIGHBOR,
            "development": neighbor_dev,
            "stress": neighbor_stress,
            "combined": neighbor_all,
        },
        "checks": checks,
        "failed_checks": failed_checks,
        "historical_shadow_admission": historical_passed,
        "decision": "FORWARD_SHADOW" if historical_passed else "PAUSED_NO_VALIDATED_EDGE",
        "live_approved": False,
        "live_blocker": (
            "requires_30_closed_forward_shadow_trades"
            if historical_passed
            else "historical_admission_failed"
        ),
    }


def main():
    parser = argparse.ArgumentParser(description="Evaluate frozen Strategy B4 promotion gate")
    parser.add_argument("--development", required=True)
    parser.add_argument("--stress", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    result = evaluate(read_json(args.development), read_json(args.stress))
    write_json(args.output, result)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
