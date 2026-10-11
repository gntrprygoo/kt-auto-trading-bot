import pathlib
import sys
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import evaluate_strategy_b7_gate as gate


class StrategyB7GateTests(unittest.TestCase):
    def test_candidate_family_is_frozen(self):
        self.assertEqual(gate.PRIMARY, "B7_DERIVATIVES_P20")
        self.assertEqual(gate.TIGHT, "B7_DERIVATIVES_P15")
        self.assertEqual(gate.WIDE, "B7_DERIVATIVES_P25")

    def test_side_gate_requires_sample_profit_and_factor(self):
        passing = {
            "trades": 30,
            "total_net_R": 1.0,
            "profit_factor": 1.05,
        }
        too_small = dict(passing, trades=29)
        losing = dict(passing, total_net_R=-0.1)
        weak_factor = dict(passing, profit_factor=1.04)

        self.assertTrue(gate.side_passes(passing, 30))
        self.assertFalse(gate.side_passes(too_small, 30))
        self.assertFalse(gate.side_passes(losing, 30))
        self.assertFalse(gate.side_passes(weak_factor, 30))


if __name__ == "__main__":
    unittest.main()
