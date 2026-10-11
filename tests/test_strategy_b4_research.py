import pathlib
import sys
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import research_strategy_b4 as research


def candle(index, close, high, low, open_price=None, volume=100.0, buy_ratio=0.5):
    open_price = close if open_price is None else open_price
    return {
        "open_time": index * 4 * 3600 * 1000,
        "close_time": (index + 1) * 4 * 3600 * 1000 - 1,
        "open": open_price,
        "high": high,
        "low": low,
        "close": close,
        "volume": volume,
        "taker_buy": volume * buy_ratio,
        "taker_sell": volume * (1.0 - buy_ratio),
    }


class StrategyB4ResearchTests(unittest.TestCase):
    def test_retest_atr_excludes_the_candle_being_evaluated(self):
        candles = [candle(i, 100.0, 101.0, 99.0) for i in range(30)]
        candles.append(candle(30, 100.0, 120.0, 80.0))

        prior = research.prior_atr(candles, 30)
        diluted = research.common.atr_value(candles[-30:])

        self.assertAlmostEqual(prior, 2.0)
        self.assertGreater(diluted, prior)

    def test_scan_advances_to_live_management_exit(self):
        record = {"exit_index_1_5R": 14, "exit_index_live": 21}
        self.assertEqual(research.advance_past_live_trade(10, record), 21)

    def test_donchian_level_excludes_breakout_and_tracks_age(self):
        history = [candle(i, 100.0, 101.0, 99.0) for i in range(12)]
        history[5]["high"] = 105.0
        level = research.donchian_level(history, "LONG", 12)
        self.assertEqual(level["level"], 105.0)
        self.assertEqual(level["age"], 6)

    def test_recent_channel_high_is_not_a_mature_breakout_level(self):
        variant = research.B4_VARIANTS[0]
        candles = []
        for index in range(90):
            price = 100.0 + index * 0.05
            candles.append(candle(index, price, price + 0.20, price - 0.20))
        candles.append(candle(90, 105.4, 105.5, 104.7, 104.8, 130.0, 0.56))
        self.assertIsNone(research.detect_b4_breakout(candles, variant))

    def test_first_retest_rejects_deep_penetration(self):
        variant = research.B4_VARIANTS[0]
        pending = {"side": "LONG", "level": 100.0}
        previous = [candle(i, 101.0, 101.2, 100.8) for i in range(20)]
        retest = candle(21, 100.1, 100.4, 99.3, 100.3, 90.0, 0.45)
        result = research.evaluate_first_retest(retest, previous, pending, 1.0, variant)
        self.assertIsNotNone(result)
        self.assertFalse(result["valid"])
        self.assertGreater(result["penetration_atr"], variant.retest_max_penetration_atr)

    def test_confirmation_requires_level_reclaim_buffer(self):
        variant = research.B4_VARIANTS[0]
        pending = {"side": "LONG", "level": 100.0}
        retest = {"high": 100.4, "low": 99.9}
        weak = candle(22, 100.03, 100.35, 100.0, 100.1, 100.0, 0.55)
        strong = candle(23, 100.7, 100.75, 100.1, 100.2, 100.0, 0.55)
        self.assertFalse(research.confirm_retest(weak, retest, pending, 1.0, variant)["valid"])
        self.assertTrue(research.confirm_retest(strong, retest, pending, 1.0, variant)["valid"])

    def test_live_management_counts_same_candle_stop_before_targets(self):
        candles = [
            candle(0, 100.0, 100.2, 99.8),
            candle(1, 100.0, 104.5, 97.5, 100.0),
        ]
        result = research.simulate_live_management(
            candles,
            signal_index=0,
            side="LONG",
            stop=98.0,
            cost_pct=0.0014,
        )
        self.assertEqual(result["outcome_live"], "SL")
        self.assertAlmostEqual(result["gross_R_live"], -1.0)

    def test_live_management_books_tp1_then_sl_plus(self):
        candles = [
            candle(0, 100.0, 100.2, 99.8),
            candle(1, 102.0, 102.2, 99.0, 100.0),
            candle(2, 101.0, 101.2, 100.8, 101.1),
        ]
        result = research.simulate_live_management(
            candles,
            signal_index=0,
            side="LONG",
            stop=98.0,
            cost_pct=0.0014,
        )
        self.assertEqual(result["outcome_live"], "SL_PLUS")
        self.assertAlmostEqual(result["gross_R_live"], 0.75)


if __name__ == "__main__":
    unittest.main()
