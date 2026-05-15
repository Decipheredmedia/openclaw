"""
social/reddit_bot.py — Posts promotional content to Reddit via PRAW.

Safety features:
  - Minimum karma threshold before posting to a subreddit
  - Minimum time interval between posts to the same subreddit (+ random jitter)
  - Posts state saved to SOCIAL_STATE_FILE to survive restarts
"""

from __future__ import annotations

import json
import logging
import random
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

log = logging.getLogger(__name__)

SOCIAL_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SOCIAL_DIR.parent))


# ---------------------------------------------------------------------------
# State persistence
# ---------------------------------------------------------------------------

def _load_state(state_file: str) -> dict[str, Any]:
    path = Path(state_file)
    if path.exists():
        try:
            return json.loads(path.read_text())
        except Exception:
            pass
    return {}


def _save_state(state_file: str, state: dict[str, Any]) -> None:
    path = Path(state_file)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2))


# ---------------------------------------------------------------------------
# Reddit client
# ---------------------------------------------------------------------------

def _get_reddit():
    try:
        import praw  # type: ignore[import]
    except ImportError:
        raise ImportError("praw package not installed. Run: pip install praw")
    from config import cfg  # noqa: PLC0415

    if not all([cfg.REDDIT_CLIENT_ID, cfg.REDDIT_CLIENT_SECRET, cfg.REDDIT_USERNAME, cfg.REDDIT_PASSWORD]):
        raise EnvironmentError(
            "Reddit credentials not fully configured. "
            "Set REDDIT_CLIENT_ID, REDDIT_CLIENT_SECRET, REDDIT_USERNAME, REDDIT_PASSWORD."
        )

    reddit = praw.Reddit(
        client_id=cfg.REDDIT_CLIENT_ID,
        client_secret=cfg.REDDIT_CLIENT_SECRET,
        username=cfg.REDDIT_USERNAME,
        password=cfg.REDDIT_PASSWORD,
        user_agent=cfg.REDDIT_USER_AGENT,
    )
    return reddit, cfg


def _can_post_to_subreddit(subreddit_name: str, state: dict, cfg) -> tuple[bool, str]:
    """
    Return (can_post, reason) for a given subreddit.

    Checks:
      1. Minimum post interval (to avoid spam bans)
      2. State file (last post timestamp)
    Karma check is done separately via API.
    """
    last_posts: dict = state.get("reddit_last_posts", {})
    last_iso: Optional[str] = last_posts.get(subreddit_name)

    if last_iso:
        last_dt = datetime.fromisoformat(last_iso)
        # Add random jitter
        jitter_hours = random.uniform(0, cfg.REDDIT_JITTER_HOURS)
        min_interval = timedelta(hours=cfg.REDDIT_MIN_POST_INTERVAL_HOURS + jitter_hours)
        next_allowed = last_dt + min_interval
        now = datetime.now(timezone.utc)
        if now < next_allowed:
            wait_hours = (next_allowed - now).total_seconds() / 3600
            return False, f"Too soon — next post allowed in {wait_hours:.1f}h"

    return True, "ok"


def post_to_reddit(domain: str, subreddit_name: Optional[str] = None) -> Optional[str]:
    """
    Generate content and post to Reddit.

    If *subreddit_name* is provided, posts only to that subreddit.
    Otherwise iterates through all configured subreddits and posts to the
    first eligible one.

    Returns the post URL on success, None on failure/skip.
    """
    from config import cfg  # noqa: PLC0415
    from social.content_generator import generate_reddit_content  # noqa: PLC0415

    if not cfg.SOCIAL_ENABLED:
        log.info("Social posting disabled.")
        return None

    try:
        reddit, cfg = _get_reddit()
    except (ImportError, EnvironmentError) as exc:
        log.warning("Reddit bot not available: %s", exc)
        return None

    state = _load_state(cfg.SOCIAL_STATE_FILE)
    subreddits_to_try = [subreddit_name] if subreddit_name else cfg.REDDIT_SUBREDDITS

    for sub in subreddits_to_try:
        can_post, reason = _can_post_to_subreddit(sub, state, cfg)
        if not can_post:
            log.info("Skipping r/%s: %s", sub, reason)
            continue

        # Check karma threshold
        try:
            me = reddit.user.me()
            karma = (me.link_karma or 0) + (me.comment_karma or 0)
            if karma < cfg.REDDIT_MIN_KARMA:
                log.warning(
                    "Account karma %d < minimum %d — skipping r/%s.",
                    karma, cfg.REDDIT_MIN_KARMA, sub,
                )
                continue
        except Exception as exc:
            log.warning("Could not fetch Reddit karma: %s", exc)

        # Generate content
        content = generate_reddit_content(domain, sub)

        if cfg.SOCIAL_DRY_RUN:
            log.info("[DRY RUN] Would post to r/%s:\nTitle: %s\n%s", sub, content.title, content.body)
            return "dry-run"

        try:
            subreddit = reddit.subreddit(sub)
            submission = subreddit.submit(
                title=content.title,
                selftext=content.body,
            )
            post_url = f"https://reddit.com{submission.permalink}"
            log.info("Posted to r/%s: %s", sub, post_url)

            # Update state
            if "reddit_last_posts" not in state:
                state["reddit_last_posts"] = {}
            state["reddit_last_posts"][sub] = datetime.now(timezone.utc).isoformat()
            _save_state(cfg.SOCIAL_STATE_FILE, state)

            return post_url

        except Exception as exc:
            log.error("Failed to post to r/%s: %s", sub, exc)
            continue

    log.info("No eligible subreddits available for posting right now.")
    return None
