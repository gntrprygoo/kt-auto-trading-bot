import csv
import hashlib
import io
import json
import math
import sqlite3
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
import zipfile
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone


ARCHIVE_BASE = "https://data.binance.vision"
S3_LIST_BASE = (
    "https://s3-ap-northeast-1.amazonaws.com/data.binance.vision"
)
FUTURES_API_BASE = "https://fapi.binance.com"
HOUR_MS = 60 * 60 * 1000
USER_AGENT = "KT-Derivatives-Audit/1.0"

METRICS_FIELDS = (
    "create_time",
    "symbol",
    "sum_open_interest",
    "sum_open_interest_value",
    "count_toptrader_long_short_ratio",
    "sum_toptrader_long_short_ratio",
    "count_long_short_ratio",
    "sum_taker_long_short_vol_ratio",
)
FUNDING_FIELDS = (
    "calc_time",
    "funding_interval_hours",
    "last_funding_rate",
)
KLINE_FIELDS = (
    "open_time",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "close_time",
    "quote_volume",
    "count",
    "taker_buy_volume",
    "taker_buy_quote_volume",
    "ignore",
)


class DataFormatError(ValueError):
    pass


class SourceMissingError(FileNotFoundError):
    pass


@dataclass(frozen=True)
class SourceObject:
    key: str
    size: int
    etag: str
    last_modified: str


@dataclass(frozen=True)
class DownloadedSource:
    key: str
    url: str
    payload: bytes
    etag: str

    @property
    def sha256(self):
        return hashlib.sha256(self.payload).hexdigest()


def parse_date(value):
    if isinstance(value, datetime):
        parsed = value
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc).date()
    if isinstance(value, date):
        return value
    text = str(value).strip()
    if len(text) == 10:
        return date.fromisoformat(text)
    parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).date()


def iter_dates(start, end):
    current = parse_date(start)
    final = parse_date(end)
    while current <= final:
        yield current
        current += timedelta(days=1)


def iter_months(start, end):
    current = parse_date(start).replace(day=1)
    final = parse_date(end).replace(day=1)
    while current <= final:
        yield current
        if current.month == 12:
            current = current.replace(
                year=current.year + 1,
                month=1,
            )
        else:
            current = current.replace(month=current.month + 1)


def utc_ms(value):
    if isinstance(value, int):
        return value
    if isinstance(value, datetime):
        parsed = value
    else:
        text = str(value).strip().replace("Z", "+00:00")
        parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return int(parsed.timestamp() * 1000)


def day_start_ms(value):
    parsed = parse_date(value)
    return int(
        datetime(
            parsed.year,
            parsed.month,
            parsed.day,
            tzinfo=timezone.utc,
        ).timestamp()
        * 1000
    )


def month_id(value):
    parsed = parse_date(value)
    return f"{parsed.year:04d}-{parsed.month:02d}"


def archive_url(key):
    return f"{ARCHIVE_BASE}/{key}"


def metrics_key(symbol, value):
    day = parse_date(value).isoformat()
    return (
        "data/futures/um/daily/metrics/"
        f"{symbol}/{symbol}-metrics-{day}.zip"
    )


def funding_monthly_key(symbol, value):
    month = month_id(value)
    return (
        "data/futures/um/monthly/fundingRate/"
        f"{symbol}/{symbol}-fundingRate-{month}.zip"
    )


def premium_monthly_key(symbol, value, interval="1h"):
    month = month_id(value)
    return (
        "data/futures/um/monthly/premiumIndexKlines/"
        f"{symbol}/{interval}/{symbol}-{interval}-{month}.zip"
    )


def premium_daily_key(symbol, value, interval="1h"):
    day = parse_date(value).isoformat()
    return (
        "data/futures/um/daily/premiumIndexKlines/"
        f"{symbol}/{interval}/{symbol}-{interval}-{day}.zip"
    )


def _request_bytes(url, timeout=30, retries=4):
    last_error = None
    for attempt in range(retries):
        request = urllib.request.Request(
            url,
            headers={"User-Agent": USER_AGENT},
        )
        try:
            with urllib.request.urlopen(
                request,
                timeout=timeout,
            ) as response:
                return (
                    response.read(),
                    response.headers.get("ETag", "").strip('"'),
                )
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                raise SourceMissingError(url) from exc
            last_error = exc
        except Exception as exc:
            last_error = exc
        if attempt + 1 < retries:
            time.sleep(1.0 + attempt)
    raise RuntimeError(f"download_failed {url}: {last_error}")


def download_source(key, timeout=30, retries=4):
    url = archive_url(key)
    payload, etag = _request_bytes(
        url,
        timeout=timeout,
        retries=retries,
    )
    return DownloadedSource(
        key=key,
        url=url,
        payload=payload,
        etag=etag,
    )


def _zip_dict_rows(payload, expected_fields):
    try:
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            bad_name = archive.testzip()
            if bad_name:
                raise DataFormatError(f"zip_crc_failed {bad_name}")
            names = [
                name
                for name in archive.namelist()
                if not name.endswith("/") and name.lower().endswith(".csv")
            ]
            if len(names) != 1:
                raise DataFormatError(
                    f"expected_one_csv found={len(names)}"
                )
            with archive.open(names[0]) as raw:
                text = io.TextIOWrapper(
                    raw,
                    encoding="utf-8-sig",
                    newline="",
                )
                reader = csv.DictReader(text)
                fields = tuple(reader.fieldnames or ())
                if fields != tuple(expected_fields):
                    raise DataFormatError(
                        "unexpected_header "
                        f"expected={tuple(expected_fields)} actual={fields}"
                    )
                return list(reader)
    except zipfile.BadZipFile as exc:
        raise DataFormatError("invalid_zip") from exc


def _finite_float(value, field):
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise DataFormatError(f"invalid_float {field}={value!r}") from exc
    if not math.isfinite(result):
        raise DataFormatError(f"non_finite_float {field}={value!r}")
    return result


def _median(values):
    ordered = sorted(values)
    length = len(ordered)
    if not length:
        raise DataFormatError("median_empty")
    middle = length // 2
    if length % 2:
        return ordered[middle]
    return (ordered[middle - 1] + ordered[middle]) / 2.0


def parse_metrics_zip(payload, expected_symbol=None):
    rows = _zip_dict_rows(payload, METRICS_FIELDS)
    buckets = defaultdict(list)
    for row in rows:
        symbol = str(row["symbol"]).strip().upper()
        if expected_symbol and symbol != expected_symbol.upper():
            raise DataFormatError(
                f"metrics_symbol_mismatch {symbol} != {expected_symbol}"
            )
        observed_at = utc_ms(row["create_time"])
        bucket_open = observed_at - (observed_at % HOUR_MS)
        parsed = {
            "symbol": symbol,
            "observed_at": observed_at,
            "open_interest": _finite_float(
                row["sum_open_interest"],
                "sum_open_interest",
            ),
            "open_interest_value": _finite_float(
                row["sum_open_interest_value"],
                "sum_open_interest_value",
            ),
            "top_account_ratio": _finite_float(
                row["count_toptrader_long_short_ratio"],
                "count_toptrader_long_short_ratio",
            ),
            "top_position_ratio": _finite_float(
                row["sum_toptrader_long_short_ratio"],
                "sum_toptrader_long_short_ratio",
            ),
            "global_account_ratio": _finite_float(
                row["count_long_short_ratio"],
                "count_long_short_ratio",
            ),
            "taker_ratio": _finite_float(
                row["sum_taker_long_short_vol_ratio"],
                "sum_taker_long_short_vol_ratio",
            ),
        }
        buckets[(symbol, bucket_open)].append(parsed)

    result = []
    for (symbol, bucket_open), items in sorted(buckets.items()):
        latest = max(items, key=lambda item: item["observed_at"])
        result.append({
            "symbol": symbol,
            "bucket_open": bucket_open,
            "observed_at": latest["observed_at"],
            "open_interest": latest["open_interest"],
            "open_interest_value": latest["open_interest_value"],
            "top_account_ratio": latest["top_account_ratio"],
            "top_position_ratio": latest["top_position_ratio"],
            "global_account_ratio": latest["global_account_ratio"],
            "taker_ratio_median": _median([
                item["taker_ratio"] for item in items
            ]),
            "source_rows": len(items),
        })
    return result


def parse_funding_zip(payload, symbol):
    rows = _zip_dict_rows(payload, FUNDING_FIELDS)
    result = []
    for row in rows:
        result.append({
            "symbol": symbol.upper(),
            "event_time": int(row["calc_time"]),
            "interval_hours": int(row["funding_interval_hours"]),
            "funding_rate": _finite_float(
                row["last_funding_rate"],
                "last_funding_rate",
            ),
            "mark_price": None,
        })
    return result


def parse_premium_zip(payload, symbol):
    rows = _zip_dict_rows(payload, KLINE_FIELDS)
    result = []
    for row in rows:
        result.append({
            "symbol": symbol.upper(),
            "open_time": int(row["open_time"]),
            "close_time": int(row["close_time"]),
            "open": _finite_float(row["open"], "open"),
            "high": _finite_float(row["high"], "high"),
            "low": _finite_float(row["low"], "low"),
            "close": _finite_float(row["close"], "close"),
            "sample_count": int(row["count"]),
        })
    return result


def parse_funding_api(payload, expected_symbol):
    try:
        rows = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise DataFormatError("invalid_funding_api_json") from exc
    if not isinstance(rows, list):
        raise DataFormatError("funding_api_not_list")
    result = []
    for row in rows:
        symbol = str(row.get("symbol", "")).upper()
        if symbol != expected_symbol.upper():
            raise DataFormatError(
                f"funding_symbol_mismatch {symbol} != {expected_symbol}"
            )
        mark_price = row.get("markPrice")
        result.append({
            "symbol": symbol,
            "event_time": int(row["fundingTime"]),
            "interval_hours": None,
            "funding_rate": _finite_float(
                row["fundingRate"],
                "fundingRate",
            ),
            "mark_price": (
                _finite_float(mark_price, "markPrice")
                if mark_price not in (None, "")
                else None
            ),
        })
    return result


def fetch_funding_api(symbol, start_ms, end_ms, timeout=30):
    cursor = int(start_ms)
    all_rows = []
    payloads = []
    while cursor <= end_ms:
        query = urllib.parse.urlencode({
            "symbol": symbol,
            "startTime": cursor,
            "endTime": int(end_ms),
            "limit": 1000,
        })
        url = f"{FUTURES_API_BASE}/fapi/v1/fundingRate?{query}"
        payload, _etag = _request_bytes(url, timeout=timeout)
        payloads.append(payload)
        page = parse_funding_api(payload, symbol)
        if not page:
            break
        all_rows.extend(page)
        next_cursor = int(page[-1]["event_time"]) + 1
        if next_cursor <= cursor or len(page) < 1000:
            break
        cursor = next_cursor
    deduped = {
        (row["symbol"], row["event_time"]): row
        for row in all_rows
        if start_ms <= row["event_time"] <= end_ms
    }
    return (
        [deduped[key] for key in sorted(deduped)],
        b"\n".join(payloads),
    )


def list_s3_objects(prefix, start_after=None, timeout=30):
    continuation = None
    while True:
        params = {
            "list-type": "2",
            "prefix": prefix,
            "max-keys": 1000,
        }
        if start_after and continuation is None:
            params["start-after"] = start_after
        if continuation:
            params["continuation-token"] = continuation
        url = f"{S3_LIST_BASE}?{urllib.parse.urlencode(params)}"
        payload, _etag = _request_bytes(url, timeout=timeout)
        try:
            root = ET.fromstring(payload)
        except ET.ParseError as exc:
            raise DataFormatError("invalid_s3_listing_xml") from exc
        namespace = {"s3": "http://s3.amazonaws.com/doc/2006-03-01/"}
        for item in root.findall("s3:Contents", namespace):
            yield SourceObject(
                key=item.findtext("s3:Key", "", namespace),
                size=int(item.findtext("s3:Size", "0", namespace)),
                etag=item.findtext(
                    "s3:ETag",
                    "",
                    namespace,
                ).strip('"'),
                last_modified=item.findtext(
                    "s3:LastModified",
                    "",
                    namespace,
                ),
            )
        truncated = (
            root.findtext("s3:IsTruncated", "false", namespace).lower()
            == "true"
        )
        if not truncated:
            break
        continuation = root.findtext(
            "s3:NextContinuationToken",
            "",
            namespace,
        )
        if not continuation:
            raise DataFormatError("s3_listing_missing_continuation")


class DerivativesStore:
    def __init__(self, path):
        self.path = str(path)
        self.connection = sqlite3.connect(self.path)
        self.connection.execute("PRAGMA journal_mode=WAL")
        self.connection.execute("PRAGMA synchronous=NORMAL")
        self._create_schema()

    def close(self):
        self.connection.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        self.close()

    def _create_schema(self):
        self.connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS metrics_hourly (
                symbol TEXT NOT NULL,
                bucket_open INTEGER NOT NULL,
                observed_at INTEGER NOT NULL,
                open_interest REAL NOT NULL,
                open_interest_value REAL NOT NULL,
                top_account_ratio REAL NOT NULL,
                top_position_ratio REAL NOT NULL,
                global_account_ratio REAL NOT NULL,
                taker_ratio_median REAL NOT NULL,
                source_rows INTEGER NOT NULL,
                PRIMARY KEY (symbol, bucket_open)
            );

            CREATE TABLE IF NOT EXISTS funding_events (
                symbol TEXT NOT NULL,
                event_time INTEGER NOT NULL,
                interval_hours INTEGER,
                funding_rate REAL NOT NULL,
                mark_price REAL,
                PRIMARY KEY (symbol, event_time)
            );

            CREATE TABLE IF NOT EXISTS premium_hourly (
                symbol TEXT NOT NULL,
                open_time INTEGER NOT NULL,
                close_time INTEGER NOT NULL,
                open REAL NOT NULL,
                high REAL NOT NULL,
                low REAL NOT NULL,
                close REAL NOT NULL,
                sample_count INTEGER NOT NULL,
                PRIMARY KEY (symbol, open_time)
            );

            CREATE TABLE IF NOT EXISTS source_manifest (
                source_key TEXT PRIMARY KEY,
                source_kind TEXT NOT NULL,
                symbol TEXT NOT NULL,
                etag TEXT,
                sha256 TEXT NOT NULL,
                size_bytes INTEGER NOT NULL,
                row_count INTEGER NOT NULL,
                ingested_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_metrics_observed
                ON metrics_hourly(symbol, observed_at);
            CREATE INDEX IF NOT EXISTS idx_funding_event
                ON funding_events(symbol, event_time);
            CREATE INDEX IF NOT EXISTS idx_premium_close
                ON premium_hourly(symbol, close_time);
            """
        )
        self.connection.commit()

    def has_source(self, source_key):
        row = self.connection.execute(
            "SELECT 1 FROM source_manifest WHERE source_key = ?",
            (source_key,),
        ).fetchone()
        return row is not None

    def upsert_metrics(self, rows):
        self.connection.executemany(
            """
            INSERT INTO metrics_hourly (
                symbol, bucket_open, observed_at,
                open_interest, open_interest_value,
                top_account_ratio, top_position_ratio,
                global_account_ratio, taker_ratio_median,
                source_rows
            ) VALUES (
                :symbol, :bucket_open, :observed_at,
                :open_interest, :open_interest_value,
                :top_account_ratio, :top_position_ratio,
                :global_account_ratio, :taker_ratio_median,
                :source_rows
            )
            ON CONFLICT(symbol, bucket_open) DO UPDATE SET
                observed_at = excluded.observed_at,
                open_interest = excluded.open_interest,
                open_interest_value = excluded.open_interest_value,
                top_account_ratio = excluded.top_account_ratio,
                top_position_ratio = excluded.top_position_ratio,
                global_account_ratio = excluded.global_account_ratio,
                taker_ratio_median = excluded.taker_ratio_median,
                source_rows = excluded.source_rows
            """,
            rows,
        )

    def upsert_funding(self, rows):
        self.connection.executemany(
            """
            INSERT INTO funding_events (
                symbol, event_time, interval_hours,
                funding_rate, mark_price
            ) VALUES (
                :symbol, :event_time, :interval_hours,
                :funding_rate, :mark_price
            )
            ON CONFLICT(symbol, event_time) DO UPDATE SET
                interval_hours = COALESCE(
                    excluded.interval_hours,
                    funding_events.interval_hours
                ),
                funding_rate = excluded.funding_rate,
                mark_price = COALESCE(
                    excluded.mark_price,
                    funding_events.mark_price
                )
            """,
            rows,
        )

    def upsert_premium(self, rows):
        self.connection.executemany(
            """
            INSERT INTO premium_hourly (
                symbol, open_time, close_time,
                open, high, low, close, sample_count
            ) VALUES (
                :symbol, :open_time, :close_time,
                :open, :high, :low, :close, :sample_count
            )
            ON CONFLICT(symbol, open_time) DO UPDATE SET
                close_time = excluded.close_time,
                open = excluded.open,
                high = excluded.high,
                low = excluded.low,
                close = excluded.close,
                sample_count = excluded.sample_count
            """,
            rows,
        )

    def record_source(
        self,
        source_key,
        source_kind,
        symbol,
        payload,
        row_count,
        etag="",
    ):
        self.connection.execute(
            """
            INSERT INTO source_manifest (
                source_key, source_kind, symbol, etag,
                sha256, size_bytes, row_count, ingested_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(source_key) DO UPDATE SET
                etag = excluded.etag,
                sha256 = excluded.sha256,
                size_bytes = excluded.size_bytes,
                row_count = excluded.row_count,
                ingested_at = excluded.ingested_at
            """,
            (
                source_key,
                source_kind,
                symbol,
                etag,
                hashlib.sha256(payload).hexdigest(),
                len(payload),
                int(row_count),
                datetime.now(timezone.utc).isoformat(),
            ),
        )

    def ingest_download(self, source, kind, symbol):
        if kind == "metrics":
            rows = parse_metrics_zip(source.payload, symbol)
            self.upsert_metrics(rows)
        elif kind == "funding":
            rows = parse_funding_zip(source.payload, symbol)
            self.upsert_funding(rows)
        elif kind == "premium":
            rows = parse_premium_zip(source.payload, symbol)
            self.upsert_premium(rows)
        else:
            raise ValueError(f"unsupported_kind {kind}")
        self.record_source(
            source.key,
            kind,
            symbol,
            source.payload,
            len(rows),
            etag=source.etag,
        )
        self.connection.commit()
        return len(rows)

    def ingest_funding_api(
        self,
        symbol,
        start_ms,
        end_ms,
        rows,
        payload,
    ):
        self.upsert_funding(rows)
        source_key = (
            "api:fapi/v1/fundingRate:"
            f"{symbol}:{int(start_ms)}:{int(end_ms)}"
        )
        self.record_source(
            source_key,
            "funding_api",
            symbol,
            payload,
            len(rows),
        )
        self.connection.commit()
        return len(rows)

    def counts(self):
        result = {}
        for table in (
            "metrics_hourly",
            "funding_events",
            "premium_hourly",
            "source_manifest",
        ):
            result[table] = self.connection.execute(
                f"SELECT COUNT(*) FROM {table}"
            ).fetchone()[0]
        return result

    def latest_at_or_before(self, table, symbol, time_column, timestamp):
        allowed = {
            ("metrics_hourly", "observed_at"),
            ("funding_events", "event_time"),
            ("premium_hourly", "close_time"),
        }
        if (table, time_column) not in allowed:
            raise ValueError("unsupported_asof_query")
        cursor = self.connection.execute(
            f"""
            SELECT *
            FROM {table}
            WHERE symbol = ? AND {time_column} <= ?
            ORDER BY {time_column} DESC
            LIMIT 1
            """,
            (symbol, int(timestamp)),
        )
        row = cursor.fetchone()
        if row is None:
            return None
        return dict(zip(
            [item[0] for item in cursor.description],
            row,
        ))
