import unittest
from tools.historical_ai_replay import (
    assert_no_future_fields,
    build_candidate,
    is_fatal_api_error,
    stage_gate,
    summarize_values,
)


class HistoricalAIReplayTests(unittest.TestCase):
    def test_candidate_builder_excludes_future_outcome(self):
        record = {
            "symbol": "SOLUSDT",
            "side": "LONG",
            "signal_time": 1000,
            "entry": 100.0,
            "stop": 98.0,
            "target": 104.0,
            "gross_r": -1.0,
            "exit_reason": "STOP",
            "baseline_net_r": -1.05,
            "stress_net_r": -1.08,
        }
        candidate = build_candidate(
            record,
            {"return_4h": 0.02, "last_confirmed_candle_close_ms": 1_999},
            decision_time_ms=2_000,
        )
        snapshot = {"candidate": candidate}
        assert_no_future_fields(snapshot)
        serialized = str(snapshot).lower()
        self.assertNotIn("gross_r", serialized)
        self.assertNotIn("exit_reason", serialized)
        self.assertEqual(candidate["signal_time_ms"], 2_000)

    def test_future_field_guard_rejects_leak(self):
        with self.assertRaises(ValueError):
            assert_no_future_fields({"candidate": {"exit_price": 101.0}})

    def test_summary_is_cost_aware_and_chronological(self):
        summary = summarize_values([1.5, -1.0, 0.5, -0.25])
        self.assertEqual(summary["trades"], 4)
        self.assertAlmostEqual(summary["total_r"], 0.75)
        self.assertAlmostEqual(summary["profit_factor"], 1.6)
        self.assertAlmostEqual(summary["max_drawdown_r"], 1.0)

    def test_gate_does_not_pass_small_sample(self):
        summary = {
            "reviewed_candidates": 10,
            "decision_coverage": 1.0,
            "baseline": summarize_values([1.5] * 9 + [-1.0]),
            "stress": summarize_values([1.4] * 9 + [-1.1]),
        }
        result = stage_gate("development", summary)
        self.assertFalse(result["passed"])
        self.assertFalse(result["checks"]["reviewed_candidates"])

    def test_quota_and_auth_errors_abort_replay_batches(self):
        self.assertTrue(is_fatal_api_error("OpenAI HTTP 429: insufficient_quota"))
        self.assertTrue(is_fatal_api_error("OpenAI HTTP 401: invalid_api_key"))
        self.assertTrue(is_fatal_api_error("OpenAI HTTP 400: invalid model"))
        self.assertFalse(is_fatal_api_error("temporary socket timeout"))


if __name__ == "__main__":
    unittest.main()
