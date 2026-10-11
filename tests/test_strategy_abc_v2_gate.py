import pathlib
import sys
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import evaluate_strategy_abc_v2_gate as gate


def replay_fixture():
    events = []
    counter = 0
    for path, count in (("A", 60), ("B", 20), ("C", 20)):
        for _ in range(count):
            counter += 1
            events.append({
                "event_id": f"E{counter}",
                "path": path,
            })
    controls = [
        {"candidate_id": f"C{index}"}
        for index in range(30)
    ]
    return {
        "events": events,
        "review_controls": controls,
    }


class ABCV2LabelGateTests(unittest.TestCase):
    def test_exact_labels_and_clean_controls_pass(self):
        replay = replay_fixture()
        labels = {
            "labels": [
                {
                    "candidate_id": item["event_id"],
                    "decision": f"VALID_{item['path']}",
                }
                for item in replay["events"]
            ] + [
                {
                    "candidate_id": item["candidate_id"],
                    "decision": "NO_SETUP",
                }
                for item in replay["review_controls"]
            ],
        }
        result = gate.evaluate_label_gate(replay, labels)
        self.assertTrue(result["passed"])
        self.assertEqual(result["overall_exact_precision"], 1.0)
        self.assertEqual(
            result["control_false_negative_rate"],
            0.0,
        )

    def test_wrong_levels_fail_precision(self):
        replay = replay_fixture()
        labels = {
            "labels": [
                {
                    "candidate_id": item["event_id"],
                    "decision": "LEVEL_WRONG",
                }
                for item in replay["events"]
            ] + [
                {
                    "candidate_id": item["candidate_id"],
                    "decision": "NO_SETUP",
                }
                for item in replay["review_controls"]
            ],
        }
        result = gate.evaluate_label_gate(replay, labels)
        self.assertFalse(result["passed"])
        self.assertEqual(result["overall_exact_precision"], 0.0)

    def test_skipped_and_unknown_labels_do_not_count(self):
        replay = replay_fixture()
        labels = {
            "labels": [
                {
                    "candidate_id": "E1",
                    "decision": "SKIP",
                },
                {
                    "candidate_id": "UNKNOWN",
                    "decision": "VALID_A",
                },
            ],
        }
        result = gate.evaluate_label_gate(replay, labels)
        self.assertEqual(result["accepted_labels"], 0)
        self.assertEqual(result["ignored"]["unknown_candidate"], 1)
        self.assertEqual(
            result["ignored"]["missing_or_unsupported_decision"],
            1,
        )

    def test_preflight_rejects_dataset_with_only_three_b_events(self):
        replay = replay_fixture()
        replay["events"] = [
            item
            for item in replay["events"]
            if item["path"] != "B"
        ] + [
            {"event_id": f"B{index}", "path": "B"}
            for index in range(3)
        ]
        result = gate.evaluate_dataset_feasibility(replay)
        self.assertFalse(result["passed"])
        self.assertEqual(result["path_counts"]["B"], 3)

    def test_blind_gate_rejects_mismatched_dataset(self):
        replay = replay_fixture()
        key = {
            "dataset_id": "RIGHT",
            "candidates": [
                {
                    "blind_candidate_id": item["event_id"],
                    "candidate_type": "ENGINE_EVENT",
                    "expected_path": item["path"],
                }
                for item in replay["events"]
            ] + [
                {
                    "blind_candidate_id": item["candidate_id"],
                    "candidate_type": "CONTROL",
                    "expected_path": None,
                }
                for item in replay["review_controls"]
            ],
        }
        labels = {
            "schema": "KT_BTC_STRUCTURE_LABELS_V2_BLIND",
            "dataset_id": "WRONG",
            "labels": [],
        }
        result = gate.evaluate_blind_label_gate(key, labels)
        self.assertFalse(result["passed"])
        self.assertFalse(result["checks"][0]["passed"])


if __name__ == "__main__":
    unittest.main()
