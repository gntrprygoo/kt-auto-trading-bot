import pathlib
import sys
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import replay_strategy_b as replay


def candle(index, close=100.0, high=101.0, low=99.0, volume=100.0):
    return {
        "open_time": index * 4 * 3600 * 1000,
        "close_time": (index + 1) * 4 * 3600 * 1000 - 1,
        "open": close,
        "high": high,
        "low": low,
        "close": close,
        "volume": volume,
        "taker_buy": volume * 0.5,
        "taker_sell": volume * 0.5,
    }


def breakout_fixture():
    candles = [candle(index) for index in range(100)]
    for index in (20, 40, 60):
        candles[index].update({"high": 105.0, "close": 100.0})
        candles[index - 1]["high"] = 101.0
        candles[index + 1]["high"] = 101.0
    candles.append(candle(100, close=106.0, high=107.0, low=100.0, volume=200.0))
    candles.append(candle(101, close=106.5, high=108.0, low=105.0, volume=150.0))
    candles.append(candle(102, close=106.5, high=106.5, low=106.5, volume=0.0))
    return candles


class StrategyBReplayTests(unittest.TestCase):
    def test_reference_window_excludes_breakout_candles(self):
        candles = breakout_fixture()
        history = replay.breakout_reference_window(candles, anchored=True)
        self.assertEqual(len(history), 100)
        self.assertEqual(history[-1]["open_time"], candles[-4]["open_time"])

    def test_anchored_level_detects_breakout_current_level_does_not(self):
        candles = breakout_fixture()
        anchored = replay.breakout_candidate(
            candles,
            replay.Variant("anchored", anchored_levels=True),
        )
        current = replay.breakout_candidate(
            candles,
            replay.Variant("current", anchored_levels=False),
        )
        self.assertEqual(anchored["side"], "LONG")
        self.assertTrue(anchored["volume_ok"])
        self.assertIsNone(current["side"])


if __name__ == "__main__":
    unittest.main()
