#!/usr/bin/env bash
set -Eeuo pipefail

APP_DIR="${1:-/opt/kt-auto-trading-bot}"
STAGED_MAIN="${2:-/tmp/v3_swing_bot_fixed.d1-command.py}"
SERVICE="kt-auto-trading-bot"
D1_SERVICE="kt-strategy-d1-shadow"
SERVICE_USER="kulitrader"
MAIN_PATH="$APP_DIR/v3_swing_bot_fixed.py"
PYTHON_PATH="$APP_DIR/.venv/bin/python"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
BACKUP_DIR="$APP_DIR/backups/deploy-d1-command-$STAMP"
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
grep -q 'D1_TELEGRAM_COMMAND_VERSION = "D1.0"' "$STAGED_MAIN"
grep -q 'def build_d1_shadow_command_text' "$STAGED_MAIN"
grep -q '"/d1shadow"' "$STAGED_MAIN"
"$PYTHON_PATH" -m py_compile "$STAGED_MAIN"

test "$(sudo systemctl is-active "$SERVICE")" = "active"
test "$(sudo systemctl is-active "$D1_SERVICE.timer")" = "active"
test -f /var/lib/kt-d1-shadow/state.json
grep -q 'KT_STRATEGY_D1_FORWARD_SHADOW_V1' \
    /var/lib/kt-d1-shadow/state.json

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
test "$(sudo systemctl is-active "$D1_SERVICE.timer")" = "active"
grep -q 'D1_TELEGRAM_COMMAND_VERSION = "D1.0"' "$MAIN_PATH"

COMMAND_PREVIEW="$(
    cd "$APP_DIR"
    sudo -u "$SERVICE_USER" env \
        KT_BOT_CONFIG="$APP_DIR/config.json" \
        "$PYTHON_PATH" -c \
        'import v3_swing_bot_fixed as bot; print(bot.handle_telegram_command("/d1shadow", chat_id=bot.ADMIN_CHAT_IDS[0]))'
)"
grep -q 'D1 FORWARD SHADOW' <<<"$COMMAND_PREVIEW"
grep -q 'LONG ONLY / NO ORDER' <<<"$COMMAND_PREVIEW"
grep -q 'Worker      : HEALTHY' <<<"$COMMAND_PREVIEW"

DEPLOY_STARTED=0
trap - ERR
echo "deploy_ok: backup=$BACKUP_DIR"
sha256sum "$MAIN_PATH"
sudo systemctl show "$SERVICE" \
    -p MainPID -p NRestarts -p ActiveEnterTimestamp --no-pager
sudo systemctl list-timers "$D1_SERVICE.timer" --no-pager
printf '%s\n' "$COMMAND_PREVIEW"
