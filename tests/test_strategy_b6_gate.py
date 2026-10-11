import pathlib
import sys
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import evaluate_strategy_b6_gate as gate


class StrategyB6GateTests(unittest.TestCase):
    def test_profit_factor_without_losses_is_unbounded(self):
        metrics = {
            "trades": 20,
            "total_net_R": 5.0,
            "profit_factor": None,
        }

        self.assertTrue(gate.profit_factor_at_least(metrics, 1.25))

    def test_annualized_frequency_uses_observation_days(self):
        self.assertAlmostEqual(
            gate.annualized_frequency([{}] * 40, 365.25),
            40.0,
        )

    def test_side_gate_requires_sample_and_positive_edge(self):
        valid = {
            "trades": 20,
            "total_net_R": 4.0,
            "profit_factor": 1.20,
        }
        sparse = {**valid, "trades": 19}
        negative = {**valid, "total_net_R": -1.0}

        self.assertTrue(gate.side_passed(valid, 20))
        self.assertFalse(gate.side_passed(sparse, 20))
        self.assertFalse(gate.side_passed(negative, 20))


if __name__ == "__main__":
    unittest.main()

