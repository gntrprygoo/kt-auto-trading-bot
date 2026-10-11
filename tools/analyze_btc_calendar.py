import argparse
import bisect
import json
import pathlib
import random
import statistics
from collections import defaultdict
from datetime import datetime, timedelta, timezone

import strategy_evidence_audit as audit


MS_HOUR = 60 * 60 * 1000
PHASES = ("D01_08", "D09_15", "D16_25", "D26_EOM")
EXPECTED_DIRECTION = {
    "D01_08": -1,
    "D09_15": 1,
    "D26_EOM": -1,
}


def write_json(path, value):
    output = pathlib.Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(value, handle, ensure_ascii=True, indent=2)
        handle.write("\n")


def next_month(value):
    if value.month == 12:
        return value.replace(
            year=value.year + 1,
            month=1,
            day=1,
        )
    return value.replace(month=value.month + 1, day=1)


def phase_bounds(year, month, utc_offset_hours):
    local_tz = timezone(timedelta(hours=utc_offset_hours))
    start = datetime(year, month, 1, tzinfo=local_tz)
    following = next_month(start)
    boundaries = (
        ("D01_08", start, start.replace(day=9)),
        ("D09_15", start.replace(day=9), start.replace(day=16)),
        ("D16_25", start.replace(day=16), start.replace(day=26)),
        ("D26_EOM", start.replace(day=26), following),
    )
    return {
        name: (
            int(first.astimezone(timezone.utc).timestamp() * 1000),
            int(last.astimezone(timezone.utc).timestamp() * 1000),
        )
        for name, first, last in boundaries
    }


def month_keys(start_ms, end_ms, utc_offset_hours):
    local_tz = timezone(timedelta(hours=utc_offset_hours))
    start = datetime.fromtimestamp(
        start_ms / 1000,
        timezone.utc,
    ).astimezone(local_tz)
    end = datetime.fromtimestamp(
        end_ms / 1000,
        timezone.utc,
    ).astimezone(local_tz)
    current = datetime(start.year, start.month, 1, tzinfo=local_tz)
    final = datetime(end.year, end.month, 1, tzinfo=local_tz)
    while current <= final:
        yield current.year, current.month
        current = next_month(current)


def extract_phase_returns(candles, utc_offset_hours):
    ordered = sorted(candles, key=lambda item: int(item["open_time"]))
    open_times = [int(item["open_time"]) for item in ordered]
    if not ordered:
        return []
    results = []
    for year, month in month_keys(
        open_times[0],
        int(ordered[-1]["close_time"]),
        utc_offset_hours,
    ):
        phase_rows = {}
        complete_month = True
        for phase, (start_ms, end_ms) in phase_bounds(
            year,
            month,
            utc_offset_hours,
        ).items():
            first = bisect.bisect_left(open_times, start_ms)
            last = bisect.bisect_left(open_times, end_ms)
            sample = ordered[first:last]
            expected = int((end_ms - start_ms) // MS_HOUR)
            complete = (
                len(sample) >= int(expected * 0.98)
                and sample
                and int(sample[0]["open_time"]) == start_ms
                and int(sample[-1]["close_time"]) >= end_ms - 1
            )
            if not complete:
                complete_month = False
                break
            phase_rows[phase] = {
                "phase": phase,
                "start_time": start_ms,
                "end_time": end_ms - 1,
                "bars": len(sample),
                "return": (
                    float(sample[-1]["close"])
                    / float(sample[0]["open"])
                    - 1.0
                ),
            }
        if not complete_month:
            continue
        prefix = (
            phase_rows["D01_08"]["return"]
            + phase_rows["D09_15"]["return"]
        )
        phase_three = phase_rows["D16_25"]["return"]
        continuation = (
            phase_three * (1.0 if prefix > 0 else -1.0)
            if prefix != 0
            else 0.0
        )
        for phase in PHASES:
            row = dict(phase_rows[phase])
            row.update({
                "month": f"{year:04d}-{month:02d}",
                "year": year,
                "utc_offset_hours": utc_offset_hours,
                "prefix_return": prefix,
                "continuation_signed_return": (
                    continuation if phase == "D16_25" else None
                ),
            })
            results.append(row)
    return results


def bootstrap_median_ci(values, samples=4000, seed=42):
    if not values:
        return [0.0, 0.0]
    generator = random.Random(seed)
    medians = []
    length = len(values)
    for _ in range(samples):
        resampled = [
            values[generator.randrange(length)]
            for _ in range(length)
        ]
        medians.append(statistics.median(resampled))
    medians.sort()
    low = medians[int(0.05 * (samples - 1))]
    high = medians[int(0.95 * (samples - 1))]
    return [low, high]


def summarize_values(values):
    if not values:
        return {
            "samples": 0,
            "mean_pct": 0.0,
            "median_pct": 0.0,
            "positive_pct": 0.0,
            "bootstrap_median_ci90_pct": [0.0, 0.0],
        }
    low, high = bootstrap_median_ci(values)
    return {
        "samples": len(values),
        "mean_pct": round(100.0 * statistics.mean(values), 4),
        "median_pct": round(100.0 * statistics.median(values), 4),
        "positive_pct": round(
            100.0 * sum(value > 0 for value in values) / len(values),
            2,
        ),
        "bootstrap_median_ci90_pct": [
            round(100.0 * low, 4),
            round(100.0 * high, 4),
        ],
    }


def summarize_phase(rows, phase):
    selected = [row for row in rows if row["phase"] == phase]
    values = [
        (
            float(row["continuation_signed_return"])
            if phase == "D16_25"
            else float(row["return"])
        )
        for row in selected
    ]
    result = summarize_values(values)
    by_year = {}
    for year in sorted({int(row["year"]) for row in selected}):
        year_values = [
            (
                float(row["continuation_signed_return"])
                if phase == "D16_25"
                else float(row["return"])
            )
            for row in selected
            if int(row["year"]) == year
        ]
        by_year[str(year)] = summarize_values(year_values)
    expected = 1 if phase == "D16_25" else EXPECTED_DIRECTION[phase]
    stable_years = sum(
        (
            summary["median_pct"] > 0
            if expected > 0
            else summary["median_pct"] < 0
        )
        for summary in by_year.values()
        if summary["samples"]
    )
    year_count = len(by_year)
    stability = stable_years / year_count if year_count else 0.0
    low, high = result["bootstrap_median_ci90_pct"]
    ci_directional = low > 0 if expected > 0 else high < 0
    median_directional = (
        result["median_pct"] > 0
        if expected > 0
        else result["median_pct"] < 0
    )
    result.update({
        "measure": (
            "continuation_signed_return"
            if phase == "D16_25"
            else "phase_return"
        ),
        "expected_direction": (
            "POSITIVE" if expected > 0 else "NEGATIVE"
        ),
        "year_stability_pct": round(100.0 * stability, 2),
        "by_year": by_year,
        "robust": (
            result["samples"] >= 48
            and median_directional
            and ci_directional
            and stability >= 0.60
        ),
    })
    return result


def build_report(candles, start, end):
    result = {
        "engine": "BTC_MONTHLY_PHASE_AUDIT_V1",
        "period": {"start": start, "end": end},
        "definitions": {
            "D01_08": "local day 1 00:00 through day 9 00:00",
            "D09_15": "local day 9 00:00 through day 16 00:00",
            "D16_25": "local day 16 00:00 through day 26 00:00",
            "D26_EOM": "local day 26 00:00 through next month day 1 00:00",
            "D16_25_measure": (
                "phase return signed by the direction of days 1-15; "
                "positive means continuation"
            ),
        },
        "timezones": {},
    }
    for label, offset in (("UTC", 0), ("WIB", 7)):
        rows = extract_phase_returns(candles, offset)
        phases = {
            phase: summarize_phase(rows, phase)
            for phase in PHASES
        }
        recent_months = sorted({row["month"] for row in rows})[-24:]
        recent_rows = [
            row for row in rows if row["month"] in recent_months
        ]
        result["timezones"][label] = {
            "utc_offset_hours": offset,
            "complete_months": len({row["month"] for row in rows}),
            "phases": phases,
            "recent_24_months": {
                phase: summarize_phase(recent_rows, phase)
                for phase in PHASES
            },
            "approved_soft_prior_phases": [
                phase
                for phase, summary in phases.items()
                if summary["robust"]
            ],
            "records": rows,
        }
    result["decision"] = {
        "calendar_is_entry_trigger": False,
        "wib_soft_prior_phases": result["timezones"]["WIB"][
            "approved_soft_prior_phases"
        ],
        "rule": (
            "Only individually robust WIB phases may alter risk. "
            "Price structure remains the entry trigger."
        ),
    }
    return result


def main():
    parser = argparse.ArgumentParser(
        description="Audit the proposed BTC monthly date phases"
    )
    parser.add_argument("--start", default="2020-01-01T00:00:00+00:00")
    parser.add_argument("--end", required=True)
    parser.add_argument("--cache-dir", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    start_ms = audit.parse_timestamp(args.start)
    end_ms = audit.parse_timestamp(args.end)
    market = audit.MarketData(args.cache_dir)
    candles = market.klines(
        "BTCUSDT",
        "1h",
        start_ms,
        end_ms,
    )
    report = build_report(candles, args.start, args.end)
    write_json(args.output, report)
    concise = {
        timezone_name: {
            phase: {
                "samples": summary["samples"],
                "median_pct": summary["median_pct"],
                "ci90_pct": summary["bootstrap_median_ci90_pct"],
                "year_stability_pct": summary["year_stability_pct"],
                "robust": summary["robust"],
            }
            for phase, summary in timezone_report["phases"].items()
        }
        for timezone_name, timezone_report
        in report["timezones"].items()
    }
    print(json.dumps({
        "results": concise,
        "decision": report["decision"],
        "output": args.output,
    }, indent=2))


if __name__ == "__main__":
    main()
