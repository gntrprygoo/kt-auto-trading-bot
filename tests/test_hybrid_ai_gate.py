import copy
import unittest

from hybrid_ai_engine import PROMPT_VERSION
from tools.evaluate_hybrid_ai_gate import evaluate


def replay_result(stage, candidate_count):
    return {
        "schema": "KT_HISTORICAL_AI_REPLAY_V1",
        "status": "RESEARCH_ONLY_NO_ORDERS",
        "provider": "openai",
        "stage": stage,
        "model": "gpt-5.6-luna",
        "prompt_version": PROMPT_VERSION,
        "candidate_family": "F2_LONG_RESIDUAL_MOMENTUM_8H_FROZEN",
        "candidate_definition": {"name": "F2", "target_r": 1.75},
        "settings": {
            "reasoning_effort": "low",
            "future_field_guard": True,
        },
        "summary": {
            "candidate_count": candidate_count,
            "decision_failures": 0,
            "baseline": {
                "trades": 30,
                "total_r": 10.0,
                "profit_factor": 1.3,
                "max_drawdown_r": 4.0,
            },
            "stress": {"total_r": 5.0, "profit_factor": 1.15},
            "gate": {"passed": True, "checks": {"example": True}},
        },
        "decisions": [{} for _ in range(candidate_count)],
    }


class HybridAIGateTests(unittest.TestCase):
    def test_matching_frozen_replays_can_pass(self):
        result = evaluate(
            replay_result("development", 100),
            replay_result("validation", 15),
        )
        self.assertEqual(result["status"], "PASSED")
        self.assertTrue(result["same_candidate_definition"])

    def test_candidate_definition_change_locks_live(self):
        development = replay_result("development", 100)
        validation = copy.deepcopy(replay_result("validation", 15))
        validation["candidate_definition"]["target_r"] = 2.0
        result = evaluate(development, validation)
        self.assertEqual(result["status"], "LOCKED")
        self.assertFalse(result["same_candidate_definition"])

    def test_missing_decision_locks_live(self):
        development = replay_result("development", 100)
        development["decisions"].pop()
        result = evaluate(development, replay_result("validation", 15))
        self.assertEqual(result["status"], "LOCKED")
        self.assertFalse(
            result["development"]["integrity"]["decision_count_complete"]
        )


if __name__ == "__main__":
    unittest.main()
