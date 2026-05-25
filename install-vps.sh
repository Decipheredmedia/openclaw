#!/usr/bin/env bash
set -euo pipefail

if [ "${EUID:-$(id -u)}" -ne 0 ]; then
  echo "Please run this installer as root or with sudo."
  exit 1
fi

OPENCLAW_REPO_URL="${OPENCLAW_REPO_URL:-https://github.com/Decipheredmedia/openclaw}"
SKILLS_REPO_URL="${SKILLS_REPO_URL:-https://github.com/Decipheredmedia/awesome-openclaw-skills}"
OPENCLAW_DIR="${OPENCLAW_DIR:-/opt/openclaw}"
SKILLS_DIR="${SKILLS_DIR:-/opt/awesome-openclaw-skills}"
STATE_DIR="${STATE_DIR:-/root/.openclaw}"
CONFIG_PATH="${CONFIG_PATH:-${STATE_DIR}/openclaw.json}"
ENV_PATH="${ENV_PATH:-${STATE_DIR}/.env}"
SERVICE_NAME="openclaw-gateway"

apt_install() {
  apt-get install -y "$@"
}

escape_sed_replacement() {
  printf '%s' "$1" | sed -e 's/[\/&]/\\&/g'
}

replace_placeholder() {
  local file_path="$1"
  local placeholder="$2"
  local value="$3"
  sed -i "s/${placeholder}/$(escape_sed_replacement "$value")/g" "$file_path"
}

read_env_value() {
  local file_path="$1"
  local key="$2"
  if [ ! -f "$file_path" ]; then
    return 0
  fi
  awk -F= -v target="$key" '$1 == target { sub(/^[^=]+=*/, "", $0); print $0; exit }' "$file_path"
}

ensure_git_checkout() {
  local repo_url="$1"
  local target_dir="$2"

  if [ -d "${target_dir}/.git" ]; then
    echo "Using existing checkout at ${target_dir}"
    git -C "$target_dir" fetch --tags origin
    git -C "$target_dir" pull --ff-only origin main
    return 0
  fi

  if [ -e "$target_dir" ]; then
    echo "Refusing to overwrite existing path that is not a git checkout: ${target_dir}"
    exit 1
  fi

  git clone --branch main --depth 1 "$repo_url" "$target_dir"
}

generate_gateway_token() {
  node -e "process.stdout.write(require('node:crypto').randomBytes(24).toString('hex'))"
}

get_primary_ip() {
  local ip
  ip="$(hostname -I 2>/dev/null | awk '{print $1}')"
  if [ -n "$ip" ]; then
    printf '%s' "$ip"
    return 0
  fi
  printf '127.0.0.1'
}

echo "==> Installing required Ubuntu packages"
export DEBIAN_FRONTEND=noninteractive
apt-get update
apt_install curl git gnupg lsb-release ca-certificates

echo "==> Installing Node.js 22.x"
curl -fsSL https://deb.nodesource.com/setup_22.x | bash -
apt_install nodejs

echo "==> Enabling pnpm via corepack"
corepack enable
corepack prepare pnpm@latest --activate

echo "==> Installing Docker CE and Docker Compose plugin"
install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | gpg --dearmor --yes -o /etc/apt/keyrings/docker.gpg
chmod a+r /etc/apt/keyrings/docker.gpg
echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable" \
  >/etc/apt/sources.list.d/docker.list
apt-get update
apt_install docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
systemctl enable docker >/dev/null 2>&1 || true
systemctl start docker >/dev/null 2>&1 || true

echo "==> Fetching OpenClaw repositories"
ensure_git_checkout "$OPENCLAW_REPO_URL" "$OPENCLAW_DIR"
ensure_git_checkout "$SKILLS_REPO_URL" "$SKILLS_DIR"

echo "==> Installing OpenClaw dependencies and build artifacts"
cd "$OPENCLAW_DIR"
pnpm install --frozen-lockfile
pnpm build:docker
pnpm ui:build

echo "==> Preparing runtime state"
install -d -m 0700 "$STATE_DIR" "$STATE_DIR/workspace"

existing_venice_key="$(read_env_value "$ENV_PATH" "OPENAI_API_KEY")"
existing_telegram_token="$(read_env_value "$ENV_PATH" "TELEGRAM_BOT_TOKEN")"
existing_gateway_token="$(read_env_value "$ENV_PATH" "OPENCLAW_GATEWAY_TOKEN")"

read -rsp "Enter your Venice AI API key (press Enter to keep the current value if one is already configured): " venice_api_key_input
echo
read -rsp "Enter your Telegram bot token (press Enter to keep the current value if one is already configured): " telegram_bot_token_input
echo

VENICE_API_KEY="${venice_api_key_input:-$existing_venice_key}"
TELEGRAM_BOT_TOKEN="${telegram_bot_token_input:-$existing_telegram_token}"
GATEWAY_TOKEN="${existing_gateway_token:-$(generate_gateway_token)}"

if [ -z "$VENICE_API_KEY" ]; then
  echo "A Venice AI API key is required."
  exit 1
fi

if [ -z "$TELEGRAM_BOT_TOKEN" ]; then
  echo "A Telegram bot token is required."
  exit 1
fi

echo "==> Writing OpenClaw environment and config"
install -m 0600 "$OPENCLAW_DIR/install/.env.template" "$ENV_PATH"
replace_placeholder "$ENV_PATH" "__VENICE_API_KEY__" "$VENICE_API_KEY"
replace_placeholder "$ENV_PATH" "__TELEGRAM_BOT_TOKEN__" "$TELEGRAM_BOT_TOKEN"
replace_placeholder "$ENV_PATH" "__GATEWAY_TOKEN__" "$GATEWAY_TOKEN"

install -m 0600 "$OPENCLAW_DIR/install/openclaw.json.template" "$CONFIG_PATH"

echo "==> Installing awesome-openclaw-skills catalog wrappers"
bash "$OPENCLAW_DIR/install/install-skills.sh"

echo "==> Installing systemd service"
install -m 0644 "$OPENCLAW_DIR/install/openclaw-gateway.service" "/etc/systemd/system/${SERVICE_NAME}.service"
systemctl daemon-reload
systemctl enable "$SERVICE_NAME"
systemctl restart "$SERVICE_NAME"

SERVER_IP="$(get_primary_ip)"

cat <<EOF

============================================================
 OpenClaw VPS install complete
============================================================

Gateway URL:
  http://${SERVER_IP}:18789/

Health checks:
  curl -fsS http://localhost:18789/healthz
  systemctl status ${SERVICE_NAME}

Telegram bot:
  Open Telegram, start a chat with your bot, and send natural-language instructions.
  The bot token is loaded from ${ENV_PATH}.

Logs:
  journalctl -u ${SERVICE_NAME} -f

Config:
  ${CONFIG_PATH}
  ${ENV_PATH}
============================================================
EOF
