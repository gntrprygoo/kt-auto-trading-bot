import pathlib
import sys
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import research_strategy_bc_v2 as research


def candle(index, close=100.0, high=None, low=None, open_price=None, volume=100.0, buy=50.0):
    high = close + 1.0 if high is None else high
    low = close - 1.0 if low is None else low
    open_price = close if open_price is None else open_price
    return {
        "open_time": index * 15 * 60 * 1000,
        "close_time": (index + 1) * 15 * 60 * 1000 - 1,
        "open": open_price,
        "high": high,
        "low": low,
        "close": close,
        "volume": volume,
        "taker_buy": buy,
        "taker_sell": max(0.0, volume - buy),
    }


class StrategyBCResearchTests(unittest.TestCase):
    def test_absorption_uses_flow_opposite_to_reversal(self):
        sweep = candle(1, volume=100.0, buy=40.0)
        self.assertAlmostEqual(research.opposing_absorption_ratio(sweep, "LONG"), 0.60)
        self.assertAlmostEqual(research.opposing_absorption_ratio(sweep, "SHORT"), 0.40)

    def test_btc_market_guard_blocks_opposite_regime(self):
        candles_4h = []
        for index in range(70):
            price = 100.0 + index * 0.10
            candles_4h.append(candle(
                index,
                close=price,
                high=price + 1.0,
                low=price - 1.0,
            ))
        self.assertTrue(research.btc_market_guard("LONG", candles_4h)["passed"])
        self.assertFalse(research.btc_market_guard("SHORT", candles_4h)["passed"])

    def test_same_candle_ambiguity_is_loss_and_cost_is_charged(self):
        candles = [
            candle(0, close=100.0),
            candle(1, close=100.0, high=102.0, low=98.0, open_price=100.0),
            candle(2, close=100.0),
        ]
        result = research.first_touch_net(
            candles,
            signal_index=0,
            side="LONG",
            stop=99.0,
            reward_r=1.5,
            cost_pct=0.0014,
        )
        self.assertEqual(result["outcome"], "LOSS")
        self.assertAlmostEqual(result["gross_R"], -1.0)
        self.assertAlmostEqual(result["net_R"], -1.14)

    def test_b2_volume_baseline_excludes_breakout_candles(self):
        closed = []
        for index in range(105):
            price = 90.0 + index * 0.10
            item = candle(index, close=price, high=price + 0.5, low=price - 0.5)
            closed.append(item)
        for index in (30, 55, 80):
            closed[index].update({"high": 105.0, "close": 100.0})
            closed[index - 1]["high"] = 101.0
            closed[index + 1]["high"] = 101.0
        closed.append(candle(105, close=106.0, high=107.0, low=100.0, open_price=100.0, volume=160.0, buy=100.0))
        closed.append(candle(106, close=106.5, high=107.0, low=105.2, open_price=106.0, volume=90.0, buy=55.0))

        setup = research.detect_b2_breakout(closed, research.B2_VARIANTS[0])
        self.assertIsNotNone(setup)
        self.assertEqual(setup["side"], "LONG")
        self.assertAlmostEqual(setup["c1_volume_ratio"], 1.60, places=2)
        self.assertAlmostEqual(setup["c2_volume_ratio"], 0.90, places=2)

    def test_c4_requires_absorption_then_mss_retest(self):
        candles_4h = []
        for index in range(70):
            price = 100.0 + index * 0.10
            candles_4h.append(candle(index, close=price, high=price + 1.0, low=price - 1.0))

        candles_15m = [
            candle(index, close=104.0, high=104.2, low=103.8, open_price=104.0)
            for index in range(45)
        ]
        candles_15m.append(candle(
            45,
            close=103.9,
            high=104.1,
            low=103.5,
            open_price=104.0,
            volume=100.0,
            buy=40.0,
        ))
        candles_15m.append(candle(
            46,
            close=104.6,
            high=104.7,
            low=103.8,
            open_price=103.9,
            volume=120.0,
            buy=75.0,
        ))
        candles_15m.append(candle(
            47,
            close=104.4,
            high=104.5,
            low=104.15,
            open_price=104.25,
            volume=100.0,
            buy=55.0,
        ))

        setup = research.detect_c4_setup(
            candles_15m,
            candles_4h,
            research.C4_VARIANTS[0],
        )
        self.assertIsNotNone(setup)
        self.assertEqual(setup["side"], "LONG")
        self.assertGreaterEqual(setup["absorption_ratio"], 0.54)
        self.assertGreater(setup["mss_level"], setup["sweep_level"])

    def test_c5_uses_atr_normalized_pullback_location(self):
        candles_4h = []
        for index in range(70):
            price = 100.0 + index * 0.10
            candles_4h.append(candle(
                index,
                close=price,
                high=price + 1.0,
                low=price - 1.0,
            ))

        candles_15m = [
            candle(index, close=104.0, high=104.2, low=103.8, open_price=104.0)
            for index in range(45)
        ]
        candles_15m.append(candle(
            45,
            close=103.9,
            high=104.1,
            low=103.5,
            open_price=104.0,
            volume=100.0,
            buy=40.0,
        ))
        candles_15m.append(candle(
            46,
            close=104.6,
            high=104.7,
            low=103.8,
            open_price=103.9,
            volume=120.0,
            buy=75.0,
        ))
        candles_15m.append(candle(
            47,
            close=104.4,
            high=104.5,
            low=104.15,
            open_price=104.25,
            volume=100.0,
            buy=55.0,
        ))

        setup = research.detect_c5_setup(
            candles_15m,
            candles_4h,
            research.C5_VARIANTS[0],
        )
        self.assertIsNotNone(setup)
        self.assertEqual(setup["side"], "LONG")
        self.assertGreaterEqual(setup["absorption_ratio"], 0.52)
        self.assertLess(abs(setup["fast_distance_atr"]), 2.0)


if __name__ == "__main__":
    unittest.main()
