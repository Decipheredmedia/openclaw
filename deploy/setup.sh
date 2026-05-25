#!/usr/bin/env bash
# OpenClaw VPS Setup Script
# Deploys Venice AI config, .env, and systemd service
# Usage: bash setup.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_DIR="/root/.openclaw"
SERVICE_FILE="/etc/systemd/system/openclaw-gateway.service"

echo "=== OpenClaw VPS Setup ==="

# 1. Create config dir
mkdir -p "$CONFIG_DIR/workspace"

# 2. Deploy openclaw.json if not present
if [ ! -f "$CONFIG_DIR/openclaw.json" ]; then
  cp "$SCRIPT_DIR/openclaw.json" "$CONFIG_DIR/openclaw.json"
  chmod 600 "$CONFIG_DIR/openclaw.json"
  echo "[OK] openclaw.json deployed"
else
  echo "[SKIP] openclaw.json already exists — not overwriting"
  echo "       To reset: cp $SCRIPT_DIR/openclaw.json $CONFIG_DIR/openclaw.json"
fi

# 3. Deploy .env if not present
if [ ! -f "$CONFIG_DIR/.env" ]; then
  cp "$SCRIPT_DIR/.env.example" "$CONFIG_DIR/.env"
  chmod 600 "$CONFIG_DIR/.env"
  echo "[!!] .env created from template — EDIT IT NOW:"
  echo "     nano $CONFIG_DIR/.env"
  echo "     Fill in: OPENAI_API_KEY, TELEGRAM_BOT_TOKEN, OPENCLAW_GATEWAY_TOKEN, OPENCLAW_OWNER_TELEGRAM_ID"
  exit 0
else
  echo "[OK] .env already exists"
fi

# 4. Validate .env has required keys
for VAR in OPENAI_API_KEY TELEGRAM_BOT_TOKEN OPENCLAW_GATEWAY_TOKEN; do
  if ! grep -q "^${VAR}=." "$CONFIG_DIR/.env"; then
    echo "[ERROR] $VAR is not set in $CONFIG_DIR/.env"
    echo "        Edit the file and re-run this script."
    exit 1
  fi
done
echo "[OK] .env validated"

# 5. Substitute env vars into openclaw.json
source "$CONFIG_DIR/.env"
BOT_TOKEN="${TELEGRAM_BOT_TOKEN:-}"
OWNER_ID="${OPENCLAW_OWNER_TELEGRAM_ID:-telegram:CHANGEME}"
sed -i "s|\${TELEGRAM_BOT_TOKEN}|$BOT_TOKEN|g" "$CONFIG_DIR/openclaw.json"
sed -i "s|\${OPENCLAW_OWNER_TELEGRAM_ID}|$OWNER_ID|g" "$CONFIG_DIR/openclaw.json"
echo "[OK] openclaw.json env vars substituted"

# 6. Stop any existing openclaw processes
openclaw gateway stop 2>/dev/null || true
pkill -9 -f "^openclaw$" 2>/dev/null || true
sleep 2

# 7. Install systemd service
cp "$SCRIPT_DIR/openclaw-gateway.service" "$SERVICE_FILE"
systemctl daemon-reload
systemctl enable openclaw-gateway
systemctl restart openclaw-gateway
sleep 6

# 8. Verify
echo ""
echo "=== Status ==="
systemctl status openclaw-gateway --no-pager | head -15
echo ""
curl -s http://localhost:18789/healthz
echo ""
echo "=== Done ==="
echo "Bot is live. Message your Telegram bot to test."
echo "Logs: journalctl -u openclaw-gateway -f"
