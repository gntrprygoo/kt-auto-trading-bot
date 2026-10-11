#!/usr/bin/env python3
"""Add or refresh Hybrid AI commands without removing existing bot commands."""

from __future__ import annotations

import argparse
import importlib
import json
from pathlib import Path
import sys


HYBRID_AI_COMMANDS = (
    {"command": "ai_status", "description": "status Hybrid AI dan live gate"},
    {"command": "ai_market", "description": "analisis market live OpenAI (shadow)"},
    {"command": "ai_pending", "description": "proposal AI menunggu persetujuan"},
    {"command": "ai_mode", "description": "ubah mode Hybrid AI (admin)"},
    {"command": "ai_approve", "description": "setujui proposal AI (admin)"},
    {"command": "ai_reject", "description": "tolak proposal AI (admin)"},
)


def merge_commands(commands):
    replacements = {item["command"]: item for item in HYBRID_AI_COMMANDS}
    merged = []
    seen = set()
    for item in commands:
        if not isinstance(item, dict):
            continue
        command = str(item.get("command", "")).strip().lower()
        description = str(item.get("description", "")).strip()
        if not command or not description or command in seen:
            continue
        merged.append(dict(replacements.get(command, {
            "command": command,
            "description": description,
        })))
        seen.add(command)
    for item in HYBRID_AI_COMMANDS:
        if item["command"] not in seen:
            merged.append(dict(item))
            seen.add(item["command"])
    return merged


def require_ok(result, method):
    if not isinstance(result, dict) or not result.get("ok"):
        raise RuntimeError(f"Telegram {method} failed")
    return result.get("result")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--app-dir", default="/opt/kt-auto-trading-bot")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    app_dir = Path(args.app_dir).resolve()
    sys.path.insert(0, str(app_dir))
    bot = importlib.import_module("v3_swing_bot_fixed")
    current = require_ok(bot.telegram_api("getMyCommands", {}), "getMyCommands")
    if not isinstance(current, list):
        raise RuntimeError("Telegram returned an invalid command list")
    merged = merge_commands(current)
    changed = merged != current
    if args.apply and changed:
        require_ok(
            bot.telegram_api("setMyCommands", {"commands": merged}),
            "setMyCommands",
        )
    verified = require_ok(
        bot.telegram_api("getMyCommands", {}),
        "getMyCommands verification",
    )
    expected = {item["command"]: item["description"] for item in HYBRID_AI_COMMANDS}
    actual = {
        str(item.get("command", "")): str(item.get("description", ""))
        for item in verified
        if isinstance(item, dict)
    }
    present = all(actual.get(command) == description for command, description in expected.items())
    if args.apply and not present:
        raise RuntimeError("Hybrid AI command verification failed")
    print(json.dumps({
        "apply": args.apply,
        "changed": changed,
        "command_count": len(verified),
        "hybrid_ai_commands_present": present,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
