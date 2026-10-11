import unittest

from tools.research_strategy_f2_long_residual import CANDIDATE, f2_gate


def metrics(trades, total_r, pf, drawdown=4.0):
    return {
        "trades": trades,
        "total_r": total_r,
        "profit_factor": pf,
        "max_drawdown_r": drawdown,
    }


class StrategyF2LongResidualTests(unittest.TestCase):
    def test_candidate_is_frozen_long_only(self):
        self.assertEqual(CANDIDATE.allowed_side, "LONG")
        self.assertEqual(CANDIDATE.target_r, 1.75)
        self.assertEqual(CANDIDATE.max_hold_bars, 32)

    def test_development_gate_requires_stress_edge_and_pair_breadth(self):
        summary = {
            "baseline": metrics(200, 20.0, 1.2),
            "stress": metrics(200, 5.0, 1.08),
            "pairs": {
                "ETHUSDT": {"total_r": 10.0},
                "SOLUSDT": {"total_r": 10.0},
            },
            "positive_month_ratio": 0.60,
        }
        self.assertTrue(f2_gate("development", summary)["passed"])
        summary["stress"]["total_r"] = -0.01
        self.assertFalse(f2_gate("development", summary)["passed"])

    def test_validation_gate_does_not_require_short_trades(self):
        summary = {
            "baseline": metrics(20, 2.0, 1.15),
            "stress": metrics(20, 0.1, 1.01),
            "positive_month_ratio": 0.50,
        }
        self.assertTrue(f2_gate("validation", summary)["passed"])


if __name__ == "__main__":
    unittest.main()
