import pathlib
import sys
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import research_strategy_b51 as research


class StrategyB51ResearchTests(unittest.TestCase):
    def test_profiles_are_frozen_cost_aware_rules(self):
        profiles = {profile.name: profile for profile in research.B51_PROFILES}
        candidate = profiles["B51_COST_AWARE_SHORT"]

        self.assertEqual(candidate.side_mode, "SHORT")
        self.assertEqual(candidate.min_risk_pct, 0.008)
        self.assertEqual(candidate.max_risk_pct, 0.020)

    def test_profile_variant_preserves_base_breakout_structure(self):
        profile = next(
            item
            for item in research.B51_PROFILES
            if item.name == "B51_MATURE_SHORT"
        )
        variant = research.profile_variant(profile)

        self.assertEqual(variant.name, profile.name)
        self.assertEqual(variant.side_mode, "SHORT")
        self.assertEqual(variant.channel_lookback_1h, 36)
        self.assertEqual(variant.min_level_age_1h, 4)


if __name__ == "__main__":
    unittest.main()
