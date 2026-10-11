import argparse
import importlib
import json
import pathlib
import sys


D1_COMMAND = {
    "command": "d1shadow",
    "description": "pantau Strategy D1 forward shadow",
}


def merge_command(commands):
    merged = []
    found = False
    for item in commands:
        if not isinstance(item, dict):
            continue
        command = str(item.get("command", "")).strip().lower()
        description = str(item.get("description", "")).strip()
        if not command or not description:
            continue
        if command == D1_COMMAND["command"]:
            if not found:
                merged.append(dict(D1_COMMAND))
                found = True
            continue
        merged.append({
            "command": command,
            "description": description,
        })
    if not found:
        merged.append(dict(D1_COMMAND))
    return merged


def require_ok(result, method):
    if not isinstance(result, dict) or not result.get("ok"):
        raise RuntimeError(f"Telegram {method} failed")
    return result.get("result")


def main():
    parser = argparse.ArgumentParser(
        description="Check or append /d1shadow to the Telegram command menu",
    )
    parser.add_argument(
        "--app-dir",
        default="/opt/kt-auto-trading-bot",
    )
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    app_dir = pathlib.Path(args.app_dir).resolve()
    sys.path.insert(0, str(app_dir))
    bot = importlib.import_module("v3_swing_bot_fixed")

    current = require_ok(
        bot.telegram_api("getMyCommands", {}),
        "getMyCommands",
    )
    if not isinstance(current, list):
        raise RuntimeError("Telegram returned an invalid command list")
    merged = merge_command(current)
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
    has_d1 = any(
        isinstance(item, dict)
        and item.get("command") == D1_COMMAND["command"]
        and item.get("description") == D1_COMMAND["description"]
        for item in verified
    )
    if args.apply and not has_d1:
        raise RuntimeError("Telegram command verification failed")

    print(json.dumps({
        "apply": args.apply,
        "changed": changed,
        "command_count": len(verified),
        "d1shadow_present": has_d1,
    }, sort_keys=True))


if __name__ == "__main__":
    main()
