import argparse
import json
import pathlib
import statistics
from collections import Counter, defaultdict
from datetime import datetime, timezone

import research_strategy_bc_v2 as common
import strategy_evidence_audit as audit


def read_json(path):
    with pathlib.Path(path).open("r", encoding="utf-8-sig") as handle:
        return json.load(handle)


def write_json(path, value):
    output = pathlib.Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(value, handle, ensure_ascii=True, indent=2)
        handle.write("\n")


def _session(timestamp_ms):
    hour = datetime.fromtimestamp(
        timestamp_ms / 1000,
        timezone.utc,
    ).hour
    if 0 <= hour < 7:
        return "ASIA"
    if 7 <= hour < 13:
        return "EUROPE"
    if 13 <= hour < 21:
        return "US"
    return "LATE_US"


def _bucket(value, bounds, labels):
    numeric = float(value)
    for bound, label in zip(bounds, labels):
        if numeric <= bound:
            return label
    return labels[-1]


def decorate(record):
    value = dict(record)
    macro = str(record.get("macro_bias_context", "NEUTRAL"))
    side = str(record.get("side", ""))
    aligned = (
        (side == "LONG" and macro == "BULL")
        or (side == "SHORT" and macro == "BEAR")
    )
    opposed = (
        (side == "LONG" and macro == "BEAR")
        or (side == "SHORT" and macro == "BULL")
    )
    value["macro_relation"] = (
        "ALIGNED"
        if aligned
        else "OPPOSED"
        if opposed
        else "NEUTRAL"
    )
    value["source_has_daily"] = (
        "YES"
        if "1D" in str(record.get("level_source_tf", ""))
        else "NO"
    )
    value["session_utc"] = _session(
        int(record["signal_time"])
    )
    value["test_count_bucket"] = _bucket(
        record.get("level_test_count", 0),
        (0, 1, 2, float("inf")),
        ("0", "1", "2", "3+"),
    )
    value["touch_bucket"] = _bucket(
        record.get("level_touches", 0),
        (2, 3, 4, float("inf")),
        ("<=2", "3", "4", "5+"),
    )
    value["risk_bucket"] = _bucket(
        100.0 * float(record.get("risk_pct", 0.0)),
        (0.75, 1.25, 2.0, float("inf")),
        ("<=0.75%", "0.75-1.25%", "1.25-2.00%", ">2.00%"),
    )
    value["planned_rr_bucket"] = _bucket(
        record.get("planned_rr", 0.0),
        (1.5, 2.0, 3.0, float("inf")),
        ("<=1.5R", "1.5-2R", "2-3R", ">3R"),
    )
    value["efficiency_bucket"] = _bucket(
        record.get("structure_efficiency_4h", 1.0),
        (0.15, 0.25, 0.32, float("inf")),
        ("<=0.15", "0.15-0.25", "0.25-0.32", ">0.32"),
    )
    value["containment_bucket"] = _bucket(
        record.get("structure_containment_ratio", 0.0),
        (0.80, 0.90, 0.96, float("inf")),
        ("<=0.80", "0.80-0.90", "0.90-0.96", ">0.96"),
    )
    value["range_width_bucket"] = _bucket(
        record.get("structure_range_width_atr", 0.0),
        (6.0, 10.0, 14.0, float("inf")),
        ("<=6", "6-10", "10-14", ">14"),
    )
    value["level_score_bucket"] = _bucket(
        record.get("level_score", 0.0),
        (6.0, 7.0, 8.0, float("inf")),
        ("<=6", "6-7", "7-8", ">8"),
    )
    value["level_volume_bucket"] = _bucket(
        record.get("level_volume_ratio", 0.0),
        (1.0, 1.25, 1.50, float("inf")),
        ("<=1.00", "1.00-1.25", "1.25-1.50", ">1.50"),
    )
    return value


def group_summary(records, fields, result_key):
    grouped = defaultdict(list)
    for record in records:
        key = " | ".join(str(record.get(field)) for field in fields)
        grouped[key].append(record)
    result = {}
    for key, rows in grouped.items():
        summary = common.summarize(rows, result_key)
        summary["median_R"] = round(
            statistics.median(
                float(item[result_key]) for item in rows
            ),
            4,
        )
        summary["outcomes"] = dict(sorted(Counter(
            item.get("outcome_live", "n/a") for item in rows
        ).items()))
        result[key] = summary
    return dict(sorted(
        result.items(),
        key=lambda item: (
            -int(item[1]["trades"]),
            item[0],
        ),
    ))


def _filter_summary(records, predicate, result_key):
    selected = [item for item in records if predicate(item)]
    return common.summarize(selected, result_key)


def diagnostic_filters(records, result_key):
    predicates = {
        "ALL": lambda item: True,
        "MACRO_NOT_OPPOSED": (
            lambda item: item["macro_relation"] != "OPPOSED"
        ),
        "MACRO_ALIGNED_ONLY": (
            lambda item: item["macro_relation"] == "ALIGNED"
        ),
        "DAILY_SOURCE": (
            lambda item: item["source_has_daily"] == "YES"
        ),
        "DAILY_CONFLUENCE_ONLY": (
            lambda item: item.get("level_source_tf") == "1D+4H"
        ),
        "LEVEL_TEST_COUNT_LE_1": (
            lambda item: int(item.get("level_test_count", 99)) <= 1
        ),
        "NOT_OPPOSED_AND_DAILY": (
            lambda item: (
                item["macro_relation"] != "OPPOSED"
                and item["source_has_daily"] == "YES"
            )
        ),
        "NOT_OPPOSED_AND_CONFLUENT": (
            lambda item: (
                item["macro_relation"] != "OPPOSED"
                and item.get("level_source_tf") == "1D+4H"
            )
        ),
    }
    return {
        name: _filter_summary(records, predicate, result_key)
        for name, predicate in predicates.items()
    }


def main():
    parser = argparse.ArgumentParser(
        description="Descriptive failure attribution for BTC ABC v2"
    )
    parser.add_argument("--replay", required=True)
    parser.add_argument("--start", required=True)
    parser.add_argument("--end", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--variant")
    parser.add_argument("--path")
    args = parser.parse_args()

    replay = read_json(args.replay)
    source = (
        replay.get("variants", {}).get(args.variant)
        if args.variant
        else replay
    )
    if source is None:
        raise SystemExit(f"Variant not found: {args.variant}")
    start_ms = audit.parse_timestamp(args.start)
    end_ms = audit.parse_timestamp(args.end)
    records = [
        decorate(item)
        for item in source.get("records", [])
        if start_ms <= int(item["signal_time"]) <= end_ms
        and (
            args.path is None
            or item.get("path") == args.path
        )
    ]
    dimensions = (
        ("path",),
        ("side",),
        ("path", "side"),
        ("macro_relation",),
        ("path", "macro_relation"),
        ("level_source_tf",),
        ("level_freshness",),
        ("test_count_bucket",),
        ("touch_bucket",),
        ("risk_bucket",),
        ("planned_rr_bucket",),
        ("efficiency_bucket",),
        ("containment_bucket",),
        ("range_width_bucket",),
        ("level_score_bucket",),
        ("level_volume_bucket",),
        ("session_utc",),
        ("calendar_phase_context",),
        ("transition",),
    )
    result = {
        "engine": replay.get("engine"),
        "variant": args.variant,
        "path": args.path,
        "period": {"start": args.start, "end": args.end},
        "purpose": (
            "calibration-only descriptive attribution; "
            "not a promotion test"
        ),
        "records": len(records),
        "baseline": common.summarize(records, "net_R_live"),
        "stress": common.summarize(
            records,
            "net_R_live_cost_0_20",
        ),
        "groups": {
            "+".join(fields): group_summary(
                records,
                fields,
                "net_R_live",
            )
            for fields in dimensions
        },
        "diagnostic_filters": diagnostic_filters(
            records,
            "net_R_live",
        ),
        "diagnostic_filters_stress": diagnostic_filters(
            records,
            "net_R_live_cost_0_20",
        ),
    }
    write_json(args.output, result)
    print(json.dumps({
        "period": result["period"],
        "records": len(records),
        "baseline": result["baseline"],
        "filters": result["diagnostic_filters"],
        "output": str(pathlib.Path(args.output).resolve()),
    }, indent=2))


if __name__ == "__main__":
    main()
