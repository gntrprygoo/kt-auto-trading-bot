import importlib.util
import json
import pathlib
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "kt_bot_d1_telegram_test",
    ROOT / "v3_swing_bot_fixed.py",
)
BOT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(BOT)

NOW_MS = 1_800_000_000_000
DAY_MS = 24 * 3600 * 1000


def make_state(**overrides):
    state = {
        "schema": BOT.D1_SHADOW_SCHEMA,
        "monitor_started_at": NOW_MS - 10 * DAY_MS,
        "last_poll_at": NOW_MS - 10 * 60 * 1000,
        "last_closed_4h": NOW_MS - 4 * 3600 * 1000,
        "closed_trades": [],
        "current_position": None,
        "funding_reconciliation": {
            "source": "BINANCE_PUBLIC_FUNDING_RATE_HISTORY",
            "last_reconciled_at": NOW_MS - 10 * 60 * 1000,
            "unreconciled_trades": 0,
        },
    }
    state.update(overrides)
    return state


def make_trade(trade_id, exit_time, stress_r, funding_r, reason):
    return {
        "trade_id": trade_id,
        "entry_time": exit_time - DAY_MS,
        "exit_time": exit_time,
        "side": "LONG",
        "exit_reason": reason,
        "observed_stress_net_R": stress_r,
        "observed_funding_R": funding_r,
    }


class D1TelegramCommandTests(unittest.TestCase):
    def test_empty_forward_state_is_clear_and_read_only(self):
        text = BOT.build_d1_shadow_command_text(
            make_state(),
            now_ms_value=NOW_MS,
        )
        self.assertIn("D1 FORWARD SHADOW", text)
        self.assertIn("Worker      : HEALTHY", text)
        self.assertIn("Market      : NEUTRAL", text)
        self.assertIn("Trade       : 0 / 30", text)
        self.assertIn("Funding     : COMPLETE", text)
        self.assertIn("Keputusan   : COLLECTING FORWARD DATA", text)
        self.assertIn("Stress R    : n/a", text)
        self.assertIn("Tidak ada posisi shadow aktif.", text)
        self.assertIn("NO ORDER", text)

    def test_forward_metrics_use_observed_funding_stress_r(self):
        trades = [
            make_trade("a", NOW_MS - 3 * DAY_MS, 1.5, -0.05, "MOMENTUM_FLIP"),
            make_trade("b", NOW_MS - 2 * DAY_MS, -0.5, -0.02, "STOP"),
            make_trade("c", NOW_MS - DAY_MS, 0.2, 0.01, "MAX_HOLD"),
        ]
        text = BOT.build_d1_shadow_command_text(
            make_state(
                monitor_started_at=NOW_MS - 300 * DAY_MS,
                closed_trades=trades,
            ),
            now_ms_value=NOW_MS,
        )
        self.assertIn("Stress R    : +1.200R", text)
        self.assertIn("Avg R       : +0.400R", text)
        self.assertIn("ProfitFact. : 3.400", text)
        self.assertIn("Max DD      : +0.500R", text)
        self.assertIn("Funding R   : -0.060R", text)
        self.assertIn("Tanpa best  : -0.300R", text)
        self.assertIn("3 Close Terakhir", text)

    def test_open_position_is_formatted_without_private_market_call(self):
        state = make_state(current_position={
            "side": "LONG",
            "entry_time": NOW_MS - DAY_MS,
            "entry": 100000.0,
            "initial_stop": 97000.0,
            "active_stop": 99000.0,
            "signal_returns": {
                "7": 0.05,
                "30": 0.12,
                "90": 0.22,
            },
        })
        text = BOT.build_d1_shadow_command_text(
            state,
            now_ms_value=NOW_MS,
        )
        self.assertIn("Market      : LONG OPEN", text)
        self.assertIn("Side        : LONG", text)
        self.assertIn("Entry       : 100000", text)
        self.assertIn("Momentum    : 7d +5.00% | 30d +12.00% | 90d +22.00%", text)

    def test_stale_and_corrupt_state_are_not_reported_as_ready(self):
        stale = make_state(last_poll_at=NOW_MS - 3 * 3600 * 1000)
        stale_text = BOT.build_d1_shadow_command_text(
            stale,
            now_ms_value=NOW_MS,
        )
        self.assertIn("Worker      : STALE", stale_text)
        self.assertIn("Keputusan   : HOLD - WORKER STALE", stale_text)

        invalid_text = BOT.build_d1_shadow_command_text(
            {"schema": "WRONG"},
            now_ms_value=NOW_MS,
        )
        self.assertIn("STATE TIDAK VALID", invalid_text)

    def test_duplicate_trade_id_fails_integrity_gate(self):
        trades = [
            make_trade("duplicate", NOW_MS - 2 * DAY_MS, 1.0, 0.0, "MAX_HOLD"),
            make_trade("duplicate", NOW_MS - DAY_MS, 1.0, 0.0, "MAX_HOLD"),
        ]
        text = BOT.build_d1_shadow_command_text(
            make_state(closed_trades=trades),
            now_ms_value=NOW_MS,
        )
        self.assertIn("Integrity   : CHECK", text)
        self.assertIn("Keputusan   : HOLD - STATE CHECK NEEDED", text)

    def test_admin_and_active_managed_user_dispatch_to_d1(self):
        state = make_state()
        old_admin_ids = BOT.ADMIN_CHAT_IDS
        BOT.ADMIN_CHAT_IDS = ["100000001"]
        old_path = BOT.D1_SHADOW_STATE_PATH
        old_is_admin = BOT.is_admin_chat
        old_access_error = BOT._managed_access_error
        try:
            with tempfile.TemporaryDirectory() as directory:
                state_path = pathlib.Path(directory) / "state.json"
                state_path.write_text(json.dumps(state), encoding="utf-8")
                BOT.D1_SHADOW_STATE_PATH = str(state_path)

                admin_id = str(BOT.ADMIN_CHAT_IDS[0])
                admin_text = BOT.handle_telegram_command(
                    "/d1shadow",
                    chat_id=admin_id,
                )
                self.assertIn("D1 FORWARD SHADOW", admin_text)

                BOT.is_admin_chat = lambda chat_id: False
                BOT._managed_access_error = lambda chat_id: None
                managed_text = BOT.handle_telegram_command(
                    "/d1shadow",
                    chat_id="managed-user",
                )
                self.assertIn("D1 FORWARD SHADOW", managed_text)
        finally:
            BOT.ADMIN_CHAT_IDS = old_admin_ids
            BOT.D1_SHADOW_STATE_PATH = old_path
            BOT.is_admin_chat = old_is_admin
            BOT._managed_access_error = old_access_error

    def test_help_lists_d1_command(self):
        self.assertIn(
            "/d1shadow  - pantau Strategy D1 forward shadow",
            BOT.build_help_text(),
        )


if __name__ == "__main__":
    unittest.main()
