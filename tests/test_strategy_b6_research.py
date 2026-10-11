import pathlib
import sys
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import research_strategy_b6 as research


def candle(
    index,
    close,
    high,
    low,
    open_price=None,
    volume=100.0,
    buy_ratio=0.5,
):
    open_price = close if open_price is None else open_price
    return {
        "open_time": index * research.MS_15M,
        "close_time": (index + 1) * research.MS_15M - 1,
        "open": open_price,
        "high": high,
        "low": low,
        "close": close,
        "volume": volume,
        "taker_buy": volume * buy_ratio,
        "taker_sell": volume * (1.0 - buy_ratio),
    }


class StrategyB6ResearchTests(unittest.TestCase):
    def test_aggregate_2h_requires_eight_contiguous_candles(self):
        candles = [
            candle(index, 100 + index, 101 + index, 99 + index)
            for index in range(15)
        ]
        result = research.aggregate_interval(candles, 2)

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["open"], 100.0)
        self.assertEqual(result[0]["close"], 107.0)
        self.assertEqual(result[0]["volume"], 800.0)

    def test_compression_ratio_detects_recent_contraction(self):
        candles = []
        close = 100.0
        for index in range(22):
            width = 2.0 if index < 18 else 0.5
            candles.append(
                candle(index, close, close + width, close - width)
            )
        ratio = research.compression_ratio(candles, 4, 20)

        self.assertIsNotNone(ratio)
        self.assertLess(ratio, 0.82)

    def test_acceptance_requires_multiple_closes_beyond_level(self):
        variant = research.B6_PRIMARY
        pending = {"side": "LONG", "level": 100.0}
        accepted = [
            candle(1, 100.15, 100.3, 99.95, buy_ratio=0.55),
            candle(2, 100.20, 100.4, 100.0, buy_ratio=0.55),
            candle(3, 99.98, 100.2, 99.9, buy_ratio=0.55),
            candle(4, 100.30, 100.5, 100.0, buy_ratio=0.55),
        ]

        result = research.evaluate_acceptance(
            accepted,
            pending,
            atr_15m=1.0,
            variant=variant,
        )

        self.assertEqual(result["status"], "ACCEPT")
        self.assertEqual(result["outside_count"], 3)

    def test_acceptance_rejects_failed_level(self):
        variant = research.B6_PRIMARY
        pending = {"side": "LONG", "level": 100.0}
        failed = [
            candle(1, 100.1, 100.2, 99.9, buy_ratio=0.55),
            candle(2, 99.6, 100.1, 99.5, buy_ratio=0.55),
            candle(3, 100.2, 100.3, 99.8, buy_ratio=0.55),
            candle(4, 100.3, 100.4, 100.0, buy_ratio=0.55),
        ]

        result = research.evaluate_acceptance(
            failed,
            pending,
            atr_15m=1.0,
            variant=variant,
        )

        self.assertEqual(result["status"], "REJECT")
        self.assertEqual(result["reason"], "acceptance_level_failed")

    def test_market_context_requires_core_consensus(self):
        contexts = {
            "BTCUSDT": {"side": "LONG"},
            "ETHUSDT": {"side": "LONG"},
            "SOLUSDT": {"side": "LONG"},
            "BNBUSDT": {"side": "SHORT"},
            "XRPUSDT": {"side": "SHORT"},
        }

        result = research.combine_market_contexts(contexts)

        self.assertIsNone(result["side"])
        self.assertEqual(result["score"], 1)

    def test_portfolio_overlay_blocks_correlated_same_side_signal(self):
        records = [
            {
                "pair": "BTCUSDT",
                "side": "LONG",
                "signal_time": 1000,
                "exit_time_live": research.MS_HOUR * 2,
                "quality_score": 2.0,
            },
            {
                "pair": "ETHUSDT",
                "side": "LONG",
                "signal_time": 1000 + research.MS_15M,
                "exit_time_live": research.MS_HOUR * 2,
                "quality_score": 3.0,
            },
        ]

        selected, diagnostics = research.portfolio_overlay(records)

        self.assertEqual(len(selected), 1)
        self.assertEqual(diagnostics["blocked_same_side_cluster"], 1)


if __name__ == "__main__":
    unittest.main()
