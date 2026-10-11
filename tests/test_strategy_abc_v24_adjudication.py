import pathlib
import sys
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import evaluate_strategy_abc_v24_adjudication as evaluator


class StrategyABCV24AdjudicationTests(unittest.TestCase):
    def test_exact_time_comparison_is_diagnostic_only(self):
        labels = {
            "dataset_id": "D1",
            "labels": [
                {
                    "candidate_id": "C1",
                    "decision": "VALID_B",
                    "side": "LONG",
                },
                {
                    "candidate_id": "C2",
                    "decision": "VALID_C",
                    "side": "SHORT",
                },
            ],
        }
        key = {
            "candidates": [
                {"candidate_id": "C1", "signal_time": 100},
                {"candidate_id": "C2", "signal_time": 200},
            ],
        }
        replay = {
            "engine": "ABC_V24_HUMAN_EXCLUSIVE",
            "events": [
                {
                    "event_id": "E1",
                    "signal_time": 100,
                    "path": "B",
                    "side": "LONG",
                },
            ],
        }
        result = evaluator.evaluate(labels, key, replay)
        self.assertEqual(result["accepted_valid_labels"], 2)
        self.assertEqual(
            result["v24_event_at_exact_signal_time"],
            1,
        )
        self.assertEqual(result["exact_path"]["count"], 1)
        self.assertEqual(result["exact_path"]["rate_detected"], 1.0)
        self.assertEqual(result["path_matrix"]["NONE"]["VALID_C"], 1)
        self.assertEqual(
            result["status"],
            "TRAINING_SAMPLE_DIAGNOSTIC_ONLY",
        )
        self.assertFalse(result["production_changed"])


if __name__ == "__main__":
    unittest.main()
