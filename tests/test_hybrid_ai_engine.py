import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from hybrid_ai_engine import (
    AITradeDecision,
    HybridAIConfig,
    HybridAIEngine,
    HybridAIError,
    HybridAIStateError,
    HybridRiskGateway,
    LIVE_GATE_SCHEMA,
    OpenAIResponsesClient,
    PROMPT_VERSION,
    candidate_id,
)


NOW_MS = 1_800_000_000_000


def decision(**overrides):
    value = AITradeDecision(
        action="TRADE",
        confidence=0.82,
        regime="TREND",
        setup_quality=78,
        risk_flags=(),
        thesis="Trend, flow, and structure are aligned.",
        invalidation="The deterministic stop invalidates the setup.",
    )
    return AITradeDecision(**{**value.__dict__, **overrides})


def candidate(signal_time=NOW_MS, entry=100.0):
    return {
        "pair": "ETHUSDT",
        "side": "LONG",
        "signal_time_ms": signal_time,
        "entry": entry,
        "sl": 98.0,
        "tp": 104.0,
        "tp2": 104.0,
        "actual_rr": 2.0,
        "notional_usdt": 10.0,
        "risk_usdt": 0.2,
        "strategy": "TEST",
        "market_context": {"trend": "UP"},
    }


def runtime(**overrides):
    value = {
        "now_ms": NOW_MS,
        "equity": 1000.0,
        "open_positions": 0,
        "open_pairs": [],
        "daily_r": 0.0,
        "entry_paused": False,
    }
    value.update(overrides)
    return value


class FakeClient:
    def __init__(self, value=None, error=None):
        self.value = value or decision()
        self.error = error
        self.calls = 0

    def decide(self, snapshot):
        self.calls += 1
        if self.error:
            raise self.error
        return self.value, {
            "response_id": "resp_test",
            "model": "gpt-5.6-luna",
            "request_hash": "hash",
            "usage": {},
        }


class HybridAIEngineTests(unittest.TestCase):
    def make_config(self, directory, **overrides):
        values = {
            "enabled": True,
            "mode": "AI_SHADOW",
            "model": "gpt-5.6-luna",
            "state_path": str(Path(directory) / "state.json"),
            "live_gate_path": str(Path(directory) / "gate.json"),
            "allow_live": False,
        }
        values.update(overrides)
        return HybridAIConfig.from_mapping(values, directory)

    def test_candidate_id_is_deterministic_and_sensitive_to_signal(self):
        first = candidate_id(candidate())
        self.assertEqual(first, candidate_id(candidate()))
        self.assertNotEqual(first, candidate_id(candidate(signal_time=NOW_MS + 1)))

    def test_decision_contract_rejects_unknown_fields(self):
        payload = {
            "action": "TRADE",
            "confidence": 0.8,
            "regime": "TREND",
            "setup_quality": 80,
            "risk_flags": [],
            "thesis": "Aligned.",
            "invalidation": "Stop hit.",
            "side": "SHORT",
        }
        with self.assertRaises(HybridAIError):
            AITradeDecision.from_mapping(payload)

    def test_responses_client_uses_store_false_and_parses_strict_json(self):
        captured = {}

        def transport(url, payload, headers, timeout):
            captured.update({"url": url, "payload": payload, "headers": headers, "timeout": timeout})
            return {
                "id": "resp_123",
                "model": "gpt-5.6-luna",
                "output_text": json.dumps({
                    "action": "SKIP",
                    "confidence": 0.91,
                    "regime": "TRANSITION",
                    "setup_quality": 40,
                    "risk_flags": ["conflicting_flow"],
                    "thesis": "Evidence is conflicting.",
                    "invalidation": "Wait for confirmed alignment.",
                }),
                "usage": {"input_tokens": 10, "output_tokens": 5},
            }

        with tempfile.TemporaryDirectory() as directory, patch.dict(
            os.environ, {"OPENAI_API_KEY": "test-key"}
        ):
            config = self.make_config(directory)
            client = OpenAIResponsesClient(config, transport=transport)
            result, metadata = client.decide({"candidate": candidate()})
        self.assertEqual(result.action, "SKIP")
        self.assertFalse(captured["payload"]["store"])
        self.assertIn("json_schema", captured["payload"]["text"]["format"]["type"])
        self.assertEqual(metadata["response_id"], "resp_123")

    def test_risk_gateway_allows_clean_candidate(self):
        with tempfile.TemporaryDirectory() as directory:
            config = self.make_config(directory)
            result = HybridRiskGateway(config).evaluate(candidate(), decision(), runtime())
        self.assertTrue(result.allowed, result.reasons)

    def test_risk_gateway_blocks_low_confidence_stale_and_open_pair(self):
        with tempfile.TemporaryDirectory() as directory:
            config = self.make_config(directory)
            result = HybridRiskGateway(config).evaluate(
                candidate(signal_time=NOW_MS - 30 * 60 * 1000),
                decision(confidence=0.6),
                runtime(open_pairs=["ETHUSDT"]),
            )
        self.assertFalse(result.allowed)
        self.assertIn("confidence_below_floor", result.reasons)
        self.assertIn("candidate_stale", result.reasons)
        self.assertIn("pair_already_open", result.reasons)

    def test_shadow_records_once_without_execution_route(self):
        with tempfile.TemporaryDirectory() as directory:
            fake = FakeClient()
            engine = HybridAIEngine(
                self.make_config(directory),
                client=fake,
                now_ms_fn=lambda: NOW_MS,
            )
            first = engine.review(candidate(), runtime(), execution={"qty_str": "0.1"})
            second = engine.review(candidate(), runtime(), execution={"qty_str": "0.1"})
        self.assertEqual(first.route, "RECORD_ONLY")
        self.assertEqual(first.status, "SHADOW_ACCEPTED")
        self.assertTrue(first.created)
        self.assertFalse(second.created)
        self.assertEqual(fake.calls, 1)

    def test_approval_requires_admin_flow_and_is_claimed_once(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(
            os.environ, {"OPENAI_API_KEY": "test-key"}
        ):
            engine = HybridAIEngine(
                self.make_config(directory),
                client=FakeClient(),
                now_ms_fn=lambda: NOW_MS,
            )
            engine.set_mode("AI_APPROVAL")
            outcome = engine.review(candidate(), runtime(), execution={"qty_str": "0.1"})
            approved = engine.approve(outcome.proposal_id, "admin")
            claimed = engine.claim_for_execution(outcome.proposal_id)
            finished = engine.finish_execution(outcome.proposal_id, True, {"status": "SIMULATED"})
        self.assertEqual(outcome.status, "PENDING_APPROVAL")
        self.assertEqual(approved["status"], "APPROVED")
        self.assertEqual(claimed["status"], "EXECUTING")
        self.assertEqual(finished["status"], "EXECUTED")

    def test_safe_shadow_mode_does_not_require_openai_key(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(
            os.environ, {}, clear=True
        ):
            engine = HybridAIEngine(self.make_config(directory), client=FakeClient())
            self.assertEqual(engine.set_mode("AI_SHADOW"), "AI_SHADOW")
            with self.assertRaises(HybridAIError):
                engine.set_mode("AI_APPROVAL")

    def test_expired_approval_is_persisted_before_error(self):
        clock = [NOW_MS]
        with tempfile.TemporaryDirectory() as directory, patch.dict(
            os.environ, {"OPENAI_API_KEY": "test-key"}
        ):
            engine = HybridAIEngine(
                self.make_config(directory, mode="AI_APPROVAL", approval_ttl_sec=30),
                client=FakeClient(),
                now_ms_fn=lambda: clock[0],
            )
            outcome = engine.review(candidate(), runtime(), execution={"qty_str": "0.1"})
            clock[0] += 31_000
            with self.assertRaises(HybridAIStateError):
                engine.approve(outcome.proposal_id, "admin")
            persisted = engine.store.find(outcome.proposal_id)
        self.assertEqual(persisted["status"], "EXPIRED")

    def test_live_mode_requires_allow_flag_and_passed_artifact(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(
            os.environ, {"OPENAI_API_KEY": "test-key"}
        ):
            locked = HybridAIEngine(self.make_config(directory), client=FakeClient())
            with self.assertRaises(HybridAIError):
                locked.set_mode("AI_LIVE")

            config = self.make_config(directory, allow_live=True)
            gate = {
                "schema": LIVE_GATE_SCHEMA,
                "status": "PASSED",
                "model": config.model,
                "prompt_version": PROMPT_VERSION,
                "development": {"passed": True},
                "validation": {"passed": True},
            }
            Path(config.live_gate_path).write_text(json.dumps(gate), encoding="utf-8")
            engine = HybridAIEngine(config, client=FakeClient())
            self.assertEqual(engine.set_mode("AI_LIVE"), "AI_LIVE")


if __name__ == "__main__":
    unittest.main()
