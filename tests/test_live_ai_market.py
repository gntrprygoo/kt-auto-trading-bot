import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest

from ai_range_setup import RangeSetupDecision
from live_ai_market import (
    HOUR_MS,
    LiveAIMarketConfig,
    LiveAIMarketEngine,
    build_live_snapshot,
)
from range_setup_shadow import create_shadow_setup
from tools.build_ai_market_dataset import market_features, prepare_symbol


SYMBOLS = ("BTCUSDT", "ETHUSDT")
SYMBOL_RULES = {
    "BTCUSDT": {"tick_size": 0.1},
    "ETHUSDT": {"tick_size": 0.01},
}


def candles(symbol, count=700, extra_open=False):
    multiplier = 1.0 if symbol == "BTCUSDT" else 0.06
    rows = []
    for index in range(count):
        open_time = index * 15 * 60 * 1000
        base = (30000.0 + index * 3.0 + (index % 11) * 2.0) * multiplier
        close = base * (1.001 if index % 2 == 0 else 0.999)
        volume = 1000.0 + index
        rows.append(
            {
                "open_time": open_time,
                "close_time": open_time + 15 * 60 * 1000 - 1,
                "open": base,
                "high": max(base, close) * 1.002,
                "low": min(base, close) * 0.998,
                "close": close,
                "volume": volume,
                "taker_buy": volume * (0.55 if index % 3 else 0.45),
                "taker_sell": volume * (0.45 if index % 3 else 0.55),
            }
        )
    if extra_open:
        row = dict(rows[-1])
        row["open_time"] += 15 * 60 * 1000
        row["close_time"] += 15 * 60 * 1000
        row["close"] *= 5
        rows.append(row)
    return rows


def no_trade_decision():
    return RangeSetupDecision.from_mapping(
        {
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
            "confidence": 0.74,
            "setup_quality": 71,
            "evidence": ["test evidence"],
            "risk_flags": ["accepted trend"],
            "thesis": "Test-only live shadow thesis.",
            "invalidation_reason": "Reassess when the market returns to a range.",
        },
        list(SYMBOLS),
    )


class FakeClient:
    def __init__(self):
        self.config = SimpleNamespace(api_key="test-openai-key")
        self.calls = []

    def decide(self, snapshot, prompt_id):
        self.calls.append((snapshot, prompt_id))
        return no_trade_decision(), {
            "model": "test-model",
            "usage": {"total_tokens": 123},
        }


class BadGroundingClient(FakeClient):
    def decide(self, snapshot, prompt_id):
        self.calls.append((snapshot, prompt_id))
        decision = RangeSetupDecision.from_mapping(
            {
                "action": "SETUP",
                "pair": "ETHUSDT",
                "side": "LONG",
                "regime": "RANGE",
                "range_basis": "24H",
                "range_low": 90,
                "range_high": 110,
                "entry_zone_low": 91,
                "entry_zone_high": 92,
                "entry_trigger": "LOWER_EDGE_ABSORPTION",
                "invalidation_level": 89,
                "stop_loss": 88,
                "take_profit_1": 100,
                "take_profit_2": 108,
                "expiry_hours": 4,
                "confidence": 0.74,
                "setup_quality": 71,
                "evidence": [
                    "ETH remains near its lower 7d range at 0.2054",
                    "The latest confirmed bar reclaimed its lower edge.",
                ],
                "risk_flags": [],
                "thesis": "Test-only live shadow thesis.",
                "invalidation_reason": "Lower-edge reclaim fails.",
            },
            list(SYMBOLS),
        )
        return decision, {"model": "test-model", "usage": {"total_tokens": 123}}


class BadNoTradeGroundingClient(FakeClient):
    def decide(self, snapshot, prompt_id):
        self.calls.append((snapshot, prompt_id))
        value = no_trade_decision().as_dict()
        value["evidence"] = ["BTC closed at 0.2054 after an hourly advance."]
        decision = RangeSetupDecision.from_mapping(value, list(SYMBOLS))
        return decision, {"model": "test-model", "usage": {"total_tokens": 123}}


class LiveAIMarketTests(unittest.TestCase):
    def test_snapshot_uses_confirmed_full_hour_and_matches_research_features(self):
        data = {symbol: candles(symbol, extra_open=True) for symbol in SYMBOLS}
        now_ms_value = data["BTCUSDT"][-2]["close_time"] + 1
        snapshot = build_live_snapshot(
            data,
            SYMBOLS,
            symbol_rules=SYMBOL_RULES,
            now_ms_value=now_ms_value,
        )
        self.assertEqual(snapshot["decision_time_ms"], data["BTCUSDT"][-2]["close_time"])
        self.assertEqual(data["BTCUSDT"][-2]["open_time"] % HOUR_MS, 45 * 60 * 1000)
        self.assertFalse(snapshot["execution_contract"]["orders_allowed"])
        serialized = json.dumps(snapshot)
        self.assertNotIn("api_key", serialized.lower())
        self.assertNotIn("api_secret", serialized.lower())

        aligned = {symbol: data[symbol][:-1] for symbol in SYMBOLS}
        features = {symbol: prepare_symbol(aligned[symbol]) for symbol in SYMBOLS}
        expected = market_features(
            "ETHUSDT",
            aligned["ETHUSDT"],
            features["ETHUSDT"],
            len(aligned["ETHUSDT"]) - 1,
            features["BTCUSDT"],
        )
        actual = snapshot["market"]["ETHUSDT"]
        for key, value in expected.items():
            if key in ("range_position_24h", "range_position_7d"):
                continue
            self.assertEqual(actual[key], value)
        self.assertNotIn("range_position_24h", actual)
        self.assertNotIn("range_position_7d", actual)
        self.assertEqual(
            actual["range_position_24h_pct"],
            round(expected["range_position_24h"] * 100, 2),
        )
        self.assertEqual(
            actual["range_position_7d_pct"],
            round(expected["range_position_7d"] * 100, 2),
        )
        self.assertAlmostEqual(actual["range_low_24h"], features["ETHUSDT"]["low_24h"][-1])
        self.assertAlmostEqual(actual["range_high_24h"], features["ETHUSDT"]["high_24h"][-1])
        self.assertAlmostEqual(actual["range_low_7d"], features["ETHUSDT"]["low_7d"][-1])
        self.assertAlmostEqual(actual["range_high_7d"], features["ETHUSDT"]["high_7d"][-1])
        semantics = snapshot["data_contract"]["numeric_semantics"]
        self.assertEqual(semantics["percentage_scale"], "0_TO_100_NOT_A_PRICE")
        self.assertEqual(actual["tick_size"], 0.01)
        self.assertIn("recent_15m_bars", actual)
        self.assertIn("recent_hourly_bars", actual)

    def test_snapshot_fails_closed_on_missing_tick_or_candle_gap(self):
        data = {symbol: candles(symbol, count=704) for symbol in SYMBOLS}
        with self.assertRaisesRegex(Exception, "tick size"):
            build_live_snapshot(
                data,
                SYMBOLS,
                symbol_rules={"BTCUSDT": {"tick_size": 0.1}},
                now_ms_value=data["BTCUSDT"][-1]["close_time"] + 1,
                min_closed_bars=700,
            )
        data["BTCUSDT"].pop(100)
        with self.assertRaisesRegex(Exception, "time gap"):
            build_live_snapshot(
                data,
                SYMBOLS,
                symbol_rules=SYMBOL_RULES,
                now_ms_value=data["ETHUSDT"][-1]["close_time"] + 1,
                min_closed_bars=700,
            )

    def test_unverified_binance_blocks_openai_call(self):
        with tempfile.TemporaryDirectory() as directory:
            config = LiveAIMarketConfig.from_mapping(
                {
                    "enabled": True,
                    "symbols": list(SYMBOLS),
                    "state_path": str(Path(directory) / "state.json"),
                    "history_path": str(Path(directory) / "history.jsonl"),
                },
                directory,
            )
            client = FakeClient()
            engine = LiveAIMarketEngine(config, client=client, now_ms_fn=lambda: 700 * 900000)
            result = engine.run_once(lambda *_: [], binance_auth_verified=False)
            self.assertEqual(result["status"], "ERROR")
            self.assertEqual(client.calls, [])
            self.assertIn("not verified", engine.summary()["last_error"])

    def test_success_is_recorded_once_and_never_allows_orders(self):
        with tempfile.TemporaryDirectory() as directory:
            config = LiveAIMarketConfig.from_mapping(
                {
                    "enabled": True,
                    "symbols": list(SYMBOLS),
                    "state_path": str(Path(directory) / "state.json"),
                    "history_path": str(Path(directory) / "history.jsonl"),
                },
                directory,
            )
            client = FakeClient()
            current = [700 * 900000]
            engine = LiveAIMarketEngine(config, client=client, now_ms_fn=lambda: current[0])
            source = {symbol: candles(symbol) for symbol in SYMBOLS}
            fetch = lambda symbol, _interval, _limit: source[symbol]

            first = engine.run_once(
                fetch, binance_auth_verified=True, symbol_rules=SYMBOL_RULES
            )
            second = engine.run_once(
                fetch, binance_auth_verified=True, symbol_rules=SYMBOL_RULES
            )
            self.assertEqual(first["status"], "RECORDED_SHADOW_ONLY")
            self.assertEqual(second["status"], "DUPLICATE")
            self.assertEqual(len(client.calls), 1)
            summary = engine.summary()
            self.assertFalse(summary["orders_allowed"])
            self.assertEqual(summary["scan_count"], 1)
            history = Path(config.history_path).read_text(encoding="utf-8").splitlines()
            self.assertEqual(len(history), 1)
            record = json.loads(history[0])
            self.assertFalse(record["orders_allowed"])
            self.assertTrue(record["binance_auth_verified"])
            self.assertIsNone(record["market_context"])
            self.assertIsNone(record["validated_plan"])

    def test_ungrounded_range_position_cannot_be_recorded_as_price(self):
        with tempfile.TemporaryDirectory() as directory:
            config = LiveAIMarketConfig.from_mapping(
                {
                    "enabled": True,
                    "symbols": list(SYMBOLS),
                    "state_path": str(Path(directory) / "state.json"),
                    "history_path": str(Path(directory) / "history.jsonl"),
                },
                directory,
            )
            client = BadGroundingClient()
            engine = LiveAIMarketEngine(
                config, client=client, now_ms_fn=lambda: 700 * 900000
            )
            source = {symbol: candles(symbol) for symbol in SYMBOLS}
            result = engine.run_once(
                lambda symbol, _interval, _limit: source[symbol],
                binance_auth_verified=True,
                symbol_rules=SYMBOL_RULES,
            )
            self.assertEqual(result["status"], "ERROR")
            self.assertIn("ungrounded AI price claim", result["error"])
            self.assertEqual(engine.summary()["scan_count"], 0)
            self.assertFalse(Path(config.history_path).exists())

    def test_no_trade_narrative_price_is_still_symbol_grounded(self):
        with tempfile.TemporaryDirectory() as directory:
            config = LiveAIMarketConfig.from_mapping(
                {
                    "enabled": True,
                    "symbols": list(SYMBOLS),
                    "state_path": str(Path(directory) / "state.json"),
                    "history_path": str(Path(directory) / "history.jsonl"),
                },
                directory,
            )
            engine = LiveAIMarketEngine(
                config,
                client=BadNoTradeGroundingClient(),
                now_ms_fn=lambda: 700 * 900000,
            )
            source = {symbol: candles(symbol) for symbol in SYMBOLS}
            result = engine.run_once(
                lambda symbol, _interval, _limit: source[symbol],
                binance_auth_verified=True,
                symbol_rules=SYMBOL_RULES,
            )
            self.assertEqual(result["status"], "ERROR")
            self.assertIn("ungrounded AI price claim for BTCUSDT", result["error"])
            self.assertEqual(engine.summary()["scan_count"], 0)

    def test_active_setup_monitor_uses_only_public_pair_data(self):
        with tempfile.TemporaryDirectory() as directory:
            config = LiveAIMarketConfig.from_mapping(
                {
                    "enabled": True,
                    "symbols": list(SYMBOLS),
                    "setup_monitor_interval_sec": 300,
                    "state_path": str(Path(directory) / "state.json"),
                    "history_path": str(Path(directory) / "history.jsonl"),
                },
                directory,
            )
            now_value = 700 * 900000
            decision = RangeSetupDecision.from_mapping(
                {
                    "action": "SETUP",
                    "pair": "ETHUSDT",
                    "side": "SHORT",
                    "regime": "RANGE",
                    "range_basis": "24H",
                    "range_low": 1.0,
                    "range_high": 2.0,
                    "entry_zone_low": 1_000_000.0,
                    "entry_zone_high": 1_000_001.0,
                    "entry_trigger": "UPPER_EDGE_ABSORPTION",
                    "invalidation_level": 1_000_002.0,
                    "stop_loss": 1_000_003.0,
                    "take_profit_1": 0.8,
                    "take_profit_2": 0.5,
                    "expiry_hours": 4,
                    "confidence": 0.7,
                    "setup_quality": 70,
                    "evidence": ["Confirmed edge test.", "Confirmed inward close."],
                    "risk_flags": [],
                    "thesis": "Lifecycle monitor fixture.",
                    "invalidation_reason": "Fixture invalidation.",
                },
                list(SYMBOLS),
            )
            created_at = now_value - 10 * 60 * 1000
            setup = create_shadow_setup(
                decision,
                {"orders_allowed": False, "round_trip_cost_pct": 0.002},
                created_at,
            )
            engine = LiveAIMarketEngine(
                config, client=FakeClient(), now_ms_fn=lambda: now_value
            )
            state = engine.store.empty()
            state["active_setup"] = setup
            state["last_ai_scan_ms"] = created_at
            state["last_success_ms"] = created_at
            engine.store.save(state)
            self.assertTrue(engine.due())
            source = {symbol: candles(symbol) for symbol in SYMBOLS}
            calls = []

            def fetch(symbol, interval, limit):
                calls.append((symbol, interval, limit))
                return source[symbol]

            result = engine.run_once(fetch, binance_auth_verified=False)
            self.assertEqual(result["status"], "MONITORED_SHADOW_SETUP")
            self.assertEqual([item[0] for item in calls], ["ETHUSDT"])
            self.assertLessEqual(calls[0][2], 96)


if __name__ == "__main__":
    unittest.main()
