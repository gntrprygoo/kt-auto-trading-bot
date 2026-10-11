import argparse
import json
import pathlib


PRIMARY = "ABC_PRIMARY"
TIGHT = "ABC_TIGHT"
WIDE = "ABC_WIDE"


def read_json(path):
    with pathlib.Path(path).open("r", encoding="utf-8-sig") as handle:
        return json.load(handle)


def write_json(path, value):
    output = pathlib.Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(value, handle, ensure_ascii=True, indent=2)
        handle.write("\n")


def factor_at_least(summary, minimum):
    factor = summary.get("profit_factor")
    return factor is not None and float(factor) >= minimum


def side_or_path_passes(summary, minimum_trades, minimum_factor=1.0):
    return (
        int(summary.get("trades", 0)) >= minimum_trades
        and float(summary.get("total_net_R", 0.0)) >= 0.0
        and factor_at_least(summary, minimum_factor)
    )


def positive_fold_ratio(folds):
    nonempty = [
        fold for fold in folds if int(fold.get("trades", 0)) > 0
    ]
    positive = [
        fold
        for fold in nonempty
        if float(fold.get("total_net_R", 0.0)) > 0
    ]
    return (
        len(positive) / len(nonempty)
        if nonempty
        else 0.0
    ), len(positive), len(nonempty)


def development_checks(report):
    variants = report["variants"]
    primary = variants[PRIMARY]["baseline"]
    tight = variants[TIGHT]["baseline"]
    wide = variants[WIDE]["baseline"]
    overall = primary["overall"]
    stress = primary["cost_stress_0_20"]
    paths = primary["paths"]
    fold_ratio, positive_folds, nonempty_folds = positive_fold_ratio(
        primary["folds_30d"]
    )
    concentration = primary["concentration"]
    checks = {
        "trades_gte_180": int(overall["trades"]) >= 180,
        "net_R_positive": float(overall["total_net_R"]) > 0,
        "profit_factor_gte_1_20": factor_at_least(overall, 1.20),
        "avg_R_gte_0_08": float(overall["avg_net_R"]) >= 0.08,
        "max_drawdown_lte_12R": (
            float(overall["max_drawdown_R"]) <= 12.0
        ),
        "positive_fold_ratio_gte_60pct": fold_ratio >= 0.60,
        "long_sample_and_edge": side_or_path_passes(
            primary["long"],
            50,
            1.05,
        ),
        "short_sample_and_edge": side_or_path_passes(
            primary["short"],
            50,
            1.05,
        ),
        "path_A_sample_and_nonnegative": side_or_path_passes(
            paths["A"],
            30,
            1.00,
        ),
        "path_B_sample_and_nonnegative": side_or_path_passes(
            paths["B"],
            20,
            1.00,
        ),
        "path_C_sample_and_nonnegative": side_or_path_passes(
            paths["C"],
            30,
            1.00,
        ),
        "stress_net_positive": float(stress["total_net_R"]) > 0,
        "stress_profit_factor_gte_1_05": factor_at_least(
            stress,
            1.05,
        ),
        "top_pair_positive_share_lte_25pct": (
            float(concentration["top_positive_pair_share"]) <= 0.25
        ),
        "tight_neighbor_positive": (
            float(tight["overall"]["total_net_R"]) > 0
            and factor_at_least(tight["overall"], 1.05)
            and float(
                tight["cost_stress_0_20"]["total_net_R"]
            ) >= 0
        ),
        "wide_neighbor_positive": (
            float(wide["overall"]["total_net_R"]) > 0
            and factor_at_least(wide["overall"], 1.05)
            and float(
                wide["cost_stress_0_20"]["total_net_R"]
            ) >= 0
        ),
    }
    diagnostics = {
        "positive_folds": positive_folds,
        "nonempty_folds": nonempty_folds,
        "positive_fold_ratio": fold_ratio,
    }
    return checks, diagnostics


def validation_checks(report):
    primary = report["variants"][PRIMARY]["baseline"]
    overall = primary["overall"]
    stress = primary["cost_stress_0_20"]
    paths = primary["paths"]
    fold_ratio, positive_folds, nonempty_folds = positive_fold_ratio(
        primary["folds_30d"]
    )
    checks = {
        "validation_trades_gte_150": int(overall["trades"]) >= 150,
        "validation_net_R_positive": (
            float(overall["total_net_R"]) > 0
        ),
        "validation_profit_factor_gte_1_10": factor_at_least(
            overall,
            1.10,
        ),
        "validation_max_drawdown_lte_15R": (
            float(overall["max_drawdown_R"]) <= 15.0
        ),
        "validation_positive_fold_ratio_gte_55pct": (
            fold_ratio >= 0.55
        ),
        "validation_stress_nonnegative": (
            float(stress["total_net_R"]) >= 0
            and factor_at_least(stress, 1.00)
        ),
        "validation_both_sides_present": (
            int(primary["long"]["trades"]) >= 35
            and int(primary["short"]["trades"]) >= 35
        ),
        "validation_all_paths_present": all(
            int(paths[path]["trades"]) >= 15
            for path in ("A", "B", "C")
        ),
    }
    diagnostics = {
        "positive_folds": positive_folds,
        "nonempty_folds": nonempty_folds,
        "positive_fold_ratio": fold_ratio,
    }
    return checks, diagnostics


def modifier_decisions(development, calendar_report=None):
    primary = development["variants"][PRIMARY]["baseline"]["overall"]
    primary_pf = float(primary.get("profit_factor") or 0.0)
    primary_dd = float(primary["max_drawdown_R"])
    calendar_diag = development["variants"][PRIMARY][
        "calendar_soft_diagnostic"
    ]["overall"]
    approved_phases = []
    if calendar_report:
        approved_phases = calendar_report["decision"].get(
            "wib_soft_prior_phases",
            [],
        )
    calendar_pf = float(calendar_diag.get("profit_factor") or 0.0)
    calendar_adopt = (
        bool(approved_phases)
        and calendar_pf >= primary_pf + 0.03
        and float(calendar_diag["max_drawdown_R"])
        <= primary_dd + 1.0
    )

    ablation = development.get("derivatives_ablation", {})
    scope = ablation.get("scope", {})
    m0 = ablation.get("M0_PRICE_VOLUME", {}).get("overall", {})
    m1 = ablation.get("M1_OI_FLOW_SOFT", {}).get("overall", {})
    m0_pf = float(m0.get("profit_factor") or 0.0)
    m1_pf = float(m1.get("profit_factor") or 0.0)
    derivatives_adopt = (
        int(scope.get("eligible_trades", 0)) >= 100
        and len(scope.get("eligible_pairs", [])) >= 10
        and m1_pf >= m0_pf + 0.03
        and float(m1.get("max_drawdown_R", 999.0))
        <= float(m0.get("max_drawdown_R", 0.0)) + 1.0
    )
    return {
        "calendar": {
            "approved_phases": approved_phases,
            "adopt_as_soft_risk_modifier": calendar_adopt,
            "reason": (
                "Requires independently robust phases plus material "
                "portfolio improvement."
            ),
        },
        "derivatives": {
            "eligible_trades": int(scope.get("eligible_trades", 0)),
            "eligible_pairs": scope.get("eligible_pairs", []),
            "adopt_oi_flow_soft_modifier": derivatives_adopt,
            "adopt_hard_oi_filter": False,
            "reason": (
                "OI never supplies direction by itself; adoption also "
                "requires at least 100 trades across 10 pairs."
            ),
        },
    }


def evaluate(development, calendar_report=None, validation=None):
    dev_checks, dev_diagnostics = development_checks(development)
    development_passed = all(dev_checks.values())
    modifiers = modifier_decisions(development, calendar_report)
    validation_result = None
    validation_passed = False
    if validation is not None:
        checks, diagnostics = validation_checks(validation)
        validation_passed = all(checks.values())
        validation_result = {
            "checks": checks,
            "failed_checks": [
                key for key, passed in checks.items() if not passed
            ],
            "diagnostics": diagnostics,
            "passed": validation_passed,
        }
    historical_shadow_admission = (
        development_passed
        and validation is not None
        and validation_passed
    )
    if not development_passed:
        decision = "PAUSED_DEVELOPMENT_FAILED"
    elif validation is None:
        decision = "DEVELOPMENT_PASS_NEEDS_PRIOR_VALIDATION"
    elif not validation_passed:
        decision = "PAUSED_PRIOR_VALIDATION_FAILED"
    else:
        decision = "HISTORICAL_GATE_PASS_SHADOW_ONLY"
    return {
        "engine": "ABC_UNIFIED_GATE_V1",
        "development": {
            "checks": dev_checks,
            "failed_checks": [
                key
                for key, passed in dev_checks.items()
                if not passed
            ],
            "diagnostics": dev_diagnostics,
            "passed": development_passed,
        },
        "prior_validation": validation_result,
        "modifier_decisions": modifiers,
        "decision": decision,
        "historical_shadow_admission": historical_shadow_admission,
        "live_approved": False,
    }


def main():
    parser = argparse.ArgumentParser(
        description="Evaluate frozen unified A/B/C gates"
    )
    parser.add_argument("--development", required=True)
    parser.add_argument("--calendar")
    parser.add_argument("--validation")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    result = evaluate(
        read_json(args.development),
        calendar_report=(
            read_json(args.calendar)
            if args.calendar
            else None
        ),
        validation=(
            read_json(args.validation)
            if args.validation
            else None
        ),
    )
    write_json(args.output, result)
    print(json.dumps(result, indent=2))
    if not result["development"]["passed"]:
        raise SystemExit(2)
    if args.validation and not result["prior_validation"]["passed"]:
        raise SystemExit(3)


if __name__ == "__main__":
    main()
