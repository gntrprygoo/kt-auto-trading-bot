import unittest

from tools.research_strategy_g_absorption import CANDIDATE, SYMBOLS, g_gate


def metric(trades, total_r, pf, drawdown=4.0):
    return {
        "trades": trades,
        "total_r": total_r,
        "profit_factor": pf,
        "max_drawdown_r": drawdown,
    }


class StrategyGAbsorptionTests(unittest.TestCase):
    def test_candidate_parameters_are_frozen(self):
        self.assertEqual(CANDIDATE.family, "FLOW_ABSORPTION")
        self.assertEqual(CANDIDATE.flow_threshold, 0.18)
        self.assertEqual(CANDIDATE.target_r, 1.25)

    def test_development_gate_requires_breadth(self):
        pairs = {symbol: {"total_r": 1.0} for symbol in SYMBOLS}
        summary = {
            "baseline": metric(60, 12.0, 1.25),
            "stress": metric(60, 5.0, 1.12),
            "pairs": pairs,
            "positive_month_ratio": 0.60,
        }
        self.assertTrue(g_gate("development", summary)["passed"])
        for symbol in SYMBOLS[:3]:
            pairs[symbol]["total_r"] = -1.0
        self.assertFalse(g_gate("development", summary)["passed"])


if __name__ == "__main__":
    unittest.main()
