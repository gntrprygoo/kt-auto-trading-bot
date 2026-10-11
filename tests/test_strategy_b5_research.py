import pathlib
import sys
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import research_strategy_b5 as research


def candle(index, close, high, low, open_price=None, volume=100.0, buy_ratio=0.5):
    open_price = close if open_price is None else open_price
    return {
        "open_time": index * 15 * 60 * 1000,
        "close_time": (index + 1) * 15 * 60 * 1000 - 1,
        "open": open_price,
        "high": high,
        "low": low,
        "close": close,
        "volume": volume,
        "taker_buy": volume * buy_ratio,
        "taker_sell": volume * (1.0 - buy_ratio),
    }


class StrategyB5ResearchTests(unittest.TestCase):
    def test_aggregate_1h_requires_four_contiguous_candles(self):
        candles = [candle(i, 100 + i, 101 + i, 99 + i) for i in range(7)]
        result = research.aggregate_1h(candles)

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["open"], 100.0)
        self.assertEqual(result[0]["close"], 103.0)
        self.assertEqual(result[0]["volume"], 400.0)

    def test_retest_score_accepts_contraction_and_absorption(self):
        variant = research.B5_VARIANTS[0]
        previous = [
            candle(i, 101.0, 101.2, 100.8, volume=100.0)
            for i in range(20)
        ]
        pending = {"side": "LONG", "level": 100.0}
        retest = candle(
            21,
            100.15,
            100.30,
            99.85,
            open_price=100.05,
            volume=75.0,
            buy_ratio=0.45,
        )

        result = research.evaluate_first_retest(
            retest,
            previous,
            pending,
            atr_15m=1.0,
            variant=variant,
        )

        self.assertTrue(result["valid"])
        self.assertTrue(result["components"]["volume_contraction"])
        self.assertTrue(result["components"]["absorption"])

    def test_retest_rejects_deep_first_touch(self):
        variant = research.B5_VARIANTS[0]
        previous = [
            candle(i, 101.0, 101.2, 100.8, volume=100.0)
            for i in range(20)
        ]
        pending = {"side": "LONG", "level": 100.0}
        retest = candle(21, 99.9, 100.2, 99.0, volume=80.0, buy_ratio=0.4)

        result = research.evaluate_first_retest(
            retest,
            previous,
            pending,
            atr_15m=1.0,
            variant=variant,
        )

        self.assertFalse(result["valid"])
        self.assertEqual(result["reason"], "deep_penetration")

    def test_btc_veto_blocks_strong_opposite_context(self):
        original = research.regime_context
        research.regime_context = lambda candles: {
            "side": "SHORT",
            "score": 4,
            "return_12h": -0.012,
        }
        try:
            result = research.btc_opposition_veto("LONG", [{}] * 60)
        finally:
            research.regime_context = original

        self.assertFalse(result["passed"])
        self.assertEqual(result["reason"], "btc_strong_opposition")


if __name__ == "__main__":
    unittest.main()
