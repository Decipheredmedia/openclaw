"""
telegram_bot/bot.py — Full Telegram bot for remote management of the automation system.

Commands implemented:
  /start      — Dashboard: site status, revenue summary, recent payments
  /status     — Health of all services (openclaw, nginx, payments listener)
  /deploy     — Trigger builder + deployer for a domain
  /revenue    — Revenue summary for today / week / month
  /post       — Immediately post to a platform for a site
  /pause      — Pause a social media platform's scheduler jobs
  /resume     — Resume a social media platform's scheduler jobs
  /logs       — Tail systemd journal for a service
  /addsite    — Add a new site domain and redeploy Nginx
  /setpayout  — Update payout configuration live
  /help       — Full command reference

Uses python-telegram-bot v20+ (asyncio-based).
"""

from __future__ import annotations

import asyncio
import logging
import subprocess
import sys
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

BOT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BOT_DIR.parent))

# ---------------------------------------------------------------------------
# Auth guard
# ---------------------------------------------------------------------------

def _is_allowed(update, cfg) -> bool:
    """Return True if the message sender is in the allowed users list."""
    if not update.effective_user:
        return False
    uid = update.effective_user.id
    allowed = set(cfg.TELEGRAM_ALLOWED_IDS)
    if cfg.TELEGRAM_OWNER_ID:
        allowed.add(cfg.TELEGRAM_OWNER_ID)
    return uid in allowed


async def _deny(update) -> None:
    await update.message.reply_text("⛔ Unauthorized.")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _run_shell(cmd: str, timeout: int = 30) -> str:
    """Run a shell command and return combined stdout+stderr."""
    try:
        result = subprocess.run(
            cmd, shell=True, capture_output=True, text=True, timeout=timeout
        )
        return (result.stdout + result.stderr).strip() or "(no output)"
    except subprocess.TimeoutExpired:
        return f"(command timed out after {timeout}s)"
    except Exception as exc:
        return f"(error: {exc})"


def _check_systemd_service(name: str) -> str:
    """Return ✅ if the service is active, ❌ otherwise."""
    result = subprocess.run(
        f"systemctl is-active {name}",
        shell=True, capture_output=True, text=True,
    )
    state = result.stdout.strip()
    return f"✅ {state}" if state == "active" else f"❌ {state}"


def _fmt_revenue(data: dict[str, Any]) -> str:
    lines = [
        f"💰 *Revenue — {data['period'].capitalize()}*",
        f"Total (USD-equiv): `${data['total_usd_equivalent']:,.2f}`",
        f"Payments: `{data['payment_count']}`",
    ]
    if data["by_source"]:
        lines.append("\n*By Source:*")
        for src, amt in data["by_source"].items():
            lines.append(f"  {src}: `{amt:,.4f}`")
    if data["by_currency"]:
        lines.append("\n*By Currency:*")
        for cur, amt in data["by_currency"].items():
            lines.append(f"  {cur}: `{amt:,.4f}`")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Command handlers
# ---------------------------------------------------------------------------

async def cmd_start(update, context) -> None:
    from config import cfg  # noqa: PLC0415
    from payments.payment_manager import get_revenue  # noqa: PLC0415

    if not _is_allowed(update, cfg):
        await _deny(update)
        return

    rev = get_revenue("week")
    site_lines = []
    for domain in cfg.SITE_DOMAINS:
        svc = _check_systemd_service("nginx")
        site_lines.append(f"  🌐 https://{domain} — Nginx: {svc}")

    sites_text = "\n".join(site_lines) if site_lines else "  (no sites configured)"
    msg = (
        f"🤖 *OpenClaw Automation Dashboard*\n\n"
        f"*Sites:*\n{sites_text}\n\n"
        f"*7-Day Revenue:* `${rev['total_usd_equivalent']:,.2f}` "
        f"({rev['payment_count']} payments)\n\n"
        f"Type /help for all commands."
    )
    await update.message.reply_text(msg, parse_mode="Markdown")


async def cmd_status(update, context) -> None:
    from config import cfg  # noqa: PLC0415

    if not _is_allowed(update, cfg):
        await _deny(update)
        return

    services = {
        "openclaw-gateway": "OpenClaw Gateway",
        "openclaw-automation": "Automation System",
        "nginx": "Nginx",
    }
    lines = ["🔍 *Service Health*\n"]
    for svc_name, label in services.items():
        state = _check_systemd_service(svc_name)
        lines.append(f"{state} — {label} (`{svc_name}`)")

    # Check payment server
    import urllib.request  # noqa: PLC0415
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{cfg.PAYMENT_SERVER_PORT}/health", timeout=3) as r:
            payment_status = "✅ running" if r.status == 200 else f"❌ HTTP {r.status}"
    except Exception:
        payment_status = "❌ unreachable"
    lines.append(f"{payment_status} — Payment Server (port {cfg.PAYMENT_SERVER_PORT})")

    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


async def cmd_deploy(update, context) -> None:
    from config import cfg  # noqa: PLC0415

    if not _is_allowed(update, cfg):
        await _deny(update)
        return

    if not context.args:
        await update.message.reply_text(
            "Usage: /deploy <domain>\nExample: /deploy example.com"
        )
        return

    domain = context.args[0].strip().lower()
    await update.message.reply_text(f"🚀 Starting deployment for `{domain}`...", parse_mode="Markdown")

    # Build
    await update.message.reply_text("📝 Building site content...")
    try:
        from website_builder.builder import build_site  # noqa: PLC0415
        output_dir = build_site(domain)
        await update.message.reply_text(f"✅ Site built at `{output_dir}`", parse_mode="Markdown")
    except Exception as exc:
        await update.message.reply_text(f"❌ Build failed: {exc}")
        return

    # Deploy
    await update.message.reply_text("🌐 Deploying to Nginx...")
    try:
        from website_builder.deployer import deploy_site  # noqa: PLC0415
        success = deploy_site(domain)
        if success:
            await update.message.reply_text(f"✅ https://{domain} is live!")
        else:
            await update.message.reply_text(f"⚠️ Deployed but site validation failed. Check Nginx logs.")
    except Exception as exc:
        await update.message.reply_text(f"❌ Deploy failed: {exc}")


async def cmd_revenue(update, context) -> None:
    from config import cfg  # noqa: PLC0415
    from payments.payment_manager import get_revenue  # noqa: PLC0415

    if not _is_allowed(update, cfg):
        await _deny(update)
        return

    period = "today"
    if context.args:
        period = context.args[0].strip().lower()
        if period not in ("today", "week", "month", "all"):
            await update.message.reply_text("Usage: /revenue [today|week|month|all]")
            return

    rev = get_revenue(period)
    await update.message.reply_text(_fmt_revenue(rev), parse_mode="Markdown")


async def cmd_post(update, context) -> None:
    from config import cfg  # noqa: PLC0415

    if not _is_allowed(update, cfg):
        await _deny(update)
        return

    if len(context.args) < 2:
        await update.message.reply_text(
            "Usage: /post <platform> <domain>\n"
            "Platforms: instagram, reddit, twitter"
        )
        return

    platform = context.args[0].strip().lower()
    domain = context.args[1].strip().lower()
    await update.message.reply_text(f"📣 Posting to {platform} for {domain}...")

    try:
        if platform == "instagram":
            from social.instagram_bot import post_to_instagram  # noqa: PLC0415
            result = post_to_instagram(domain)
            msg = f"✅ Instagram post: `{result}`" if result else "⚠️ Instagram post skipped/failed."

        elif platform == "reddit":
            from social.reddit_bot import post_to_reddit  # noqa: PLC0415
            result = post_to_reddit(domain)
            msg = f"✅ Reddit post: {result}" if result else "⚠️ Reddit post skipped/failed."

        elif platform == "twitter":
            from social.twitter_bot import post_to_twitter  # noqa: PLC0415
            result = post_to_twitter(domain)
            msg = f"✅ Tweets posted: `{result}`" if result else "⚠️ Twitter post skipped/failed."

        else:
            msg = f"❌ Unknown platform: {platform}. Use: instagram, reddit, twitter"

        await update.message.reply_text(msg, parse_mode="Markdown")

    except Exception as exc:
        await update.message.reply_text(f"❌ Error: {exc}")


async def cmd_pause(update, context) -> None:
    from config import cfg  # noqa: PLC0415
    from social.scheduler import pause_platform  # noqa: PLC0415

    if not _is_allowed(update, cfg):
        await _deny(update)
        return

    if not context.args:
        await update.message.reply_text("Usage: /pause <platform>\nPlatforms: instagram, reddit, twitter, crypto")
        return

    platform = context.args[0].strip().lower()
    ok = pause_platform(platform)
    msg = f"⏸ {platform} jobs paused." if ok else f"⚠️ No jobs found for '{platform}'."
    await update.message.reply_text(msg)


async def cmd_resume(update, context) -> None:
    from config import cfg  # noqa: PLC0415
    from social.scheduler import resume_platform  # noqa: PLC0415

    if not _is_allowed(update, cfg):
        await _deny(update)
        return

    if not context.args:
        await update.message.reply_text("Usage: /resume <platform>\nPlatforms: instagram, reddit, twitter, crypto")
        return

    platform = context.args[0].strip().lower()
    ok = resume_platform(platform)
    msg = f"▶️ {platform} jobs resumed." if ok else f"⚠️ No jobs found for '{platform}'."
    await update.message.reply_text(msg)


async def cmd_logs(update, context) -> None:
    from config import cfg  # noqa: PLC0415

    if not _is_allowed(update, cfg):
        await _deny(update)
        return

    service = "openclaw-automation"
    lines = 50
    if context.args:
        service = context.args[0]
    if len(context.args) > 1:
        try:
            lines = int(context.args[1])
        except ValueError:
            pass

    lines = min(lines, 200)  # cap to avoid huge messages
    output = _run_shell(f"journalctl -u {service} -n {lines} --no-pager")
    # Truncate to fit Telegram's 4096 char limit
    if len(output) > 3800:
        output = "...(truncated)\n" + output[-3800:]

    await update.message.reply_text(
        f"📋 *Logs: {service} (last {lines} lines)*\n```\n{output}\n```",
        parse_mode="Markdown",
    )


async def cmd_addsite(update, context) -> None:
    from config import cfg  # noqa: PLC0415

    if not _is_allowed(update, cfg):
        await _deny(update)
        return

    if not context.args:
        await update.message.reply_text(
            "Usage: /addsite <domain> [template]\nExample: /addsite shop.example.com base"
        )
        return

    domain = context.args[0].strip().lower()
    template = context.args[1] if len(context.args) > 1 else "base"

    # Update config in memory (note: this won't persist across restarts without writing to config.env)
    if domain not in cfg.SITE_DOMAINS:
        cfg.SITE_DOMAINS.append(domain)
    cfg.SITE_TEMPLATES[domain] = template

    await update.message.reply_text(
        f"📌 Domain `{domain}` added with template `{template}`.\n"
        f"Running /deploy {domain} now...",
        parse_mode="Markdown",
    )

    # Trigger deploy
    context.args = [domain]
    await cmd_deploy(update, context)


async def cmd_setpayout(update, context) -> None:
    from config import cfg  # noqa: PLC0415

    if not _is_allowed(update, cfg):
        await _deny(update)
        return

    if len(context.args) < 3:
        await update.message.reply_text(
            "Usage: /setpayout <type> <key> <value>\n"
            "Examples:\n"
            "  /setpayout btc address bc1q...\n"
            "  /setpayout stripe key sk_live_...\n"
            "  /setpayout paypal client_id Abc..."
        )
        return

    payout_type = context.args[0].lower()
    key = context.args[1].lower()
    value = context.args[2]

    updated = False
    if payout_type == "btc" and key == "address":
        cfg.BTC_WALLET_ADDRESS = value
        updated = True
    elif payout_type == "eth" and key == "address":
        cfg.ETH_WALLET_ADDRESS = value
        updated = True
    elif payout_type == "usdt" and key == "address":
        cfg.USDT_TRC20_WALLET_ADDRESS = value
        updated = True
    elif payout_type == "stripe" and key == "key":
        cfg.STRIPE_SECRET_KEY = value
        updated = True
    elif payout_type == "paypal" and key == "client_id":
        cfg.PAYPAL_CLIENT_ID = value
        updated = True
    else:
        await update.message.reply_text(
            f"❌ Unknown payout type/key combination: {payout_type}/{key}\n"
            "Supported: btc/address, eth/address, usdt/address, stripe/key, paypal/client_id"
        )
        return

    if updated:
        await update.message.reply_text(
            f"✅ Payout config updated: `{payout_type}.{key}` set.\n"
            f"⚠️ Note: changes are in-memory only. Update `config.env` to persist.",
            parse_mode="Markdown",
        )


async def cmd_help(update, context) -> None:
    from config import cfg  # noqa: PLC0415

    if not _is_allowed(update, cfg):
        await _deny(update)
        return

    help_text = """
🤖 *OpenClaw Automation Bot — Command Reference*

*/start* — Dashboard: site status + 7-day revenue
*/status* — Health check for all services
*/deploy <domain>* — Build and deploy a website
*/revenue [today|week|month|all]* — Revenue summary
*/post <platform> <domain>* — Post immediately to instagram/reddit/twitter
*/pause <platform>* — Pause scheduler jobs (instagram/reddit/twitter/crypto)
*/resume <platform>* — Resume scheduler jobs
*/logs [service] [lines]* — Tail systemd logs (default: openclaw-automation, 50 lines)
*/addsite <domain> [template]* — Add a new site and deploy it
*/setpayout <type> <key> <value>* — Update payout config live
*/help* — Show this message
""".strip()
    await update.message.reply_text(help_text, parse_mode="Markdown")


# ---------------------------------------------------------------------------
# Bot startup
# ---------------------------------------------------------------------------

def run_bot() -> None:
    """Build and run the Telegram bot application."""
    try:
        from telegram.ext import Application, CommandHandler  # type: ignore[import]
    except ImportError:
        raise ImportError(
            "python-telegram-bot not installed. Run: pip install python-telegram-bot"
        )

    from config import cfg  # noqa: PLC0415

    if not cfg.TELEGRAM_BOT_TOKEN:
        raise EnvironmentError("TELEGRAM_BOT_TOKEN is not set in config.env")

    app = Application.builder().token(cfg.TELEGRAM_BOT_TOKEN).build()

    handlers = [
        CommandHandler("start", cmd_start),
        CommandHandler("status", cmd_status),
        CommandHandler("deploy", cmd_deploy),
        CommandHandler("revenue", cmd_revenue),
        CommandHandler("post", cmd_post),
        CommandHandler("pause", cmd_pause),
        CommandHandler("resume", cmd_resume),
        CommandHandler("logs", cmd_logs),
        CommandHandler("addsite", cmd_addsite),
        CommandHandler("setpayout", cmd_setpayout),
        CommandHandler("help", cmd_help),
    ]

    for handler in handlers:
        app.add_handler(handler)

    log.info("Telegram bot starting (polling)...")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    run_bot()
