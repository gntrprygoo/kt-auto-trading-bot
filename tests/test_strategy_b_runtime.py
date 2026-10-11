import importlib.util
import pathlib
import unittest
from unittest.mock import patch


ROOT = pathlib.Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "kt_bot_strategy_b_runtime_test",
    ROOT / "v3_swing_bot_fixed.py",
)
BOT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(BOT)


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


class StrategyBRuntimeTests(unittest.TestCase):
    def test_new_strategy_b_entries_are_paused_by_default(self):
        self.assertFalse(BOT.ENABLE_STRATEGY_B_LIVE)

    def test_breakout_reference_excludes_confirmation_candles(self):
        candles = breakout_fixture()
        support, resistance = BOT.breakout_reference_levels(candles)
        self.assertEqual(resistance, 105.0)

        anchored = BOT.detect_breakout_4h(candles, support, resistance)
        self.assertAlmostEqual(anchored["c1_vol_ratio"], 2.0)
        self.assertAlmostEqual(anchored["c2_vol_ratio"], 1.5)
        current_support, current_resistance = BOT.support_resistance_multi(
            candles[:-1],
            min_touches=BOT.SR_MIN_TOUCHES,
            lookback=BOT.SR_LOOKBACK,
        )
        current = BOT.detect_breakout_4h(
            candles,
            current_support,
            current_resistance,
        )

        self.assertTrue(anchored["bullish"])
        self.assertFalse(current["bullish"])

    def test_status_exposes_strategy_pause_state(self):
        with patch.object(BOT, "ENABLE_STRATEGY_B_LIVE", False), patch.object(BOT, "ENABLE_SMART_MONEY_C_SHADOW", True), patch.object(BOT, "SMART_MONEY_C_VERSION", 6):
            status = BOT.build_status_text()
        self.assertIn("Strategi    : A LIVE | B PAUSED | C SHADOW C6", status)


if __name__ == "__main__":
    unittest.main()
