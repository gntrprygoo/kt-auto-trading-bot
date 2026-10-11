import pathlib
import sys
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import research_strategy_b61 as research


class StrategyB61ResearchTests(unittest.TestCase):
    def test_primary_is_frozen_short_only_cost_aware_model(self):
        candidate = research.B61_PRIMARY

        self.assertEqual(candidate.side_mode, "SHORT")
        self.assertEqual(candidate.trigger_hours, 1)
        self.assertEqual(candidate.min_risk_pct, 0.008)
        self.assertEqual(candidate.max_risk_pct, 0.022)
        self.assertEqual(candidate.btc_return_tolerance, 0.0)

    def test_neighbor_preserves_hypothesis(self):
        candidate = research.B61_PRIMARY
        neighbor = research.B61_NEIGHBOR

        self.assertEqual(neighbor.side_mode, candidate.side_mode)
        self.assertEqual(neighbor.trigger_hours, candidate.trigger_hours)
        self.assertEqual(
            neighbor.acceptance_window_bars,
            candidate.acceptance_window_bars,
        )
        self.assertGreater(
            neighbor.compression_max_ratio,
            candidate.compression_max_ratio,
        )


if __name__ == "__main__":
    unittest.main()

