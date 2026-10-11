#!/usr/bin/env python3
"""Verify retired shadow state and render production Telegram command text."""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
from pathlib import Path


def load_bot(app_dir: Path):
    os.environ["KT_BOT_CONFIG"] = str(app_dir / "config.json")
    spec = importlib.util.spec_from_file_location(
        "kt_bot_shadow_runtime_verify",
        app_dir / "v3_swing_bot_fixed.py",
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def verify(app_dir: Path) -> dict:
    config = json.loads((app_dir / "config.json").read_text(encoding="utf-8-sig"))
    active_path = Path(config["paths"]["shadow_trades_path"])
    active = json.loads(active_path.read_text(encoding="utf-8-sig"))
    archives = sorted((active_path.parent / "archive").glob("shadow_legacy_retired_*.json"))
    if not archives:
        raise AssertionError("retirement archive is missing")
    archive = json.loads(archives[-1].read_text(encoding="utf-8-sig"))

    assert config["strategy_a"]["enable_volume_shadow"] is False
    assert config["smart_money_c"]["version"] == 6
    assert config["smart_money_c"]["enable_shadow"] is True
    assert config["smart_money_c"]["enable_daily_report"] is False
    assert all(
        row.get("blocked_reason") == "smart_money_c_v6"
        or row.get("strategy_version") == "C6"
        for row in active
    )
    assert archive["original_count"] == len(active) + archive["retired_count"]

    bot = load_bot(app_dir)
    status_text = bot.build_status_text()
    shadow_text = bot.build_shadow_command_text(active)
    assert "Strategi    : A LIVE" in status_text
    assert "NOT APPROVED LIVE" in shadow_text
    assert "C1 legacy: RETIRED" in shadow_text
    assert "A high-volume shadow: RETIRED" in shadow_text

    return {
        "active_c6": len(active),
        "closed_c6": sum(
            row.get("status") in ("SHADOW_WIN", "SHADOW_LOSS")
            for row in active
        ),
        "open_c6": sum(row.get("status") == "SHADOW_OPEN" for row in active),
        "retired": archive["retired_count"],
        "archive": str(archives[-1]),
        "status_text": status_text,
        "shadow_text": shadow_text,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--app-dir", type=Path, default=Path("/opt/kt-auto-trading-bot"))
    args = parser.parse_args()
    print(json.dumps(verify(args.app_dir), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
