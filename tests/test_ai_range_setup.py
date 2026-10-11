import json
import os
import unittest

from ai_market_scanner import MarketScannerConfig, MarketScannerError
from ai_range_setup import (
    RANGE_SETUP_PROMPT_VERSION,
    OpenAIRangeSetupClient,
    RangeSetupDecision,
    range_setup_prompt_definition,
    validate_range_setup,
)
from range_setup_shadow import (
    apply_terminal_stats,
    create_shadow_setup,
    empty_setup_stats,
    update_shadow_setup,
)


UNIVERSE = ["BTCUSDT", "XRPUSDT"]


def valid_setup(**changes):
    value = {
        "action": "SETUP",
        "pair": "XRPUSDT",
        "side": "SHORT",
        "regime": "RANGE",
        "range_basis": "24H",
        "range_low": 90.0,
        "range_high": 110.0,
        "entry_zone_low": 107.8,
        "entry_zone_high": 108.0,
        "entry_trigger": "UPPER_EDGE_SWEEP_RECLAIM",
        "invalidation_level": 110.1,
        "stop_loss": 110.5,
        "take_profit_1": 103.0,
        "take_profit_2": 92.0,
        "expiry_hours": 4,
        "confidence": 0.72,
        "setup_quality": 74,
        "evidence": [
            "Upper-edge sweep closed back inside the range.",
            "The sweep bar closed in the lower half of its range.",
        ],
        "risk_flags": [],
        "thesis": "Failed upside auction supports range reversion.",
        "invalidation_reason": "Acceptance above the confirmed range high.",
    }
    value.update(changes)
    return value


def no_trade():
    return {
        "action": "NO_TRADE",
        "pair": "NONE",
        "side": "NONE",
        "regime": "TREND",
        "range_basis": "NONE",
        "range_low": 0,
        "range_high": 0,
        "entry_zone_low": 0,
        "entry_zone_high": 0,
        "entry_trigger": "NONE",
        "invalidation_level": 0,
        "stop_loss": 0,
        "take_profit_1": 0,
        "take_profit_2": 0,
        "expiry_hours": 0,
        "confidence": 0.91,
        "setup_quality": 20,
        "evidence": ["BTC shows accepted expansion."],
        "risk_flags": ["Market is not range-bound."],
        "thesis": "Range-reversion conditions are absent.",
        "invalidation_reason": "Reassess after a confirmed range forms.",
    }


def snapshot():
    return {
        "schema": "KT_AI_MARKET_SCANNER_V1",
        "snapshot_id": "TEST-RANGE-1",
        "decision_time_ms": 1_000_000,
        "universe": list(UNIVERSE),
        "market": {
            "BTCUSDT": {
                "last_close": 100_000.0,
                "tick_size": 0.1,
            },
            "XRPUSDT": {
                "last_close": 108.0,
                "tick_size": 0.1,
                "atr_price": 2.0,
                "range_low_24h": 90.0,
                "range_high_24h": 110.0,
                "range_low_7d": 85.0,
                "range_high_7d": 115.0,
                "recent_swing_lows_1h": [{"price": 92.0}],
                "recent_swing_highs_1h": [{"price": 110.0}],
                "recent_15m_bars": [
                    {
                        "open": 108.5,
                        "high": 109.2,
                        "low": 107.6,
                        "close": 108.8,
                        "close_location": 0.75,
                        "volume_ratio": 0.9,
                        "taker_flow": 0.15,
                    },
                    {
                        "open": 109.0,
                        "high": 110.0,
                        "low": 107.8,
                        "close": 108.5,
                        "close_location": 0.32,
                        "volume_ratio": 1.4,
                        "taker_flow": -0.2,
                    },
                ],
            },
        },
        "execution_contract": {"orders_allowed": False},
    }


def candle(index, open_price, high, low, close):
    open_time = 1_000_001 + index * 900_000
    return {
        "open_time": open_time,
        "close_time": open_time + 899_999,
        "open": open_price,
        "high": high,
        "low": low,
        "close": close,
    }


class RangeSetupTests(unittest.TestCase):
    def test_prompt_is_explicitly_shadow_only_and_structured(self):
        prompt = range_setup_prompt_definition()
        self.assertEqual(prompt["version"], RANGE_SETUP_PROMPT_VERSION)
        self.assertIn("shadow research", prompt["instructions"])
        self.assertIn("never calculate position size", prompt["instructions"])

    def test_valid_setup_geometry_is_cost_checked(self):
        decision = RangeSetupDecision.from_mapping(valid_setup(), UNIVERSE)
        validation = validate_range_setup(decision, snapshot())
        self.assertEqual(validation["status"], "VALIDATED_SHADOW_ONLY")
        self.assertFalse(validation["orders_allowed"])
        self.assertGreaterEqual(validation["cost_adjusted_rr_tp1"], 1.0)
        self.assertGreaterEqual(validation["cost_adjusted_rr_tp2"], 1.8)

    def test_invalid_tick_range_and_rr_fail_closed(self):
        with self.assertRaisesRegex(MarketScannerError, "tick size"):
            validate_range_setup(
                RangeSetupDecision.from_mapping(
                    valid_setup(entry_zone_low=107.85), UNIVERSE
                ),
                snapshot(),
            )
        with self.assertRaisesRegex(MarketScannerError, "not grounded"):
            validate_range_setup(
                RangeSetupDecision.from_mapping(
                    valid_setup(range_low=91.0), UNIVERSE
                ),
                snapshot(),
            )
        with self.assertRaisesRegex(MarketScannerError, "R:R below gate"):
            validate_range_setup(
                RangeSetupDecision.from_mapping(
                    valid_setup(take_profit_1=105.0, take_profit_2=102.0), UNIVERSE
                ),
                snapshot(),
            )

    def test_no_trade_has_no_geometry(self):
        decision = RangeSetupDecision.from_mapping(no_trade(), UNIVERSE)
        self.assertEqual(decision.action, "NO_TRADE")
        self.assertIsNone(validate_range_setup(decision, snapshot()))

    def test_openai_request_uses_strict_schema_and_store_false(self):
        captured = {}

        def transport(_url, payload, _headers, _timeout):
            captured.update(payload)
            return {
                "id": "resp_test",
                "model": "test-model",
                "output_text": json.dumps(no_trade()),
                "usage": {"total_tokens": 100},
            }

        original = os.environ.get("TEST_OPENAI_KEY")
        os.environ["TEST_OPENAI_KEY"] = "test-key"
        try:
            client = OpenAIRangeSetupClient(
                MarketScannerConfig(api_key_env="TEST_OPENAI_KEY"), transport=transport
            )
            decision, metadata = client.decide(snapshot())
        finally:
            if original is None:
                os.environ.pop("TEST_OPENAI_KEY", None)
            else:
                os.environ["TEST_OPENAI_KEY"] = original
        self.assertEqual(decision.action, "NO_TRADE")
        self.assertFalse(captured["store"])
        self.assertTrue(captured["text"]["format"]["strict"])
        self.assertEqual(metadata["prompt_version"], RANGE_SETUP_PROMPT_VERSION)

    def test_shadow_lifecycle_fill_tp1_tp2_and_stats(self):
        decision = RangeSetupDecision.from_mapping(valid_setup(), UNIVERSE)
        validation = validate_range_setup(decision, snapshot())
        setup = create_shadow_setup(decision, validation, 1_000_000)
        bars = [
            candle(0, 108.2, 108.3, 107.9, 108.0),
            candle(1, 107.9, 108.0, 102.9, 103.2),
            candle(2, 103.2, 103.4, 91.8, 92.2),
        ]
        updated, events = update_shadow_setup(setup, bars, bars[-1]["close_time"])
        self.assertEqual(updated["status"], "TP2_HIT")
        self.assertTrue(updated["tp1_hit"])
        self.assertGreater(updated["result_r"], 0)
        self.assertEqual([event["event"] for event in events], ["FILLED", "TP1_HIT", "TP2_HIT"])
        stats = apply_terminal_stats(empty_setup_stats(), updated)
        self.assertEqual(stats["closed"], 1)
        self.assertEqual(stats["wins"], 1)

    def test_same_bar_stop_and_target_is_scored_as_stop(self):
        decision = RangeSetupDecision.from_mapping(valid_setup(), UNIVERSE)
        validation = validate_range_setup(decision, snapshot())
        setup = create_shadow_setup(decision, validation, 1_000_000)
        bar = candle(0, 108.0, 111.0, 91.0, 100.0)
        updated, events = update_shadow_setup(setup, [bar], bar["close_time"])
        self.assertEqual(updated["status"], "SL_HIT")
        self.assertLess(updated["result_r"], 0)
        self.assertEqual([event["event"] for event in events], ["FILLED", "SL_HIT"])

    def test_same_entry_bar_target_is_not_awarded_without_path_order(self):
        decision = RangeSetupDecision.from_mapping(valid_setup(), UNIVERSE)
        validation = validate_range_setup(decision, snapshot())
        setup = create_shadow_setup(decision, validation, 1_000_000)
        bar = candle(0, 108.2, 108.3, 102.5, 103.2)
        updated, events = update_shadow_setup(setup, [bar], bar["close_time"])
        self.assertEqual(updated["status"], "ACTIVE")
        self.assertFalse(updated["tp1_hit"])
        self.assertEqual([event["event"] for event in events], ["FILLED"])

    def test_time_exit_uses_last_confirmed_price_at_expiry(self):
        decision = RangeSetupDecision.from_mapping(
            valid_setup(expiry_hours=1), UNIVERSE
        )
        validation = validate_range_setup(decision, snapshot())
        setup = create_shadow_setup(decision, validation, 1_000_000)
        first = candle(0, 108.0, 108.2, 107.9, 108.1)
        active, _events = update_shadow_setup(setup, [first], first["close_time"])
        after_expiry = candle(5, 105.0, 105.2, 104.8, 105.1)
        updated, events = update_shadow_setup(
            active,
            [after_expiry],
            setup["expires_at_ms"] + 1,
        )
        self.assertEqual(updated["status"], "TIME_EXIT")
        self.assertEqual(updated["closed_at_ms"], setup["expires_at_ms"])
        self.assertAlmostEqual(updated["exit_price"], 108.1)
        self.assertEqual([event["event"] for event in events], ["TIME_EXIT"])


if __name__ == "__main__":
    unittest.main()
