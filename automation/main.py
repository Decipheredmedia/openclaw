#!/usr/bin/env python3
"""
main.py — Single entry point for the OpenClaw Automation System.

Subcommands:
  --install   Run the full installer (requires root)
  --start     Start the automation daemon (scheduler + payment server + Telegram bot)
  --deploy    Build and deploy all configured sites
  --bot       Run the Telegram bot only (no scheduler/payment server)

Usage:
  sudo python3 main.py --install
  python3 main.py --start
  python3 main.py --deploy
  python3 main.py --bot
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import multiprocessing
import signal
import sys
from pathlib import Path

AUTOMATION_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(AUTOMATION_DIR))

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("main")


# ---------------------------------------------------------------------------
# Subcommand: install
# ---------------------------------------------------------------------------

def do_install() -> None:
    log.info("Running installer...")
    from install import main as install_main  # noqa: PLC0415
    install_main()


# ---------------------------------------------------------------------------
# Subcommand: deploy
# ---------------------------------------------------------------------------

def do_deploy() -> None:
    log.info("Building and deploying all sites...")
    from website_builder.builder import build_all_sites  # noqa: PLC0415
    from website_builder.deployer import deploy_all_sites  # noqa: PLC0415

    built = build_all_sites()
    log.info("Built %d site(s).", len(built))

    results = deploy_all_sites()
    for domain, success in results.items():
        status = "✓ LIVE" if success else "✗ FAILED"
        log.info("  %s: %s", domain, status)


# ---------------------------------------------------------------------------
# Subcommand: bot (Telegram only)
# ---------------------------------------------------------------------------

def do_bot() -> None:
    log.info("Starting Telegram bot (no scheduler)...")
    from telegram_bot.bot import run_bot  # noqa: PLC0415
    run_bot()


# ---------------------------------------------------------------------------
# Payment server (FastAPI) process
# ---------------------------------------------------------------------------

def _run_payment_server(port: int) -> None:
    """Run the FastAPI payment webhook server in a subprocess."""
    import uvicorn  # type: ignore[import]
    from fastapi import FastAPI  # type: ignore[import]
    from payments.stripe_handler import router as stripe_router  # noqa: PLC0415
    from payments.paypal_handler import router as paypal_router  # noqa: PLC0415

    app = FastAPI(title="OpenClaw Payment Server", docs_url=None, redoc_url=None)
    app.include_router(stripe_router)
    app.include_router(paypal_router)

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    @app.post("/api/contact")
    async def contact(request):
        """Accept contact form submissions and log them."""
        from fastapi import Request  # noqa: PLC0415
        body = await request.json()
        log.info("Contact form submission: %s", body)
        return {"status": "received"}

    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")


# ---------------------------------------------------------------------------
# Subcommand: start (full daemon)
# ---------------------------------------------------------------------------

def do_start() -> None:
    """
    Start all components:
      1. Payment webhook server (FastAPI/uvicorn) in a child process
      2. Social media scheduler (APScheduler) in background threads
      3. Telegram bot (blocking, in main process)
    """
    from config import cfg  # noqa: PLC0415

    # Validate config before starting
    cfg.validate()

    # Initialise payment ledger
    from payments.payment_manager import init_ledger  # noqa: PLC0415
    init_ledger()

    # Start payment server process
    payment_proc = multiprocessing.Process(
        target=_run_payment_server,
        args=(cfg.PAYMENT_SERVER_PORT,),
        daemon=True,
        name="payment-server",
    )
    payment_proc.start()
    log.info("Payment server started (pid=%d, port=%d)", payment_proc.pid, cfg.PAYMENT_SERVER_PORT)

    # Start scheduler
    from social.scheduler import start_scheduler  # noqa: PLC0415
    scheduler = start_scheduler()

    # Graceful shutdown handler
    def _shutdown(signum, frame):
        log.info("Shutdown signal received — stopping scheduler...")
        scheduler.shutdown(wait=False)
        payment_proc.terminate()
        sys.exit(0)

    signal.signal(signal.SIGTERM, _shutdown)
    signal.signal(signal.SIGINT, _shutdown)

    # Start Telegram bot (blocking)
    log.info("Starting Telegram bot...")
    from telegram_bot.bot import run_bot  # noqa: PLC0415
    run_bot()


# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="OpenClaw Automation System",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  sudo python3 main.py --install          # First-time setup
  python3 main.py --deploy                # Build and deploy all sites
  python3 main.py --start                 # Run full automation daemon
  python3 main.py --bot                   # Run Telegram bot only
""",
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--install", action="store_true", help="Run the full installer")
    group.add_argument("--start", action="store_true", help="Start the full automation daemon")
    group.add_argument("--deploy", action="store_true", help="Build and deploy all configured sites")
    group.add_argument("--bot", action="store_true", help="Run Telegram bot only")
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    if args.install:
        do_install()
    elif args.deploy:
        do_deploy()
    elif args.bot:
        do_bot()
    elif args.start:
        do_start()


if __name__ == "__main__":
    main()
