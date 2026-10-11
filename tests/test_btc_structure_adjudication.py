import pathlib
import sys
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import build_btc_structure_adjudication as adjudication


def joined_row(
    candidate_id,
    expected,
    decision,
    candidate_type="ENGINE_EVENT",
):
    return {
        "candidate_id": candidate_id,
        "candidate": {
            "candidate_id": candidate_id,
            "signal_time": 123,
            "level": 100.0,
            "support": 90.0,
            "resistance": 110.0,
            "context": {"15m": [], "4h": []},
        },
        "key": {
            "candidate_type": candidate_type,
            "expected_path": expected,
        },
        "label": {
            "candidate_id": candidate_id,
            "decision": decision,
        },
        "stratum": adjudication.classify_stratum(
            {
                "candidate_type": candidate_type,
                "expected_path": expected,
            },
            {"decision": decision},
        ),
    }


class BTCStructureAdjudicationTests(unittest.TestCase):
    def test_classifies_disagreement_and_control_strata(self):
        self.assertEqual(
            adjudication.classify_stratum(
                {
                    "candidate_type": "ENGINE_EVENT",
                    "expected_path": "A",
                },
                {"decision": "VALID_B"},
            ),
            "A_TO_B",
        )
        self.assertEqual(
            adjudication.classify_stratum(
                {
                    "candidate_type": "ENGINE_EVENT",
                    "expected_path": "C",
                },
                {"decision": "VALID_C"},
            ),
            "AGREE_C",
        )
        self.assertEqual(
            adjudication.classify_stratum(
                {
                    "candidate_type": "CONTROL",
                    "expected_path": None,
                },
                {"decision": "VALID_A"},
            ),
            "CONTROL_VALID_A",
        )

    def test_sampler_is_deterministic_and_respects_maximum(self):
        rows = []
        counter = 0
        for stratum, count in adjudication.STRATUM_QUOTAS:
            if stratum.startswith("AGREE_"):
                expected = stratum[-1]
                decision = f"VALID_{expected}"
                candidate_type = "ENGINE_EVENT"
            elif stratum.startswith("CONTROL_"):
                expected = None
                decision = stratum.removeprefix("CONTROL_")
                candidate_type = "CONTROL"
            else:
                expected = stratum[0]
                decision = f"VALID_{stratum[-1]}"
                candidate_type = "ENGINE_EVENT"
            for _ in range(count + 2):
                counter += 1
                rows.append(joined_row(
                    f"BTCR-{counter:04d}",
                    expected,
                    decision,
                    candidate_type,
                ))
        first = adjudication.select_adjudication_rows(rows, 36)
        second = adjudication.select_adjudication_rows(rows, 36)
        self.assertEqual(len(first), 36)
        self.assertEqual(
            [item["candidate_id"] for item in first],
            [item["candidate_id"] for item in second],
        )
        counts = adjudication.stratum_counts(first)
        for stratum, quota in adjudication.STRATUM_QUOTAS:
            self.assertEqual(counts[stratum], quota)

    def test_browser_candidate_hides_machine_and_prior_answers(self):
        row = joined_row("BTCR-secret", "B", "VALID_C")
        row["candidate"].update({
            "candidate_type": "ENGINE_EVENT",
            "expected_path": "B",
            "side": "LONG",
            "transition": "SECRET_TRANSITION",
            "prior_human_decision": "VALID_C",
            "selection_stratum": "B_TO_C",
        })
        result = adjudication.make_browser_candidate(row)
        self.assertTrue(result["candidate_id"].startswith("KTADJ-"))
        self.assertNotEqual(result["candidate_id"], "BTCR-secret")
        for hidden in (
            "candidate_type",
            "expected_path",
            "side",
            "transition",
            "prior_human_decision",
            "selection_stratum",
        ):
            self.assertNotIn(hidden, result)

    def test_join_requires_matching_candidate_key_and_label(self):
        review_data = {
            "candidates": [
                {"candidate_id": "BTCR-1", "signal_time": 1},
                {"candidate_id": "BTCR-2", "signal_time": 2},
            ]
        }
        review_key = {
            "candidates": [
                {
                    "blind_candidate_id": "BTCR-1",
                    "candidate_type": "ENGINE_EVENT",
                    "expected_path": "A",
                },
                {
                    "blind_candidate_id": "BTCR-2",
                    "candidate_type": "ENGINE_EVENT",
                    "expected_path": "B",
                },
            ]
        }
        labels = {
            "labels": [
                {
                    "candidate_id": "BTCR-1",
                    "decision": "VALID_B",
                }
            ]
        }
        result = adjudication.build_joined_rows(
            review_data,
            review_key,
            labels,
        )
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["stratum"], "A_TO_B")


if __name__ == "__main__":
    unittest.main()
