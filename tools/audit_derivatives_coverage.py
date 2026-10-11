import argparse
import concurrent.futures
import json
import pathlib
import re
from datetime import date, timedelta, timezone, datetime

import derivatives_data as data


def read_json(path):
    with open(path, "r", encoding="utf-8-sig") as handle:
        return json.load(handle)


def write_json(path, value):
    output = pathlib.Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    with open(output, "w", encoding="utf-8") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2)


def previous_day(value):
    return data.parse_date(value) - timedelta(days=1)


def previous_month(value):
    parsed = data.parse_date(value).replace(day=1)
    return (parsed - timedelta(days=1)).replace(day=1)


def is_current_month(value, as_of):
    parsed = data.parse_date(value)
    current = data.parse_date(as_of)
    return (
        parsed.year == current.year
        and parsed.month == current.month
    )


def list_dated_archives(
    prefix,
    filename_pattern,
    start,
    end,
    start_after,
):
    pattern = re.compile(filename_pattern)
    present = {}
    for item in data.list_s3_objects(
        prefix,
        start_after=start_after,
    ):
        if not item.key.endswith(".zip"):
            continue
        match = pattern.search(item.key)
        if not match:
            continue
        value = date.fromisoformat(match.group(1))
        if value > end:
            break
        if value >= start:
            present[value] = item
    return present


def list_monthly_archives(
    prefix,
    filename_pattern,
    start,
    end,
    start_after,
):
    pattern = re.compile(filename_pattern)
    present = {}
    for item in data.list_s3_objects(
        prefix,
        start_after=start_after,
    ):
        if not item.key.endswith(".zip"):
            continue
        match = pattern.search(item.key)
        if not match:
            continue
        value = date.fromisoformat(f"{match.group(1)}-01")
        if value > end:
            break
        if value >= start:
            present[value] = item
    return present


def metric_coverage(symbol, start, end):
    prefix = f"data/futures/um/daily/metrics/{symbol}/"
    before = previous_day(start).isoformat()
    start_after = (
        f"{prefix}{symbol}-metrics-{before}.zip.CHECKSUM"
    )
    present = list_dated_archives(
        prefix,
        rf"{re.escape(symbol)}-metrics-(\d{{4}}-\d{{2}}-\d{{2}})\.zip$",
        start,
        end,
        start_after,
    )
    expected = list(data.iter_dates(start, end))
    missing = [value.isoformat() for value in expected if value not in present]
    first_present = min(present) if present else None
    unavailable_before_first = [
        value
        for value in expected
        if value not in present
        and first_present is not None
        and value < first_present
    ]
    missing_after_first = [
        value
        for value in expected
        if value not in present
        and (
            first_present is None
            or value >= first_present
        )
    ]
    return {
        "expected_files": len(expected),
        "present_files": len(present),
        "missing_count": len(missing),
        "missing": missing,
        "unavailable_before_first_count": len(
            unavailable_before_first
        ),
        "missing_after_first_count": len(missing_after_first),
        "missing_after_first": [
            value.isoformat() for value in missing_after_first
        ],
        "compressed_bytes": sum(item.size for item in present.values()),
        "first_present": (
            first_present.isoformat() if first_present else None
        ),
        "last_present": max(present).isoformat() if present else None,
    }


def monthly_coverage(symbol, kind, start, end, as_of):
    start_month = start.replace(day=1)
    end_month = end.replace(day=1)
    current_month = as_of.replace(day=1)
    archive_end = min(end_month, current_month - timedelta(days=1))
    archive_end = archive_end.replace(day=1)
    expected = [
        value
        for value in data.iter_months(start_month, archive_end)
        if value < current_month
    ]

    if kind == "funding":
        prefix = (
            "data/futures/um/monthly/fundingRate/"
            f"{symbol}/"
        )
        previous = previous_month(start_month)
        start_after = (
            f"{prefix}{symbol}-fundingRate-"
            f"{data.month_id(previous)}.zip.CHECKSUM"
        )
        pattern = (
            rf"{re.escape(symbol)}-fundingRate-"
            r"(\d{4}-\d{2})\.zip$"
        )
    elif kind == "premium":
        prefix = (
            "data/futures/um/monthly/premiumIndexKlines/"
            f"{symbol}/1h/"
        )
        previous = previous_month(start_month)
        start_after = (
            f"{prefix}{symbol}-1h-"
            f"{data.month_id(previous)}.zip.CHECKSUM"
        )
        pattern = (
            rf"{re.escape(symbol)}-1h-"
            r"(\d{4}-\d{2})\.zip$"
        )
    else:
        raise ValueError(f"unsupported_monthly_kind {kind}")

    present = list_monthly_archives(
        prefix,
        pattern,
        start_month,
        archive_end,
        start_after,
    )
    missing = [data.month_id(value) for value in expected if value not in present]
    first_present = min(present) if present else None
    unavailable_before_first = [
        value
        for value in expected
        if value not in present
        and first_present is not None
        and value < first_present
    ]
    missing_after_first = [
        value
        for value in expected
        if value not in present
        and (
            first_present is None
            or value >= first_present
        )
    ]
    return {
        "expected_files": len(expected),
        "present_files": len(present),
        "missing_count": len(missing),
        "missing": missing,
        "unavailable_before_first_count": len(
            unavailable_before_first
        ),
        "missing_after_first_count": len(missing_after_first),
        "missing_after_first": [
            data.month_id(value) for value in missing_after_first
        ],
        "compressed_bytes": sum(item.size for item in present.values()),
        "first_present": (
            data.month_id(first_present) if first_present else None
        ),
        "last_present": data.month_id(max(present)) if present else None,
    }


def premium_current_month_coverage(symbol, start, end, as_of):
    if not is_current_month(end, as_of):
        return {
            "required": False,
            "expected_files": 0,
            "present_files": 0,
            "missing_count": 0,
            "missing": [],
            "unavailable_before_first_count": 0,
            "missing_after_first_count": 0,
            "missing_after_first": [],
            "compressed_bytes": 0,
        }
    current_month = as_of.replace(day=1)
    partial_start = max(start, current_month)
    prefix = (
        "data/futures/um/daily/premiumIndexKlines/"
        f"{symbol}/1h/"
    )
    before = previous_day(partial_start).isoformat()
    start_after = (
        f"{prefix}{symbol}-1h-{before}.zip.CHECKSUM"
    )
    present = list_dated_archives(
        prefix,
        rf"{re.escape(symbol)}-1h-(\d{{4}}-\d{{2}}-\d{{2}})\.zip$",
        partial_start,
        end,
        start_after,
    )
    expected = list(data.iter_dates(partial_start, end))
    missing = [value.isoformat() for value in expected if value not in present]
    first_present = min(present) if present else None
    unavailable_before_first = [
        value
        for value in expected
        if value not in present
        and first_present is not None
        and value < first_present
    ]
    missing_after_first = [
        value
        for value in expected
        if value not in present
        and (
            first_present is None
            or value >= first_present
        )
    ]
    return {
        "required": True,
        "expected_files": len(expected),
        "present_files": len(present),
        "missing_count": len(missing),
        "missing": missing,
        "unavailable_before_first_count": len(
            unavailable_before_first
        ),
        "missing_after_first_count": len(missing_after_first),
        "missing_after_first": [
            value.isoformat() for value in missing_after_first
        ],
        "compressed_bytes": sum(item.size for item in present.values()),
        "first_present": (
            first_present.isoformat() if first_present else None
        ),
        "last_present": max(present).isoformat() if present else None,
    }


def funding_current_month_coverage(symbol, start, end, as_of):
    if not is_current_month(end, as_of):
        return {
            "required": False,
            "event_count": 0,
            "first_event": None,
            "last_event": None,
            "error": None,
        }
    current_month = as_of.replace(day=1)
    partial_start = max(start, current_month)
    start_ms = data.day_start_ms(partial_start)
    end_ms = data.day_start_ms(end + timedelta(days=1)) - 1
    try:
        rows, _payload = data.fetch_funding_api(
            symbol,
            start_ms,
            end_ms,
        )
        return {
            "required": True,
            "event_count": len(rows),
            "first_event": rows[0]["event_time"] if rows else None,
            "last_event": rows[-1]["event_time"] if rows else None,
            "error": None,
        }
    except Exception as exc:
        return {
            "required": True,
            "event_count": 0,
            "first_event": None,
            "last_event": None,
            "error": f"{type(exc).__name__}: {exc}",
        }


def pair_coverage(symbol, start, end, as_of):
    return {
        "metrics_daily": metric_coverage(symbol, start, end),
        "funding_monthly": monthly_coverage(
            symbol,
            "funding",
            start,
            end,
            as_of,
        ),
        "funding_current_api": funding_current_month_coverage(
            symbol,
            start,
            end,
            as_of,
        ),
        "premium_monthly_1h": monthly_coverage(
            symbol,
            "premium",
            start,
            end,
            as_of,
        ),
        "premium_current_daily_1h": premium_current_month_coverage(
            symbol,
            start,
            end,
            as_of,
        ),
    }


def summarize(pairs):
    fields = (
        "metrics_daily",
        "funding_monthly",
        "premium_monthly_1h",
        "premium_current_daily_1h",
    )
    summary = {}
    for field in fields:
        reports = [value[field] for value in pairs.values()]
        summary[field] = {
            "expected_files": sum(
                item.get("expected_files", 0) for item in reports
            ),
            "present_files": sum(
                item.get("present_files", 0) for item in reports
            ),
            "missing_count": sum(
                item.get("missing_count", 0) for item in reports
            ),
            "unavailable_before_first_count": sum(
                item.get("unavailable_before_first_count", 0)
                for item in reports
            ),
            "missing_after_first_count": sum(
                item.get("missing_after_first_count", 0)
                for item in reports
            ),
            "compressed_bytes": sum(
                item.get("compressed_bytes", 0) for item in reports
            ),
            "pairs_complete": sum(
                item.get("missing_count", 0) == 0
                for item in reports
            ),
            "pairs_complete_after_first": sum(
                item.get("missing_after_first_count", 0) == 0
                for item in reports
            ),
        }
    funding_api = [
        value["funding_current_api"] for value in pairs.values()
    ]
    summary["funding_current_api"] = {
        "required_pairs": sum(item["required"] for item in funding_api),
        "successful_pairs": sum(
            item["required"]
            and not item["error"]
            and item["event_count"] > 0
            for item in funding_api
        ),
        "event_count": sum(item["event_count"] for item in funding_api),
        "errors": [
            item["error"] for item in funding_api if item["error"]
        ],
    }
    summary["all_archive_files_present"] = all(
        summary[field]["missing_count"] == 0
        for field in fields
    )
    summary["all_archives_complete_after_first"] = all(
        summary[field]["missing_after_first_count"] == 0
        for field in fields
    )
    summary["funding_api_healthy"] = (
        summary["funding_current_api"]["required_pairs"]
        == summary["funding_current_api"]["successful_pairs"]
    )
    return summary


def main():
    parser = argparse.ArgumentParser(
        description="Audit Binance USD-M derivatives archive coverage"
    )
    parser.add_argument("--pairs-file", required=True)
    parser.add_argument("--start", required=True)
    parser.add_argument("--end", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--max-pairs", type=int, default=30)
    parser.add_argument("--workers", type=int, default=6)
    parser.add_argument(
        "--as-of",
        default=datetime.now(timezone.utc).date().isoformat(),
    )
    args = parser.parse_args()

    start = data.parse_date(args.start)
    end = data.parse_date(args.end)
    as_of = data.parse_date(args.as_of)
    if end > as_of:
        raise SystemExit("end date cannot be later than as-of date")
    pairs = read_json(args.pairs_file).get("pairs", [])[:args.max_pairs]

    def inspect(symbol):
        return symbol, pair_coverage(
            symbol,
            start,
            end,
            as_of,
        )

    reports = {}
    with concurrent.futures.ThreadPoolExecutor(
        max_workers=args.workers
    ) as executor:
        for number, (symbol, report) in enumerate(
            executor.map(inspect, pairs),
            1,
        ):
            reports[symbol] = report
            print(
                f"coverage {number}/{len(pairs)} {symbol}",
                flush=True,
            )

    result = {
        "engine": "B7_DERIVATIVES_DATA_COVERAGE_V1",
        "source": {
            "archive": data.ARCHIVE_BASE,
            "listing": data.S3_LIST_BASE,
            "funding_api": (
                f"{data.FUTURES_API_BASE}/fapi/v1/fundingRate"
            ),
        },
        "period": {
            "requested_start": args.start,
            "requested_end": args.end,
            "archive_start_utc": start.isoformat(),
            "archive_end_utc": end.isoformat(),
            "as_of": as_of.isoformat(),
        },
        "pair_count": len(pairs),
        "pairs": reports,
        "summary": summarize(reports),
    }
    write_json(args.output, result)
    print(json.dumps(result["summary"], indent=2))
    print(f"output={args.output}")


if __name__ == "__main__":
    main()
