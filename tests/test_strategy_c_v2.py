import importlib.util
import pathlib
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("kt_bot", ROOT / "v3_swing_bot_fixed.py")
BOT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(BOT)
BOT.ENABLE_SMART_MONEY_C_SHADOW = True


def candle(open_price, high, low, close, volume=100.0, idx=0):
    return {
        "open_time": idx * 900_000,
        "open": float(open_price),
        "high": float(high),
        "low": float(low),
        "close": float(close),
        "volume": float(volume),
        "taker_buy": float(volume) * 0.5,
        "taker_sell": float(volume) * 0.5,
        "close_time": (idx + 1) * 900_000 - 1,
    }


def make_4h_context(range_low=99.5):
    candles = []
    for idx in range(31):
        center = 106.0 + (idx % 5) * 0.7
        low = center - 2.0
        high = center + 2.0
        if idx == 4:
            low = range_low
        if idx == 14:
            high = 112.0
        if idx == 20:
            high = 120.0
        candles.append(candle(center - 0.2, high, low, center + 0.2, 500.0, idx))
    candles.append(candle(101.0, 102.0, 99.7, 101.2, 500.0, 31))
    return candles


def make_long_setup():
    candles = []
    for idx in range(40):
        open_price = 100.45 + (idx % 3) * 0.05
        close = open_price + (0.06 if idx % 2 == 0 else -0.04)
        high = max(open_price, close) + 0.25
        low = min(open_price, close) - 0.25
        candles.append(candle(open_price, high, low, close, 100.0, idx))

    # Bentuk minor pivot high terakhir sebelum sweep.
    candles[36].update({"open": 100.7, "high": 101.25, "low": 100.35, "close": 100.65})
    candles[37].update({"open": 100.6, "high": 100.9, "low": 100.3, "close": 100.55})
    candles[38].update({"open": 100.5, "high": 100.8, "low": 100.2, "close": 100.45})
    candles[39].update({"open": 100.45, "high": 100.9, "low": 100.0, "close": 100.4})

    # Sweep -> displacement/MSS + FVG -> continuation -> retest.
    candles.append(candle(100.40, 100.60, 99.80, 100.35, 220.0, 40))
    candles.append(candle(100.45, 101.85, 101.05, 101.75, 150.0, 41))
    candles.append(candle(101.70, 101.90, 101.35, 101.50, 110.0, 42))
    candles.append(candle(101.15, 101.30, 101.00, 101.08, 105.0, 43))
    # Candle terakhir selalu dianggap masih berjalan oleh bot.
    candles.append(candle(101.08, 101.20, 101.00, 101.10, 20.0, 44))
    return candles


def make_short_setup():
    candles = []
    for idx in range(40):
        open_price = 119.45 + (idx % 3) * 0.05
        close = open_price + (0.04 if idx % 2 == 0 else -0.06)
        high = max(open_price, close) + 0.25
        low = min(open_price, close) - 0.25
        candles.append(candle(open_price, high, low, close, 100.0, idx))

    candles[36].update({"open": 119.3, "high": 119.7, "low": 118.70, "close": 119.35})
    candles[37].update({"open": 119.4, "high": 119.75, "low": 119.0, "close": 119.45})
    candles[38].update({"open": 119.5, "high": 119.8, "low": 119.1, "close": 119.55})
    candles[39].update({"open": 119.55, "high": 120.0, "low": 119.35, "close": 119.6})

    candles.append(candle(119.60, 120.20, 119.40, 119.65, 220.0, 40))
    candles.append(candle(119.55, 119.80, 118.90, 119.10, 125.0, 41))
    candles.append(candle(119.00, 119.05, 117.80, 118.00, 150.0, 42))
    candles.append(candle(118.05, 118.50, 117.95, 118.35, 110.0, 43))
    candles.append(candle(119.32, 119.45, 119.15, 119.20, 105.0, 44))
    candles.append(candle(119.20, 119.30, 119.10, 119.18, 20.0, 45))
    return candles


class StrategyCV2Tests(unittest.TestCase):
    def test_valid_long_requires_full_sequence(self):
        signal = BOT.detect_smart_money_c_v2_shadow(
            "TESTUSDT", make_long_setup(), make_4h_context(), "SIDEWAYS"
        )
        self.assertIsNotNone(signal)
        self.assertEqual(signal["bias"], "LONG")
        self.assertEqual(signal["blocked_reason"], "smart_money_c_v2")
        self.assertEqual(signal["meta"]["strategy_version"], "C2")
        self.assertEqual(signal["meta"]["smc_location_zone"], "DISCOUNT")
        self.assertGreaterEqual(signal["meta"]["actual_rr"], BOT.SMC_MIN_RR)

    def test_rejects_sweep_in_middle_of_4h_range(self):
        signal = BOT.detect_smart_money_c_v2_shadow(
            "TESTUSDT", make_long_setup(), make_4h_context(range_low=80.0), "BULLISH"
        )
        self.assertIsNone(signal)

    def test_target_is_structural_not_forced_two_r(self):
        signal = BOT.detect_smart_money_c_v2_shadow(
            "TESTUSDT", make_long_setup(), make_4h_context(), "BULLISH"
        )
        self.assertIsNotNone(signal)
        risk = signal["entry"] - signal["sl"]
        mechanical_two_r = signal["entry"] + 2.0 * risk
        self.assertNotAlmostEqual(signal["tp"], mechanical_two_r, places=5)
        expected = signal["meta"]["smc_target_level"] * (1 - BOT.SMC_TARGET_BUFFER_PCT)
        self.assertAlmostEqual(signal["tp"], expected, places=8)

    def test_valid_short_requires_full_sequence(self):
        signal = BOT.detect_smart_money_c_v2_shadow(
            "TESTUSDT", make_short_setup(), make_4h_context(), "SIDEWAYS"
        )
        self.assertIsNotNone(signal)
        self.assertEqual(signal["bias"], "SHORT")
        self.assertEqual(signal["meta"]["smc_location_zone"], "PREMIUM")
        self.assertGreaterEqual(signal["meta"]["actual_rr"], BOT.SMC_MIN_RR)

    def test_rejects_sweep_without_displacement(self):
        candles = make_long_setup()
        candles[41].update({"open": 100.45, "high": 101.0, "low": 100.3, "close": 100.8, "volume": 105.0})
        signal = BOT.detect_smart_money_c_v2_shadow(
            "TESTUSDT", candles, make_4h_context(), "BULLISH"
        )
        self.assertIsNone(signal)

    def test_report_labels_keep_legacy_separate(self):
        self.assertEqual(BOT._shadow_strategy_label("smart_money_c"), "Jalur C v1 (legacy)")
        self.assertEqual(
            BOT._shadow_strategy_label("smart_money_c_v2"),
            "Jalur C v2 Liquidity Sweep",
        )

    def test_c2_shadow_result_uses_candle_high_low(self):
        original_path = BOT.SHADOW_TRADES_PATH
        original_trades = BOT.shadow_trades
        try:
            with tempfile.TemporaryDirectory() as tmp:
                BOT.SHADOW_TRADES_PATH = str(pathlib.Path(tmp) / "shadow.json")
                BOT.shadow_trades = [{
                    "pair": "TESTUSDT",
                    "bias": "LONG",
                    "blocked_reason": "smart_money_c_v2",
                    "strategy_version": "C2",
                    "entry": 100.0,
                    "sl": 99.0,
                    "tp": 102.0,
                    "timestamp": BOT.now_ms(),
                    "status": "SHADOW_OPEN",
                }]
                candles = [
                    candle(100.0, 100.5, 99.5, 100.2, idx=0),
                    candle(100.2, 102.1, 99.5, 100.5, idx=1),
                    candle(100.5, 100.6, 100.4, 100.5, idx=2),
                ]
                BOT.update_shadow_trades_for_pair("TESTUSDT", candles)
                self.assertEqual(BOT.shadow_trades[0]["status"], "SHADOW_WIN")
                self.assertEqual(BOT.shadow_trades[0]["result_R"], 2.0)
        finally:
            BOT.SHADOW_TRADES_PATH = original_path
            BOT.shadow_trades = original_trades


if __name__ == "__main__":
    unittest.main()
