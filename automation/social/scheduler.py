"""
social/scheduler.py — APScheduler-based social media posting scheduler.

Creates one job per platform per site, based on cron expressions in config.
Also schedules the crypto monitor polling job.

Usage:
    from social.scheduler import start_scheduler, pause_platform, resume_platform
    scheduler = start_scheduler()
    # ... later ...
    scheduler.shutdown()
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)

SOCIAL_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SOCIAL_DIR.parent))

_scheduler: Optional[object] = None  # APScheduler BackgroundScheduler instance


def _parse_cron(expr: str) -> dict[str, str]:
    """
    Parse a 5-field cron expression into APScheduler CronTrigger kwargs.
    Fields: minute hour day_of_month month day_of_week
    Example: '0 9 * * *' → {'minute': '0', 'hour': '9', ...}
    """
    fields = expr.strip().split()
    if len(fields) != 5:
        raise ValueError(f"Invalid cron expression (expected 5 fields): {expr!r}")
    keys = ["minute", "hour", "day", "month", "day_of_week"]
    return dict(zip(keys, fields))


def _instagram_job(domain: str) -> None:
    """APScheduler job: post to Instagram for *domain*."""
    try:
        from social.instagram_bot import post_to_instagram  # noqa: PLC0415
        result = post_to_instagram(domain)
        log.info("Instagram job for %s: %s", domain, result or "skipped")
    except Exception as exc:
        log.error("Instagram job error for %s: %s", domain, exc, exc_info=True)


def _reddit_job(domain: str) -> None:
    """APScheduler job: post to Reddit for *domain*."""
    try:
        from social.reddit_bot import post_to_reddit  # noqa: PLC0415
        result = post_to_reddit(domain)
        log.info("Reddit job for %s: %s", domain, result or "skipped")
    except Exception as exc:
        log.error("Reddit job error for %s: %s", domain, exc, exc_info=True)


def _twitter_job(domain: str) -> None:
    """APScheduler job: post to Twitter for *domain*."""
    try:
        from social.twitter_bot import post_to_twitter  # noqa: PLC0415
        result = post_to_twitter(domain)
        log.info("Twitter job for %s: %s", domain, result or "skipped")
    except Exception as exc:
        log.error("Twitter job error for %s: %s", domain, exc, exc_info=True)


def _crypto_monitor_job() -> None:
    """APScheduler job: poll crypto wallets for new transactions."""
    try:
        from payments.crypto_monitor import check_all_wallets  # noqa: PLC0415
        check_all_wallets()
    except Exception as exc:
        log.error("Crypto monitor job error: %s", exc, exc_info=True)


def start_scheduler():
    """
    Create and start the BackgroundScheduler with all configured jobs.
    Returns the scheduler instance.
    """
    global _scheduler

    try:
        from apscheduler.schedulers.background import BackgroundScheduler  # type: ignore[import]
        from apscheduler.triggers.cron import CronTrigger  # type: ignore[import]
        from apscheduler.triggers.interval import IntervalTrigger  # type: ignore[import]
    except ImportError:
        raise ImportError("apscheduler not installed. Run: pip install apscheduler")

    from config import cfg  # noqa: PLC0415

    scheduler = BackgroundScheduler(timezone="UTC")

    # ── Instagram jobs ──────────────────────────────────────────────────
    if cfg.INSTAGRAM_ACCESS_TOKEN:
        for domain in cfg.SITE_DOMAINS:
            cron_expr = cfg.INSTAGRAM_SCHEDULE.get(domain)
            if not cron_expr:
                log.debug("No Instagram schedule for %s — skipping.", domain)
                continue
            try:
                cron_kwargs = _parse_cron(cron_expr)
                scheduler.add_job(
                    _instagram_job,
                    CronTrigger(**cron_kwargs),
                    args=[domain],
                    id=f"instagram_{domain}",
                    name=f"Instagram: {domain}",
                    replace_existing=True,
                    misfire_grace_time=3600,
                )
                log.info("Scheduled Instagram job for %s: %s", domain, cron_expr)
            except Exception as exc:
                log.warning("Instagram schedule error for %s: %s", domain, exc)
    else:
        log.info("INSTAGRAM_ACCESS_TOKEN not set — Instagram jobs skipped.")

    # ── Reddit jobs ─────────────────────────────────────────────────────
    if cfg.REDDIT_CLIENT_ID:
        for domain in cfg.SITE_DOMAINS:
            # Reddit posts to subreddits on a rotating basis.
            # Schedule one post attempt per domain every 24h + jitter.
            scheduler.add_job(
                _reddit_job,
                "interval",
                hours=cfg.REDDIT_MIN_POST_INTERVAL_HOURS,
                jitter=cfg.REDDIT_JITTER_HOURS * 3600,
                args=[domain],
                id=f"reddit_{domain}",
                name=f"Reddit: {domain}",
                replace_existing=True,
                misfire_grace_time=7200,
            )
            log.info("Scheduled Reddit job for %s (every %dh).", domain, cfg.REDDIT_MIN_POST_INTERVAL_HOURS)
    else:
        log.info("REDDIT_CLIENT_ID not set — Reddit jobs skipped.")

    # ── Twitter jobs ────────────────────────────────────────────────────
    if cfg.TWITTER_API_KEY:
        for domain in cfg.SITE_DOMAINS:
            cron_expr = cfg.TWITTER_SCHEDULE.get(domain)
            if not cron_expr:
                log.debug("No Twitter schedule for %s — skipping.", domain)
                continue
            try:
                cron_kwargs = _parse_cron(cron_expr)
                scheduler.add_job(
                    _twitter_job,
                    CronTrigger(**cron_kwargs),
                    args=[domain],
                    id=f"twitter_{domain}",
                    name=f"Twitter: {domain}",
                    replace_existing=True,
                    misfire_grace_time=3600,
                )
                log.info("Scheduled Twitter job for %s: %s", domain, cron_expr)
            except Exception as exc:
                log.warning("Twitter schedule error for %s: %s", domain, exc)
    else:
        log.info("TWITTER_API_KEY not set — Twitter jobs skipped.")

    # ── Crypto monitor job ───────────────────────────────────────────────
    if any([cfg.BTC_WALLET_ADDRESS, cfg.ETH_WALLET_ADDRESS, cfg.USDT_TRC20_WALLET_ADDRESS]):
        scheduler.add_job(
            _crypto_monitor_job,
            "interval",
            seconds=cfg.CRYPTO_POLL_INTERVAL,
            id="crypto_monitor",
            name="Crypto Wallet Monitor",
            replace_existing=True,
            misfire_grace_time=300,
        )
        log.info("Crypto monitor scheduled every %ds.", cfg.CRYPTO_POLL_INTERVAL)

    scheduler.start()
    log.info("Scheduler started with %d jobs.", len(scheduler.get_jobs()))
    _scheduler = scheduler
    return scheduler


def get_scheduler():
    """Return the running scheduler instance (or None if not started)."""
    return _scheduler


def pause_platform(platform: str) -> bool:
    """
    Pause all jobs for the given *platform* (instagram, reddit, twitter, crypto).
    Returns True if any jobs were paused.
    """
    scheduler = get_scheduler()
    if not scheduler:
        log.warning("Scheduler not running.")
        return False

    paused = 0
    for job in scheduler.get_jobs():
        if job.id.startswith(f"{platform}_") or job.id == f"{platform}_monitor":
            job.pause()
            log.info("Paused job: %s", job.id)
            paused += 1

    return paused > 0


def resume_platform(platform: str) -> bool:
    """
    Resume all jobs for the given *platform*.
    Returns True if any jobs were resumed.
    """
    scheduler = get_scheduler()
    if not scheduler:
        log.warning("Scheduler not running.")
        return False

    resumed = 0
    for job in scheduler.get_jobs():
        if job.id.startswith(f"{platform}_") or job.id == f"{platform}_monitor":
            job.resume()
            log.info("Resumed job: %s", job.id)
            resumed += 1

    return resumed > 0


def list_jobs() -> list[dict]:
    """Return a list of all scheduled jobs with id, name, next_run_time, and state."""
    scheduler = get_scheduler()
    if not scheduler:
        return []
    return [
        {
            "id": job.id,
            "name": job.name,
            "next_run": str(job.next_run_time) if job.next_run_time else "paused",
        }
        for job in scheduler.get_jobs()
    ]
