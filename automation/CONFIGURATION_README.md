# OpenClaw Automation System — Configuration & Deployment Guide

Complete reference for every configuration variable, Telegram command, and deployment procedure.

---

## Table of Contents

1. [Prerequisites](#1-prerequisites)
2. [Quick Start](#2-quick-start)
3. [Configuration Reference](#3-configuration-reference)
   - [VPS / Server](#31-vps--server)
   - [OpenClaw](#32-openclaw)
   - [Websites](#33-websites)
   - [OpenAI](#34-openai)
   - [Stripe](#35-stripe)
   - [PayPal](#36-paypal)
   - [Cryptocurrency Wallets](#37-cryptocurrency-wallets)
   - [Telegram Bot](#38-telegram-bot)
   - [Instagram](#39-instagram)
   - [Reddit](#310-reddit)
   - [Twitter / X](#311-twitter--x)
   - [Social Media Global](#312-social-media-global)
4. [Telegram Bot Commands](#4-telegram-bot-commands)
5. [Deployment Walkthrough](#5-deployment-walkthrough)
6. [Website Builder](#6-website-builder)
7. [Payment Integration](#7-payment-integration)
8. [Social Media Automation](#8-social-media-automation)
9. [Monitoring & Logs](#9-monitoring--logs)
10. [Troubleshooting](#10-troubleshooting)
11. [Security Notes](#11-security-notes)

---

## 1. Prerequisites

| Requirement | Minimum Version | Notes |
|---|---|---|
| Ubuntu | 22.04 LTS | Other Debian-based distros may work |
| Python | 3.11+ | Installed by `install.py` |
| Node.js | 22+ | Installed by `install.py` |
| pnpm | latest | Installed by `install.py` |
| Nginx | 1.18+ | Installed by `install.py` |
| Certbot | latest | Installed by `install.py` |
| RAM | 1 GB minimum | 2 GB recommended |
| Disk | 10 GB minimum | |
| DNS | A records pointed to VPS | Required before running installer |

**API keys you need before starting:**

- Telegram bot token (from [@BotFather](https://t.me/BotFather))
- OpenAI API key (required for website builder and content generation)
- Stripe API keys (optional — for card payment processing)
- PayPal API credentials (optional)
- Instagram Graph API token (optional — for Instagram posting)
- Reddit OAuth2 credentials (optional)
- Twitter API v2 credentials (optional)
- Alchemy API key (optional — for ETH monitoring)

---

## 2. Quick Start

```bash
# 1. Clone this repository to your VPS
git clone https://github.com/Decipheredmedia/openclaw /opt/openclaw-automation
cd /opt/openclaw-automation/automation

# 2. Copy and fill in the config file
cp config.env.example config.env
nano config.env        # Fill in every variable (see Section 3)

# 3. Run the installer (as root)
sudo python3 install.py

# 4. Build and deploy your websites
python3 main.py --deploy

# 5. Start the full automation daemon
python3 main.py --start
# Or let systemd manage it:
sudo systemctl start openclaw-automation
```

After step 5, open Telegram and send `/start` to your bot.

---

## 3. Configuration Reference

All configuration lives in `automation/config.env`. Copy from `config.env.example`.

### 3.1 VPS / Server

| Variable | Required | Default | Description |
|---|---|---|---|
| `VPS_IP` | No | `""` | Public IP of your VPS (used for validation in the installer) |
| `VPS_USER` | No | `root` | SSH user (informational only) |
| `OPENCLAW_DIR` | No | `/opt/openclaw` | Where openclaw is cloned on the VPS |
| `AUTOMATION_DIR` | No | `/opt/openclaw-automation` | Where this automation repo lives |
| `LOG_DIR` | No | `/var/log/openclaw-automation` | Log directory |

### 3.2 OpenClaw

| Variable | Required | Default | Description |
|---|---|---|---|
| `OPENCLAW_REPO` | No | `https://github.com/Decipheredmedia/openclaw` | Git URL to clone |
| `OPENCLAW_BRANCH` | No | `main` | Branch/tag to check out |
| `OPENCLAW_PORT` | No | `18789` | Port the openclaw gateway listens on internally |
| `OPENCLAW_BIND` | No | `127.0.0.1` | Bind address (`127.0.0.1` = loopback only, safer) |

### 3.3 Websites

| Variable | Required | Default | Description |
|---|---|---|---|
| `SITE_DOMAINS` | No | `""` | Comma-separated list of domains to deploy. DNS must already point to this VPS. Example: `example.com,shop.example.com` |
| `SITE_TEMPLATES` | No | `""` | Template per domain. Format: `domain=template_name`. Available: `base`. Example: `example.com=base` |
| `SITE_DESCRIPTIONS` | No | `""` | Short description per domain for AI content. Example: `example.com=A consulting agency specialising in growth strategy` |
| `SITE_AUDIENCES` | No | `""` | Target audience per domain. Example: `example.com=small business owners` |
| `CERTBOT_WEBROOT` | No | `/var/www/certbot` | Web root for Let's Encrypt ACME HTTP-01 challenge |
| `CERTBOT_EMAIL` | No | `""` | Email for Let's Encrypt registration and expiry notices |

### 3.4 OpenAI

| Variable | Required | Default | Description |
|---|---|---|---|
| `OPENAI_API_KEY` | **Yes** (for AI features) | — | OpenAI API key. Get from [platform.openai.com](https://platform.openai.com/account/api-keys) |
| `OPENAI_MODEL` | No | `gpt-4o` | Model for content generation. `gpt-4o` recommended |
| `OPENAI_MAX_TOKENS` | No | `4096` | Max tokens per call |
| `OPENAI_TEMPERATURE` | No | `0.7` | Creativity (0=deterministic, 1=creative) |

### 3.5 Stripe

| Variable | Required | Default | Description |
|---|---|---|---|
| `STRIPE_PUBLISHABLE_KEY` | No | — | Stripe publishable key (`pk_live_...`) — safe to embed in HTML |
| `STRIPE_SECRET_KEY` | No | — | Stripe secret key (`sk_live_...`) — **never expose this** |
| `STRIPE_WEBHOOK_SECRET` | No | — | Webhook signing secret from Stripe Dashboard → Webhooks (`whsec_...`) |
| `STRIPE_CONNECT_ACCOUNT_ID` | No | — | Stripe Connect account ID if using Connect for payouts |
| `PAYMENT_SERVER_PORT` | No | `8000` | Local port for the FastAPI payment webhook server |

**Setting up Stripe webhooks:**

1. Go to [Stripe Dashboard → Webhooks](https://dashboard.stripe.com/webhooks)
2. Add endpoint: `https://yourdomain.com/webhook/stripe`
3. Select events: `checkout.session.completed`, `payment_intent.succeeded`, `payment_intent.payment_failed`
4. Copy the signing secret into `STRIPE_WEBHOOK_SECRET`

### 3.6 PayPal

| Variable | Required | Default | Description |
|---|---|---|---|
| `PAYPAL_CLIENT_ID` | No | — | PayPal REST API client ID |
| `PAYPAL_SECRET` | No | — | PayPal REST API secret |
| `PAYPAL_ENV` | No | `live` | `sandbox` for testing, `live` for production |
| `PAYPAL_WEBHOOK_ID` | No | — | Webhook ID from PayPal Developer Dashboard |

**Setting up PayPal webhooks:**

1. Go to [PayPal Developer Dashboard](https://developer.paypal.com/dashboard/)
2. Create a REST app → Webhooks → Add Webhook
3. URL: `https://yourdomain.com/webhook/paypal`
4. Events: `PAYMENT.CAPTURE.COMPLETED`, `PAYMENT.SALE.COMPLETED`
5. Copy the Webhook ID into `PAYPAL_WEBHOOK_ID`

### 3.7 Cryptocurrency Wallets

| Variable | Required | Default | Description |
|---|---|---|---|
| `BTC_WALLET_ADDRESS` | No | — | Bitcoin wallet address (native SegWit `bc1q...` or legacy `1...`) |
| `ETH_WALLET_ADDRESS` | No | — | Ethereum wallet address (`0x...`) |
| `USDT_TRC20_WALLET_ADDRESS` | No | — | USDT TRC-20 address on TRON (starts with `T`) |
| `ALCHEMY_API_KEY` | No | — | Alchemy API key for ETH/ERC-20 monitoring |
| `TRON_API_KEY` | No | — | TronGrid API key for USDT TRC-20 monitoring |
| `BTC_CONFIRMATIONS_REQUIRED` | No | `2` | BTC confirmations before notifying |
| `ETH_CONFIRMATIONS_REQUIRED` | No | `12` | ETH confirmations before notifying |
| `TRON_CONFIRMATIONS_REQUIRED` | No | `19` | TRON confirmations before notifying |
| `CRYPTO_POLL_INTERVAL` | No | `60` | Seconds between blockchain polls |

**Monitoring limitations:** The free tier of Blockstream, Alchemy, and TronGrid APIs have rate limits. For high-volume monitoring, upgrade your API plan.

### 3.8 Telegram Bot

| Variable | Required | Default | Description |
|---|---|---|---|
| `TELEGRAM_BOT_TOKEN` | **Yes** | — | Bot token from [@BotFather](https://t.me/BotFather) |
| `TELEGRAM_OWNER_ID` | **Yes** | — | Your numeric Telegram user ID. Get from [@userinfobot](https://t.me/userinfobot) |
| `TELEGRAM_ALLOWED_IDS` | No | — | Comma-separated additional operator user IDs |
| `TELEGRAM_NOTIFY_CHAT_ID` | No | — | Chat ID for payment/alert notifications (can be same as `TELEGRAM_OWNER_ID`) |

### 3.9 Instagram

| Variable | Required | Default | Description |
|---|---|---|---|
| `INSTAGRAM_ACCESS_TOKEN` | No | — | Long-lived Instagram Graph API token from Meta Developer Console |
| `INSTAGRAM_ACCOUNT_ID` | No | — | Instagram Business Account numeric ID |
| `INSTAGRAM_DEFAULT_IMAGE_URL` | No | — | Default promo image URL (must be publicly accessible, JPG/PNG) |
| `INSTAGRAM_SCHEDULE` | No | — | Cron per domain. Example: `example.com=0 9 * * *` (9 AM daily) |
| `INSTAGRAM_MAX_POSTS_PER_DAY` | No | `3` | Daily post cap per account (Instagram enforces 25; stay low) |

**Getting an Instagram token:**

1. Create a [Meta Developer App](https://developers.facebook.com/)
2. Add the Instagram Graph API product
3. Connect your Instagram Business / Creator account
4. Generate a long-lived access token (valid ~60 days; automate refresh for production)

### 3.10 Reddit

| Variable | Required | Default | Description |
|---|---|---|---|
| `REDDIT_CLIENT_ID` | No | — | Reddit OAuth2 app client ID |
| `REDDIT_CLIENT_SECRET` | No | — | Reddit OAuth2 app secret |
| `REDDIT_USERNAME` | No | — | Reddit account username |
| `REDDIT_PASSWORD` | No | — | Reddit account password |
| `REDDIT_USER_AGENT` | No | `openclaw-automation/1.0` | User agent string (Reddit requires a descriptive UA) |
| `REDDIT_SUBREDDITS` | No | — | Comma-separated subreddit names (without `r/`). Example: `entrepreneur,smallbusiness` |
| `REDDIT_MIN_KARMA` | No | `10` | Minimum account karma before posting |
| `REDDIT_MIN_POST_INTERVAL_HOURS` | No | `24` | Minimum hours between posts to the same subreddit |
| `REDDIT_JITTER_HOURS` | No | `6` | Random extra delay added to interval (avoids pattern detection) |

**Creating a Reddit app:**

1. Go to [reddit.com/prefs/apps](https://www.reddit.com/prefs/apps)
2. Click "Create Another App" → type: **script**
3. Set redirect URI to `http://localhost`
4. Copy Client ID and Secret

### 3.11 Twitter / X

| Variable | Required | Default | Description |
|---|---|---|---|
| `TWITTER_API_KEY` | No | — | Twitter API key (consumer key) |
| `TWITTER_API_SECRET` | No | — | Twitter API secret |
| `TWITTER_ACCESS_TOKEN` | No | — | Access token |
| `TWITTER_ACCESS_SECRET` | No | — | Access token secret |
| `TWITTER_BEARER_TOKEN` | No | — | Bearer token for read-only operations |
| `TWITTER_SCHEDULE` | No | — | Cron per domain. Example: `example.com=0 12 * * *` (12 PM daily) |
| `TWITTER_THREAD_ENABLED` | No | `true` | Post as thread when content exceeds 280 chars |
| `TWITTER_MAX_TWEETS_PER_DAY` | No | `10` | Daily tweet cap |

**Cron expression format:**

```
┌───── minute (0-59)
│ ┌───── hour (0-23)
│ │ ┌───── day of month (1-31)
│ │ │ ┌───── month (1-12)
│ │ │ │ ┌───── day of week (0=Sun, 6=Sat)
│ │ │ │ │
* * * * *
```

Examples:
- `0 9 * * *` — every day at 9:00 AM UTC
- `0 9,18 * * *` — every day at 9 AM and 6 PM UTC
- `0 12 * * 1` — every Monday at noon UTC

### 3.12 Social Media Global

| Variable | Required | Default | Description |
|---|---|---|---|
| `SOCIAL_ENABLED` | No | `true` | Master switch. Set to `false` to disable all social posting |
| `SOCIAL_DRY_RUN` | No | `false` | When `true`, generates and logs content but does **not** post anything |
| `SOCIAL_STATE_FILE` | No | `/var/lib/openclaw-automation/social_state.json` | Path to persist posting state (last post times, tweet IDs) |

---

## 4. Telegram Bot Commands

Send these commands to your bot from Telegram.

| Command | Description | Example |
|---|---|---|
| `/start` | Dashboard: site URLs, service status, 7-day revenue | `/start` |
| `/status` | Health check for all systemd services + payment server | `/status` |
| `/deploy <domain>` | Build AI-generated site and deploy with SSL | `/deploy example.com` |
| `/revenue [period]` | Revenue summary. Period: `today`, `week`, `month`, `all` | `/revenue week` |
| `/post <platform> <domain>` | Post immediately. Platforms: `instagram`, `reddit`, `twitter` | `/post twitter example.com` |
| `/pause <platform>` | Pause scheduler for a platform | `/pause instagram` |
| `/resume <platform>` | Resume scheduler for a platform | `/resume instagram` |
| `/logs [service] [lines]` | Tail systemd journal | `/logs nginx 100` |
| `/addsite <domain> [template]` | Add new site and deploy it | `/addsite shop.example.com base` |
| `/setpayout <type> <key> <value>` | Update payout config live (in-memory) | `/setpayout btc address bc1q...` |
| `/help` | Full command reference | `/help` |

**Supported service names for `/logs`:**
`openclaw-automation`, `openclaw-gateway`, `nginx`

**Supported setpayout types:**
- `btc address <address>` — Update Bitcoin wallet
- `eth address <address>` — Update Ethereum wallet
- `usdt address <address>` — Update USDT TRC-20 wallet
- `stripe key <sk_live_...>` — Update Stripe secret key
- `paypal client_id <id>` — Update PayPal client ID

⚠️ `/setpayout` changes are **in-memory only**. Edit `config.env` to persist them across restarts.

---

## 5. Deployment Walkthrough

### Fresh VPS Setup

```bash
# SSH into your VPS as root
ssh root@your-vps-ip

# Clone the automation repo
git clone https://github.com/Decipheredmedia/openclaw /tmp/openclaw-src
cp -r /tmp/openclaw-src/automation /opt/openclaw-automation
cd /opt/openclaw-automation

# Configure
cp config.env.example config.env
nano config.env
# Set at minimum:
#   SITE_DOMAINS=yourdomain.com
#   CERTBOT_EMAIL=you@example.com
#   OPENAI_API_KEY=sk-proj-...
#   TELEGRAM_BOT_TOKEN=...
#   TELEGRAM_OWNER_ID=...

# Run installer
python3 install.py

# Check openclaw is running
systemctl status openclaw-gateway

# Deploy sites
python3 main.py --deploy

# Start the automation daemon
systemctl start openclaw-automation
systemctl status openclaw-automation
```

### Adding a New Site

**Via Telegram:**
```
/addsite shop.example.com base
```

**Via CLI:**
```bash
# Add domain to config.env, then:
python3 main.py --deploy
```

### Updating OpenClaw

```bash
cd /opt/openclaw
git pull --rebase origin main
pnpm install --frozen-lockfile
pnpm build
systemctl restart openclaw-gateway
```

---

## 6. Website Builder

### How It Works

1. `website_builder/builder.py` reads reference files from `website_builder/examples/` (HTML files or a `urls.txt`).
2. It calls the OpenAI API with a detailed prompt that includes the domain, description, audience, and the base template.
3. The AI generates a complete HTML5 website with real copy tailored to the business.
4. Output is written to `website_builder/generated/<domain>/index.html`.
5. `website_builder/deployer.py` writes the Nginx config, obtains SSL, and validates the site is live.

### Providing Reference Examples

Drop reference files in `website_builder/examples/`:

```bash
# Option A: Place HTML files
cp ~/my-reference-site.html /opt/openclaw-automation/automation/website_builder/examples/

# Option B: List URLs
cat > /opt/openclaw-automation/automation/website_builder/examples/urls.txt << EOF
https://stripe.com
https://linear.app
EOF
```

### Customising Templates

Edit `website_builder/templates/base.html` to change the base layout. CSS custom properties (`--color-primary`, etc.) at the top of the template control theming — the AI will override these with brand-appropriate values.

To add a new template:
```bash
cp automation/website_builder/templates/base.html automation/website_builder/templates/agency.html
# Edit agency.html, then in config.env:
SITE_TEMPLATES=yourdomain.com=agency
```

---

## 7. Payment Integration

### Payment Flow

```
Customer → Website → Stripe/PayPal checkout → Webhook POST → FastAPI server
                                                                ↓
                                                    Record in SQLite ledger
                                                                ↓
                                                    Telegram notification
```

### Webhook URLs

Configure these in your payment dashboards:

| Provider | Webhook URL |
|---|---|
| Stripe | `https://yourdomain.com/webhook/stripe` |
| PayPal | `https://yourdomain.com/webhook/paypal` |

### Crypto Payment Display

Crypto wallets are displayed on the website automatically when configured. The crypto monitor polls blockchain APIs every `CRYPTO_POLL_INTERVAL` seconds and sends Telegram alerts on new confirmed transactions.

### Revenue Ledger

Payments are stored in `automation/payments/ledger.db` (SQLite).

Query the ledger directly:
```bash
sqlite3 /opt/openclaw-automation/automation/payments/ledger.db \
  "SELECT source, SUM(amount), currency FROM payments WHERE status='confirmed' GROUP BY source, currency;"
```

---

## 8. Social Media Automation

### Content Generation

All social content is generated by OpenAI using the site's `SITE_DESCRIPTIONS` and `SITE_AUDIENCES` values. Content is platform-optimized:

- **Instagram**: Engaging caption (200 words max) + 20-25 hashtags
- **Reddit**: Authentic, value-first title + body (link to site at the end)
- **Twitter**: Single tweet or thread of up to 5 tweets

### Dry Run Mode

Test content generation without posting:
```bash
# In config.env:
SOCIAL_DRY_RUN=true
```

Then trigger a post via Telegram: `/post instagram yourdomain.com`

Generated content will be logged but not posted.

### Scheduler Jobs

View scheduled jobs:
```bash
python3 - << 'EOF'
from social.scheduler import start_scheduler, list_jobs
s = start_scheduler()
for job in list_jobs():
    print(job)
s.shutdown()
EOF
```

---

## 9. Monitoring & Logs

### Systemd Service Logs

```bash
# Automation daemon
journalctl -u openclaw-automation -f

# OpenClaw gateway
journalctl -u openclaw-gateway -f

# Nginx
journalctl -u nginx -f
```

### Application Logs

```bash
# Follow all automation logs
journalctl -u openclaw-automation -f --no-hostname
```

### Via Telegram

```
/logs openclaw-automation 100
/logs nginx 50
/status
```

---

## 10. Troubleshooting

### Certbot fails

```
Problem: certbot failed for yourdomain.com
```

**Check:**
1. DNS A record for `yourdomain.com` points to your VPS IP: `dig +short yourdomain.com`
2. Port 80 is open: `ufw status` / `curl http://yourdomain.com`
3. Nginx is running: `systemctl status nginx`
4. No Nginx config errors: `nginx -t`

### Telegram bot not responding

1. Check the token: `TELEGRAM_BOT_TOKEN` must match what @BotFather gave you
2. Check `TELEGRAM_OWNER_ID` — get yours from [@userinfobot](https://t.me/userinfobot)
3. Check service: `systemctl status openclaw-automation`
4. Check logs: `journalctl -u openclaw-automation -n 50`

### OpenAI errors

```
openai.RateLimitError: You exceeded your current quota
```
**Fix:** Upgrade your OpenAI plan at [platform.openai.com/account/billing](https://platform.openai.com/account/billing)

### Payment webhooks not received

1. Confirm Nginx proxies `/webhook/` to `127.0.0.1:8000`: `curl -X POST http://127.0.0.1:8000/webhook/stripe`
2. Check payment server is running: `/status` in Telegram
3. Verify webhook URL in Stripe/PayPal dashboard is correct
4. Check `STRIPE_WEBHOOK_SECRET` / `PAYPAL_WEBHOOK_ID` are set correctly

### Instagram posting fails

- Long-lived tokens expire after 60 days. Refresh at [developers.facebook.com/tools/accesstoken](https://developers.facebook.com/tools/accesstoken/)
- Image URL must be publicly accessible (not localhost)
- Account must be a Professional (Business or Creator) account

### Reddit posts getting removed

- Stay well above subreddit karma thresholds (increase `REDDIT_MIN_KARMA`)
- Increase posting intervals (`REDDIT_MIN_POST_INTERVAL_HOURS`)
- Enable `SOCIAL_DRY_RUN=true` to preview content before posting
- Some subreddits require account age — check each subreddit's rules

---

## 11. Security Notes

1. **Never commit `config.env`** to git. It is in `.gitignore`.
2. **Firewall:** The installer enables UFW allowing only SSH (22), HTTP (80), HTTPS (443). The payment server (port 8000) is bound to `127.0.0.1` only.
3. **Nginx proxies webhooks** — Stripe/PayPal only reach port 8000 via Nginx on 443.
4. **Telegram auth:** Only `TELEGRAM_OWNER_ID` and `TELEGRAM_ALLOWED_IDS` can issue commands. All other users receive ⛔ Unauthorized.
5. **Stripe signature verification:** Every webhook is cryptographically verified before processing.
6. **PayPal signature verification:** Webhooks are verified via the PayPal REST API.
7. **Crypto monitoring:** The system only monitors wallets — it never has access to private keys.
8. **SQLite ledger** (`payments/ledger.db`) contains payment records. Restrict access: `chmod 600 payments/ledger.db`.
9. **OpenAI API key:** Treat it like a password. Set usage limits at [platform.openai.com/account/limits](https://platform.openai.com/account/limits).
10. **Social credentials:** Reddit and Twitter credentials are used with `script`-type OAuth apps. Use dedicated accounts, not personal ones.
