import pathlib
import sys
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import abc_derivatives_context as context
import derivatives_data as data


class ABCDerivativesContextTests(unittest.TestCase):
    def test_resolver_uses_only_rows_available_at_signal_time(self):
        with tempfile.TemporaryDirectory() as directory:
            database = pathlib.Path(directory) / "derivatives.sqlite"
            start = data.utc_ms("2025-01-01T00:00:00+00:00")
            with data.DerivativesStore(database) as store:
                metrics = []
                for index in range(20):
                    observed = start + index * context.MS_HOUR + 55 * 60 * 1000
                    metrics.append({
                        "symbol": "BTCUSDT",
                        "bucket_open": start + index * context.MS_HOUR,
                        "observed_at": observed,
                        "open_interest": 100.0 + index,
                        "open_interest_value": 1000.0,
                        "top_account_ratio": 1.0,
                        "top_position_ratio": 1.0,
                        "global_account_ratio": 1.0,
                        "taker_ratio_median": 1.05,
                        "source_rows": 12,
                    })
                store.upsert_metrics(metrics)
                store.upsert_funding([
                    {
                        "symbol": "BTCUSDT",
                        "event_time": start - (90 - index) * 8 * context.MS_HOUR,
                        "interval_hours": 8,
                        "funding_rate": 0.0001,
                        "mark_price": 100.0,
                    }
                    for index in range(90)
                ])
                store.upsert_premium([
                    {
                        "symbol": "BTCUSDT",
                        "open_time": start - (168 - index) * context.MS_HOUR,
                        "close_time": (
                            start
                            - (168 - index) * context.MS_HOUR
                            + context.MS_HOUR
                            - 1
                        ),
                        "open": 0.0,
                        "high": 0.0,
                        "low": 0.0,
                        "close": 0.0,
                        "sample_count": 1,
                    }
                    for index in range(168)
                ])
                store.connection.commit()

            signal_time = start + 19 * context.MS_HOUR + 56 * 60 * 1000
            with context.DerivativesResolver(database) as resolver:
                resolved = resolver.context(
                    "BTCUSDT",
                    signal_time,
                    "LONG",
                )

            self.assertTrue(resolved["derivatives_complete"])
            self.assertLessEqual(
                resolved["derivatives_observed_at"],
                signal_time,
            )
            self.assertGreater(resolved["oi_change_12h"], 0)
            self.assertTrue(resolved["flow_aligned"])
            self.assertTrue(resolved["oi_hard_confirmed"])

    def test_missing_history_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            database = pathlib.Path(directory) / "derivatives.sqlite"
            with data.DerivativesStore(database):
                pass
            with context.DerivativesResolver(database) as resolver:
                resolved = resolver.context(
                    "BTCUSDT",
                    1,
                    "LONG",
                )
            self.assertFalse(resolved["derivatives_complete"])
            self.assertFalse(context.validate_context(resolved))


if __name__ == "__main__":
    unittest.main()
