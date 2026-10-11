#!/usr/bin/env bash
set -Eeuo pipefail

APP_DIR="${1:-/opt/kt-auto-trading-bot}"
UPLOAD_DIR="${2:-/tmp/kt-shadow-retirement}"
SERVICE="kt-auto-trading-bot"
D1_TIMER="kt-strategy-d1-shadow.timer"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
BACKUP_DIR="$APP_DIR/backups/deploy-shadow-retirement-$STAMP"
CONFIG_PATH="$APP_DIR/config.json"
SHADOW_PATH="$APP_DIR/data/shadow_trades_v3.json"
ARCHIVE_PATH="$APP_DIR/data/archive/shadow_legacy_retired_$STAMP.json"
PYTHON="$APP_DIR/.venv/bin/python"
ROLLED_BACK=0

rollback() {
    exit_code=$?
    if [ "$exit_code" -eq 0 ] || [ "$ROLLED_BACK" -eq 1 ]; then
        return
    fi
    ROLLED_BACK=1
    echo "deploy_failed: restoring $BACKUP_DIR" >&2
    sudo systemctl stop "$SERVICE" || true
    sudo cp -p "$BACKUP_DIR/v3_swing_bot_fixed.py" "$APP_DIR/v3_swing_bot_fixed.py" || true
    sudo cp -p "$BACKUP_DIR/config.json" "$CONFIG_PATH" || true
    sudo cp -p "$BACKUP_DIR/shadow_trades_v3.json" "$SHADOW_PATH" || true
    sudo systemctl restart "$SERVICE" || true
    exit "$exit_code"
}
trap rollback ERR

test -f "$UPLOAD_DIR/v3_swing_bot_fixed.py"
test -f "$UPLOAD_DIR/retire_legacy_shadow_data.py"
test -x "$PYTHON"
test -f "$CONFIG_PATH"
test -f "$SHADOW_PATH"

D1_UNIT_HASH_BEFORE="$(sudo systemctl cat kt-strategy-d1-shadow.service | sha256sum | awk '{print $1}')"
test "$(sudo systemctl is-active "$D1_TIMER")" = "active"

sudo mkdir -p "$BACKUP_DIR"
sudo cp -p "$APP_DIR/v3_swing_bot_fixed.py" "$BACKUP_DIR/v3_swing_bot_fixed.py"
sudo cp -p "$CONFIG_PATH" "$BACKUP_DIR/config.json"
sudo cp -p "$SHADOW_PATH" "$BACKUP_DIR/shadow_trades_v3.json"

sudo systemctl stop "$SERVICE"
sudo install -o kulitrader -g kulitrader -m 0644 \
    "$UPLOAD_DIR/v3_swing_bot_fixed.py" "$APP_DIR/v3_swing_bot_fixed.py"
sudo install -o kulitrader -g kulitrader -m 0644 \
    "$UPLOAD_DIR/retire_legacy_shadow_data.py" \
    "$APP_DIR/tools/retire_legacy_shadow_data.py"

sudo -u kulitrader /usr/bin/python3 - "$CONFIG_PATH" <<'PY'
import json
import os
from pathlib import Path
import sys
import tempfile

path = Path(sys.argv[1])
config = json.loads(path.read_text(encoding="utf-8-sig"))
strategy_a = config.setdefault("strategy_a", {})
strategy_a["enable_volume_shadow"] = False
strategy_a["research_status"] = "volume_shadow_retired_2026_08_04"
smart_money_c = config.setdefault("smart_money_c", {})
smart_money_c["version"] = 6
smart_money_c["enable_shadow"] = True
smart_money_c["enable_daily_report"] = False
smart_money_c["research_status"] = "forward_shadow_validation"

fd, temp_name = tempfile.mkstemp(prefix=".config.", suffix=".tmp", dir=str(path.parent))
try:
    with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
        json.dump(config, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temp_name, path)
    os.chmod(path, 0o600)
except Exception:
    try:
        os.unlink(temp_name)
    except FileNotFoundError:
        pass
    raise
PY

DRY_RUN_JSON="$(sudo -u kulitrader /usr/bin/python3 \
    "$APP_DIR/tools/retire_legacy_shadow_data.py" \
    --source "$SHADOW_PATH" --archive "$ARCHIVE_PATH" --dry-run)"
RETIRED_COUNT="$(printf '%s' "$DRY_RUN_JSON" | /usr/bin/python3 -c \
    'import json,sys; print(json.load(sys.stdin)["retired_count"])')"
ACTIVE_C6_COUNT="$(printf '%s' "$DRY_RUN_JSON" | /usr/bin/python3 -c \
    'import json,sys; print(json.load(sys.stdin)["active_c6_count"])')"
if [ "$RETIRED_COUNT" -gt 0 ]; then
    sudo -u kulitrader /usr/bin/python3 \
        "$APP_DIR/tools/retire_legacy_shadow_data.py" \
        --source "$SHADOW_PATH" --archive "$ARCHIVE_PATH"
else
    echo "shadow_migration_skipped: no legacy records"
fi

sudo -u kulitrader "$PYTHON" -m py_compile "$APP_DIR/v3_swing_bot_fixed.py"
sudo systemctl restart "$SERVICE"
sleep 5
test "$(sudo systemctl is-active "$SERVICE")" = "active"
test "$(sudo systemctl is-active "$D1_TIMER")" = "active"

D1_UNIT_HASH_AFTER="$(sudo systemctl cat kt-strategy-d1-shadow.service | sha256sum | awk '{print $1}')"
test "$D1_UNIT_HASH_BEFORE" = "$D1_UNIT_HASH_AFTER"

sudo -u kulitrader /usr/bin/python3 - \
    "$CONFIG_PATH" "$SHADOW_PATH" "$ACTIVE_C6_COUNT" <<'PY'
import json
from pathlib import Path
import sys

config = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8-sig"))
records = json.loads(Path(sys.argv[2]).read_text(encoding="utf-8-sig"))
expected_active = int(sys.argv[3])
assert config["strategy_a"]["enable_volume_shadow"] is False
assert config["smart_money_c"]["version"] == 6
assert config["smart_money_c"]["enable_shadow"] is True
assert config["smart_money_c"]["enable_daily_report"] is False
assert len(records) == expected_active, (len(records), expected_active)
assert all(
    row.get("blocked_reason") == "smart_money_c_v6"
    or row.get("strategy_version") == "C6"
    for row in records
)
print(f"runtime_state_ok active_c6={len(records)}")
PY

if sudo journalctl -u "$SERVICE" --since "2 minutes ago" --no-pager \
    | grep -E "Traceback|SyntaxError|NameError"; then
    echo "runtime_error_detected" >&2
    false
fi

trap - ERR
echo "deploy_ok backup=$BACKUP_DIR archive=$ARCHIVE_PATH retired=$RETIRED_COUNT"
sha256sum "$APP_DIR/v3_swing_bot_fixed.py"
sudo systemctl show "$SERVICE" -p ActiveState -p MainPID -p NRestarts --value
sudo systemctl list-timers "$D1_TIMER" --no-pager
