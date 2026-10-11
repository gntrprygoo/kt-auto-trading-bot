import importlib.util
import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("kt_bot_quality_test", ROOT / "v3_swing_bot_fixed.py")
BOT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(BOT)


def candle(open_price, high, low, close, idx):
    interval_ms = 4 * 60 * 60 * 1000
    return {
        "open_time": idx * interval_ms,
        "open": float(open_price),
        "high": float(high),
        "low": float(low),
        "close": float(close),
        "volume": 1000.0,
        "taker_buy": 500.0,
        "taker_sell": 500.0,
        "close_time": (idx + 1) * interval_ms - 1,
    }


def trend_candles(direction=1, current_close=None):
    candles = []
    for idx in range(60):
        base = 100.0 + direction * idx * 0.45
        high_extra = 3.0 if idx % 4 == 1 else 1.0
        low_extra = 3.0 if idx % 4 == 3 else 1.0
        close = base + direction * 0.10
        candles.append(candle(base, base + high_extra, base - low_extra, close, idx))

    base = candles[-1]["close"]
    if current_close is None:
        current_close = base + direction * 0.45
    candles.append(candle(base, max(base, current_close) + 1.0,
                          min(base, current_close) - 1.0, current_close, 60))
    return candles


class QualityGateV8Tests(unittest.TestCase):
    def test_local_bullish_context_scores_three_of_three(self):
        snapshot = BOT.quality_local_snapshot(trend_candles(1), "LONG")
        self.assertEqual(snapshot["score"], 3)
        self.assertTrue(snapshot["structure"])
        self.assertTrue(snapshot["ema"])
        self.assertTrue(snapshot["momentum_12h"])

    def test_local_bearish_context_scores_three_of_three(self):
        snapshot = BOT.quality_local_snapshot(trend_candles(-1), "SHORT")
        self.assertEqual(snapshot["score"], 3)

    def test_unclosed_spike_does_not_flip_context(self):
        candles = trend_candles(1, current_close=1.0)
        context = BOT.quality_context_4h(candles)
        self.assertEqual(context["structure"], "BULLISH")
        self.assertEqual(context["ema_alignment"], "BULLISH")
        self.assertGreater(context["ret_12h"], 0)

    def test_market_regime_requires_four_of_five(self):
        data = {
            pair: trend_candles(1 if index < 4 else -1)
            for index, pair in enumerate(BOT.QUALITY_MARKET_CORE_PAIRS)
        }
        regime = BOT.classify_quality_market_regime(data)
        self.assertEqual(regime["direction"], "BULLISH")
        self.assertEqual(regime["bull_count"], 4)
        self.assertEqual(regime["bear_count"], 1)

    def test_three_two_market_split_is_neutral(self):
        data = {
            pair: trend_candles(1 if index < 3 else -1)
            for index, pair in enumerate(BOT.QUALITY_MARKET_CORE_PAIRS)
        }
        regime = BOT.classify_quality_market_regime(data)
        self.assertEqual(regime["direction"], "NEUTRAL")

    def test_universe_cap_keeps_core_pairs(self):
        source = [f"PAIR{index}USDT" for index in range(50)] + BOT.CORE_PAIRS
        limited = BOT._limit_pair_universe(source, 30)
        self.assertEqual(len(limited), 30)
        self.assertTrue(set(BOT.CORE_PAIRS).issubset(limited))

    def test_side_aware_long_requires_strict_structure(self):
        snapshot = BOT.quality_local_snapshot(trend_candles(1), "LONG")
        allowed, reason = BOT.quality_live_gate_decision(snapshot, "LONG")
        self.assertTrue(allowed, reason)
        snapshot["structure"] = False
        allowed, reason = BOT.quality_live_gate_decision(snapshot, "LONG")
        self.assertFalse(allowed)
        self.assertEqual(reason, "long_structure_not_bullish")

    def test_side_aware_short_blocks_bottom_range(self):
        snapshot = {
            "context": {"ok": True},
            "ema": True,
            "structure": True,
            "range_position": 0.20,
        }
        allowed, reason = BOT.quality_live_gate_decision(snapshot, "SHORT")
        self.assertFalse(allowed)
        self.assertIn("short_too_low_in_range", reason)
        snapshot["range_position"] = 0.60
        allowed, reason = BOT.quality_live_gate_decision(snapshot, "SHORT")
        self.assertTrue(allowed, reason)

    def test_risk_gate_rejects_three_percent_or_more(self):
        self.assertTrue(BOT.quality_risk_gate_decision(0.0299)[0])
        self.assertFalse(BOT.quality_risk_gate_decision(0.0300)[0])


if __name__ == "__main__":
    unittest.main()
