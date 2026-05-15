# OpenClaw

> **The AI that actually does things.**
> Run it on your devices, in your channels, with your rules.

OpenClaw is a multi-channel AI gateway that connects large language models (LLMs) such as OpenAI, Anthropic Claude, and Google Gemini to messaging platforms like Telegram, Discord, Slack, and many more. It runs locally on your machine or in a container and routes conversations through a central gateway that you control.

---

## Table of Contents

1. [What Is OpenClaw?](#what-is-openclaw)
2. [Prerequisites](#prerequisites)
3. [Installation](#installation)
   - [Option A – Install from npm (Recommended for most users)](#option-a--install-from-npm-recommended-for-most-users)
   - [Option B – Run from Source (For developers)](#option-b--run-from-source-for-developers)
   - [Option C – Docker / Docker Compose](#option-c--docker--docker-compose)
4. [Configuration](#configuration)
   - [Step 1 – Create your `.env` file](#step-1--create-your-env-file)
   - [Step 2 – Gateway auth token](#step-2--gateway-auth-token)
   - [Step 3 – Add at least one AI provider key](#step-3--add-at-least-one-ai-provider-key)
   - [Step 4 – Add at least one channel](#step-4--add-at-least-one-channel)
   - [Full `.env` reference](#full-env-reference)
5. [Starting the Gateway](#starting-the-gateway)
6. [Using the CLI](#using-the-cli)
7. [Testing](#testing)
8. [Build System Overview](#build-system-overview)
9. [Project Structure](#project-structure)
10. [Plugins & Extensions](#plugins--extensions)
11. [Deployment](#deployment)
    - [Docker Compose (self-hosted)](#docker-compose-self-hosted)
    - [Fly.io](#flyio)
    - [Render](#render)
    - [Podman](#podman)
12. [Security Notes](#security-notes)
13. [Contributing](#contributing)
14. [License](#license)

---

## What Is OpenClaw?

OpenClaw is an **open-source, self-hosted AI assistant gateway**. At its core it is an orchestration layer that:

- Accepts messages from one or more **channels** (Telegram, Discord, Slack, etc.).
- Forwards them to an **AI model provider** you configure (OpenAI, Anthropic, Gemini, …).
- Returns the AI response back to the channel.
- Exposes a **web control UI** and a **REST gateway API** for management.

Everything runs under your own API keys — you keep full control over costs, data, and behaviour.

---

## Prerequisites

Before you begin, make sure you have the following installed on your computer.

| Tool | Minimum version | How to check |
|------|----------------|--------------|
| [Node.js](https://nodejs.org) | **v22.12** or newer | `node --version` |
| [pnpm](https://pnpm.io) | v9 or newer | `pnpm --version` |
| [Git](https://git-scm.com) | any recent version | `git --version` |
| [Docker](https://www.docker.com) *(optional)* | v24 or newer | `docker --version` |

> **Tip – Installing Node.js via nvm (recommended):**
> ```bash
> curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.39.7/install.sh | bash
> nvm install 22
> nvm use 22
> nvm alias default 22
> ```

> **Tip – Installing pnpm:**
> ```bash
> npm install -g pnpm
> ```

---

## Installation

Choose **one** of the three methods below.

---

### Option A – Install from npm (Recommended for most users)

This installs the pre-built package. No source checkout required.

```bash
npm install -g openclaw@latest
```

Verify the install:

```bash
openclaw --help
```

---

### Option B – Run from Source (For developers)

Use this if you want to modify OpenClaw's code or contribute to the project.

#### 1 – Clone the repository

```bash
git clone https://github.com/Decipheredmedia/openclaw.git
cd openclaw
```

#### 2 – Check out the branch you want to work on

```bash
git checkout copilot/build-automation-and-management-system
```

#### 3 – Install dependencies

```bash
pnpm install
```

This installs all workspace packages (root, `ui/`, `packages/*`, `extensions/*`) in one step.

#### 4 – Build the project

```bash
pnpm build
# or equivalently:
make build
```

The compiled output lands in `dist/`.

#### 5 – Verify the build

```bash
node openclaw.mjs --help
```

You should see the OpenClaw CLI help text.

---

### Option C – Docker / Docker Compose

If you prefer containers and don't want to install Node.js locally, use Docker.

#### 1 – Clone the repository

```bash
git clone https://github.com/Decipheredmedia/openclaw.git
cd openclaw
git checkout copilot/build-automation-and-management-system
```

#### 2 – Build the Docker image

```bash
docker build -t openclaw:local .
```

#### 3 – Prepare config directories

```bash
mkdir -p ~/.openclaw/workspace
```

#### 4 – Set up your environment (see [Configuration](#configuration) below, then come back here)

#### 5 – Start with Docker Compose

```bash
OPENCLAW_CONFIG_DIR=~/.openclaw \
OPENCLAW_WORKSPACE_DIR=~/.openclaw/workspace \
docker compose up -d
```

The gateway will be available at `http://localhost:18789`.

---

## Configuration

OpenClaw is configured through environment variables. The easiest way to manage them is with a `.env` file.

---

### Step 1 – Create your `.env` file

Copy the example file:

```bash
cp .env.example .env
```

Now open `.env` in any text editor (e.g. VS Code, nano, Notepad). You only need to fill in the sections that apply to you.

---

### Step 2 – Gateway auth token

This token protects the gateway API. **Set this before exposing the gateway to a network.**

```dotenv
OPENCLAW_GATEWAY_TOKEN=change-me-to-a-long-random-token
```

Generate a secure token:

```bash
openssl rand -hex 32
```

Paste the output as the value of `OPENCLAW_GATEWAY_TOKEN`.

---

### Step 3 – Add at least one AI provider key

Uncomment and fill in **at least one** of the following:

```dotenv
# OpenAI
OPENAI_API_KEY=sk-...

# Anthropic (Claude)
ANTHROPIC_API_KEY=sk-ant-...

# Google Gemini
GEMINI_API_KEY=...

# OpenRouter (routes to many providers)
OPENROUTER_API_KEY=sk-or-...
```

You can set multiple keys. OpenClaw will use the one that matches the model you select.

---

### Step 4 – Add at least one channel

Uncomment the token(s) for each messaging platform you want to use.

```dotenv
# Telegram – get a token from @BotFather on Telegram
TELEGRAM_BOT_TOKEN=123456:ABCDEF...

# Discord – get a token from https://discord.com/developers/applications
DISCORD_BOT_TOKEN=...

# Slack – get tokens from https://api.slack.com/apps
SLACK_BOT_TOKEN=xoxb-...
SLACK_APP_TOKEN=xapp-...
```

You don't need all of them — just uncomment the ones you're using.

---

### Full `.env` reference

Here is a complete annotated reference of every supported variable:

```dotenv
# ── Gateway ───────────────────────────────────────────────────────────────────
# Required if the gateway is accessible beyond localhost.
OPENCLAW_GATEWAY_TOKEN=change-me-to-a-long-random-token

# Alternative: protect with a password instead of a token (use one or the other).
# OPENCLAW_GATEWAY_PASSWORD=change-me-to-a-strong-password

# ── Path overrides (optional, defaults shown) ─────────────────────────────────
# OPENCLAW_STATE_DIR=~/.openclaw
# OPENCLAW_CONFIG_PATH=~/.openclaw/openclaw.json
# OPENCLAW_HOME=~

# ── Shell environment import (optional) ───────────────────────────────────────
# Set to 1 to import missing keys from your login shell profile.
# OPENCLAW_LOAD_SHELL_ENV=1
# OPENCLAW_SHELL_ENV_TIMEOUT_MS=15000

# ── AI Model Providers ────────────────────────────────────────────────────────
# OPENAI_API_KEY=sk-...
# ANTHROPIC_API_KEY=sk-ant-...
# GEMINI_API_KEY=...
# GOOGLE_API_KEY=...
# OPENROUTER_API_KEY=sk-or-...

# Multiple keys (comma-separated for rotation):
# OPENAI_API_KEYS=sk-1,sk-2
# ANTHROPIC_API_KEYS=sk-ant-1,sk-ant-2
# GEMINI_API_KEYS=key-1,key-2

# Additional providers:
# ZAI_API_KEY=...
# AI_GATEWAY_API_KEY=...
# MINIMAX_API_KEY=...

# ── Channels ──────────────────────────────────────────────────────────────────
# TELEGRAM_BOT_TOKEN=123456:ABCDEF...
# DISCORD_BOT_TOKEN=...
# SLACK_BOT_TOKEN=xoxb-...
# SLACK_APP_TOKEN=xapp-...
# MATTERMOST_BOT_TOKEN=...
# MATTERMOST_URL=https://chat.example.com
# ZALO_BOT_TOKEN=...
# OPENCLAW_TWITCH_ACCESS_TOKEN=oauth:...

# ── Tools & Media (optional) ─────────────────────────────────────────────────
# BRAVE_API_KEY=...          # Web search via Brave
# PERPLEXITY_API_KEY=pplx-...
# FIRECRAWL_API_KEY=...      # Web scraping

# ELEVENLABS_API_KEY=...     # Text-to-speech
# DEEPGRAM_API_KEY=...       # Speech-to-text
```

> **Variable precedence (highest → lowest):**
> 1. Variables already set in the process environment (e.g. system-level env vars)
> 2. `./.env` (in the project directory)
> 3. `~/.openclaw/.env` (user home config)
> 4. The `env` block inside `openclaw.json`

---

## Starting the Gateway

### From source or npm install

```bash
# Start the gateway (binds to LAN by default on port 18789)
openclaw gateway

# Bind to localhost only (more secure for local testing)
openclaw gateway --bind localhost

# Use a custom port
openclaw gateway --port 8080
```

The gateway runs in the foreground. Press `Ctrl+C` to stop it.

### Check it is running

```bash
curl http://localhost:18789/healthz
```

You should get a `200 OK` response.

---

## Using the CLI

Once the gateway is running, open a second terminal and use the `openclaw` CLI to interact with it.

```bash
# See all available commands
openclaw --help

# Chat interactively
openclaw chat

# Send a single message and exit
openclaw chat --message "Hello, what can you do?"

# List configured channels
openclaw channels list

# Check gateway status
openclaw status
```

> **Note:** When running from source, replace `openclaw` with `node openclaw.mjs`.

---

## Testing

OpenClaw uses [Vitest](https://vitest.dev/) for its test suite. There are several test configurations for different test types.

```bash
# Run all unit tests (fastest, no network needed)
pnpm test:unit

# Run integration/channel tests
pnpm test:channels

# Run end-to-end tests
pnpm test:e2e

# Run all tests
pnpm test

# Run tests in watch mode (re-runs on file change)
pnpm test:watch
```

---

## Build System Overview

| Command | What it does |
|---------|-------------|
| `pnpm install` | Install all workspace dependencies |
| `pnpm build` | Compile TypeScript → `dist/` via `tsdown` |
| `make build` | Alias for `pnpm build` |
| `pnpm lint` | Run `oxlint` on the codebase |
| `pnpm format` | Format code with `oxfmt` / Prettier |
| `pnpm test` | Run all tests |
| `pnpm test:unit` | Run unit tests only |
| `pnpm test:e2e` | Run end-to-end tests |
| `pnpm knip` | Detect unused exports / dead code |

The workspace layout is managed by `pnpm-workspace.yaml`. The root package, `ui/`, `packages/*`, and `extensions/*` are all built together.

Key build configuration files:

| File | Purpose |
|------|---------|
| `tsdown.config.ts` | TypeScript bundler config (entry points, output format) |
| `tsconfig.json` | TypeScript compiler options |
| `vitest.config.ts` | Main test runner config |
| `vitest.unit.config.ts` | Unit-only test config |
| `vitest.e2e.config.ts` | End-to-end test config |
| `knip.config.ts` | Dead code / unused exports detection |
| `.oxlintrc.json` | Linting rules |
| `.oxfmtrc.jsonc` | Formatting rules |

---

## Project Structure

```
openclaw/
├── src/                  # Core TypeScript source
├── dist/                 # Compiled output (generated, not committed)
├── ui/                   # Web control UI (Vite + Lit)
├── packages/             # Internal workspace packages
├── extensions/           # Optional bundled extensions (e.g. acpx)
├── skills/               # Built-in skills shipped with the package
├── scripts/              # Build & maintenance scripts
├── automation/           # CI/CD automation helpers
├── docs/                 # Documentation source
├── test/                 # Test suites
├── test-fixtures/        # Shared test data
├── assets/               # Static assets
├── git-hooks/            # Developer git hook scripts
├── openclaw.mjs          # CLI entry point (runs dist/entry.js)
├── Dockerfile            # Main production Docker image
├── Dockerfile.sandbox    # Sandbox isolation image
├── docker-compose.yml    # Compose setup (gateway + CLI)
├── fly.toml              # Fly.io deployment config
├── render.yaml           # Render.com deployment config
├── Makefile              # Simple build shortcuts
├── package.json          # Root package manifest
├── pnpm-workspace.yaml   # Workspace package paths
├── tsdown.config.ts      # Bundler config
└── .env.example          # Environment variable template
```

---

## Plugins & Extensions

OpenClaw has a rich plugin system. Extensions live in the `extensions/` directory and are loaded automatically.

### Installing a community plugin

```bash
npm install -g @some-org/openclaw-plugin-name
```

Then reference it in your `~/.openclaw/openclaw.json`:

```json
{
  "plugins": ["@some-org/openclaw-plugin-name"]
}
```

### Writing your own plugin

OpenClaw exposes a typed Plugin SDK:

```typescript
import type { Plugin } from "openclaw/plugin-sdk";

const myPlugin: Plugin = {
  name: "my-plugin",
  setup(ctx) {
    ctx.tool("hello", async () => "Hello from my plugin!");
  },
};

export default myPlugin;
```

See [`docs/tools/plugin.md`](docs/tools/plugin.md) and the community plugin listing at [clawhub.ai](https://clawhub.ai) for more.

---

## Deployment

### Docker Compose (self-hosted)

1. **Set environment variables** – Create `~/.openclaw/.env` with your tokens.
2. **Start services:**

```bash
OPENCLAW_CONFIG_DIR=~/.openclaw \
OPENCLAW_WORKSPACE_DIR=~/.openclaw/workspace \
OPENCLAW_GATEWAY_TOKEN=your-token-here \
docker compose up -d
```

3. **Check health:**

```bash
curl http://localhost:18789/healthz
```

4. **View logs:**

```bash
docker compose logs -f openclaw-gateway
```

5. **Stop:**

```bash
docker compose down
```

The gateway listens on port `18789` (API) and `18790` (bridge). These can be changed via `OPENCLAW_GATEWAY_PORT` and `OPENCLAW_BRIDGE_PORT`.

---

### Fly.io

A `fly.toml` is included for one-command deployment to [Fly.io](https://fly.io).

```bash
# Install flyctl if you haven't
curl -L https://fly.io/install.sh | sh

# Authenticate
fly auth login

# Deploy
fly deploy
```

Set secrets via:

```bash
fly secrets set OPENCLAW_GATEWAY_TOKEN=your-token OPENAI_API_KEY=sk-...
```

---

### Render

A `render.yaml` is included for deployment to [Render](https://render.com). Connect your repository on the Render dashboard and it will auto-detect the config.

---

### Podman

An alternative to Docker using rootless containers:

```bash
# Run the setup helper
bash setup-podman.sh

# Or use the env file directly
podman run --env-file openclaw.podman.env \
  -p 18789:18789 \
  openclaw:local node dist/index.js gateway
```

---

## Security Notes

- **Always set `OPENCLAW_GATEWAY_TOKEN`** if the gateway is accessible outside `localhost`. Without it, anyone who can reach port 18789 can send commands.
- **Never commit your `.env` file** to git. It is already listed in `.gitignore`.
- Secret scanning is configured via `.detect-secrets.cfg` and `.secrets.baseline` to catch accidental leaks in CI.
- Pre-commit hooks (`.pre-commit-config.yaml`) enforce additional checks locally.
- See [`SECURITY.md`](SECURITY.md) for the full security policy and vulnerability reporting instructions.

---

## Contributing

We welcome contributions! Please read [`CONTRIBUTING.md`](CONTRIBUTING.md) before opening a pull request.

Key rules:
- One PR = one issue or topic. Don't bundle unrelated changes.
- Keep PRs under ~5,000 changed lines.
- Don't open many tiny PRs at once.
- New skills should go to [ClawHub](https://clawhub.ai), not core.

See [`VISION.md`](VISION.md) for the project roadmap and what we will and won't merge.

---

## License

OpenClaw is released under the [MIT License](LICENSE).
