import argparse
import importlib.util
import pathlib


def main():
    parser = argparse.ArgumentParser(description="Send one KT bot admin update.")
    parser.add_argument("bot_script")
    parser.add_argument("message_file")
    args = parser.parse_args()

    bot_script = pathlib.Path(args.bot_script).resolve()
    message_file = pathlib.Path(args.message_file).resolve()
    spec = importlib.util.spec_from_file_location("kt_bot_admin_sender", bot_script)
    bot = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(bot)
    bot._load_config_overrides()

    message = message_file.read_text(encoding="utf-8").strip()
    result = bot.telegram_api("sendMessage", {
        "chat_id": str(bot.TARGET_CHAT_ID),
        "text": message,
        "disable_web_page_preview": True,
    })
    if not result or not result.get("ok"):
        raise SystemExit("telegram_update_sent=false")
    print("telegram_update_sent=true")


if __name__ == "__main__":
    main()
