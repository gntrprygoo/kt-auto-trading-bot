#!/usr/bin/env python3
"""Verify the live OpenAI market analyzer without making network requests."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ai_range_setup import RANGE_SETUP_PROMPT_ID, RANGE_SETUP_PROMPT_VERSION
from live_ai_market import (
    LIVE_FEATURE_SET,
    LiveAIMarketConfig,
    LiveAIMarketEngine,
    RESEARCH_STATUS,
)


def _load_named_environment_value(path: Path, variable_name: str) -> None:
    if not path.is_file():
        raise FileNotFoundError(f"environment file is missing: {path}")
    for raw_line in path.read_text(encoding="utf-8-sig").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].lstrip()
        key, separator, value = line.partition("=")
        if separator and key.strip() == variable_name:
            normalized = value.strip()
            if (
                len(normalized) >= 2
                and normalized[0] == normalized[-1]
                and normalized[0] in ("'", '"')
            ):
                normalized = normalized[1:-1]
            os.environ[variable_name] = normalized
            return


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument(
        "--expect-openai-key", choices=("any", "present", "missing"), default="any"
    )
    parser.add_argument(
        "--environment-file",
        type=Path,
        help="Read only the configured OpenAI variable from this service env file.",
    )
    args = parser.parse_args()

    raw = json.loads(args.config.read_text(encoding="utf-8-sig"))
    section = raw.get("ai_market_live") if isinstance(raw, dict) else None
    api_key_env = (
        str(section.get("api_key_env", "OPENAI_API_KEY"))
        if isinstance(section, dict)
        else "OPENAI_API_KEY"
    )
    if args.environment_file:
        _load_named_environment_value(args.environment_file, api_key_env)
    config = LiveAIMarketConfig.from_mapping(section, args.config.parent / "data")
    engine = LiveAIMarketEngine(config)
    summary = engine.summary()
    active_setup = (
        summary.get("active_setup")
        if isinstance(summary.get("active_setup"), dict)
        else None
    )
    binance = raw.get("binance") if isinstance(raw.get("binance"), dict) else {}
    binance_present = bool(binance.get("api_key") and binance.get("api_secret"))
    checks = {
        "enabled": config.enabled,
        "research_shadow_only": summary.get("mode") == "RESEARCH_SHADOW_ONLY",
        "rejected_gate_preserved": summary.get("research_status") == RESEARCH_STATUS,
        "orders_locked": summary.get("orders_allowed") is False,
        "p6_setup_prompt": (
            summary.get("prompt_id") == RANGE_SETUP_PROMPT_ID
            and summary.get("prompt_version") == RANGE_SETUP_PROMPT_VERSION
        ),
        "range_structure_feature_set": summary.get("feature_set") == LIVE_FEATURE_SET,
        "active_setup_orders_locked": (
            active_setup is None and True
            or active_setup.get("orders_allowed") is False
        ),
        "binance_credentials_present_locally": binance_present,
        "state_parent_exists": Path(config.state_path).parent.exists(),
        "openai_key_expectation": (
            args.expect_openai_key == "any"
            or (args.expect_openai_key == "present" and summary["openai_key_present"])
            or (args.expect_openai_key == "missing" and not summary["openai_key_present"])
        ),
    }
    result = {
        "ok": all(checks.values()),
        "checks": checks,
        "model": config.model,
        "prompt_id": config.prompt_id,
        "symbols": list(config.symbols),
        "scan_interval_sec": config.scan_interval_sec,
        "setup_monitor_interval_sec": config.setup_monitor_interval_sec,
    }
    print(json.dumps(result, sort_keys=True))
    return 0 if result["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
