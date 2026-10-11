import argparse
import json

import evaluate_strategy_b6_gate as gate


PRIMARY = "B62_SHORT_TREND_RUNNER_2_5"
TIGHT = "B62_SHORT_TREND_RUNNER_2_0"
WIDE = "B62_SHORT_TREND_RUNNER_3_0"
RESULT_KEY = "net_R_live"
STRESS_KEY = "net_R_live_cost_0_20"


def records(report, candidate):
    return list(report["strategy_b"][candidate]["records"])


def candidate_metrics(report, candidate):
    items = records(report, candidate)
    return {
        "overall": gate.common.summarize(items, RESULT_KEY),
        "cost_stress_0_20": gate.common.summarize(items, STRESS_KEY),
    }


def evaluate(report):
    primary = candidate_metrics(report, PRIMARY)
    tight = candidate_metrics(report, TIGHT)
    wide = candidate_metrics(report, WIDE)
    folds = gate.fold_stats(report, PRIMARY)
    concentration = gate.pair_concentration(records(report, PRIMARY))
    checks = {
        "design_trades_gte_30": primary["overall"]["trades"] >= 30,
        "design_net_positive": primary["overall"]["total_net_R"] > 0,
        "design_pf_gte_1_25": gate.profit_factor_at_least(
            primary["overall"],
            1.25,
        ),
        "design_avg_R_gte_0_10": primary["overall"]["avg_net_R"] >= 0.10,
        "design_dd_lte_10R": primary["overall"]["max_drawdown_R"] <= 10.0,
        "positive_folds_gte_55pct": folds["positive_ratio"] >= 0.55,
        "worst_fold_gte_minus_4R": folds["worst_net_R"] >= -4.0,
        "pair_count_gte_15": concentration["pair_count"] >= 15,
        "top_pair_share_lte_30pct": (
            concentration["top_positive_pair_share"] <= 0.30
        ),
        "cost_stress_net_positive": (
            primary["cost_stress_0_20"]["total_net_R"] > 0
        ),
        "cost_stress_pf_gte_1_15": gate.profit_factor_at_least(
            primary["cost_stress_0_20"],
            1.15,
        ),
        "tight_neighbor_net_positive": tight["overall"]["total_net_R"] > 0,
        "tight_neighbor_pf_gte_1_10": gate.profit_factor_at_least(
            tight["overall"],
            1.10,
        ),
        "tight_neighbor_cost_stress_nonnegative": (
            tight["cost_stress_0_20"]["total_net_R"] >= 0
        ),
        "wide_neighbor_net_positive": wide["overall"]["total_net_R"] > 0,
        "wide_neighbor_pf_gte_1_10": gate.profit_factor_at_least(
            wide["overall"],
            1.10,
        ),
        "wide_neighbor_cost_stress_nonnegative": (
            wide["cost_stress_0_20"]["total_net_R"] >= 0
        ),
    }
    passed = all(checks.values())
    return {
        "candidate": PRIMARY,
        "neighbors": [TIGHT, WIDE],
        "stage": "RECENT_DESIGN",
        "primary": primary,
        "tight_neighbor": tight,
        "wide_neighbor": wide,
        "folds": folds,
        "concentration": concentration,
        "checks": checks,
        "failed_checks": [
            name for name, value in checks.items() if not value
        ],
        "design_passed": passed,
        "decision": (
            "READY_FOR_PRIOR_VALIDATION"
            if passed
            else "PAUSED_DESIGN_FAILED"
        ),
        "holdout_opened": False,
        "historical_shadow_admission": False,
        "live_approved": False,
    }


def main():
    parser = argparse.ArgumentParser(
        description="Evaluate frozen Strategy B6.2 design gate"
    )
    parser.add_argument("--report", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    result = evaluate(gate.read_json(args.report))
    gate.write_json(args.output, result)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()

