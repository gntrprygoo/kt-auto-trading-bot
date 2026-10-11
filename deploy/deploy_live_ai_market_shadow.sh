#!/usr/bin/env bash
set -euo pipefail

UPLOAD_DIR="${1:-/tmp/kt-ai-market-live-upload}"
APP_DIR="${APP_DIR:-/opt/kt-auto-trading-bot}"
SERVICE_NAME="${SERVICE_NAME:-kt-auto-trading-bot}"
SERVICE_USER="${SERVICE_USER:-kulitrader}"
ENV_FILE="${ENV_FILE:-/etc/kt-auto-trading-bot/hybrid-ai.env}"
PYTHON_PATH="$APP_DIR/.venv/bin/python"
STAMP="$(date -u +%Y%m%d_%H%M%S)"
BACKUP_DIR="$APP_DIR/backups/deploy-ai-market-live-$STAMP"

for required in \
    v3_swing_bot_fixed.py \
    ai_market_scanner.py \
    ai_range_setup.py \
    live_ai_market.py \
    range_setup_shadow.py \
    tools/verify_live_ai_market_deployment.py \
    tools/sync_hybrid_ai_telegram_commands.py; do
    test -f "$UPLOAD_DIR/$required" || {
        echo "Missing staged file: $UPLOAD_DIR/$required" >&2
        exit 2
    }
done
test -f "$APP_DIR/config.json" || {
    echo "Production config is missing: $APP_DIR/config.json" >&2
    exit 2
}
test -x "$PYTHON_PATH" || {
    echo "Production Python is missing: $PYTHON_PATH" >&2
    exit 2
}
sudo test -r "$ENV_FILE" || {
    echo "Service environment file is missing or unreadable: $ENV_FILE" >&2
    exit 2
}

sudo install -d -o "$SERVICE_USER" -g "$SERVICE_USER" -m 0700 "$BACKUP_DIR"
for filename in v3_swing_bot_fixed.py ai_market_scanner.py ai_range_setup.py live_ai_market.py range_setup_shadow.py config.json; do
    sudo cp -p "$APP_DIR/$filename" "$BACKUP_DIR/" 2>/dev/null || true
done

rollback() {
    echo "Deployment failed; restoring backup from $BACKUP_DIR" >&2
    for filename in v3_swing_bot_fixed.py ai_market_scanner.py ai_range_setup.py live_ai_market.py range_setup_shadow.py config.json; do
        sudo cp -p "$BACKUP_DIR/$filename" "$APP_DIR/$filename" 2>/dev/null || true
    done
    sudo systemctl restart "$SERVICE_NAME" || true
}
trap rollback ERR

sudo install -o "$SERVICE_USER" -g "$SERVICE_USER" -m 0644 \
    "$UPLOAD_DIR/v3_swing_bot_fixed.py" "$APP_DIR/v3_swing_bot_fixed.py"
sudo install -o "$SERVICE_USER" -g "$SERVICE_USER" -m 0644 \
    "$UPLOAD_DIR/ai_market_scanner.py" "$APP_DIR/ai_market_scanner.py"
sudo install -o "$SERVICE_USER" -g "$SERVICE_USER" -m 0644 \
    "$UPLOAD_DIR/ai_range_setup.py" "$APP_DIR/ai_range_setup.py"
sudo install -o "$SERVICE_USER" -g "$SERVICE_USER" -m 0644 \
    "$UPLOAD_DIR/live_ai_market.py" "$APP_DIR/live_ai_market.py"
sudo install -o "$SERVICE_USER" -g "$SERVICE_USER" -m 0644 \
    "$UPLOAD_DIR/range_setup_shadow.py" "$APP_DIR/range_setup_shadow.py"
sudo install -d -o "$SERVICE_USER" -g "$SERVICE_USER" -m 0755 "$APP_DIR/tools"
sudo install -o "$SERVICE_USER" -g "$SERVICE_USER" -m 0644 \
    "$UPLOAD_DIR/tools/verify_live_ai_market_deployment.py" \
    "$APP_DIR/tools/verify_live_ai_market_deployment.py"
sudo install -o "$SERVICE_USER" -g "$SERVICE_USER" -m 0644 \
    "$UPLOAD_DIR/tools/sync_hybrid_ai_telegram_commands.py" \
    "$APP_DIR/tools/sync_hybrid_ai_telegram_commands.py"
sudo install -d -o "$SERVICE_USER" -g "$SERVICE_USER" -m 0700 "$APP_DIR/data"

sudo -u "$SERVICE_USER" /usr/bin/python3 - "$APP_DIR/config.json" "$APP_DIR" <<'PY'
import json
import os
from pathlib import Path
import sys
import tempfile

path = Path(sys.argv[1])
app_dir = Path(sys.argv[2])
config = json.loads(path.read_text(encoding="utf-8-sig"))
live = config.setdefault("ai_market_live", {})
live.update({
    "enabled": True,
    "mode": "RESEARCH_SHADOW_ONLY",
    "research_status": "rejected_historical_shadow_observation_only",
    "model": "gpt-5.6-sol",
    "reasoning_effort": "low",
    "api_key_env": "OPENAI_API_KEY",
    "prompt_id": "P6_RANGE_ABSORPTION_SETUP",
    "scan_interval_sec": 3600,
    "setup_monitor_interval_sec": 300,
    "failure_retry_sec": 900,
    "request_timeout_sec": 45,
    "max_output_tokens": 1800,
    "candle_limit": 800,
    "min_closed_bars": 700,
    "symbols": [
        "BTCUSDT", "ETHUSDT", "SOLUSDT",
        "ADAUSDT", "DOGEUSDT", "XRPUSDT",
    ],
    "require_authenticated_binance": True,
    "notify_admin_on_setup": True,
    "notify_admin_on_lifecycle": True,
    "state_path": str(app_dir / "data/ai_market_live_state_v3.json"),
    "history_path": str(app_dir / "data/ai_market_live_history_v3.jsonl"),
})
fd, temp_name = tempfile.mkstemp(prefix=".config.", dir=str(path.parent))
try:
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        json.dump(config, handle, indent=2)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temp_name, path)
    os.chmod(path, 0o600)
except Exception:
    try:
        os.unlink(temp_name)
    except OSError:
        pass
    raise
PY

sudo -u "$SERVICE_USER" "$PYTHON_PATH" - \
    "$APP_DIR/v3_swing_bot_fixed.py" \
    "$APP_DIR/ai_market_scanner.py" \
    "$APP_DIR/ai_range_setup.py" \
    "$APP_DIR/live_ai_market.py" \
    "$APP_DIR/range_setup_shadow.py" \
    "$APP_DIR/tools/verify_live_ai_market_deployment.py" \
    "$APP_DIR/tools/sync_hybrid_ai_telegram_commands.py" <<'PY'
from pathlib import Path
import sys
import tokenize

for filename in sys.argv[1:]:
    with tokenize.open(filename) as handle:
        compile(handle.read(), str(Path(filename)), "exec")
print(f"syntax_ok files={len(sys.argv) - 1}")
PY

sudo systemctl restart "$SERVICE_NAME"
sleep 5
sudo systemctl is-active --quiet "$SERVICE_NAME"
sudo systemctl show "$SERVICE_NAME" -p ActiveState -p SubState -p NRestarts -p MainPID
sudo "$PYTHON_PATH" \
    "$APP_DIR/tools/verify_live_ai_market_deployment.py" \
    --config "$APP_DIR/config.json" \
    --environment-file "$ENV_FILE" \
    --expect-openai-key present

sudo -u "$SERVICE_USER" env KT_BOT_CONFIG="$APP_DIR/config.json" \
    "$PYTHON_PATH" \
    "$APP_DIR/tools/sync_hybrid_ai_telegram_commands.py" \
    --app-dir "$APP_DIR" --apply || \
    echo "WARNING: Telegram command sync failed; deployment remains active." >&2

trap - ERR
echo "OpenAI live market analyzer deployed in research shadow-only mode."
echo "Order access remains locked. No Binance credential is sent to OpenAI."
