import pathlib
import sys
import unittest


sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from test_strategy_c_v2 import BOT, make_4h_context, make_long_setup, make_short_setup


def make_v3_long_setup():
    candles = make_long_setup()
    candles[43].update({
        "open": 100.38,
        "high": 100.55,
        "low": 100.33,
        "close": 100.45,
    })
    return candles


def make_v3_short_setup():
    candles = make_short_setup()
    candles[44].update({
        "open": 119.62,
        "high": 119.68,
        "low": 119.55,
        "close": 119.58,
    })
    return candles


class StrategyCV3Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.original_version = BOT.SMART_MONEY_C_VERSION
        BOT.SMART_MONEY_C_VERSION = 3

    @classmethod
    def tearDownClass(cls):
        BOT.SMART_MONEY_C_VERSION = cls.original_version

    def test_wrapper_uses_v3_long_engine(self):
        signal = BOT.detect_smart_money_c_shadow(
            "TESTUSDT", make_v3_long_setup(), make_4h_context(), "SIDEWAYS"
        )
        self.assertIsNotNone(signal)
        self.assertEqual(signal["bias"], "LONG")
        self.assertEqual(signal["blocked_reason"], "smart_money_c_v3")
        self.assertEqual(signal["meta"]["strategy_version"], "C3")
        self.assertGreaterEqual(signal["meta"]["smc_displacement_score"], 2)
        self.assertGreaterEqual(signal["meta"]["actual_rr"], BOT.SMC_V3_MIN_RR)

    def test_v3_short_engine(self):
        signal = BOT.detect_smart_money_c_shadow(
            "TESTUSDT", make_v3_short_setup(), make_4h_context(), "SIDEWAYS"
        )
        self.assertIsNotNone(signal)
        self.assertEqual(signal["bias"], "SHORT")
        self.assertEqual(signal["meta"]["smc_location_zone"], "PREMIUM")

    def test_fvg_is_confluence_not_mandatory(self):
        candles = make_v3_long_setup()
        candles[41]["low"] = 100.85  # remove the three-candle imbalance
        candles[43].update({
            "open": 100.38,
            "high": 100.55,
            "low": 100.33,
            "close": 100.45,
        })
        signal = BOT.detect_smart_money_c_shadow(
            "TESTUSDT", candles, make_4h_context(), "SIDEWAYS"
        )
        self.assertIsNotNone(signal)
        self.assertFalse(signal["meta"]["smc_has_fvg"])
        self.assertEqual(signal["meta"]["smc_zone_source"], "OB")

    def test_countertrend_reversal_requires_extreme_location_and_full_displacement(self):
        signal = BOT.detect_smart_money_c_shadow(
            "TESTUSDT", make_v3_long_setup(), make_4h_context(), "BEARISH"
        )
        self.assertIsNotNone(signal)
        self.assertTrue(signal["meta"]["smc_countertrend"])
        self.assertEqual(signal["meta"]["smc_displacement_score"], 3)
        self.assertLessEqual(
            signal["meta"]["smc_range_position"],
            BOT.SMC_V3_COUNTERTREND_EXTREME_PCT,
        )

    def test_report_keeps_c2_and_c3_separate(self):
        self.assertEqual(
            BOT._shadow_strategy_key({"strategy_version": "C3"}),
            "smart_money_c_v3",
        )
        self.assertEqual(
            BOT._shadow_strategy_label("smart_money_c_v3"),
            "Jalur C v3 Liquidity Reversal",
        )
        self.assertEqual(
            BOT._shadow_strategy_label("smart_money_c_v2"),
            "Jalur C v2 Liquidity Sweep",
        )


if __name__ == "__main__":
    unittest.main()
