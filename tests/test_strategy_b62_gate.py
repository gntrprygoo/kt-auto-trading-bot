import pathlib
import sys
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import evaluate_strategy_b62_design_gate as gate


class StrategyB62GateTests(unittest.TestCase):
    def test_candidate_and_neighbors_are_frozen(self):
        self.assertEqual(gate.PRIMARY, "B62_SHORT_TREND_RUNNER_2_5")
        self.assertEqual(gate.TIGHT, "B62_SHORT_TREND_RUNNER_2_0")
        self.assertEqual(gate.WIDE, "B62_SHORT_TREND_RUNNER_3_0")


if __name__ == "__main__":
    unittest.main()

