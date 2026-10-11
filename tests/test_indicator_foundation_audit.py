import pathlib
import sys
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import audit_indicator_foundation as research


def candle(index, close, high, low, open_price=None, interval_hours=4):
    interval_ms = interval_hours * 60 * 60 * 1000
    open_price = close if open_price is None else open_price
    return {
        "open_time": index * interval_ms,
        "close_time": (index + 1) * interval_ms - 1,
        "open": float(open_price),
        "high": float(high),
        "low": float(low),
        "close": float(close),
        "volume": 100.0,
        "taker_buy": 50.0,
        "taker_sell": 50.0,
    }


class IndicatorFoundationAuditTests(unittest.TestCase):
    def test_ema_matches_known_seeded_sequence(self):
        values = [1.0, 2.0, 3.0, 4.0, 5.0]
        self.assertAlmostEqual(research.BOT.ema(values, 3), 4.0)

    def test_scale_invariant_near_has_same_answer_after_rescaling(self):
        self.assertTrue(research.price_invariant_near(0.00097, 0.001, 0.04))
        self.assertTrue(research.price_invariant_near(97.0, 100.0, 0.04))
        self.assertFalse(research.price_invariant_near(0.00094, 0.001, 0.04))
        self.assertFalse(research.price_invariant_near(94.0, 100.0, 0.04))

    def test_runtime_near_level_is_now_scale_invariant(self):
        self.assertEqual(
            research.BOT.near_level(0.00097, 0.001, 0.04),
            research.BOT.near_level(97.0, 100.0, 0.04),
        )
        self.assertEqual(
            research.BOT.near_level(0.00094, 0.001, 0.04),
            research.BOT.near_level(94.0, 100.0, 0.04),
        )

    def test_legacy_near_level_changes_with_nominal_price(self):
        self.assertTrue(research.legacy_near_level(0.00094, 0.001, 0.025))
        self.assertFalse(research.legacy_near_level(94.0, 100.0, 0.025))

    def test_level_touch_requires_rejection_wick_at_the_level(self):
        away = candle(
            1,
            close=102.0,
            high=102.2,
            low=101.5,
            open_price=102.0,
            interval_hours=0.25,
        )
        touching = candle(
            2,
            close=100.6,
            high=101.0,
            low=99.8,
            open_price=100.7,
            interval_hours=0.25,
        )
        self.assertFalse(
            research.rejection_touches_level(away, "LONG", 100.0, 0.005)
        )
        self.assertTrue(
            research.rejection_touches_level(touching, "LONG", 100.0, 0.005)
        )
        self.assertFalse(
            research.BOT.is_rejection_candle_at_level(
                away,
                "LONG",
                100.0,
                0.005,
            )
        )
        self.assertTrue(
            research.BOT.is_rejection_candle_at_level(
                touching,
                "LONG",
                100.0,
                0.005,
            )
        )

    def test_clustered_sr_counts_distinct_pivot_events(self):
        closes = [
            105, 103, 100, 103, 106,
            104, 100.2, 104, 107,
            105, 99.9, 105, 108,
            106, 101, 106, 104,
            103, 102, 103,
        ]
        candles = [
            candle(
                index,
                close=value,
                high=value + 0.4,
                low=value - (1.0 if index in (2, 6, 10) else 0.4),
            )
            for index, value in enumerate(closes)
        ]
        support, _, meta = research.clustered_support_resistance(
            candles,
            lookback=20,
            min_touches=2,
        )
        self.assertIsNotNone(support)
        self.assertGreaterEqual(support["touches"], 2)
        self.assertGreaterEqual(len(meta["zones"]), 1)

    def test_context_uses_only_supplied_closed_candles(self):
        candles = []
        for index in range(120):
            close = 100.0 + index * 0.2
            candles.append(candle(index, close, close + 1.0, close - 1.0))
        baseline = research.build_4h_context(candles)
        altered = list(candles)
        altered.append(candle(120, 1.0, 2.0, 0.5))
        self.assertNotEqual(
            baseline["ema55"],
            research.build_4h_context(altered)["ema55"],
        )
        self.assertEqual(baseline["close"], candles[-1]["close"])


if __name__ == "__main__":
    unittest.main()
