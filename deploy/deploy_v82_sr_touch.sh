#!/usr/bin/env bash
set -Eeuo pipefail

APP_DIR="${1:-/opt/kt-auto-trading-bot}"
STAGED_MAIN="${2:-/tmp/v3_swing_bot_fixed.v82.py}"
SERVICE="kt-auto-trading-bot"
SERVICE_USER="kulitrader"
MAIN_PATH="$APP_DIR/v3_swing_bot_fixed.py"
PYTHON_PATH="$APP_DIR/.venv/bin/python"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
BACKUP_DIR="$APP_DIR/backups/deploy-v82-sr-touch-$STAMP"
DEPLOY_STARTED=0

rollback() {
    local exit_code=$?
    trap - ERR
    if [[ "$DEPLOY_STARTED" == "1" ]]; then
        echo "deploy_failed: restoring $BACKUP_DIR"
        sudo install -o "$SERVICE_USER" -g "$SERVICE_USER" -m 0644 \
            "$BACKUP_DIR/v3_swing_bot_fixed.py" "$MAIN_PATH"
        sudo systemctl restart "$SERVICE" || true
    fi
    exit "$exit_code"
}
trap rollback ERR

test -f "$STAGED_MAIN"
test -x "$PYTHON_PATH"
test -f "$MAIN_PATH"
grep -q 'QUALITY_GATE_VERSION.*V8.2-SR-TOUCH' "$STAGED_MAIN"
"$PYTHON_PATH" -m py_compile "$STAGED_MAIN"

sudo mkdir -p "$BACKUP_DIR"
sudo cp -p "$MAIN_PATH" "$BACKUP_DIR/v3_swing_bot_fixed.py"
DEPLOY_STARTED=1

sudo systemctl stop "$SERVICE"
sudo install -o "$SERVICE_USER" -g "$SERVICE_USER" -m 0644 \
    "$STAGED_MAIN" "$MAIN_PATH"
sudo "$PYTHON_PATH" -m py_compile "$MAIN_PATH"
sudo systemctl restart "$SERVICE"
sleep 8

test "$(sudo systemctl is-active "$SERVICE")" = "active"
test "$(pgrep -fc "$PYTHON_PATH $MAIN_PATH --run-interval")" = "1"
grep -q 'QUALITY_GATE_VERSION.*V8.2-SR-TOUCH' "$MAIN_PATH"

DEPLOY_STARTED=0
trap - ERR
echo "deploy_ok: backup=$BACKUP_DIR"
sha256sum "$MAIN_PATH"
sudo systemctl show "$SERVICE" \
    -p MainPID -p NRestarts -p ActiveEnterTimestamp --no-pager
