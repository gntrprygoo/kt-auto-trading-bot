#!/usr/bin/env bash
set -Eeuo pipefail

APP_DIR="${1:-/opt/kt-auto-trading-bot}"
STAGED_MAIN="${2:-/tmp/v3_swing_bot_fixed.c6.py}"
STAGED_CONFIG_TOOL="${3:-/tmp/apply_quality_config.c6.py}"
STAGED_VERIFY_TOOL="${4:-/tmp/verify_runtime_settings.c6.py}"
SERVICE="kt-auto-trading-bot"
SERVICE_USER="kulitrader"
MAIN_PATH="$APP_DIR/v3_swing_bot_fixed.py"
CONFIG_PATH="$APP_DIR/config.json"
VERIFY_PATH="$APP_DIR/tools/verify_runtime_settings.py"
PYTHON_PATH="$APP_DIR/.venv/bin/python"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
BACKUP_DIR="$APP_DIR/backups/deploy-c6-$STAMP"
DEPLOY_STARTED=0

rollback() {
    local exit_code=$?
    trap - ERR
    if [[ "$DEPLOY_STARTED" == "1" ]]; then
        echo "deploy_failed: restoring $BACKUP_DIR"
        sudo install -o "$SERVICE_USER" -g "$SERVICE_USER" -m 0644 \
            "$BACKUP_DIR/v3_swing_bot_fixed.py" "$MAIN_PATH"
        sudo install -o "$SERVICE_USER" -g "$SERVICE_USER" -m 0600 \
            "$BACKUP_DIR/config.json" "$CONFIG_PATH"
        if [[ -f "$BACKUP_DIR/verify_runtime_settings.py" ]]; then
            sudo install -o "$SERVICE_USER" -g "$SERVICE_USER" -m 0644 \
                "$BACKUP_DIR/verify_runtime_settings.py" "$VERIFY_PATH"
        fi
        sudo systemctl restart "$SERVICE" || true
    fi
    exit "$exit_code"
}
trap rollback ERR

test -f "$STAGED_MAIN"
test -f "$STAGED_CONFIG_TOOL"
test -f "$STAGED_VERIFY_TOOL"
test -x "$PYTHON_PATH"
test -f "$MAIN_PATH"
test -f "$CONFIG_PATH"

"$PYTHON_PATH" -m py_compile \
    "$STAGED_MAIN" "$STAGED_CONFIG_TOOL" "$STAGED_VERIFY_TOOL"

sudo mkdir -p "$BACKUP_DIR" "$APP_DIR/tools"
sudo cp -p "$MAIN_PATH" "$BACKUP_DIR/v3_swing_bot_fixed.py"
sudo cp -p "$CONFIG_PATH" "$BACKUP_DIR/config.json"
if [[ -f "$VERIFY_PATH" ]]; then
    sudo cp -p "$VERIFY_PATH" "$BACKUP_DIR/verify_runtime_settings.py"
fi
DEPLOY_STARTED=1

sudo systemctl stop "$SERVICE"
sudo install -o "$SERVICE_USER" -g "$SERVICE_USER" -m 0644 "$STAGED_MAIN" "$MAIN_PATH"
sudo install -o "$SERVICE_USER" -g "$SERVICE_USER" -m 0644 \
    "$STAGED_VERIFY_TOOL" "$VERIFY_PATH"
sudo "$PYTHON_PATH" "$STAGED_CONFIG_TOOL" "$CONFIG_PATH"
sudo chown "$SERVICE_USER:$SERVICE_USER" "$CONFIG_PATH"
sudo chmod 0600 "$CONFIG_PATH"
sudo "$PYTHON_PATH" -m py_compile "$MAIN_PATH" "$VERIFY_PATH"
sudo -u "$SERVICE_USER" "$PYTHON_PATH" "$VERIFY_PATH" "$MAIN_PATH"

sudo systemctl restart "$SERVICE"
sleep 8
test "$(sudo systemctl is-active "$SERVICE")" = "active"

DEPLOY_STARTED=0
trap - ERR
echo "deploy_ok: backup=$BACKUP_DIR"
sha256sum "$MAIN_PATH"
sudo systemctl show "$SERVICE" -p MainPID -p NRestarts --value
