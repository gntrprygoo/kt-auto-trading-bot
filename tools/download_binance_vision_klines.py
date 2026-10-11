#!/usr/bin/env python3
"""Download and verify official Binance Vision USD-M monthly kline archives."""

from __future__ import annotations

import argparse
import csv
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
import hashlib
from io import BytesIO, TextIOWrapper
import json
from pathlib import Path
import urllib.error
import urllib.request
import zipfile


BASE_URL = "https://data.binance.vision/data/futures/um/monthly/klines"
USER_AGENT = "KT-Strategy-Research/1.0"


def month_range(start: str, end: str) -> list[str]:
    current = datetime.strptime(start, "%Y-%m")
    final = datetime.strptime(end, "%Y-%m")
    if current > final:
        raise ValueError("start month is after end month")
    output = []
    while current <= final:
        output.append(current.strftime("%Y-%m"))
        year = current.year + (1 if current.month == 12 else 0)
        month = 1 if current.month == 12 else current.month + 1
        current = current.replace(year=year, month=month)
    return output


def download_bytes(url: str, timeout: int = 60) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read()


def parse_archive(content: bytes) -> list[dict]:
    rows = []
    with zipfile.ZipFile(BytesIO(content)) as archive:
        names = [name for name in archive.namelist() if name.lower().endswith(".csv")]
        if len(names) != 1:
            raise ValueError(f"expected one CSV in archive, found {len(names)}")
        with archive.open(names[0]) as raw:
            text = TextIOWrapper(raw, encoding="utf-8-sig", newline="")
            for columns in csv.reader(text):
                if not columns or not columns[0].strip().isdigit():
                    continue
                if len(columns) < 11:
                    raise ValueError(f"unexpected Binance kline column count: {len(columns)}")
                rows.append({
                    "open_time": int(columns[0]),
                    "open": float(columns[1]),
                    "high": float(columns[2]),
                    "low": float(columns[3]),
                    "close": float(columns[4]),
                    "volume": float(columns[5]),
                    "close_time": int(columns[6]),
                    "quote_volume": float(columns[7]),
                    "taker_buy": float(columns[9]),
                    "taker_sell": float(columns[5]) - float(columns[9]),
                })
    return rows


def download_month(symbol: str, interval: str, month: str) -> tuple[str, str, str, list[dict]]:
    filename = f"{symbol}-{interval}-{month}.zip"
    url = f"{BASE_URL}/{symbol}/{interval}/{filename}"
    checksum_url = f"{url}.CHECKSUM"
    try:
        expected = download_bytes(checksum_url).decode("ascii").strip().split()[0].lower()
        content = download_bytes(url)
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"Binance Vision returned HTTP {exc.code} for {url}") from exc
    actual = hashlib.sha256(content).hexdigest()
    if actual != expected:
        raise ValueError(f"checksum mismatch for {filename}: {actual} != {expected}")
    return month, url, actual, parse_archive(content)


def download_symbol(
    symbol: str, interval: str, months: list[str], workers: int
) -> tuple[list[dict], list[dict]]:
    deduped = {}
    manifest = []
    completed = 0
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {
            executor.submit(download_month, symbol, interval, month): month
            for month in months
        }
        for future in as_completed(futures):
            month, url, actual, rows = future.result()
            completed += 1
            for row in rows:
                deduped[int(row["open_time"])] = row
            manifest.append({
                "month": month,
                "url": url,
                "sha256": actual,
                "rows": len(rows),
            })
            print(
                f"[{symbol}] {completed}/{len(months)} {month}: {len(rows)} rows verified",
                flush=True,
            )
    manifest.sort(key=lambda item: item["month"])
    ordered = [deduped[key] for key in sorted(deduped)]
    return ordered, manifest


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--symbols", nargs="+", default=["BTCUSDT", "ETHUSDT", "SOLUSDT"])
    parser.add_argument("--interval", default="15m")
    parser.add_argument("--start", default="2021-01")
    parser.add_argument("--end", default="2024-10")
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--force", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    months = month_range(args.start, args.end)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    combined_manifest = {
        "source": "Binance Vision USD-M monthly klines",
        "base_url": BASE_URL,
        "interval": args.interval,
        "start_month": args.start,
        "end_month": args.end,
        "symbols": {},
    }
    for symbol in args.symbols:
        output = args.output_dir / f"{symbol}_{args.interval}_{args.start}_{args.end}.json"
        symbol_manifest = args.output_dir / f"{symbol}_{args.interval}_{args.start}_{args.end}.manifest.json"
        if output.exists() and symbol_manifest.exists() and not args.force:
            existing = json.loads(symbol_manifest.read_text(encoding="utf-8"))
            combined_manifest["symbols"][symbol] = existing
            print(f"[{symbol}] existing verified dataset reused: {output}", flush=True)
            continue
        rows, files = download_symbol(symbol, args.interval, months, max(1, args.workers))
        if not rows:
            raise ValueError(f"no rows downloaded for {symbol}")
        metadata = {
            "symbol": symbol,
            "rows": len(rows),
            "first_open_time": int(rows[0]["open_time"]),
            "last_open_time": int(rows[-1]["open_time"]),
            "files": files,
        }
        output.write_text(json.dumps(rows, separators=(",", ":")) + "\n", encoding="utf-8")
        symbol_manifest.write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
        combined_manifest["symbols"][symbol] = metadata
        print(f"[{symbol}] wrote {len(rows)} unique rows to {output}", flush=True)
    (args.output_dir / "manifest.json").write_text(
        json.dumps(combined_manifest, indent=2) + "\n", encoding="utf-8"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
