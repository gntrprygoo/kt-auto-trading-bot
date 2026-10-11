import argparse
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parents[1]
BOT_SCRIPT = PROJECT_DIR / "v3_swing_bot_fixed.py"
USERS_DIR = PROJECT_DIR / "users"
RUNTIME_DIR = PROJECT_DIR / "runtime"


def read_json(path, default=None):
    if not path.exists():
        return default
    with path.open("r", encoding="utf-8-sig") as f:
        return json.load(f)


def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def bundled_python():
    candidate = Path.home() / ".cache" / "codex-runtimes" / "codex-primary-runtime" / "dependencies" / "python" / "python.exe"
    if candidate.exists():
        return str(candidate)
    return sys.executable or "python"


def user_dir(chat_id):
    return USERS_DIR / str(chat_id)


def user_config_path(chat_id):
    return user_dir(chat_id) / "config.json"


def pid_path(chat_id):
    return user_dir(chat_id) / "worker.pid"


def load_base_config():
    config_path = PROJECT_DIR / "config.json"
    if not config_path.exists():
        config_path = PROJECT_DIR / "config.example.json"
    return read_json(config_path, {})


def is_process_running(pid):
    if not pid:
        return False
    try:
        os.kill(int(pid), 0)
        return True
    except OSError:
        return False


def build_user_config(args):
    chat_id = str(args.chat_id)
    base = load_base_config()
    udir = user_dir(chat_id)
    data_dir = udir / "data"
    logs_dir = udir / "logs"
    backups_dir = udir / "backups"

    cfg = {
        "product": {
            "bot_tag": f"KT-U{chat_id[-4:]}",
        },
        "telegram": {
            "bot_token": args.telegram_token or base.get("telegram", {}).get("bot_token", ""),
            "chat_id": chat_id,
            "admin_chat_ids": base.get("telegram", {}).get("admin_chat_ids", []),
            "default_trial_days": base.get("telegram", {}).get("default_trial_days", 7),
            "enable_commands": False,
        },
        "binance": {
            "base_url": base.get("binance", {}).get("base_url", "https://fapi.binance.com"),
            "api_key": args.api_key,
            "api_secret": args.api_secret,
        },
        "risk": {
            "fixed_notional_usdt": args.notional,
            "risk_per_trade_usdt": base.get("risk", {}).get("risk_per_trade_usdt", 0.5),
            "leverage": args.leverage,
            "max_concurrent_trades": args.max_concurrent,
            "max_same_pair_open": 1,
            "daily_loss_limit_r": args.daily_loss_limit_r,
        },
        "universe": base.get("universe", {
            "enable_dynamic_pairs": True,
            "min_pair_volume_usdt": 15000000,
            "max_dynamic_pairs": 100,
        }),
        "safety": base.get("safety", {
            "enable_time_filter": False,
            "enable_startup_audit": True,
            "enable_orphan_order_audit": True,
            "audit_alert_cooldown_sec": 21600,
        }),
        "paths": {
            "journal_path": str(data_dir / "journal_v3.json"),
            "log_path": str(logs_dir / "scan_v3.log"),
            "report_state_path": str(data_dir / "daily_report_state_v3.json"),
            "heartbeat_path": str(data_dir / "heartbeat_v3.txt"),
            "user_registry_path": str(RUNTIME_DIR / "user_registry_v1.json"),
            "breakout_state_path": str(data_dir / "breakout_state_v3.json"),
            "shadow_trades_path": str(data_dir / "shadow_trades_v3.json"),
            "journal_backup_dir": str(backups_dir),
        },
    }
    return cfg


def cmd_create(args):
    cfg_path = user_config_path(args.chat_id)
    if cfg_path.exists() and not args.force:
        raise SystemExit(f"Config already exists: {cfg_path}. Use --force to overwrite.")
    cfg = build_user_config(args)
    write_json(cfg_path, cfg)
    print(f"created user config: {cfg_path}")


def cmd_start(args):
    chat_id = str(args.chat_id)
    cfg_path = user_config_path(chat_id)
    if not cfg_path.exists():
        raise SystemExit(f"Missing user config: {cfg_path}. Run create first.")

    ppath = pid_path(chat_id)
    if ppath.exists():
        old_pid = ppath.read_text(encoding="utf-8").strip()
        if is_process_running(old_pid):
            raise SystemExit(f"Worker already running for {chat_id}: pid {old_pid}")

    log_dir = user_dir(chat_id) / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    stdout_path = log_dir / "worker_stdout.log"

    env = os.environ.copy()
    env["KT_BOT_CONFIG"] = str(cfg_path)

    cmd = [
        bundled_python(),
        str(BOT_SCRIPT),
        "--run-interval",
        str(args.run_interval),
        "--max-workers",
        str(args.max_workers),
    ]
    if args.simulate:
        cmd.insert(2, "--simulate")

    stdout = stdout_path.open("a", encoding="utf-8")
    proc = subprocess.Popen(
        cmd,
        cwd=str(PROJECT_DIR),
        env=env,
        stdout=stdout,
        stderr=subprocess.STDOUT,
        creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0),
    )
    ppath.write_text(str(proc.pid), encoding="utf-8")
    print(f"started worker chat_id={chat_id} pid={proc.pid}")
    print(f"stdout log: {stdout_path}")


def cmd_stop(args):
    ppath = pid_path(args.chat_id)
    if not ppath.exists():
        print(f"no pid file for {args.chat_id}")
        return
    pid = int(ppath.read_text(encoding="utf-8").strip())
    if not is_process_running(pid):
        print(f"worker not running: {pid}")
        ppath.unlink(missing_ok=True)
        return
    os.kill(pid, signal.SIGTERM)
    time.sleep(2)
    if is_process_running(pid):
        print(f"worker still running after SIGTERM: {pid}")
    else:
        ppath.unlink(missing_ok=True)
        print(f"stopped worker: {pid}")


def cmd_status(args):
    chat_id = str(args.chat_id)
    cfg_path = user_config_path(chat_id)
    ppath = pid_path(chat_id)
    pid = ppath.read_text(encoding="utf-8").strip() if ppath.exists() else ""
    running = is_process_running(pid) if pid else False
    cfg = read_json(cfg_path, {}) if cfg_path.exists() else {}
    heartbeat_value = cfg.get("paths", {}).get("heartbeat_path")
    heartbeat = Path(heartbeat_value) if heartbeat_value else None
    age = "n/a"
    if heartbeat and heartbeat.exists():
        age = f"{int(time.time() - heartbeat.stat().st_mtime)}s"
    print(f"chat_id: {chat_id}")
    print(f"config : {cfg_path} ({'yes' if cfg_path.exists() else 'missing'})")
    print(f"pid    : {pid or 'n/a'}")
    print(f"running: {running}")
    print(f"heartbeat_age: {age}")


def main():
    parser = argparse.ArgumentParser(description="KT Auto Trading Bot managed worker manager")
    sub = parser.add_subparsers(dest="cmd", required=True)

    create = sub.add_parser("create")
    create.add_argument("--chat-id", required=True)
    create.add_argument("--api-key", required=True)
    create.add_argument("--api-secret", required=True)
    create.add_argument("--telegram-token", default="")
    create.add_argument("--notional", type=float, default=50)
    create.add_argument("--leverage", type=int, default=3)
    create.add_argument("--max-concurrent", type=int, default=3)
    create.add_argument("--daily-loss-limit-r", type=float, default=-3)
    create.add_argument("--force", action="store_true")
    create.set_defaults(func=cmd_create)

    start = sub.add_parser("start")
    start.add_argument("--chat-id", required=True)
    start.add_argument("--run-interval", type=int, default=15)
    start.add_argument("--max-workers", type=int, default=8)
    start.add_argument("--simulate", action="store_true")
    start.set_defaults(func=cmd_start)

    stop = sub.add_parser("stop")
    stop.add_argument("--chat-id", required=True)
    stop.set_defaults(func=cmd_stop)

    status = sub.add_parser("status")
    status.add_argument("--chat-id", required=True)
    status.set_defaults(func=cmd_status)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
