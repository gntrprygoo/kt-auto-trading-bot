import pathlib
import sys
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import evaluate_strategy_abc_gate as gate


class StrategyABCGateTests(unittest.TestCase):
    def test_candidate_family_is_frozen(self):
        self.assertEqual(gate.PRIMARY, "ABC_PRIMARY")
        self.assertEqual(gate.TIGHT, "ABC_TIGHT")
        self.assertEqual(gate.WIDE, "ABC_WIDE")

    def test_path_gate_requires_sample_nonnegative_and_factor(self):
        passing = {
            "trades": 30,
            "total_net_R": 1.0,
            "profit_factor": 1.05,
        }
        self.assertTrue(
            gate.side_or_path_passes(passing, 30, 1.05)
        )
        self.assertFalse(
            gate.side_or_path_passes(
                dict(passing, trades=29),
                30,
                1.05,
            )
        )
        self.assertFalse(
            gate.side_or_path_passes(
                dict(passing, total_net_R=-0.1),
                30,
                1.05,
            )
        )
        self.assertFalse(
            gate.side_or_path_passes(
                dict(passing, profit_factor=1.04),
                30,
                1.05,
            )
        )

    def test_positive_fold_ratio_ignores_empty_folds(self):
        ratio, positive, nonempty = gate.positive_fold_ratio([
            {"trades": 10, "total_net_R": 1.0},
            {"trades": 10, "total_net_R": -1.0},
            {"trades": 0, "total_net_R": 0.0},
        ])
        self.assertEqual(positive, 1)
        self.assertEqual(nonempty, 2)
        self.assertEqual(ratio, 0.5)


if __name__ == "__main__":
    unittest.main()
