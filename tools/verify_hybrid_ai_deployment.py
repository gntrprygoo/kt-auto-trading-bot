#!/usr/bin/env python3
"""Verify Hybrid AI deployment without printing any secret value."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from hybrid_ai_engine import HybridAIConfig, HybridAIEngine


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument(
        "--expect-key",
        choices=("present", "absent", "any"),
        default="any",
    )
    parser.add_argument("--pid", type=int)
    return parser.parse_args()


def process_key_present(pid: int, key_name: str) -> bool:
    environment = Path(f"/proc/{pid}/environ").read_bytes().split(b"\0")
    prefix = (key_name + "=").encode("utf-8")
    for item in environment:
        if item.startswith(prefix):
            return bool(item[len(prefix):])
    return False


def main() -> int:
    args = parse_args()
    raw = json.loads(args.config.read_text(encoding="utf-8-sig"))
    hybrid_raw = raw.get("hybrid_ai") if isinstance(raw, dict) else None
    config = HybridAIConfig.from_mapping(hybrid_raw, args.config.parent / "data")
    summary = HybridAIEngine(config).summary()
    key_present = (
        process_key_present(args.pid, config.api_key_env)
        if args.pid
        else bool(config.api_key)
    )
    checks = {
        "enabled": config.enabled,
        "mode_shadow": summary.get("mode") == "AI_SHADOW",
        "baseline_preserved": config.preserve_baseline_in_shadow,
        "allow_live_false": not config.allow_live,
        "notional_cap_usd_10": config.max_notional_usdt <= 10.0,
        "live_gate_locked": not bool(summary.get("live_gate", {}).get("passed")),
        "key_expectation": (
            args.expect_key == "any"
            or (args.expect_key == "present" and key_present)
            or (args.expect_key == "absent" and not key_present)
        ),
    }
    output = {
        "status": "PASS" if all(checks.values()) else "FAIL",
        "checks": checks,
        "mode": summary.get("mode"),
        "model": config.model,
        "api_key_present": key_present,
        "allow_live": config.allow_live,
        "max_notional_usdt": config.max_notional_usdt,
        "live_gate": "PASSED" if summary.get("live_gate", {}).get("passed") else "LOCKED",
    }
    print(json.dumps(output, indent=2))
    return 0 if output["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
