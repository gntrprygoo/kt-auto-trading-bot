import json
from pathlib import Path
import tempfile
import unittest

from ai_market_scanner import (
    SCANNER_PROMPT_FAMILY,
    SCANNER_SCHEMA,
    MarketScanDecision,
    MarketScannerConfig,
    MarketScannerError,
    OpenAIMarketScannerClient,
    assert_snapshot_has_no_future_data,
    prompt_definition,
)
from tools.build_ai_market_dataset import (
    DATASET_SCHEMA,
    FEATURE_SET,
    feature_contract_sha256,
    simulate_outcome,
)
from tools.replay_ai_market_prompts import (
    REPLAY_SCHEMA,
    evaluate_prompt,
    exclusive_replay_lock,
    validate_dataset,
)
from tools.select_ai_market_prompt import build_artifact


def valid_decision(**changes):
    value = {
        "action": "TRADE",
        "pair": "ETHUSDT",
        "side": "LONG",
        "confidence": 0.81,
        "regime": "TREND",
        "setup_quality": 78,
        "evidence": ["trend and flow align"],
        "risk_flags": [],
        "thesis": "ETH shows coherent relative strength and participation.",
        "invalidation": "The deterministic stop invalidates the setup.",
    }
    value.update(changes)
    return value


def valid_feature_contract(**changes):
    value = {
        "feature_set": FEATURE_SET,
        "snapshot_schema": SCANNER_SCHEMA,
        "symbols": ["ETHUSDT"],
        "market_fields": ["return_4h"],
        "uses_only_confirmed_bars": True,
        "includes_open_interest": False,
        "includes_funding": False,
        "includes_order_book": False,
    }
    value.update(changes)
    return value


def valid_replay(stage, prompt_results, contract=None):
    contract = contract or valid_feature_contract()
    return {
        "schema": REPLAY_SCHEMA,
        "status": "RESEARCH_ONLY_NO_ORDERS",
        "provider": "openai",
        "stage": stage,
        "prompt_family": SCANNER_PROMPT_FAMILY,
        "fatal_api_error": None,
        "model": "gpt-5.6-luna",
        "reasoning_effort": "low",
        "settings": {
            "future_field_guard": True,
            "max_simultaneous_positions": 1,
            "min_confidence": 0.7,
            "min_quality": 65,
        },
        "dataset_feature_contract": contract,
        "dataset_feature_contract_sha256": feature_contract_sha256(contract),
        "dataset_execution_model": {"entry": "NEXT_15M_OPEN"},
        "prompt_definitions": [
            {**prompt_definition("P1_REGIME_STRUCTURE"), "instructions": None}
        ],
        "prompt_results": prompt_results,
    }


class MarketScannerTests(unittest.TestCase):
    def test_p6_grounding_contract_distinguishes_price_from_range_position(self):
        prompt = prompt_definition("P6_RANGE_ABSORPTION_REVERSAL")
        self.assertEqual(
            prompt["version"], "P6_RANGE_ABSORPTION_REVERSAL_V3_GROUNDED"
        )
        self.assertIn("Fields ending in _pct", prompt["instructions"])
        self.assertIn("are never prices", prompt["instructions"])

    def test_replay_lock_rejects_a_second_process_path(self):
        with tempfile.TemporaryDirectory() as directory:
            lock_path = Path(directory) / "replay.lock"
            with exclusive_replay_lock(lock_path):
                with self.assertRaisesRegex(RuntimeError, "already holds lock"):
                    with exclusive_replay_lock(lock_path):
                        pass

    def test_trade_pair_must_be_in_universe(self):
        with self.assertRaises(MarketScannerError):
            MarketScanDecision.from_mapping(valid_decision(pair="SOLUSDT"), ["ETHUSDT"])

    def test_no_trade_requires_none_identity(self):
        decision = MarketScanDecision.from_mapping(
            valid_decision(action="NO_TRADE", pair="NONE", side="NONE"),
            ["ETHUSDT"],
        )
        self.assertEqual(decision.action, "NO_TRADE")
        with self.assertRaises(MarketScannerError):
            MarketScanDecision.from_mapping(
                valid_decision(action="NO_TRADE", side="NONE"), ["ETHUSDT"]
            )

    def test_decision_serializes_arrays_for_replay(self):
        decision = MarketScanDecision.from_mapping(valid_decision(), ["ETHUSDT"])
        serialized = decision.as_dict()
        self.assertIsInstance(serialized["evidence"], list)
        self.assertIsInstance(serialized["risk_flags"], list)
        MarketScanDecision.from_mapping(serialized, ["ETHUSDT"])

    def test_future_fields_are_rejected_recursively(self):
        with self.assertRaises(MarketScannerError):
            assert_snapshot_has_no_future_data(
                {"market": {"ETHUSDT": {"baseline_net_r": 1.2}}}
            )

    def test_dataset_contract_hash_is_enforced_before_api_calls(self):
        contract = valid_feature_contract()
        dataset = {
            "schema": DATASET_SCHEMA,
            "status": "RESEARCH_ONLY_NO_ORDERS",
            "stage": "development",
            "symbols": ["ETHUSDT"],
            "feature_contract": contract,
            "feature_contract_sha256": "0" * 64,
            "records": [
                {
                    "snapshot": {
                        "schema": SCANNER_SCHEMA,
                        "snapshot_id": "MS-1",
                        "universe": ["ETHUSDT"],
                        "market": {"ETHUSDT": {"return_4h": 0.01}},
                        "execution_contract": {
                            "model_must_not_size_or_set_geometry": True,
                            "max_simultaneous_positions": 1,
                        },
                    }
                }
            ],
        }
        with self.assertRaisesRegex(ValueError, "hash mismatch"):
            validate_dataset(dataset, "development")

        dataset["feature_contract_sha256"] = feature_contract_sha256(contract)
        records = validate_dataset(dataset, "development")
        self.assertEqual(len(records), 1)

        dataset["records"][0]["snapshot"]["market"]["ETHUSDT"]["future_feature"] = 1
        with self.assertRaisesRegex(ValueError, "fields do not match"):
            validate_dataset(dataset, "development")

    def test_request_is_strict_and_does_not_contain_credentials(self):
        snapshot = {
            "schema": "KT_AI_MARKET_SCANNER_V1",
            "snapshot_id": "MS-1",
            "universe": ["ETHUSDT"],
            "market": {"ETHUSDT": {"return_4h": 0.01}},
        }
        client = OpenAIMarketScannerClient(MarketScannerConfig())
        request, prompt = client.build_request(snapshot, "P1_REGIME_STRUCTURE")
        serialized = json.dumps(request)
        self.assertTrue(request["text"]["format"]["strict"])
        self.assertNotIn("OPENAI_API_KEY", serialized)
        self.assertEqual(prompt["id"], "P1_REGIME_STRUCTURE")
        self.assertEqual(len(prompt_definition("P2_LIQUIDITY_FLOW")["sha256"]), 64)

    def test_same_bar_stop_is_pessimistic(self):
        candles = [
            {
                "open_time": 0,
                "close_time": 899999,
                "open": 100,
                "high": 101,
                "low": 99,
                "close": 100,
            },
            {
                "open_time": 900000,
                "close_time": 1799999,
                "open": 100,
                "high": 103,
                "low": 98,
                "close": 101,
            },
        ]
        outcome = simulate_outcome(candles, 0, 0.01, "LONG", 1.0, 2.0, 1, 0.005, 0.03)
        self.assertEqual(outcome["exit_reason"], "STOP")
        self.assertEqual(outcome["gross_r"], -1.0)

    def test_prompt_evaluation_enforces_single_position(self):
        records = []
        decisions = []
        for index in range(2):
            snapshot_id = f"MS-{index}"
            records.append(
                {
                    "snapshot": {
                        "snapshot_id": snapshot_id,
                        "decision_time_ms": index * 1000,
                        "universe": ["ETHUSDT"],
                    },
                    "outcomes": {
                        "ETHUSDT": {
                            "LONG": {
                                "entry_time": index * 1000 + 100,
                                "exit_time": 5000,
                                "entry": 100,
                                "stop": 99,
                                "target": 102,
                                "exit_reason": "TARGET",
                                "baseline_net_r": 1.8,
                                "stress_net_r": 1.7,
                            }
                        }
                    },
                }
            )
            decisions.append(
                {
                    "prompt_id": "P1_REGIME_STRUCTURE",
                    "snapshot_id": snapshot_id,
                    "decision_time_ms": index * 1000,
                    "decision": valid_decision(),
                    "openai": {"usage": {}},
                    "error": None,
                }
            )
        result = evaluate_prompt(
            "P1_REGIME_STRUCTURE", records, decisions, "development", 0.7, 65, 0.2, 1.2
        )
        self.assertEqual(result["summary"]["baseline"]["trades"], 1)
        self.assertEqual(result["summary"]["overlap_blocked"], 1)

    def test_selector_never_forces_a_failed_prompt(self):
        replay = valid_replay(
            "development",
            [
                {
                    "prompt_id": "P1_REGIME_STRUCTURE",
                    "summary": {"gate": {"passed": False}, "selection_score": None},
                }
            ],
        )
        artifact = build_artifact(replay)
        self.assertEqual(artifact["status"], "LOCKED")
        self.assertIsNone(artifact["winner"])
        self.assertFalse(artifact["ai_live_eligible"])

    def test_historical_pass_unlocks_signal_only(self):
        development_summary = {
            "gate": {"passed": True},
            "selection_score": 3.2,
            "baseline": {"trades": 35, "total_r": 8.0, "profit_factor": 1.5, "max_drawdown_r": 4.0},
            "stress": {"total_r": 5.0, "profit_factor": 1.25},
        }
        development = valid_replay(
            "development",
            [{"prompt_id": "P1_REGIME_STRUCTURE", "summary": development_summary}],
        )
        validation = valid_replay(
            "validation",
            [
                {
                    "prompt_id": "P1_REGIME_STRUCTURE",
                    "summary": {"gate": {"passed": True}},
                }
            ],
        )
        artifact = build_artifact(development, validation)
        self.assertEqual(artifact["status"], "PASSED_HISTORICAL")
        self.assertTrue(artifact["ai_signal_eligible"])
        self.assertFalse(artifact["ai_approval_eligible"])
        self.assertFalse(artifact["ai_live_eligible"])

    def test_validation_feature_drift_keeps_deployment_locked(self):
        development = valid_replay(
            "development",
            [
                {
                    "prompt_id": "P1_REGIME_STRUCTURE",
                    "summary": {
                        "gate": {"passed": True},
                        "selection_score": 2.0,
                        "baseline": {
                            "trades": 30,
                            "total_r": 6.0,
                            "profit_factor": 1.3,
                            "max_drawdown_r": 4.0,
                        },
                        "stress": {"total_r": 3.0, "profit_factor": 1.15},
                    },
                }
            ],
        )
        changed_contract = valid_feature_contract(includes_open_interest=True)
        validation = valid_replay(
            "validation",
            [
                {
                    "prompt_id": "P1_REGIME_STRUCTURE",
                    "summary": {"gate": {"passed": True}},
                }
            ],
            changed_contract,
        )
        artifact = build_artifact(development, validation)
        self.assertFalse(artifact["validation"]["consistency"]["same_feature_contract"])
        self.assertEqual(artifact["status"], "LOCKED")
        self.assertFalse(artifact["ai_signal_eligible"])


if __name__ == "__main__":
    unittest.main()
