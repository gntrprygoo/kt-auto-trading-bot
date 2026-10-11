import importlib.util
import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "kt_bot_strategy_c_v6_test",
    ROOT / "v3_swing_bot_fixed.py",
)
BOT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(BOT)


def candle(index, close=104.0, high=104.2, low=103.8, open_price=104.0,
           volume=100.0, buy=50.0, interval_ms=900_000):
    return {
        "open_time": index * interval_ms,
        "close_time": (index + 1) * interval_ms - 1,
        "open": float(open_price),
        "high": float(high),
        "low": float(low),
        "close": float(close),
        "volume": float(volume),
        "taker_buy": float(buy),
        "taker_sell": max(0.0, float(volume) - float(buy)),
    }


def four_hour_uptrend():
    candles = []
    for index in range(70):
        price = 100.0 + index * 0.10
        candles.append(candle(
            index,
            close=price,
            high=price + 1.0,
            low=price - 1.0,
            open_price=price,
            interval_ms=4 * 60 * 60 * 1000,
        ))
    candles.append(candle(
        70,
        close=107.0,
        high=107.2,
        low=106.8,
        open_price=106.9,
        interval_ms=4 * 60 * 60 * 1000,
    ))
    return candles


def long_setup(absorption_buy=40.0):
    candles = [candle(index) for index in range(45)]
    candles.append(candle(
        45,
        close=103.9,
        high=104.1,
        low=103.5,
        open_price=104.0,
        volume=100.0,
        buy=absorption_buy,
    ))
    candles.append(candle(
        46,
        close=104.6,
        high=104.7,
        low=103.8,
        open_price=103.9,
        volume=120.0,
        buy=75.0,
    ))
    candles.append(candle(
        47,
        close=104.4,
        high=104.5,
        low=104.15,
        open_price=104.25,
        volume=100.0,
        buy=55.0,
    ))
    candles.append(candle(
        48,
        close=104.4,
        high=104.45,
        low=104.35,
        open_price=104.4,
        volume=10.0,
        buy=5.0,
    ))
    return candles


class StrategyCV6Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.original_version = BOT.SMART_MONEY_C_VERSION
        cls.original_enabled = BOT.ENABLE_SMART_MONEY_C_SHADOW
        BOT.SMART_MONEY_C_VERSION = 6
        BOT.ENABLE_SMART_MONEY_C_SHADOW = True

    @classmethod
    def tearDownClass(cls):
        BOT.SMART_MONEY_C_VERSION = cls.original_version
        BOT.ENABLE_SMART_MONEY_C_SHADOW = cls.original_enabled

    def test_valid_sequence_is_shadow_only_with_fixed_target(self):
        signal = BOT.detect_smart_money_c_shadow(
            "TESTUSDT",
            long_setup(),
            four_hour_uptrend(),
            "BULLISH",
            market_context={"trend": "BULLISH", "ret_12h": 0.01},
        )
        self.assertIsNotNone(signal)
        self.assertEqual(signal["blocked_reason"], "smart_money_c_v6")
        self.assertEqual(signal["meta"]["strategy_version"], "C6")
        risk = signal["entry"] - signal["sl"]
        self.assertAlmostEqual(signal["tp"], signal["entry"] + 1.5 * risk)
        self.assertEqual(signal["meta"]["shadow_timeout_hours"], 96)

    def test_opposite_btc_regime_blocks_signal(self):
        signal = BOT.detect_smart_money_c_shadow(
            "TESTUSDT",
            long_setup(),
            four_hour_uptrend(),
            "BULLISH",
            market_context={"trend": "BEARISH", "ret_12h": -0.02},
        )
        self.assertIsNone(signal)

    def test_missing_absorption_blocks_signal(self):
        signal = BOT.detect_smart_money_c_shadow(
            "TESTUSDT",
            long_setup(absorption_buy=60.0),
            four_hour_uptrend(),
            "BULLISH",
            market_context={"trend": "BULLISH", "ret_12h": 0.01},
        )
        self.assertIsNone(signal)

    def test_report_label_keeps_c6_separate(self):
        self.assertEqual(
            BOT._shadow_strategy_key({"strategy_version": "C6"}),
            "smart_money_c_v6",
        )
        self.assertEqual(
            BOT._shadow_strategy_label("smart_money_c_v6"),
            "Jalur C v6 Market Liquidity Sweep",
        )


if __name__ == "__main__":
    unittest.main()
