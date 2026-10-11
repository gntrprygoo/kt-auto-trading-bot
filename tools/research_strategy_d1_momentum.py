import argparse
import json
import pathlib
import statistics
from datetime import datetime, timezone

import research_strategy_bc_v2 as common
import strategy_evidence_audit as audit
from build_btc_structure_review import read_json, write_json
from strategy_d_momentum_engine import D1, parameters_dict, simulate


DEV_END = audit.parse_timestamp("2022-12-31T23:59:59Z")
HOLDOUT_START = audit.parse_timestamp("2023-01-01T00:00:00Z")


def merge_candles(paths):
    rows = {}
    for path in paths:
        for candle in read_json(path):
            rows[int(candle["open_time"])] = candle
    return [rows[key] for key in sorted(rows)]


def pf_at_least(summary, threshold):
    value = summary["profit_factor"]
    return (
        summary["trades"] > 0
        and (value is None or value >= threshold)
    )


def period_records(records, start_ms, end_ms):
    return [
        record
        for record in records
        if start_ms <= int(record["signal_time"]) <= end_ms
    ]


def summaries(records):
    return {
        "baseline": common.summarize(records, "net_R"),
        "stress": common.summarize(records, "stress_net_R"),
    }


def robustness(records, result_key="stress_net_R"):
    ordered = sorted(
        records,
        key=lambda row: int(row["signal_time"]),
    )
    values = [float(row[result_key]) for row in ordered]
    if not values:
        return {
            "trades": 0,
            "median_R": None,
            "mean_95pct_ci": None,
            "positive_years": 0,
            "nonempty_years": 0,
            "top_concentration": {},
            "years": {},
        }
    average = statistics.mean(values)
    deviation = (
        statistics.stdev(values)
        if len(values) > 1 else 0.0
    )
    standard_error = deviation / (len(values) ** 0.5)
    sorted_values = sorted(values, reverse=True)
    total = sum(values)
    concentration = {}
    for count in (1, 5, 10):
        selected = sum(sorted_values[:count])
        concentration[f"top_{count}"] = {
            "R": round(selected, 3),
            "share_of_total": (
                round(selected / total, 4)
                if total else None
            ),
            "R_without": round(total - selected, 3),
        }
    years = {}
    for year in range(2019, 2027):
        year_rows = [
            row
            for row in ordered
            if datetime.fromtimestamp(
                int(row["signal_time"]) / 1000,
                timezone.utc,
            ).year == year
        ]
        if year_rows:
            years[str(year)] = common.summarize(
                year_rows,
                result_key,
            )
    return {
        "trades": len(values),
        "median_R": round(statistics.median(values), 4),
        "mean_R": round(average, 4),
        "std_R": round(deviation, 4),
        "mean_95pct_ci": {
            "low": round(
                average - 1.96 * standard_error,
                4,
            ),
            "high": round(
                average + 1.96 * standard_error,
                4,
            ),
        },
        "positive_years": sum(
            item["total_net_R"] > 0
            for item in years.values()
        ),
        "nonempty_years": len(years),
        "top_concentration": concentration,
        "years": years,
    }


def side_gate(full, development, holdout):
    checks = {
        "minimum_full_trades": (
            full["baseline"]["trades"] >= 12
        ),
        "minimum_development_trades": (
            development["baseline"]["trades"] >= 4
        ),
        "minimum_holdout_trades": (
            holdout["baseline"]["trades"] >= 4
        ),
        "positive_full_baseline": (
            full["baseline"]["total_net_R"] > 0
        ),
        "full_baseline_pf": pf_at_least(
            full["baseline"],
            1.15,
        ),
        "positive_full_stress": (
            full["stress"]["total_net_R"] > 0
        ),
        "full_stress_pf": pf_at_least(
            full["stress"],
            1.05,
        ),
        "positive_development_stress": (
            development["stress"]["total_net_R"] > 0
        ),
        "positive_holdout_stress": (
            holdout["stress"]["total_net_R"] > 0
        ),
    }
    return {
        "checks": checks,
        "passed": all(checks.values()),
    }


def full_gate(full, development, holdout):
    checks = {
        "minimum_trades": full["baseline"]["trades"] >= 24,
        "positive_baseline": (
            full["baseline"]["total_net_R"] > 0
        ),
        "baseline_pf": pf_at_least(
            full["baseline"],
            1.15,
        ),
        "positive_stress": (
            full["stress"]["total_net_R"] > 0
        ),
        "stress_pf": pf_at_least(
            full["stress"],
            1.05,
        ),
        "max_drawdown": (
            full["baseline"]["max_drawdown_R"] <= 12.0
        ),
        "positive_development_stress": (
            development["stress"]["total_net_R"] > 0
        ),
        "positive_holdout_stress": (
            holdout["stress"]["total_net_R"] > 0
        ),
    }
    return {
        "checks": checks,
        "passed": all(checks.values()),
    }


def build_report(
    combined_records,
    side_runs,
    diagnostics,
    start_ms,
    end_ms,
    sources,
):
    development_rows = period_records(
        combined_records,
        start_ms,
        min(end_ms, DEV_END),
    )
    holdout_rows = period_records(
        combined_records,
        max(start_ms, HOLDOUT_START),
        end_ms,
    )
    full = summaries(combined_records)
    development = summaries(development_rows)
    holdout = summaries(holdout_rows)
    sides = {}
    admitted_sides = []
    for side in ("LONG", "SHORT"):
        side_rows = side_runs[side]["records"]
        side_development = period_records(
            side_rows,
            start_ms,
            min(end_ms, DEV_END),
        )
        side_holdout = period_records(
            side_rows,
            max(start_ms, HOLDOUT_START),
            end_ms,
        )
        side_full_summary = summaries(side_rows)
        side_dev_summary = summaries(side_development)
        side_holdout_summary = summaries(side_holdout)
        gate = side_gate(
            side_full_summary,
            side_dev_summary,
            side_holdout_summary,
        )
        if gate["passed"]:
            admitted_sides.append(side)
        sides[side] = {
            "full": side_full_summary,
            "development": side_dev_summary,
            "holdout": side_holdout_summary,
            "gate": gate,
            "diagnostics": side_runs[side]["diagnostics"],
            "robustness": robustness(side_rows),
        }
    gate = full_gate(full, development, holdout)
    if gate["passed"]:
        decision = "FORWARD_SHADOW_CANDIDATE_FULL"
    elif admitted_sides:
        decision = (
            "FORWARD_SHADOW_CANDIDATE_"
            + "_".join(admitted_sides)
        )
    else:
        decision = "REJECT_NO_ROBUST_EDGE"
    return {
        "engine": D1.name,
        "status": "RESEARCH_ONLY",
        "decision": decision,
        "production_changed": False,
        "symbol": "BTCUSDT",
        "period": {
            "start": datetime.fromtimestamp(
                start_ms / 1000,
                timezone.utc,
            ).isoformat(),
            "end": datetime.fromtimestamp(
                end_ms / 1000,
                timezone.utc,
            ).isoformat(),
        },
        "split": {
            "development_end": "2022-12-31T23:59:59Z",
            "holdout_start": "2023-01-01T00:00:00Z",
        },
        "data_source": {
            "candles_4h": [
                str(pathlib.Path(path).resolve())
                for path in sources
            ],
        },
        "parameters": parameters_dict(),
        "full": full,
        "development": development,
        "holdout": holdout,
        "sides": sides,
        "full_gate": gate,
        "admitted_sides": admitted_sides,
        "yearly": {
            str(year): summaries([
                record
                for record in combined_records
                if datetime.fromtimestamp(
                    int(record["signal_time"]) / 1000,
                    timezone.utc,
                ).year == year
            ])
            for year in range(2019, 2027)
        },
        "diagnostics": diagnostics,
        "records": combined_records,
        "side_records": {
            side: value["records"]
            for side, value in side_runs.items()
        },
    }


def main():
    parser = argparse.ArgumentParser(
        description="Frozen BTC Strategy D1 time-series momentum"
    )
    parser.add_argument("--start", required=True)
    parser.add_argument("--end", required=True)
    parser.add_argument("--candles-4h", action="append", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    start_ms = audit.parse_timestamp(args.start)
    end_ms = audit.parse_timestamp(args.end)
    candles = merge_candles(args.candles_4h)
    records, diagnostics = simulate(
        candles,
        start_ms,
        end_ms,
        D1,
    )
    side_runs = {}
    for side in ("LONG", "SHORT"):
        side_records, side_diagnostics = simulate(
            candles,
            start_ms,
            end_ms,
            D1,
            allowed_sides=(side,),
        )
        side_runs[side] = {
            "records": side_records,
            "diagnostics": side_diagnostics,
        }
    report = build_report(
        records,
        side_runs,
        diagnostics,
        start_ms,
        end_ms,
        args.candles_4h,
    )
    write_json(args.output, report)
    print(json.dumps({
        "engine": report["engine"],
        "decision": report["decision"],
        "full": report["full"],
        "sides": {
            side: {
                "full": value["full"],
                "gate": value["gate"],
            }
            for side, value in report["sides"].items()
        },
        "output": str(pathlib.Path(args.output).resolve()),
    }, indent=2))


if __name__ == "__main__":
    main()
