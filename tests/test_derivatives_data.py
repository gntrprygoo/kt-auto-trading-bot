import csv
import io
import pathlib
import sys
import tempfile
import unittest
import zipfile
from datetime import date
from unittest import mock


ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import derivatives_data as data
import audit_derivatives_coverage as coverage
import ingest_derivatives_data as ingest


def zip_csv(name, header, rows):
    output = io.StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow(header)
    writer.writerows(rows)
    payload = io.BytesIO()
    with zipfile.ZipFile(
        payload,
        "w",
        compression=zipfile.ZIP_DEFLATED,
    ) as archive:
        archive.writestr(name, output.getvalue())
    return payload.getvalue()


class DerivativesParserTests(unittest.TestCase):
    def test_metrics_are_aggregated_without_future_rows(self):
        payload = zip_csv(
            "BTCUSDT-metrics.csv",
            data.METRICS_FIELDS,
            [
                [
                    "2025-01-01 00:00:00",
                    "BTCUSDT",
                    "100",
                    "1000",
                    "1.1",
                    "1.2",
                    "1.3",
                    "1.0",
                ],
                [
                    "2025-01-01 00:55:00",
                    "BTCUSDT",
                    "120",
                    "1300",
                    "1.4",
                    "1.5",
                    "1.6",
                    "3.0",
                ],
                [
                    "2025-01-01 01:00:00",
                    "BTCUSDT",
                    "125",
                    "1400",
                    "1.7",
                    "1.8",
                    "1.9",
                    "2.0",
                ],
            ],
        )

        rows = data.parse_metrics_zip(payload, "BTCUSDT")

        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["open_interest"], 120.0)
        self.assertEqual(rows[0]["source_rows"], 2)
        self.assertEqual(rows[0]["taker_ratio_median"], 2.0)
        self.assertEqual(
            rows[0]["observed_at"],
            data.utc_ms("2025-01-01T00:55:00+00:00"),
        )
        self.assertEqual(
            rows[1]["observed_at"],
            data.utc_ms("2025-01-01T01:00:00+00:00"),
        )

    def test_metrics_reject_symbol_mismatch(self):
        payload = zip_csv(
            "metrics.csv",
            data.METRICS_FIELDS,
            [[
                "2025-01-01 00:00:00",
                "ETHUSDT",
                "1",
                "1",
                "1",
                "1",
                "1",
                "1",
            ]],
        )
        with self.assertRaises(data.DataFormatError):
            data.parse_metrics_zip(payload, "BTCUSDT")

    def test_parser_rejects_unexpected_header(self):
        payload = zip_csv(
            "metrics.csv",
            ("create_time", "symbol"),
            [["2025-01-01 00:00:00", "BTCUSDT"]],
        )
        with self.assertRaises(data.DataFormatError):
            data.parse_metrics_zip(payload, "BTCUSDT")

    def test_funding_and_premium_parsers(self):
        funding = zip_csv(
            "funding.csv",
            data.FUNDING_FIELDS,
            [["1735689600015", "8", "0.0001"]],
        )
        premium = zip_csv(
            "premium.csv",
            data.KLINE_FIELDS,
            [[
                "1735689600000",
                "-0.0002",
                "0.0001",
                "-0.0005",
                "-0.0001",
                "0",
                "1735693199999",
                "0",
                "720",
                "0",
                "0",
                "0",
            ]],
        )

        funding_rows = data.parse_funding_zip(funding, "BTCUSDT")
        premium_rows = data.parse_premium_zip(premium, "BTCUSDT")

        self.assertEqual(funding_rows[0]["interval_hours"], 8)
        self.assertAlmostEqual(funding_rows[0]["funding_rate"], 0.0001)
        self.assertEqual(premium_rows[0]["sample_count"], 720)
        self.assertAlmostEqual(premium_rows[0]["close"], -0.0001)

    def test_funding_api_parser_rejects_other_symbol(self):
        payload = (
            b'[{"symbol":"ETHUSDT","fundingTime":1,'
            b'"fundingRate":"0.1","markPrice":"2"}]'
        )
        with self.assertRaises(data.DataFormatError):
            data.parse_funding_api(payload, "BTCUSDT")


class DerivativesStoreTests(unittest.TestCase):
    def test_asof_query_never_uses_future_observation(self):
        first_time = data.utc_ms("2025-01-01T00:55:00+00:00")
        second_time = data.utc_ms("2025-01-01T01:55:00+00:00")
        with tempfile.TemporaryDirectory() as directory:
            path = pathlib.Path(directory) / "derivatives.sqlite"
            with data.DerivativesStore(path) as store:
                store.upsert_metrics([
                    {
                        "symbol": "BTCUSDT",
                        "bucket_open": (
                            first_time - first_time % data.HOUR_MS
                        ),
                        "observed_at": first_time,
                        "open_interest": 100.0,
                        "open_interest_value": 1000.0,
                        "top_account_ratio": 1.0,
                        "top_position_ratio": 1.0,
                        "global_account_ratio": 1.0,
                        "taker_ratio_median": 1.0,
                        "source_rows": 12,
                    },
                    {
                        "symbol": "BTCUSDT",
                        "bucket_open": (
                            second_time - second_time % data.HOUR_MS
                        ),
                        "observed_at": second_time,
                        "open_interest": 200.0,
                        "open_interest_value": 2000.0,
                        "top_account_ratio": 2.0,
                        "top_position_ratio": 2.0,
                        "global_account_ratio": 2.0,
                        "taker_ratio_median": 2.0,
                        "source_rows": 12,
                    },
                ])
                before_first = store.latest_at_or_before(
                    "metrics_hourly",
                    "BTCUSDT",
                    "observed_at",
                    first_time - 1,
                )
                at_one_hour = store.latest_at_or_before(
                    "metrics_hourly",
                    "BTCUSDT",
                    "observed_at",
                    data.utc_ms("2025-01-01T01:00:00+00:00"),
                )

                self.assertIsNone(before_first)
                self.assertEqual(at_one_hour["open_interest"], 100.0)

    def test_source_manifest_allows_idempotent_ingest(self):
        with tempfile.TemporaryDirectory() as directory:
            path = pathlib.Path(directory) / "derivatives.sqlite"
            with data.DerivativesStore(path) as store:
                store.record_source(
                    "source.zip",
                    "metrics",
                    "BTCUSDT",
                    b"payload",
                    1,
                    etag="abc",
                )
                store.connection.commit()
                self.assertTrue(store.has_source("source.zip"))
                self.assertEqual(store.counts()["source_manifest"], 1)


class DerivativesSourceTests(unittest.TestCase):
    def test_archive_date_bounds_convert_wib_to_utc(self):
        self.assertEqual(
            data.parse_date("2025-10-25T00:00:00+07:00"),
            date(2025, 10, 24),
        )
        self.assertEqual(
            data.parse_date("2026-07-22T04:00:00+07:00"),
            date(2026, 7, 21),
        )

    def test_archive_key_builders(self):
        value = date(2025, 1, 15)
        self.assertEqual(
            data.metrics_key("BTCUSDT", value),
            (
                "data/futures/um/daily/metrics/BTCUSDT/"
                "BTCUSDT-metrics-2025-01-15.zip"
            ),
        )
        self.assertEqual(
            data.funding_monthly_key("BTCUSDT", value),
            (
                "data/futures/um/monthly/fundingRate/BTCUSDT/"
                "BTCUSDT-fundingRate-2025-01.zip"
            ),
        )

    def test_s3_listing_parser(self):
        xml = b"""<?xml version="1.0" encoding="UTF-8"?>
        <ListBucketResult xmlns="http://s3.amazonaws.com/doc/2006-03-01/">
          <Name>data.binance.vision</Name>
          <Prefix>data/test/</Prefix>
          <KeyCount>1</KeyCount>
          <MaxKeys>1000</MaxKeys>
          <IsTruncated>false</IsTruncated>
          <Contents>
            <Key>data/test/file.zip</Key>
            <LastModified>2026-01-01T00:00:00.000Z</LastModified>
            <ETag>&quot;abc&quot;</ETag>
            <Size>123</Size>
            <StorageClass>STANDARD</StorageClass>
          </Contents>
        </ListBucketResult>"""
        with mock.patch.object(
            data,
            "_request_bytes",
            return_value=(xml, ""),
        ):
            rows = list(data.list_s3_objects("data/test/"))

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].key, "data/test/file.zip")
        self.assertEqual(rows[0].size, 123)
        self.assertEqual(rows[0].etag, "abc")

    def test_ingest_task_plan_uses_monthly_and_current_daily(self):
        tasks = ingest.build_tasks(
            ["BTCUSDT"],
            date(2026, 6, 30),
            date(2026, 7, 2),
            date(2026, 7, 29),
            {"metrics", "funding", "premium"},
        )
        kinds = [task.kind for task in tasks]

        self.assertEqual(kinds.count("metrics"), 3)
        self.assertEqual(kinds.count("funding"), 1)
        self.assertEqual(kinds.count("premium"), 3)
        self.assertTrue(any(
            "monthly/premiumIndexKlines" in task.key
            for task in tasks
        ))
        self.assertEqual(sum(
            "daily/premiumIndexKlines" in task.key
            for task in tasks
        ), 2)

    def test_coverage_separates_pre_archive_period_from_internal_gap(self):
        objects = [
            data.SourceObject(
                key=(
                    "data/futures/um/daily/metrics/BTCUSDT/"
                    "BTCUSDT-metrics-2025-01-03.zip"
                ),
                size=10,
                etag="a",
                last_modified="",
            ),
            data.SourceObject(
                key=(
                    "data/futures/um/daily/metrics/BTCUSDT/"
                    "BTCUSDT-metrics-2025-01-05.zip"
                ),
                size=10,
                etag="b",
                last_modified="",
            ),
        ]
        with mock.patch.object(
            coverage.data,
            "list_s3_objects",
            return_value=iter(objects),
        ):
            report = coverage.metric_coverage(
                "BTCUSDT",
                date(2025, 1, 1),
                date(2025, 1, 5),
            )

        self.assertEqual(report["unavailable_before_first_count"], 2)
        self.assertEqual(report["missing_after_first_count"], 1)
        self.assertEqual(
            report["missing_after_first"],
            ["2025-01-04"],
        )


if __name__ == "__main__":
    unittest.main()
