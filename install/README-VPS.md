# OpenClaw VPS install guide (Venice AI + Telegram)

This guide provisions OpenClaw on Ubuntu 20.04 with:

- Venice AI as the only configured model provider
- Telegram for natural-language chat with your bot
- awesome-openclaw-skills category wrappers auto-installed
- a systemd service that survives reboots

## 1. Prerequisites

- Ubuntu 20.04 VPS with sudo/root access
- A Venice AI account: https://venice.ai
- A Telegram bot token from @BotFather

## 2. One-command install

```bash
curl -fsSL https://raw.githubusercontent.com/Decipheredmedia/openclaw/main/install-vps.sh | bash
```

If you prefer to inspect before running, download the script first and review it locally before executing it with `bash install-vps.sh`.

The installer will:

1. install Node.js 22, pnpm, Docker, and Docker Compose
2. clone OpenClaw into `/opt/openclaw`
3. clone `awesome-openclaw-skills` into `/opt/awesome-openclaw-skills`
4. build OpenClaw
5. prompt for your Venice API key and Telegram bot token
6. write `/root/.openclaw/openclaw.json` and `/root/.openclaw/.env`
7. install the systemd gateway service

## 3. Get your Venice AI API key

1. Sign in at https://venice.ai
2. Open **Settings**
3. Go to **API Keys**
4. Create or copy a key from https://venice.ai/settings

## 4. Verify the installation

```bash
systemctl status openclaw-gateway
curl -fsS http://localhost:18789/healthz
```

Useful files:

- Config: `/root/.openclaw/openclaw.json`
- Env: `/root/.openclaw/.env`
- Service: `/etc/systemd/system/openclaw-gateway.service`

## 5. Use your Telegram bot

1. Open Telegram
2. Start a DM with your bot
3. Send natural-language instructions such as:
   - “Summarize my plan for today”
   - “Find the right community skill for browser automation”
   - “Help me research a deployment problem”

The configured Telegram channel accepts DM chat and routes requests into OpenClaw.

## 6. Change the Venice AI model

Current default:

- `venice-openai/venice-uncensored`

Other preconfigured Venice models:

- `venice-openai/llama-3.3-70b`
- `venice-openai/mistral-31-24b`
- `venice-openai/qwen-2.5-vl`
- `venice-openai/dolphin-2.9.2-qwen2-72b`

To switch models:

```bash
sed -i 's#venice-openai/venice-uncensored#venice-openai/llama-3.3-70b#' /root/.openclaw/openclaw.json
systemctl restart openclaw-gateway
```

## 7. Add more skills manually

Managed skills live in:

```bash
/root/.openclaw/skills
```

Each installed category is wrapped as a discoverable OpenClaw skill directory with:

- `SKILL.md`
- `REFERENCE.md`

You can add your own skill directories under `/root/.openclaw/skills/<skill-name>/SKILL.md`.

## 8. Troubleshooting

Follow live logs:

```bash
journalctl -u openclaw-gateway -f
```

Common checks:

```bash
systemctl restart openclaw-gateway
curl -fsS http://localhost:18789/healthz
docker --version
pnpm --version
```

If Telegram does not respond:

- verify `TELEGRAM_BOT_TOKEN` in `/root/.openclaw/.env`
- verify the service is running
- inspect logs with `journalctl -u openclaw-gateway -f`

If Venice requests fail:

- verify `OPENAI_API_KEY`
- verify `OPENAI_API_BASE=https://api.venice.ai/v1`
- confirm the selected model exists in `openclaw.json`

## 9. Update OpenClaw

```bash
cd /opt/openclaw
git pull --ff-only origin main
pnpm install --frozen-lockfile
pnpm build:docker
pnpm ui:build
systemctl restart openclaw-gateway
```

To refresh the imported awesome-openclaw-skills category wrappers:

```bash
cd /opt/awesome-openclaw-skills
git pull --ff-only origin main
bash /opt/openclaw/install/install-skills.sh
systemctl restart openclaw-gateway
```
