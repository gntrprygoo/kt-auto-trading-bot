import pathlib
import sys
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import research_strategy_b62 as research


class StrategyB62ResearchTests(unittest.TestCase):
    def test_runner_family_changes_only_trail_distance(self):
        primary, tight, wide = research.B62_RUNNERS

        self.assertEqual(primary.trail_atr, 2.5)
        self.assertEqual(tight.trail_atr, 2.0)
        self.assertEqual(wide.trail_atr, 3.0)
        self.assertEqual(primary.tp1_fraction, tight.tp1_fraction)
        self.assertEqual(primary.trail_activation_r, wide.trail_activation_r)

    def test_runner_horizon_is_five_days_of_15m_bars(self):
        self.assertEqual(research.B62_RUNNERS[0].horizon_bars, 480)


if __name__ == "__main__":
    unittest.main()
