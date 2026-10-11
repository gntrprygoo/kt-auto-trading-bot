import pathlib
import sys
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import evaluate_indicator_foundation_gate as gate


class IndicatorFoundationGateTests(unittest.TestCase):
    def test_declared_candidate_is_narrow_level_touch_fix(self):
        self.assertEqual(gate.CANDIDATE, "A2_LEVEL_TOUCH")
        self.assertNotIn(gate.CANDIDATE, gate.REJECTED_STRUCTURAL_VARIANTS)

    def test_clustered_and_strict_ema_profiles_are_explicitly_rejected(self):
        self.assertIn("A3_CLUSTERED_SR", gate.REJECTED_STRUCTURAL_VARIANTS)
        self.assertIn(
            "A4_CLUSTERED_SR_TREND",
            gate.REJECTED_STRUCTURAL_VARIANTS,
        )
        self.assertIn(
            "A5_CLUSTERED_SR_TREND_PULLBACK",
            gate.REJECTED_STRUCTURAL_VARIANTS,
        )


if __name__ == "__main__":
    unittest.main()
