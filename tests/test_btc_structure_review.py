import pathlib
import sys
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import build_btc_structure_review as review


def candle(index, interval):
    return {
        "open_time": index * interval,
        "close_time": (index + 1) * interval - 1,
        "open": 100.0,
        "high": 101.0,
        "low": 99.0,
        "close": 100.5,
        "volume": 10.0,
    }


class BTCStructureReviewTests(unittest.TestCase):
    def test_selection_keeps_events_and_fills_controls(self):
        replay = {
            "events": [
                {
                    "event_id": f"E{index}",
                    "signal_time": index,
                    "path": "A",
                }
                for index in range(5)
            ],
            "review_controls": [
                {
                    "candidate_id": f"C{index}",
                    "signal_time": 100 + index,
                }
                for index in range(20)
            ],
        }
        selected = review.select_candidates(replay, 12)
        ids = {
            item.get("event_id") or item.get("candidate_id")
            for item in selected
        }
        self.assertEqual(len(selected), 12)
        self.assertTrue({f"E{index}" for index in range(5)} <= ids)

    def test_context_contains_past_and_hidden_future(self):
        interval_15m = 15 * 60 * 1000
        interval_4h = 4 * 60 * 60 * 1000
        candles_15m = [
            candle(index, interval_15m)
            for index in range(100)
        ]
        candles_4h = [
            candle(index, interval_4h)
            for index in range(20)
        ]
        signal_time = candles_15m[70]["close_time"]
        result = review.attach_context(
            {
                "event_id": "E1",
                "signal_time": signal_time,
                "path": "A",
            },
            candles_15m,
            candles_4h,
        )
        self.assertEqual(result["candidate_id"], "E1")
        self.assertEqual(result["candidate_type"], "ENGINE_EVENT")
        self.assertTrue(any(
            item["t"] > signal_time
            for item in result["context"]["15m"]
        ))
        self.assertTrue(any(
            item["t"] == signal_time
            for item in result["context"]["15m"]
        ))

    def test_blind_candidate_hides_machine_answer(self):
        contextual = {
            "event_id": "ABC-B-SECRET",
            "candidate_id": "ABC-B-SECRET",
            "candidate_type": "ENGINE_EVENT",
            "expected_path": "B",
            "path": "B",
            "side": "LONG",
            "transition": "BREAKOUT_RETEST",
            "signal_time": 123,
            "level": 100.0,
            "support": 90.0,
            "resistance": 100.0,
            "context": {"15m": [], "4h": []},
        }
        blinded = review.make_blind_candidate(contextual)
        self.assertTrue(
            blinded["candidate_id"].startswith("BTCR-")
        )
        for hidden in (
            "event_id",
            "candidate_type",
            "expected_path",
            "path",
            "side",
            "transition",
        ):
            self.assertNotIn(hidden, blinded)

    def test_preflight_rejects_impossible_b_coverage(self):
        key = [
            {
                "candidate_type": "ENGINE_EVENT",
                "expected_path": path,
            }
            for path, count in (("A", 20), ("B", 3), ("C", 10))
            for _ in range(count)
        ] + [
            {
                "candidate_type": "CONTROL",
                "expected_path": None,
            }
            for _ in range(30)
        ]
        result = review.review_feasibility(key)
        self.assertFalse(result["passed"])
        self.assertFalse(
            result["checks"]["path_B_coverage_possible"]
        )

    def test_sampler_reserves_thirty_controls(self):
        events = []
        counter = 0
        for path, count in (("A", 100), ("B", 20), ("C", 20)):
            for _ in range(count):
                counter += 1
                events.append({
                    "event_id": f"E{counter}",
                    "signal_time": counter,
                    "path": path,
                })
        controls = [
            {
                "candidate_id": f"C{index}",
                "candidate_type": "CONTROL",
                "signal_time": 1000 + index,
            }
            for index in range(100)
        ]
        selected = review.select_candidates(
            {
                "events": events,
                "review_controls": controls,
            },
            150,
        )
        selected_controls = [
            item for item in selected
            if "candidate_id" in item
        ]
        self.assertEqual(len(selected), 150)
        self.assertEqual(len(selected_controls), 30)


if __name__ == "__main__":
    unittest.main()
