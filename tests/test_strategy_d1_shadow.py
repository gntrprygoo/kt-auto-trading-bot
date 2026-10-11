import pathlib
import sys
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import strategy_d1_shadow as shadow


class StrategyD1ShadowTests(unittest.TestCase):
    def test_first_run_suppresses_historical_notifications(self):
        position = {
            "side": "LONG",
            "signal_time": 100,
            "entry_time": 101,
            "entry": 100.0,
            "initial_stop": 95.0,
            "stop": 98.0,
            "best_close": 110.0,
            "signal_returns": {"7": 0.1},
        }
        state, changes = shadow.update_shadow_state(
            None,
            [],
            position,
            200,
        )
        self.assertTrue(changes["initialized"])
        self.assertEqual(changes["new_entries"], [])
        self.assertEqual(state["monitor_started_at"], 200)

    def test_new_entry_and_close_are_idempotent(self):
        previous = {
            "schema": shadow.SCHEMA,
            "monitor_started_at": 100,
            "last_poll_at": 100,
            "notified_entry_times": [],
            "recorded_trade_ids": [],
            "closed_trades": [],
            "current_position": None,
        }
        position = {
            "side": "LONG",
            "signal_time": 109,
            "entry_time": 110,
            "entry": 100.0,
            "initial_stop": 95.0,
            "stop": 98.0,
            "best_close": 110.0,
            "signal_returns": {"7": 0.1},
        }
        trade = {
            "signal_time": 109,
            "entry_time": 110,
            "exit_time": 120,
            "side": "LONG",
            "entry": 100.0,
            "initial_stop": 95.0,
            "signal_returns": {"7": 0.1},
        }
        state, changes = shadow.update_shadow_state(
            previous,
            [trade],
            position,
            130,
        )
        self.assertEqual(len(changes["new_entries"]), 1)
        self.assertEqual(len(changes["new_closed_trades"]), 1)
        _, repeated = shadow.update_shadow_state(
            state,
            [trade],
            position,
            140,
        )
        self.assertEqual(repeated["new_entries"], [])
        self.assertEqual(repeated["new_closed_trades"], [])

    def test_carried_position_close_is_recorded_by_exit_time(self):
        previous = {
            "schema": shadow.SCHEMA,
            "monitor_started_at": 100,
            "last_poll_at": 100,
            "notified_entry_times": [],
            "recorded_trade_ids": [],
            "closed_trades": [],
            "current_position": {
                "entry_time": 80,
            },
        }
        trade = {
            "signal_time": 70,
            "entry_time": 80,
            "exit_time": 120,
            "side": "LONG",
        }
        _, changes = shadow.update_shadow_state(
            previous,
            [trade],
            None,
            130,
        )
        self.assertEqual(changes["new_entries"], [])
        self.assertEqual(len(changes["new_closed_trades"]), 1)

    def test_poll_time_cannot_move_backwards(self):
        previous = {
            "schema": shadow.SCHEMA,
            "monitor_started_at": 100,
            "last_poll_at": 120,
        }
        with self.assertRaisesRegex(ValueError, "move backwards"):
            shadow.update_shadow_state(
                previous,
                [],
                None,
                119,
            )

    def test_quiet_mode_only_reports_state_changes(self):
        unchanged = {
            "initialized": False,
            "new_entries": [],
            "new_closed_trades": [],
        }
        self.assertFalse(shadow.report_has_changes(unchanged))
        self.assertTrue(shadow.report_has_changes({
            **unchanged,
            "new_entries": [{"entry_time": 1}],
        }))

    def test_fetch_uses_injected_json_client(self):
        calls = []

        def fake_get(url, params, timeout):
            calls.append((url, params, timeout))
            return [
                [0, "100", "110", "90", "105", "12", 99],
                [100, "105", "115", "95", "110", "13", 199],
            ]

        rows = shadow.fetch_4h_candles(
            "https://example.test",
            0,
            150,
            get_json=fake_get,
        )
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["close_time"], 99)
        self.assertEqual(rows[1]["open_time"], 100)
        self.assertEqual(
            calls[0][0],
            "https://example.test/fapi/v1/klines",
        )
        self.assertEqual(calls[0][2], 20)

    def test_kline_parser_uses_binance_close_time(self):
        raw = [
            0,
            "100",
            "110",
            "90",
            "105",
            "12",
            99,
        ]
        result = shadow.parse_kline(raw)
        self.assertEqual(result["open_time"], 0)
        self.assertEqual(result["close_time"], 99)
        self.assertEqual(result["close"], 105.0)

    def test_positive_funding_is_a_cost_for_long(self):
        record = {
            "side": "LONG",
            "entry_time": 100,
            "exit_time": 300,
            "initial_risk": 100.0,
            "gross_R": 1.0,
            "baseline_cost_R": 0.1,
            "stress_cost_R": 0.2,
        }
        funding = [
            {
                "funding_time": 200,
                "funding_rate": 0.001,
                "mark_price": 10000.0,
            },
        ]
        result = shadow.enrich_trade_funding(record, funding)
        self.assertAlmostEqual(result["observed_funding_R"], -0.1)
        self.assertAlmostEqual(
            result["observed_stress_net_R"],
            0.7,
        )
        self.assertEqual(result["funding_event_count"], 1)

    def test_funding_outside_trade_is_ignored(self):
        record = {
            "side": "LONG",
            "entry_time": 100,
            "exit_time": 300,
            "initial_risk": 100.0,
            "gross_R": 0.0,
            "baseline_cost_R": 0.1,
            "stress_cost_R": 0.2,
        }
        funding = [
            {
                "funding_time": 99,
                "funding_rate": 0.001,
                "mark_price": 10000.0,
            },
            {
                "funding_time": 301,
                "funding_rate": 0.001,
                "mark_price": 10000.0,
            },
        ]
        result = shadow.enrich_trade_funding(record, funding)
        self.assertEqual(result["funding_event_count"], 0)
        self.assertEqual(result["observed_funding_R"], 0.0)

    def test_funding_fetch_uses_public_endpoint(self):
        calls = []

        def fake_get(url, params, timeout):
            calls.append((url, params, timeout))
            return [{
                "symbol": "BTCUSDT",
                "fundingTime": 200,
                "fundingRate": "0.0001",
                "markPrice": "10000",
            }]

        rows = shadow.fetch_funding_rates(
            "https://example.test",
            100,
            300,
            get_json=fake_get,
        )
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["funding_time"], 200)
        self.assertEqual(
            calls[0][0],
            "https://example.test/fapi/v1/fundingRate",
        )
        self.assertEqual(calls[0][1]["limit"], 1000)


if __name__ == "__main__":
    unittest.main()
