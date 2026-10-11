import pathlib
import sys
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import abc_structure_engine_v2 as engine
import research_strategy_abc_v23 as research
import research_strategy_abc_v23_review as review


class StrategyABCV23Tests(unittest.TestCase):
    def test_candidate_is_frozen_before_holdout(self):
        self.assertEqual(
            engine.BALANCED_A.name,
            "ABC_V23_BALANCED_A",
        )
        self.assertTrue(engine.BALANCED_A.a_requires_mss)
        self.assertFalse(engine.BALANCED_A.allow_failed_b_c)
        self.assertEqual(
            engine.BALANCED_A.acceptance_window_bars,
            3,
        )
        self.assertEqual(
            engine.BALANCED_A.acceptance_min_outside,
            2,
        )
        self.assertEqual(
            engine.BALANCED_A.a_min_range_width_atr,
            6.0,
        )
        self.assertEqual(
            engine.BALANCED_A.a_max_range_width_atr,
            10.0,
        )

    def test_holdout_period_is_not_discovery_period(self):
        self.assertEqual(research.HOLDOUT_START, "2020-10-25")
        self.assertEqual(research.HOLDOUT_END, "2022-10-24")

    def test_extended_review_uses_frozen_period(self):
        self.assertEqual(review.REVIEW_START, "2019-09-01")
        self.assertEqual(review.REVIEW_END, "2026-07-22")


if __name__ == "__main__":
    unittest.main()
