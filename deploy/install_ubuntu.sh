#!/usr/bin/env bash
set -euo pipefail

APP_USER="${APP_USER:-kulitrader}"
APP_DIR="${APP_DIR:-/opt/kt-auto-trading-bot}"
SERVICE_NAME="${SERVICE_NAME:-kt-auto-trading-bot}"

echo "[1/7] Updating Ubuntu packages..."
sudo apt-get update
sudo apt-get install -y python3 python3-venv python3-pip rsync unzip ca-certificates curl

echo "[2/7] Creating app directory: ${APP_DIR}"
sudo mkdir -p "${APP_DIR}"
sudo chown -R "${APP_USER}:${APP_USER}" "${APP_DIR}"

echo "[3/7] Creating runtime directories..."
mkdir -p "${APP_DIR}/data/backups" "${APP_DIR}/logs"

echo "[4/7] Creating Python virtual environment..."
python3 -m venv "${APP_DIR}/.venv"
"${APP_DIR}/.venv/bin/python" -m pip install --upgrade pip

echo "[5/7] Setting file permissions..."
chmod 700 "${APP_DIR}"
if [ -f "${APP_DIR}/config.json" ]; then
  chmod 600 "${APP_DIR}/config.json"
fi

echo "[6/7] Installing systemd service..."
sudo cp "${APP_DIR}/deploy/${SERVICE_NAME}.service" "/etc/systemd/system/${SERVICE_NAME}.service"
sudo systemctl daemon-reload
sudo systemctl enable "${SERVICE_NAME}"

echo "[7/7] Done."
echo ""
echo "Next:"
echo "  sudo systemctl start ${SERVICE_NAME}"
echo "  sudo systemctl status ${SERVICE_NAME}"
echo "  journalctl -u ${SERVICE_NAME} -f"
