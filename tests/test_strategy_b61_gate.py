import pathlib
import sys
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import evaluate_strategy_b6_gate as base_gate
import evaluate_strategy_b61_gate as gate


class StrategyB61GateTests(unittest.TestCase):
    def test_gate_uses_short_only_candidates(self):
        self.assertEqual(gate.PRIMARY, "B61_SHORT_EXPANSION_ACCEPTANCE")
        self.assertEqual(
            gate.NEIGHBOR,
            "B61_SHORT_EXPANSION_ACCEPTANCE_NEIGHBOR",
        )

    def test_base_side_requirement_can_be_asymmetric(self):
        metrics = {
            "trades": 20,
            "total_net_R": 4.0,
            "profit_factor": 1.20,
        }

        self.assertTrue(base_gate.side_passed(metrics, 20))


if __name__ == "__main__":
    unittest.main()

