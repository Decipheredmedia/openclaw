# OpenClaw VPS Deployment (Venice AI + Telegram)

This directory contains everything needed to deploy OpenClaw on a VPS with Venice AI as the provider and Telegram as the channel.

## Prerequisites

- Ubuntu VPS with Node.js 22+ installed via nvm
- OpenClaw installed globally: `npm install -g openclaw`
- Venice AI account with credits: https://venice.ai/settings/api
- Telegram bot token from @BotFather

## Quick Deploy

```bash
# Clone or pull the repo
git clone https://github.com/Decipheredmedia/openclaw.git
cd openclaw/deploy

# Run setup (first run creates .env template and exits)
bash setup.sh

# Edit .env with your real values
nano /root/.openclaw/.env

# Re-run setup to deploy and start
bash setup.sh
```

## What it deploys

| File | Destination | Purpose |
|---|---|---|
| `openclaw.json` | `/root/.openclaw/openclaw.json` | Gateway config with Venice AI models |
| `.env.example` | `/root/.openclaw/.env` | Environment variables template |
| `openclaw-gateway.service` | `/etc/systemd/system/` | Systemd service (auto-restart on boot) |

## Models configured

| Model | Role |
|---|---|
| `venice-uncensored-1-2` | Primary model |
| `llama-3.3-70b` | Fallback model |

To change the model, edit `/root/.openclaw/openclaw.json` and run:
```bash
systemctl restart openclaw-gateway
```

## Useful commands

```bash
# View live logs
journalctl -u openclaw-gateway -f

# Check status
systemctl status openclaw-gateway

# Restart
systemctl restart openclaw-gateway

# Health check
curl -s http://localhost:18789/healthz
```

## Troubleshooting

| Error | Fix |
|---|---|
| `Insufficient balance` | Add credits at https://venice.ai/settings/api |
| `Unknown model` | Check `models.providers.openai.models[]` in `openclaw.json` |
| `model_not_found` | Model ID must exist in both `agents.defaults.models` AND `models.providers.openai.models[]` |
| Bot not responding | Check `TELEGRAM_BOT_TOKEN` in `.env` and `botToken` in `openclaw.json` |
