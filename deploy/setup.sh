#!/usr/bin/env bash
# OpenClaw VPS Setup Script
# Deploys Venice AI config, .env, and systemd service
# Usage: bash setup.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_DIR="/root/.openclaw"
SERVICE_FILE="/etc/systemd/system/openclaw-gateway.service"

echo "=== OpenClaw VPS Setup ==="

# 1. Load nvm if available
export NVM_DIR="$HOME/.nvm"
if [ -f "$NVM_DIR/nvm.sh" ]; then
  # shellcheck source=/dev/null
  source "$NVM_DIR/nvm.sh"
fi

# 2. Ensure Node >= 22
NODE_MAJOR=$(node --version 2>/dev/null | cut -d. -f1 | tr -d 'v' || echo "0")
if [ "${NODE_MAJOR}" -lt 22 ] 2>/dev/null; then
  echo "[!!] Node.js 22+ required (found: $(node --version 2>/dev/null || echo 'none'))"
  echo "     Installing nvm + Node 22..."
  curl -fsSL https://raw.githubusercontent.com/nvm-sh/nvm/v0.39.7/install.sh | bash
  # shellcheck source=/dev/null
  source "$NVM_DIR/nvm.sh"
  nvm install 22
  nvm use 22
  nvm alias default 22
  echo "[OK] Node $(node --version) installed"
fi

# 3. Ensure openclaw is installed
if ! command -v openclaw &>/dev/null; then
  echo "[!!] openclaw not found — installing..."
  npm install -g openclaw
fi

OPENCLAW_BIN=$(command -v openclaw)
NVM_BIN=$(dirname "$OPENCLAW_BIN")
echo "[OK] openclaw: $OPENCLAW_BIN"

# 4. Create config dir
mkdir -p "$CONFIG_DIR/workspace"

# 5. Deploy openclaw.json if not present
if [ ! -f "$CONFIG_DIR/openclaw.json" ]; then
  cp "$SCRIPT_DIR/openclaw.json" "$CONFIG_DIR/openclaw.json"
  chmod 600 "$CONFIG_DIR/openclaw.json"
  echo "[OK] openclaw.json deployed"
else
  echo "[SKIP] openclaw.json already exists — not overwriting"
  echo "       To reset: cp $SCRIPT_DIR/openclaw.json $CONFIG_DIR/openclaw.json"
fi

# 6. Deploy .env if not present
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

# 7. Validate .env has required keys
for VAR in OPENAI_API_KEY TELEGRAM_BOT_TOKEN OPENCLAW_GATEWAY_TOKEN; do
  if ! grep -q "^${VAR}=." "$CONFIG_DIR/.env"; then
    echo "[ERROR] $VAR is not set in $CONFIG_DIR/.env"
    echo "        Edit the file and re-run this script."
    exit 1
  fi
done
echo "[OK] .env validated"

# 8. Substitute env vars into openclaw.json
# shellcheck source=/dev/null
source "$CONFIG_DIR/.env"
BOT_TOKEN="${TELEGRAM_BOT_TOKEN:-}"
OWNER_ID="${OPENCLAW_OWNER_TELEGRAM_ID:-telegram:CHANGEME}"
sed -i "s|\${TELEGRAM_BOT_TOKEN}|$BOT_TOKEN|g" "$CONFIG_DIR/openclaw.json"
sed -i "s|\${OPENCLAW_OWNER_TELEGRAM_ID}|$OWNER_ID|g" "$CONFIG_DIR/openclaw.json"
echo "[OK] openclaw.json env vars substituted"

# 9. Stop any existing openclaw processes
openclaw gateway stop 2>/dev/null || true
pkill -9 -f "^openclaw$" 2>/dev/null || true
sleep 2

# 10. Write systemd service with auto-detected binary path
cat > "$SERVICE_FILE" << EOF
[Unit]
Description=OpenClaw Gateway (Venice AI)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=root
WorkingDirectory=/root
EnvironmentFile=$CONFIG_DIR/.env
Environment="PATH=$NVM_BIN:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
ExecStart=$OPENCLAW_BIN gateway --bind lan --port 18789
Restart=on-failure
RestartSec=10
StartLimitIntervalSec=60
StartLimitBurst=3
SuccessExitStatus=78
StandardOutput=journal
StandardError=journal
SyslogIdentifier=openclaw-gateway

[Install]
WantedBy=multi-user.target
EOF
echo "[OK] systemd service written: $OPENCLAW_BIN"

# 11. Enable and start
systemctl daemon-reload
systemctl enable openclaw-gateway
systemctl restart openclaw-gateway
sleep 6

# 12. Verify
echo ""
echo "=== Status ==="
systemctl status openclaw-gateway --no-pager | head -15
echo ""
curl -s http://localhost:18789/healthz && echo ""
echo ""
echo "=== Done ==="
echo "Bot is live. Message your Telegram bot to test."
echo "Logs: journalctl -u openclaw-gateway -f"
