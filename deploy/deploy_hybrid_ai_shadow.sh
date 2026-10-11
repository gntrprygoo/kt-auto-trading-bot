#!/usr/bin/env bash
set -euo pipefail

UPLOAD_DIR="${1:-/tmp/kt-hybrid-ai-upload}"
APP_DIR="${APP_DIR:-/opt/kt-auto-trading-bot}"
SERVICE_NAME="${SERVICE_NAME:-kt-auto-trading-bot}"
SERVICE_USER="${SERVICE_USER:-kulitrader}"
PYTHON_PATH="$APP_DIR/.venv/bin/python"
STAMP="$(date -u +%Y%m%d_%H%M%S)"
BACKUP_DIR="$APP_DIR/backups/deploy-hybrid-ai-$STAMP"

for required in v3_swing_bot_fixed.py hybrid_ai_engine.py tools/verify_hybrid_ai_deployment.py tools/sync_hybrid_ai_telegram_commands.py deploy/kt-auto-trading-bot.service; do
    test -f "$UPLOAD_DIR/$required" || {
        echo "Missing staged file: $UPLOAD_DIR/$required" >&2
        exit 2
    }
done
test -f "$APP_DIR/config.json" || {
    echo "Production config is missing: $APP_DIR/config.json" >&2
    exit 2
}

sudo install -d -o "$SERVICE_USER" -g "$SERVICE_USER" -m 0700 "$BACKUP_DIR"
sudo cp -p "$APP_DIR/v3_swing_bot_fixed.py" "$BACKUP_DIR/" 2>/dev/null || true
sudo cp -p "$APP_DIR/hybrid_ai_engine.py" "$BACKUP_DIR/" 2>/dev/null || true
sudo cp -p "$APP_DIR/config.json" "$BACKUP_DIR/"
sudo cp -p "/etc/systemd/system/$SERVICE_NAME.service" "$BACKUP_DIR/" 2>/dev/null || true

rollback() {
    echo "Deployment failed; restoring backup from $BACKUP_DIR" >&2
    sudo cp -p "$BACKUP_DIR/v3_swing_bot_fixed.py" "$APP_DIR/" 2>/dev/null || true
    sudo cp -p "$BACKUP_DIR/hybrid_ai_engine.py" "$APP_DIR/" 2>/dev/null || true
    sudo cp -p "$BACKUP_DIR/config.json" "$APP_DIR/config.json" 2>/dev/null || true
    sudo cp -p "$BACKUP_DIR/$SERVICE_NAME.service" "/etc/systemd/system/$SERVICE_NAME.service" 2>/dev/null || true
    sudo systemctl daemon-reload || true
    sudo systemctl restart "$SERVICE_NAME" || true
}
trap rollback ERR

sudo install -o "$SERVICE_USER" -g "$SERVICE_USER" -m 0644 \
    "$UPLOAD_DIR/v3_swing_bot_fixed.py" "$APP_DIR/v3_swing_bot_fixed.py"
sudo install -o "$SERVICE_USER" -g "$SERVICE_USER" -m 0644 \
    "$UPLOAD_DIR/hybrid_ai_engine.py" "$APP_DIR/hybrid_ai_engine.py"
sudo install -d -o "$SERVICE_USER" -g "$SERVICE_USER" -m 0755 "$APP_DIR/tools"
sudo install -o "$SERVICE_USER" -g "$SERVICE_USER" -m 0644 \
    "$UPLOAD_DIR/tools/verify_hybrid_ai_deployment.py" \
    "$APP_DIR/tools/verify_hybrid_ai_deployment.py"
sudo install -o "$SERVICE_USER" -g "$SERVICE_USER" -m 0644 \
    "$UPLOAD_DIR/tools/sync_hybrid_ai_telegram_commands.py" \
    "$APP_DIR/tools/sync_hybrid_ai_telegram_commands.py"
sudo install -o root -g root -m 0644 \
    "$UPLOAD_DIR/deploy/kt-auto-trading-bot.service" "/etc/systemd/system/$SERVICE_NAME.service"

sudo -u "$SERVICE_USER" /usr/bin/python3 - "$APP_DIR/config.json" "$APP_DIR" <<'PY'
import json
import os
from pathlib import Path
import sys
import tempfile

path = Path(sys.argv[1])
app_dir = Path(sys.argv[2])
config = json.loads(path.read_text(encoding="utf-8-sig"))
hybrid = config.setdefault("hybrid_ai", {})
defaults = {
    "enabled": True,
    "mode": "AI_SHADOW",
    "preserve_baseline_in_shadow": True,
    "model": "gpt-5.6-luna",
    "reasoning_effort": "low",
    "api_key_env": "OPENAI_API_KEY",
    "request_timeout_sec": 30,
    "max_parallel_calls": 2,
    "min_confidence": 0.72,
    "min_setup_quality": 65,
    "min_rr": 1.5,
    "max_stop_pct": 0.03,
    "max_account_risk_pct": 0.0025,
    "max_notional_usdt": 10,
    "max_open_positions": 1,
    "max_daily_loss_r": -1,
    "max_candidate_age_sec": 1200,
    "approval_ttl_sec": 300,
    "max_price_deviation_pct": 0.003,
    "allow_live": False,
    "state_path": str(app_dir / "data/hybrid_ai_state.json"),
    "live_gate_path": str(app_dir / "data/hybrid_ai_live_gate.json"),
}
hybrid.update(defaults)
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

sudo install -d -o root -g root -m 0700 /etc/kt-auto-trading-bot
if ! sudo test -f /etc/kt-auto-trading-bot/hybrid-ai.env; then
    printf 'OPENAI_API_KEY=\n' | sudo tee /etc/kt-auto-trading-bot/hybrid-ai.env >/dev/null
fi
sudo chmod 0600 /etc/kt-auto-trading-bot/hybrid-ai.env

sudo -u "$SERVICE_USER" "$PYTHON_PATH" - \
    "$APP_DIR/hybrid_ai_engine.py" "$APP_DIR/v3_swing_bot_fixed.py" \
    "$APP_DIR/tools/verify_hybrid_ai_deployment.py" \
    "$APP_DIR/tools/sync_hybrid_ai_telegram_commands.py" <<'PY'
from pathlib import Path
import sys
import tokenize

for filename in sys.argv[1:]:
    with tokenize.open(filename) as handle:
        compile(handle.read(), str(Path(filename)), "exec")
print(f"syntax_ok files={len(sys.argv) - 1}")
PY
sudo systemctl daemon-reload
sudo systemctl restart "$SERVICE_NAME"
sleep 5
sudo systemctl is-active --quiet "$SERVICE_NAME"
sudo systemctl show "$SERVICE_NAME" -p ActiveState -p SubState -p NRestarts -p MainPID
sudo -u "$SERVICE_USER" "$PYTHON_PATH" \
    "$APP_DIR/tools/verify_hybrid_ai_deployment.py" \
    --config "$APP_DIR/config.json" --expect-key any

trap - ERR
echo "Hybrid AI code deployed in AI_SHADOW with allow_live=false."
echo "OPENAI_API_KEY is intentionally not populated by this script."
