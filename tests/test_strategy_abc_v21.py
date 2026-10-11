import pathlib
import sys
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import abc_structure_engine_v2 as engine
import research_strategy_abc_v21 as research
import research_strategy_abc_v22 as secondary


class StrategyABCV21Tests(unittest.TestCase):
    def test_variant_family_is_frozen_and_scoped(self):
        self.assertEqual(
            [item.name for item in engine.V21_VARIANTS],
            [
                "ABC_V2_BTC_STRUCTURE",
                "ABC_V21_CONFIRMED_A",
                "ABC_V21_FASTER_B",
                "ABC_V21_DIRECT_C",
                "ABC_V21_COMBINED",
            ],
        )
        self.assertTrue(engine.CONFIRMED_A.a_requires_mss)
        self.assertEqual(
            engine.FASTER_B.acceptance_window_bars,
            3,
        )
        self.assertEqual(
            engine.FASTER_B.acceptance_min_outside,
            2,
        )
        self.assertFalse(engine.DIRECT_C.allow_failed_b_c)

    def test_infinite_profit_factor_requires_non_empty_sample(self):
        self.assertFalse(research._profit_factor_at_least(
            {"profit_factor": None, "trades": 0},
            1.1,
        ))
        self.assertTrue(research._profit_factor_at_least(
            {"profit_factor": None, "trades": 2},
            1.1,
        ))

    def test_period_gate_enforces_sample_and_stress(self):
        report = {
            "baseline": {
                "trades": 15,
                "total_net_R": 2.0,
                "profit_factor": 1.3,
                "max_drawdown_R": 3.0,
            },
            "stress": {
                "trades": 15,
                "total_net_R": 1.0,
                "profit_factor": 1.1,
            },
            "positive_60d_folds": {
                "positive": 2,
                "non_empty": 3,
                "ratio": 0.6667,
            },
        }
        self.assertTrue(research.period_gate(report)["passed"])
        report["stress"]["total_net_R"] = -0.1
        self.assertFalse(research.period_gate(report)["passed"])

    def test_secondary_gate_requires_positive_stress_and_folds(self):
        baseline = {
            "trades": 18,
            "total_net_R": 3.0,
            "profit_factor": 1.4,
            "avg_net_R": 0.1667,
            "max_drawdown_R": 4.0,
        }
        stress = {
            "trades": 18,
            "total_net_R": 1.5,
            "profit_factor": 1.2,
        }
        folds = {
            "positive": 3,
            "non_empty": 5,
            "ratio": 0.6,
        }
        self.assertTrue(
            secondary.evaluate_gate(
                baseline,
                stress,
                folds,
            )["passed"]
        )
        folds["ratio"] = 0.4
        self.assertFalse(
            secondary.evaluate_gate(
                baseline,
                stress,
                folds,
            )["passed"]
        )


if __name__ == "__main__":
    unittest.main()
