import importlib.util
import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "kt_bot_shadow_retirement_test",
    ROOT / "v3_swing_bot_fixed.py",
)
BOT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(BOT)


class ShadowRetirementRuntimeTests(unittest.TestCase):
    def test_retired_volume_shadow_is_disabled_by_default(self):
        self.assertFalse(BOT.ENABLE_JALUR_A_VOLUME_SHADOW)
        self.assertFalse(BOT.SHADOW_DAILY_REPORT_ENABLED)

    def test_shadow_command_reports_only_active_c6(self):
        trades = [
            {
                "pair": "OLDUSDT",
                "bias": "LONG",
                "blocked_reason": "smart_money_c",
                "status": "SHADOW_LOSS",
                "result_R": -1.0,
                "timestamp": 1,
            },
            {
                "pair": "AUSDT",
                "bias": "LONG",
                "blocked_reason": "vol_too_high",
                "status": "SHADOW_WIN",
                "result_R": 5.0,
                "timestamp": 2,
            },
            {
                "pair": "C6USDT",
                "bias": "SHORT",
                "blocked_reason": "smart_money_c_v6",
                "strategy_version": "C6",
                "status": "SHADOW_WIN",
                "result_R": 1.5,
                "entry": 100.0,
                "sl": 101.0,
                "tp": 98.5,
                "timestamp": 3,
                "closed_at": 4,
            },
        ]
        old_enabled = BOT.ENABLE_SMART_MONEY_C_SHADOW
        old_version = BOT.SMART_MONEY_C_VERSION
        try:
            BOT.ENABLE_SMART_MONEY_C_SHADOW = True
            BOT.SMART_MONEY_C_VERSION = 6
            text = BOT.build_shadow_command_text(trades)
        finally:
            BOT.ENABLE_SMART_MONEY_C_SHADOW = old_enabled
            BOT.SMART_MONEY_C_VERSION = old_version

        self.assertIn("Progress    : 1 / 30 closed", text)
        self.assertIn("Total R     : +1.50R", text)
        self.assertIn("COLLECTING - NOT APPROVED LIVE", text)
        self.assertNotIn("OLDUSDT", text)
        self.assertNotIn("AUSDT", text)
        self.assertIn("Legacy tersisa di file aktif: 2", text)

    def test_live_strategy_a_status_is_unchanged(self):
        text = BOT.build_status_text()
        self.assertIn("Strategi    : A LIVE", text)


if __name__ == "__main__":
    unittest.main()
