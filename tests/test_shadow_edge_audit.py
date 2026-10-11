import unittest

from tools.audit_shadow_edges import (
    audit_group,
    build_audit,
    estimated_cost_r,
    strategy_key,
    summarize,
)


def trade(reason, status, result_r=None, version=None, timestamp=1):
    return {
        "blocked_reason": reason,
        "strategy_version": version,
        "status": status,
        "result_R": result_r,
        "entry": 100.0,
        "sl": 99.0,
        "timestamp": timestamp,
        "closed_at": timestamp + 1,
    }


class ShadowEdgeAuditTests(unittest.TestCase):
    def test_strategy_classification(self):
        self.assertEqual(strategy_key(trade("vol_too_high", "SHADOW_LOSS")), "A_HIGH_VOLUME")
        self.assertEqual(strategy_key(trade("smart_money_c", "SHADOW_LOSS")), "C1")
        self.assertEqual(strategy_key(trade("anything", "SHADOW_OPEN", version="C6")), "C6")

    def test_metrics_and_cost_are_conservative(self):
        values = [1.5, -1.0, 1.5, -1.0]
        metrics = summarize(values)
        self.assertEqual(metrics["n"], 4)
        self.assertAlmostEqual(metrics["total_r"], 1.0)
        self.assertAlmostEqual(metrics["profit_factor"], 1.5)
        self.assertAlmostEqual(metrics["max_drawdown_r"], 1.0)
        self.assertAlmostEqual(estimated_cost_r(trade("x", "SHADOW_WIN"), 0.0014), 0.14)

    def test_audit_does_not_promote_two_c6_wins(self):
        records = [
            trade("smart_money_c_v6", "SHADOW_WIN", 1.5, "C6", 1),
            trade("smart_money_c_v6", "SHADOW_WIN", 1.5, "C6", 2),
            trade("smart_money_c_v6", "SHADOW_OPEN", None, "C6", 3),
        ]
        result = build_audit(records, 0.0014)
        self.assertEqual(result["strategies"]["C6"]["gross"]["n"], 2)
        self.assertIn("CONTINUE_FORWARD_SHADOW", result["decisions"]["C6"])
        self.assertIn("unapproved", result["decisions"]["C6"])

    def test_group_reports_open_and_chronological_decay(self):
        records = [
            trade("vol_too_high", "SHADOW_WIN", 1.0, timestamp=1),
            trade("vol_too_high", "SHADOW_LOSS", -1.0, timestamp=2),
            trade("vol_too_high", "SHADOW_LOSS", -1.0, timestamp=3),
            trade("vol_too_high", "SHADOW_OPEN", timestamp=4),
        ]
        result = audit_group(records, 0.0014)
        self.assertEqual(result["open"], 1)
        self.assertLess(result["chronological_gross"]["last_half"]["total_r"], 0)


if __name__ == "__main__":
    unittest.main()
