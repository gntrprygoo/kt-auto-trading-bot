import pathlib
import sys
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import evaluate_btc_structure_adjudication as evaluator


def valid_b(candidate_id="KTADJ-1"):
    return {
        "candidate_id": candidate_id,
        "decision": "VALID_B",
        "level_valid": "YES",
        "side": "LONG",
        "boundary_reaction": "NO",
        "breakout_accepted": "YES",
        "retest_completed": "YES",
        "retest_held": "YES",
        "sweep": "NO",
        "reclaim": "NO",
        "mss": "NO",
    }


class BTCStructureAdjudicationEvaluatorTests(
    unittest.TestCase
):
    def test_minimum_path_eligibility_exposes_overlap(self):
        label = valid_b()
        label.update({
            "sweep": "YES",
            "reclaim": "YES",
            "mss": "YES",
        })
        self.assertEqual(
            evaluator.minimum_path_eligibility(label),
            ("B", "C"),
        )
        summary = evaluator.overlap_summary([label])
        self.assertEqual(summary["multiple_eligible"], 1)
        self.assertEqual(summary["rate"], 1.0)
        self.assertEqual(
            summary["decision_patterns"]["VALID_B"]["B+C"],
            1,
        )

    def test_valid_b_requires_completed_held_retest(self):
        label = valid_b()
        self.assertEqual(
            evaluator.label_validation_errors(label),
            [],
        )
        label["retest_completed"] = "NO"
        self.assertIn(
            "valid_b_requires_retest_completed",
            evaluator.label_validation_errors(label),
        )

    def test_valid_c_requires_sweep_reclaim_and_mss(self):
        label = valid_b()
        label.update({
            "decision": "VALID_C",
            "breakout_accepted": "NO",
            "retest_completed": "NO",
            "retest_held": "NO",
            "sweep": "YES",
            "reclaim": "YES",
            "mss": "YES",
        })
        self.assertEqual(
            evaluator.label_validation_errors(label),
            [],
        )
        label["mss"] = "UNCLEAR"
        self.assertIn(
            "valid_c_requires_mss",
            evaluator.label_validation_errors(label),
        )

    def test_missing_candidate_blocks_spec_readiness(self):
        data = {
            "dataset_id": "D1",
            "parent_dataset_id": "P1",
        }
        key = {
            "dataset_id": "D1",
            "parent_dataset_id": "P1",
            "candidates": [
                {
                    "candidate_id": "KTADJ-1",
                    "machine_expected_path": "B",
                    "machine_side": "LONG",
                    "prior_human_decision": "VALID_A",
                    "selection_stratum": "A_TO_B",
                },
                {
                    "candidate_id": "KTADJ-2",
                    "machine_expected_path": None,
                    "machine_side": None,
                    "prior_human_decision": "VALID_B",
                    "selection_stratum": "CONTROL_VALID_B",
                },
            ],
        }
        labels = {
            "schema": evaluator.LABEL_SCHEMA,
            "dataset_id": "D1",
            "parent_dataset_id": "P1",
            "labels": [valid_b()],
        }
        result = evaluator.evaluate(data, key, labels)
        self.assertFalse(result["ready_for_spec"])
        self.assertEqual(
            result["missing_candidate_ids"],
            ["KTADJ-2"],
        )
        self.assertEqual(result["accepted_labels"], 1)

    def test_complete_consistent_export_is_ready(self):
        data = {
            "dataset_id": "D1",
            "parent_dataset_id": "P1",
        }
        key = {
            "dataset_id": "D1",
            "parent_dataset_id": "P1",
            "candidates": [
                {
                    "candidate_id": "KTADJ-1",
                    "machine_expected_path": "B",
                    "machine_side": "LONG",
                    "prior_human_decision": "VALID_A",
                    "selection_stratum": "A_TO_B",
                }
            ],
        }
        labels = {
            "schema": evaluator.LABEL_SCHEMA,
            "dataset_id": "D1",
            "parent_dataset_id": "P1",
            "labels": [valid_b()],
        }
        result = evaluator.evaluate(data, key, labels)
        self.assertTrue(result["ready_for_spec"])
        self.assertEqual(
            result["agreement"]["machine_path"]["rate"],
            1.0,
        )
        self.assertEqual(
            result["agreement"]["machine_side"]["rate"],
            1.0,
        )


if __name__ == "__main__":
    unittest.main()
