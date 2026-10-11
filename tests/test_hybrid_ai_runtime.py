import importlib.util
from pathlib import Path
from types import SimpleNamespace
import unittest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("kt_bot_hybrid_ai_test", ROOT / "v3_swing_bot_fixed.py")
BOT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(BOT)


class FakeStore:
    def pending(self, now_ms):
        return []


class FakeEngine:
    def __init__(self):
        self.config = SimpleNamespace(
            max_notional_usdt=10.0,
            preserve_baseline_in_shadow=True,
        )
        self.store = FakeStore()
        self.changed_mode = None

    def summary(self):
        return {
            "enabled": True,
            "mode": "AI_SHADOW",
            "model": "gpt-5.6-luna",
            "api_key_present": True,
            "allow_live": False,
            "live_gate": {"passed": False},
            "statuses": {"SHADOW_ACCEPTED": 3, "SHADOW_SKIPPED": 2},
            "pending": 0,
            "total": 5,
        }

    def set_mode(self, mode):
        self.changed_mode = mode
        return mode


class FakeLiveMarketEngine:
    def summary(self):
        return {
            "enabled": True,
            "mode": "RESEARCH_SHADOW_ONLY",
            "research_status": "REJECTED_HISTORICAL_SHADOW_OBSERVATION_ONLY",
            "model": "gpt-5.6-sol",
            "prompt_id": "P6_RANGE_ABSORPTION_SETUP",
            "prompt_version": "P6_RANGE_ABSORPTION_SETUP_V1_SHADOW",
            "feature_set": "OHLCV_TAKER_RANGE_STRUCTURE_V3",
            "openai_key_present": True,
            "scan_count": 1,
            "decision_counts": {"SETUP": 1, "NO_TRADE": 0},
            "setup_stats": {"closed": 0, "total_r": 0.0},
            "orders_allowed": False,
            "last_error": None,
            "latest": {
                "decision_time_ms": 1_800_000_000_000,
                "binance_auth_verified": True,
                "feature_set": "OHLCV_TAKER_RANGE_STRUCTURE_V3",
                "decision": {
                    "action": "SETUP",
                    "pair": "ETHUSDT",
                    "side": "LONG",
                    "confidence": 0.74,
                    "regime": "RANGE",
                    "setup_quality": 71,
                    "range_basis": "24H",
                    "range_low": 1875.0,
                    "range_high": 1930.0,
                    "entry_zone_low": 1880.0,
                    "entry_zone_high": 1883.0,
                    "entry_trigger": "LOWER_EDGE_SWEEP_RECLAIM",
                    "invalidation_level": 1874.0,
                    "stop_loss": 1872.0,
                    "take_profit_1": 1900.0,
                    "take_profit_2": 1925.0,
                    "expiry_hours": 4,
                    "evidence": ["test evidence one", "test evidence two"],
                    "risk_flags": [],
                    "thesis": "Research-only thesis.",
                    "invalidation_reason": "Acceptance below range support.",
                },
                "validated_plan": {
                    "orders_allowed": False,
                    "cost_adjusted_rr_tp1": 1.15,
                    "cost_adjusted_rr_tp2": 2.75,
                },
                "market_context": {
                    "pair": "ETHUSDT",
                    "quote_currency": "USDT",
                    "last_close": 1909.9,
                    "range_low_24h": 1875.0,
                    "range_high_24h": 1930.0,
                    "range_position_24h_pct": 63.45,
                    "range_low_7d": 1800.0,
                    "range_high_7d": 1950.0,
                    "range_position_7d_pct": 73.27,
                },
                "openai": {"usage": {"total_tokens": 123}},
            },
        }


class HybridAIRuntimeTests(unittest.TestCase):
    def test_help_lists_hybrid_ai_controls(self):
        text = BOT.build_help_text()
        self.assertIn("/ai_status - status Hybrid AI Engine", text)
        self.assertIn("/ai_market - analisis market live OpenAI", text)
        self.assertIn("/ai_approve ID", text)

    def test_live_market_text_is_explicitly_shadow_only(self):
        original = BOT.get_live_ai_market_engine
        try:
            BOT.get_live_ai_market_engine = lambda reset=False: FakeLiveMarketEngine()
            text = BOT.build_live_ai_market_text()
        finally:
            BOT.get_live_ai_market_engine = original
        self.assertIn("RESEARCH SHADOW ONLY", text)
        self.assertIn("Order access: LOCKED", text)
        self.assertIn("ETHUSDT / LONG", text)
        self.assertIn("Harga close : 1909.90 USDT", text)
        self.assertIn("posisi 73.27%", text)
        self.assertIn("Setup P6 tervalidasi", text)
        self.assertIn("Entry zone  : 1880.00 - 1883.00", text)
        self.assertIn("SL          : 1872.00", text)
        self.assertNotIn("test-openai-key", text)

    def test_setup_and_lifecycle_alerts_remain_shadow_only(self):
        setup_result = {
            "decision": FakeLiveMarketEngine().summary()["latest"]["decision"],
            "validated_plan": {
                "cost_adjusted_rr_tp1": 1.15,
                "cost_adjusted_rr_tp2": 2.75,
            },
            "setup": {"id": "P6S-TEST"},
        }
        setup_text = BOT._build_live_ai_setup_alert(setup_result)
        self.assertIn("P6 RANGE SETUP (SHADOW)", setup_text)
        self.assertIn("Tidak ada order Binance", setup_text)
        lifecycle_text = BOT._build_live_ai_lifecycle_alert(
            {
                "events": [{"event": "TP2_HIT", "price": 1925.0}],
                "setup": {
                    "id": "P6S-TEST",
                    "pair": "ETHUSDT",
                    "side": "LONG",
                    "status": "TP2_HIT",
                    "result_r": 1.8,
                },
            }
        )
        self.assertIn("TP2 shadow tercapai", lifecycle_text)
        self.assertIn("+1.80R", lifecycle_text)

    def test_status_does_not_expose_api_key(self):
        original = BOT.get_hybrid_ai_engine
        try:
            BOT.get_hybrid_ai_engine = lambda reset=False: FakeEngine()
            text = BOT.build_hybrid_ai_status_text()
        finally:
            BOT.get_hybrid_ai_engine = original
        self.assertIn("OpenAI key  : READY", text)
        self.assertNotIn("sk-", text)
        self.assertIn("Replay gate : LOCKED", text)

    def test_non_admin_cannot_change_ai_mode(self):
        original = BOT.is_admin_chat
        try:
            BOT.is_admin_chat = lambda chat_id: False
            text = BOT.handle_hybrid_ai_command(
                "/ai_mode", ["/ai_mode", "live"], "user", None, None
            )
        finally:
            BOT.is_admin_chat = original
        self.assertIn("ACCESS DENIED", text)

    def test_admin_can_select_shadow_mode(self):
        fake = FakeEngine()
        original_engine = BOT.get_hybrid_ai_engine
        original_admin = BOT.is_admin_chat
        try:
            BOT.get_hybrid_ai_engine = lambda reset=False: fake
            BOT.is_admin_chat = lambda chat_id: True
            text = BOT.handle_hybrid_ai_command(
                "/ai_mode", ["/ai_mode", "shadow"], "admin", "key", "secret"
            )
        finally:
            BOT.get_hybrid_ai_engine = original_engine
            BOT.is_admin_chat = original_admin
        self.assertEqual(fake.changed_mode, "AI_SHADOW")
        self.assertIn("Mode aktif: AI_SHADOW", text)

    def test_quantity_blocks_exchange_minimum_above_cap(self):
        config = SimpleNamespace(max_notional_usdt=10.0)
        with self.assertRaises(BOT.HybridAIError):
            BOT._hybrid_quantity_spec(
                entry=100000.0,
                sl=98000.0,
                step="0.001",
                min_qty=0.001,
                min_notional=5.0,
                config=config,
            )

    def test_quantity_for_small_contract_stays_under_cap(self):
        config = SimpleNamespace(max_notional_usdt=10.0)
        result = BOT._hybrid_quantity_spec(
            entry=2000.0,
            sl=1960.0,
            step="0.001",
            min_qty=0.001,
            min_notional=5.0,
            config=config,
        )
        self.assertLessEqual(result["notional_usdt"], 10.02)
        self.assertEqual(result["qty_str"], "0.005")

    def test_daily_ai_stop_uses_close_day_not_entry_day(self):
        now_value = 1_800_000_000_000
        original = BOT.journal
        try:
            BOT.journal = [{
                "timestamp": now_value - 2 * 24 * 60 * 60 * 1000,
                "closed_at": now_value - 60 * 60 * 1000,
                "status": "SL",
                "result_R": -1.2,
                "hybrid_ai": {"proposal_id": "AI-TEST"},
            }]
            context = BOT._hybrid_runtime_context(
                "ETHUSDT",
                {"totalWalletBalance": "1000", "availableBalance": "900"},
                now_value=now_value,
            )
        finally:
            BOT.journal = original
        self.assertAlmostEqual(context["daily_r"], -1.2)


if __name__ == "__main__":
    unittest.main()
