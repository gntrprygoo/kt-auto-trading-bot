import argparse
import concurrent.futures
import json
import pathlib
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import derivatives_data as data


@dataclass(frozen=True)
class IngestTask:
    kind: str
    symbol: str
    key: str


@dataclass
class IngestResult:
    task: IngestTask
    source: object = None
    rows: object = None
    error: str = None


def read_json(path):
    with open(path, "r", encoding="utf-8-sig") as handle:
        return json.load(handle)


def write_json(path, value):
    output = pathlib.Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    with open(output, "w", encoding="utf-8") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2)


def parse_download(task):
    try:
        source = data.download_source(task.key)
        if task.kind == "metrics":
            rows = data.parse_metrics_zip(
                source.payload,
                task.symbol,
            )
        elif task.kind == "funding":
            rows = data.parse_funding_zip(
                source.payload,
                task.symbol,
            )
        elif task.kind == "premium":
            rows = data.parse_premium_zip(
                source.payload,
                task.symbol,
            )
        else:
            raise ValueError(f"unsupported_kind {task.kind}")
        if not rows:
            raise data.DataFormatError("source_contains_no_rows")
        return IngestResult(
            task=task,
            source=source,
            rows=rows,
        )
    except Exception as exc:
        return IngestResult(
            task=task,
            error=f"{type(exc).__name__}: {exc}",
        )


def build_tasks(symbols, start, end, as_of, kinds):
    tasks = []
    current_month = as_of.replace(day=1)
    requested_months = list(data.iter_months(start, end))
    requested_days = list(data.iter_dates(start, end))
    for symbol in symbols:
        if "metrics" in kinds:
            tasks.extend(
                IngestTask(
                    "metrics",
                    symbol,
                    data.metrics_key(symbol, day),
                )
                for day in requested_days
            )
        if "funding" in kinds:
            tasks.extend(
                IngestTask(
                    "funding",
                    symbol,
                    data.funding_monthly_key(symbol, month),
                )
                for month in requested_months
                if month < current_month
            )
        if "premium" in kinds:
            tasks.extend(
                IngestTask(
                    "premium",
                    symbol,
                    data.premium_monthly_key(symbol, month),
                )
                for month in requested_months
                if month < current_month
            )
            if end >= current_month:
                partial_start = max(start, current_month)
                tasks.extend(
                    IngestTask(
                        "premium",
                        symbol,
                        data.premium_daily_key(symbol, day),
                    )
                    for day in data.iter_dates(partial_start, end)
                )
    return sorted(
        tasks,
        key=lambda item: (item.kind, item.symbol, item.key),
    )


def store_result(store, result):
    if result.task.kind == "metrics":
        store.upsert_metrics(result.rows)
    elif result.task.kind == "funding":
        store.upsert_funding(result.rows)
    elif result.task.kind == "premium":
        store.upsert_premium(result.rows)
    else:
        raise ValueError(f"unsupported_kind {result.task.kind}")
    store.record_source(
        result.source.key,
        result.task.kind,
        result.task.symbol,
        result.source.payload,
        len(result.rows),
        etag=result.source.etag,
    )


def ingest_funding_current(
    store,
    symbols,
    start,
    end,
    as_of,
    workers,
):
    current_month = as_of.replace(day=1)
    if end < current_month:
        return {
            "required": False,
            "pairs": 0,
            "events": 0,
            "errors": [],
        }
    partial_start = max(start, current_month)
    start_ms = data.day_start_ms(partial_start)
    end_ms = data.day_start_ms(end + timedelta(days=1)) - 1

    def fetch(symbol):
        try:
            rows, payload = data.fetch_funding_api(
                symbol,
                start_ms,
                end_ms,
            )
            if not rows:
                raise data.DataFormatError("funding_api_no_rows")
            return symbol, rows, payload, None
        except Exception as exc:
            return (
                symbol,
                None,
                None,
                f"{type(exc).__name__}: {exc}",
            )

    events = 0
    errors = []
    with concurrent.futures.ThreadPoolExecutor(
        max_workers=workers
    ) as executor:
        for symbol, rows, payload, error in executor.map(fetch, symbols):
            if error:
                errors.append(f"{symbol}: {error}")
                continue
            store.ingest_funding_api(
                symbol,
                start_ms,
                end_ms,
                rows,
                payload,
            )
            events += len(rows)
    return {
        "required": True,
        "pairs": len(symbols),
        "events": events,
        "errors": errors,
    }


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Stream, aggregate, and cache official Binance USD-M "
            "derivatives data"
        )
    )
    parser.add_argument("--pairs-file", required=True)
    parser.add_argument("--start", required=True)
    parser.add_argument("--end", required=True)
    parser.add_argument("--db", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--max-pairs", type=int, default=30)
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--commit-every", type=int, default=100)
    parser.add_argument(
        "--kinds",
        default="metrics,funding,premium",
    )
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
    kinds = {
        item.strip().lower()
        for item in args.kinds.split(",")
        if item.strip()
    }
    unsupported = kinds - {"metrics", "funding", "premium"}
    if unsupported:
        raise SystemExit(f"unsupported kinds: {sorted(unsupported)}")
    pairs = read_json(args.pairs_file).get("pairs", [])[:args.max_pairs]
    tasks = build_tasks(pairs, start, end, as_of, kinds)

    summary = {
        "engine": "B7_DERIVATIVES_INGEST_V1",
        "period": {
            "requested_start": args.start,
            "requested_end": args.end,
            "archive_start_utc": start.isoformat(),
            "archive_end_utc": end.isoformat(),
            "as_of": as_of.isoformat(),
        },
        "pair_count": len(pairs),
        "workers": args.workers,
        "database": str(pathlib.Path(args.db).resolve()),
        "source_tasks": len(tasks),
        "skipped_cached": 0,
        "downloaded": 0,
        "downloaded_bytes": 0,
        "parsed_rows": 0,
        "errors": [],
    }

    pathlib.Path(args.db).parent.mkdir(parents=True, exist_ok=True)
    with data.DerivativesStore(args.db) as store:
        pending = []
        for task in tasks:
            if store.has_source(task.key):
                summary["skipped_cached"] += 1
            else:
                pending.append(task)
        print(
            f"sources total={len(tasks)} pending={len(pending)} "
            f"cached={summary['skipped_cached']}",
            flush=True,
        )

        completed_since_commit = 0
        with concurrent.futures.ThreadPoolExecutor(
            max_workers=args.workers
        ) as executor:
            for number, result in enumerate(
                executor.map(parse_download, pending),
                1,
            ):
                if result.error:
                    summary["errors"].append(
                        f"{result.task.key}: {result.error}"
                    )
                else:
                    store_result(store, result)
                    summary["downloaded"] += 1
                    summary["downloaded_bytes"] += len(
                        result.source.payload
                    )
                    summary["parsed_rows"] += len(result.rows)
                    completed_since_commit += 1
                if completed_since_commit >= args.commit_every:
                    store.connection.commit()
                    completed_since_commit = 0
                if number % 100 == 0 or number == len(pending):
                    print(
                        f"ingest {number}/{len(pending)} "
                        f"errors={len(summary['errors'])}",
                        flush=True,
                    )
        store.connection.commit()

        if "funding" in kinds:
            print("funding current-month API fallback", flush=True)
            summary["funding_current_api"] = ingest_funding_current(
                store,
                pairs,
                start,
                end,
                as_of,
                args.workers,
            )
        else:
            summary["funding_current_api"] = {
                "required": False,
                "pairs": 0,
                "events": 0,
                "errors": [],
            }
        summary["database_counts"] = store.counts()

    summary["ok"] = (
        not summary["errors"]
        and not summary["funding_current_api"]["errors"]
    )
    write_json(args.output, summary)
    print(json.dumps({
        "ok": summary["ok"],
        "downloaded": summary["downloaded"],
        "skipped_cached": summary["skipped_cached"],
        "downloaded_bytes": summary["downloaded_bytes"],
        "parsed_rows": summary["parsed_rows"],
        "database_counts": summary["database_counts"],
        "archive_errors": len(summary["errors"]),
        "funding_api_errors": len(
            summary["funding_current_api"]["errors"]
        ),
        "output": args.output,
    }, indent=2))
    if not summary["ok"]:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
