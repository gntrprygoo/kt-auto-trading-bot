#!/usr/bin/env bash
set -Eeuo pipefail

STAGED_DIR="${1:-/tmp/kt-d1-shadow-upload}"
APP_DIR="${2:-/opt/kt-d1-shadow}"
STATE_DIR="${3:-/var/lib/kt-d1-shadow}"
SERVICE_USER="${SERVICE_USER:-kulitrader}"
SERVICE="kt-strategy-d1-shadow"
LIVE_SERVICE="kt-auto-trading-bot"
PYTHON="/usr/bin/python3"
LIVE_PID_BEFORE="$(sudo systemctl show "$LIVE_SERVICE" -p MainPID --value)"

test -x "$PYTHON"
test -f "$STAGED_DIR/strategy_d1_shadow.py"
test -f "$STAGED_DIR/strategy_d_momentum_engine.py"
test -f "$STAGED_DIR/build_btc_structure_review.py"
test -f "$STAGED_DIR/STRATEGY_D1_FORWARD_SHADOW_RUNBOOK.md"
test -f "$STAGED_DIR/$SERVICE.service"
test -f "$STAGED_DIR/$SERVICE.timer"
grep -q 'production_orders.*False' "$STAGED_DIR/strategy_d1_shadow.py"
if grep -Eq 'v3_swing_bot_fixed|config\.json|fapi/v1/order' \
    "$STAGED_DIR/strategy_d1_shadow.py"; then
    echo "shadow_isolation_check_failed"
    exit 1
fi

"$PYTHON" -m py_compile \
    "$STAGED_DIR/strategy_d1_shadow.py" \
    "$STAGED_DIR/strategy_d_momentum_engine.py" \
    "$STAGED_DIR/build_btc_structure_review.py"

sudo install -d -o root -g root -m 0755 "$APP_DIR"
sudo install -d -o "$SERVICE_USER" -g "$SERVICE_USER" -m 0700 \
    "$STATE_DIR"
sudo install -o root -g root -m 0644 \
    "$STAGED_DIR/strategy_d1_shadow.py" \
    "$STAGED_DIR/strategy_d_momentum_engine.py" \
    "$STAGED_DIR/build_btc_structure_review.py" \
    "$APP_DIR/"
sudo install -o root -g root -m 0644 \
    "$STAGED_DIR/STRATEGY_D1_FORWARD_SHADOW_RUNBOOK.md" \
    "$APP_DIR/"
sudo install -o root -g root -m 0644 \
    "$STAGED_DIR/$SERVICE.service" \
    "/etc/systemd/system/$SERVICE.service"
sudo install -o root -g root -m 0644 \
    "$STAGED_DIR/$SERVICE.timer" \
    "/etc/systemd/system/$SERVICE.timer"

sudo systemctl daemon-reload
sudo systemctl start "$SERVICE.service"
test "$(sudo systemctl show "$SERVICE.service" -p Result --value)" = \
    "success"
test -f "$STATE_DIR/state.json"
grep -q 'KT_STRATEGY_D1_FORWARD_SHADOW_V1' "$STATE_DIR/state.json"
sudo systemctl enable --now "$SERVICE.timer"
test "$(sudo systemctl is-active "$SERVICE.timer")" = "active"

test "$(sudo systemctl is-active "$LIVE_SERVICE")" = "active"
LIVE_PID_AFTER="$(sudo systemctl show "$LIVE_SERVICE" -p MainPID --value)"
test "$LIVE_PID_BEFORE" = "$LIVE_PID_AFTER"

echo "d1_shadow_install_ok"
echo "live_service_pid=$LIVE_PID_AFTER"
sudo systemctl list-timers "$SERVICE.timer" --no-pager
