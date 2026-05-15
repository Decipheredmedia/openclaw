"""
config.py — Loads, validates, and exposes all settings from config.env.

Usage:
    from config import cfg
    print(cfg.TELEGRAM_BOT_TOKEN)
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Minimal bootstrap: load python-dotenv if available, else read file manually
# ---------------------------------------------------------------------------

def _load_dotenv(path: Path) -> None:
    """Parse key=value lines from *path* and populate os.environ."""
    if not path.exists():
        return
    try:
        from dotenv import load_dotenv  # type: ignore[import]
        load_dotenv(dotenv_path=path, override=False)
        return
    except ImportError:
        pass
    # Fallback: manual parser
    with path.open() as fh:
        for raw in fh:
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = value


_ENV_FILE = Path(__file__).parent / "config.env"
_EXAMPLE_FILE = Path(__file__).parent / "config.env.example"
_load_dotenv(_ENV_FILE)


# ---------------------------------------------------------------------------
# Helper utilities
# ---------------------------------------------------------------------------

def _get(key: str, default: str | None = None, required: bool = False) -> str | None:
    value = os.environ.get(key, default)
    if required and not value:
        raise EnvironmentError(
            f"[config] Required variable '{key}' is missing or empty.\n"
            f"  → Copy config.env.example to config.env and set '{key}'."
        )
    return value


def _get_int(key: str, default: int | None = None, required: bool = False) -> int | None:
    raw = _get(key, str(default) if default is not None else None, required=required)
    if raw is None:
        return None
    try:
        return int(raw)
    except ValueError:
        raise EnvironmentError(
            f"[config] '{key}' must be an integer, got: {raw!r}"
        )


def _get_bool(key: str, default: bool = False) -> bool:
    raw = (_get(key) or "").lower()
    if raw in ("1", "true", "yes", "on"):
        return True
    if raw in ("0", "false", "no", "off", ""):
        return default
    raise EnvironmentError(f"[config] '{key}' must be a boolean (true/false), got: {raw!r}")


def _get_list(key: str, default: str = "") -> list[str]:
    raw = _get(key, default) or ""
    return [item.strip() for item in raw.split(",") if item.strip()]


def _get_mapping(key: str) -> dict[str, str]:
    """Parse 'domain1=val1,domain2=val2' into {'domain1': 'val1', 'domain2': 'val2'}."""
    raw = _get(key, "") or ""
    result: dict[str, str] = {}
    for pair in raw.split(","):
        pair = pair.strip()
        if "=" in pair:
            k, _, v = pair.partition("=")
            result[k.strip()] = v.strip()
    return result


# ---------------------------------------------------------------------------
# Configuration class
# ---------------------------------------------------------------------------

class Config:
    """Singleton holding all configuration values."""

    # ── VPS / Server ──────────────────────────────────────────────────────
    VPS_IP: str = _get("VPS_IP", "")
    VPS_USER: str = _get("VPS_USER", "root")
    OPENCLAW_DIR: str = _get("OPENCLAW_DIR", "/opt/openclaw")
    AUTOMATION_DIR: str = _get("AUTOMATION_DIR", "/opt/openclaw-automation")
    LOG_DIR: str = _get("LOG_DIR", "/var/log/openclaw-automation")

    # ── OpenClaw ──────────────────────────────────────────────────────────
    OPENCLAW_REPO: str = _get("OPENCLAW_REPO", "https://github.com/Decipheredmedia/openclaw")
    OPENCLAW_BRANCH: str = _get("OPENCLAW_BRANCH", "main")
    OPENCLAW_PORT: int = _get_int("OPENCLAW_PORT", 18789)
    OPENCLAW_BIND: str = _get("OPENCLAW_BIND", "127.0.0.1")

    # ── Websites ──────────────────────────────────────────────────────────
    SITE_DOMAINS: list[str] = _get_list("SITE_DOMAINS")
    SITE_TEMPLATES: dict[str, str] = _get_mapping("SITE_TEMPLATES")
    SITE_DESCRIPTIONS: dict[str, str] = _get_mapping("SITE_DESCRIPTIONS")
    SITE_AUDIENCES: dict[str, str] = _get_mapping("SITE_AUDIENCES")
    CERTBOT_WEBROOT: str = _get("CERTBOT_WEBROOT", "/var/www/certbot")
    CERTBOT_EMAIL: str = _get("CERTBOT_EMAIL", "")

    # ── OpenAI ────────────────────────────────────────────────────────────
    OPENAI_API_KEY: str | None = _get("OPENAI_API_KEY")
    OPENAI_MODEL: str = _get("OPENAI_MODEL", "gpt-4o")
    OPENAI_MAX_TOKENS: int = _get_int("OPENAI_MAX_TOKENS", 4096)
    OPENAI_TEMPERATURE: float = float(_get("OPENAI_TEMPERATURE", "0.7"))

    # ── Stripe ────────────────────────────────────────────────────────────
    STRIPE_PUBLISHABLE_KEY: str | None = _get("STRIPE_PUBLISHABLE_KEY")
    STRIPE_SECRET_KEY: str | None = _get("STRIPE_SECRET_KEY")
    STRIPE_WEBHOOK_SECRET: str | None = _get("STRIPE_WEBHOOK_SECRET")
    STRIPE_CONNECT_ACCOUNT_ID: str | None = _get("STRIPE_CONNECT_ACCOUNT_ID")
    PAYMENT_SERVER_PORT: int = _get_int("PAYMENT_SERVER_PORT", 8000)

    # ── PayPal ────────────────────────────────────────────────────────────
    PAYPAL_CLIENT_ID: str | None = _get("PAYPAL_CLIENT_ID")
    PAYPAL_SECRET: str | None = _get("PAYPAL_SECRET")
    PAYPAL_ENV: str = _get("PAYPAL_ENV", "live")
    PAYPAL_WEBHOOK_ID: str | None = _get("PAYPAL_WEBHOOK_ID")

    # ── Crypto ────────────────────────────────────────────────────────────
    BTC_WALLET_ADDRESS: str | None = _get("BTC_WALLET_ADDRESS")
    ETH_WALLET_ADDRESS: str | None = _get("ETH_WALLET_ADDRESS")
    USDT_TRC20_WALLET_ADDRESS: str | None = _get("USDT_TRC20_WALLET_ADDRESS")
    ALCHEMY_API_KEY: str | None = _get("ALCHEMY_API_KEY")
    TRON_API_KEY: str | None = _get("TRON_API_KEY")
    BTC_CONFIRMATIONS_REQUIRED: int = _get_int("BTC_CONFIRMATIONS_REQUIRED", 2)
    ETH_CONFIRMATIONS_REQUIRED: int = _get_int("ETH_CONFIRMATIONS_REQUIRED", 12)
    TRON_CONFIRMATIONS_REQUIRED: int = _get_int("TRON_CONFIRMATIONS_REQUIRED", 19)
    CRYPTO_POLL_INTERVAL: int = _get_int("CRYPTO_POLL_INTERVAL", 60)

    # ── Telegram ──────────────────────────────────────────────────────────
    TELEGRAM_BOT_TOKEN: str | None = _get("TELEGRAM_BOT_TOKEN")
    TELEGRAM_OWNER_ID: int | None = _get_int("TELEGRAM_OWNER_ID")
    TELEGRAM_ALLOWED_IDS: list[int] = [
        int(x) for x in _get_list("TELEGRAM_ALLOWED_IDS") if x.isdigit()
    ]
    TELEGRAM_NOTIFY_CHAT_ID: int | None = _get_int("TELEGRAM_NOTIFY_CHAT_ID")

    # ── Instagram ─────────────────────────────────────────────────────────
    INSTAGRAM_ACCESS_TOKEN: str | None = _get("INSTAGRAM_ACCESS_TOKEN")
    INSTAGRAM_ACCOUNT_ID: str | None = _get("INSTAGRAM_ACCOUNT_ID")
    INSTAGRAM_DEFAULT_IMAGE_URL: str = _get("INSTAGRAM_DEFAULT_IMAGE_URL", "")
    INSTAGRAM_SCHEDULE: dict[str, str] = _get_mapping("INSTAGRAM_SCHEDULE")
    INSTAGRAM_MAX_POSTS_PER_DAY: int = _get_int("INSTAGRAM_MAX_POSTS_PER_DAY", 3)

    # ── Reddit ────────────────────────────────────────────────────────────
    REDDIT_CLIENT_ID: str | None = _get("REDDIT_CLIENT_ID")
    REDDIT_CLIENT_SECRET: str | None = _get("REDDIT_CLIENT_SECRET")
    REDDIT_USERNAME: str | None = _get("REDDIT_USERNAME")
    REDDIT_PASSWORD: str | None = _get("REDDIT_PASSWORD")
    REDDIT_USER_AGENT: str = _get("REDDIT_USER_AGENT", "openclaw-automation/1.0")
    REDDIT_SUBREDDITS: list[str] = _get_list("REDDIT_SUBREDDITS")
    REDDIT_MIN_KARMA: int = _get_int("REDDIT_MIN_KARMA", 10)
    REDDIT_MIN_POST_INTERVAL_HOURS: int = _get_int("REDDIT_MIN_POST_INTERVAL_HOURS", 24)
    REDDIT_JITTER_HOURS: int = _get_int("REDDIT_JITTER_HOURS", 6)

    # ── Twitter / X ───────────────────────────────────────────────────────
    TWITTER_API_KEY: str | None = _get("TWITTER_API_KEY")
    TWITTER_API_SECRET: str | None = _get("TWITTER_API_SECRET")
    TWITTER_ACCESS_TOKEN: str | None = _get("TWITTER_ACCESS_TOKEN")
    TWITTER_ACCESS_SECRET: str | None = _get("TWITTER_ACCESS_SECRET")
    TWITTER_BEARER_TOKEN: str | None = _get("TWITTER_BEARER_TOKEN")
    TWITTER_SCHEDULE: dict[str, str] = _get_mapping("TWITTER_SCHEDULE")
    TWITTER_THREAD_ENABLED: bool = _get_bool("TWITTER_THREAD_ENABLED", True)
    TWITTER_MAX_TWEETS_PER_DAY: int = _get_int("TWITTER_MAX_TWEETS_PER_DAY", 10)

    # ── Social Global ─────────────────────────────────────────────────────
    SOCIAL_ENABLED: bool = _get_bool("SOCIAL_ENABLED", True)
    SOCIAL_DRY_RUN: bool = _get_bool("SOCIAL_DRY_RUN", False)
    SOCIAL_STATE_FILE: str = _get(
        "SOCIAL_STATE_FILE", "/var/lib/openclaw-automation/social_state.json"
    )

    # ─────────────────────────────────────────────────────────────────────
    def validate(self) -> None:
        """Raise EnvironmentError with a summary of all missing required fields."""
        errors: list[str] = []

        def require(field: str, label: str) -> None:
            if not getattr(self, field):
                errors.append(f"  • {label} ({field})")

        require("TELEGRAM_BOT_TOKEN", "Telegram bot token")
        require("TELEGRAM_OWNER_ID", "Telegram owner user ID")

        if errors:
            msg = "Missing required configuration values:\n" + "\n".join(errors)
            msg += "\n\nEdit config.env and set these variables."
            raise EnvironmentError(msg)

        # Validate domain list
        for domain in self.SITE_DOMAINS:
            if not re.match(r"^[a-z0-9.-]+\.[a-z]{2,}$", domain, re.IGNORECASE):
                raise EnvironmentError(
                    f"[config] SITE_DOMAINS contains an invalid domain: {domain!r}"
                )

        # Warn about missing optional integrations
        _warn_if_missing = []
        if self.SOCIAL_ENABLED:
            if not self.OPENAI_API_KEY:
                _warn_if_missing.append("OPENAI_API_KEY (social content generation will fail)")
            if not self.INSTAGRAM_ACCESS_TOKEN:
                _warn_if_missing.append("INSTAGRAM_ACCESS_TOKEN (Instagram posting disabled)")
            if not self.REDDIT_CLIENT_ID:
                _warn_if_missing.append("REDDIT_CLIENT_ID (Reddit posting disabled)")
            if not self.TWITTER_API_KEY:
                _warn_if_missing.append("TWITTER_API_KEY (Twitter posting disabled)")
        if _warn_if_missing:
            import warnings
            warnings.warn(
                "Optional configuration not set — some features will be unavailable:\n"
                + "\n".join(f"  • {w}" for w in _warn_if_missing),
                stacklevel=2,
            )

    def get_template_for(self, domain: str) -> str:
        """Return the template name configured for *domain*, defaulting to 'base'."""
        return self.SITE_TEMPLATES.get(domain, "base")

    def get_description_for(self, domain: str) -> str:
        return self.SITE_DESCRIPTIONS.get(domain, f"A professional website at {domain}")

    def get_audience_for(self, domain: str) -> str:
        return self.SITE_AUDIENCES.get(domain, "general audience")


# Module-level singleton
cfg = Config()
