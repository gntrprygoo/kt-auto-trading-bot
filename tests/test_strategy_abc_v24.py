import pathlib
import sys
import unittest
from types import SimpleNamespace


ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import abc_structure_engine_v2 as engine
import research_strategy_abc_v24 as research


class StrategyABCV24Tests(unittest.TestCase):
    def test_result_is_explicitly_not_promotion_evidence(self):
        args = SimpleNamespace(
            start="2026-01-01",
            end="2026-01-31",
        )
        result = research.build_result(
            args,
            {"source": "test"},
            [],
            [],
            [],
            {},
            0,
            1,
        )
        self.assertEqual(
            result["status"],
            "RESEARCH_ONLY_TRAINING_SAMPLE",
        )
        self.assertEqual(
            result["validation_role"],
            "HISTORICAL_REGRESSION_NOT_PROMOTION_EVIDENCE",
        )
        self.assertFalse(result["production_changed"])
        self.assertEqual(
            result["parameters"]["name"],
            engine.HUMAN_V24.name,
        )


if __name__ == "__main__":
    unittest.main()
