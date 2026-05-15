"""
social/twitter_bot.py — Posts promotional tweets via Twitter API v2 (Tweepy).

Supports:
  - Single tweets
  - Multi-tweet threads (when TWITTER_THREAD_ENABLED=true)
  - Daily cap enforcement
  - State persistence to avoid duplicate posts
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

log = logging.getLogger(__name__)

SOCIAL_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SOCIAL_DIR.parent))


# ---------------------------------------------------------------------------
# State persistence (shared with reddit_bot)
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
# Tweepy client
# ---------------------------------------------------------------------------

def _get_tweepy_client():
    try:
        import tweepy  # type: ignore[import]
    except ImportError:
        raise ImportError("tweepy package not installed. Run: pip install tweepy")
    from config import cfg  # noqa: PLC0415

    if not all([
        cfg.TWITTER_API_KEY,
        cfg.TWITTER_API_SECRET,
        cfg.TWITTER_ACCESS_TOKEN,
        cfg.TWITTER_ACCESS_SECRET,
    ]):
        raise EnvironmentError(
            "Twitter credentials not fully configured. "
            "Set TWITTER_API_KEY, TWITTER_API_SECRET, TWITTER_ACCESS_TOKEN, TWITTER_ACCESS_SECRET."
        )

    client = tweepy.Client(
        bearer_token=cfg.TWITTER_BEARER_TOKEN,
        consumer_key=cfg.TWITTER_API_KEY,
        consumer_secret=cfg.TWITTER_API_SECRET,
        access_token=cfg.TWITTER_ACCESS_TOKEN,
        access_token_secret=cfg.TWITTER_ACCESS_SECRET,
        wait_on_rate_limit=True,
    )
    return client, cfg


def _get_today_tweet_count(state: dict) -> int:
    """Count tweets sent today (UTC) from the persisted state."""
    today = datetime.now(timezone.utc).date().isoformat()
    daily = state.get("twitter_daily", {})
    if daily.get("date") != today:
        return 0
    return int(daily.get("count", 0))


def _increment_tweet_count(state: dict) -> dict:
    today = datetime.now(timezone.utc).date().isoformat()
    daily = state.get("twitter_daily", {})
    if daily.get("date") != today:
        state["twitter_daily"] = {"date": today, "count": 1}
    else:
        state["twitter_daily"]["count"] = daily.get("count", 0) + 1
    return state


def _post_thread(client, tweets: list[str]) -> list[str]:
    """
    Post a list of tweets as a thread.
    Each tweet is a reply to the previous one.
    Returns list of tweet IDs.
    """
    tweet_ids: list[str] = []
    reply_to: Optional[str] = None

    for tweet_text in tweets:
        kwargs: dict[str, Any] = {"text": tweet_text}
        if reply_to:
            kwargs["in_reply_to_tweet_id"] = reply_to

        response = client.create_tweet(**kwargs)
        tweet_id = str(response.data["id"])
        tweet_ids.append(tweet_id)
        reply_to = tweet_id
        log.info("Tweet posted: id=%s", tweet_id)

    return tweet_ids


def post_to_twitter(domain: str) -> Optional[list[str]]:
    """
    Generate content and post to Twitter/X for the given *domain*.

    Returns list of tweet IDs on success, None on failure.
    """
    from config import cfg  # noqa: PLC0415
    from social.content_generator import generate_twitter_content  # noqa: PLC0415

    if not cfg.SOCIAL_ENABLED:
        log.info("Social posting disabled.")
        return None

    try:
        client, cfg = _get_tweepy_client()
    except (ImportError, EnvironmentError) as exc:
        log.warning("Twitter bot not available: %s", exc)
        return None

    state = _load_state(cfg.SOCIAL_STATE_FILE)

    # Check daily limit
    today_count = _get_today_tweet_count(state)
    if today_count >= cfg.TWITTER_MAX_TWEETS_PER_DAY:
        log.warning(
            "Twitter daily tweet limit reached (%d/%d) — skipping.",
            today_count, cfg.TWITTER_MAX_TWEETS_PER_DAY,
        )
        return None

    # Generate content
    content = generate_twitter_content(domain)

    if cfg.SOCIAL_DRY_RUN:
        log.info(
            "[DRY RUN] Would tweet for %s:\n%s",
            domain, "\n---\n".join(content.tweets),
        )
        return ["dry-run"]

    try:
        if len(content.tweets) == 1 or not cfg.TWITTER_THREAD_ENABLED:
            # Single tweet
            response = client.create_tweet(text=content.tweets[0])
            tweet_id = str(response.data["id"])
            tweet_ids = [tweet_id]
            log.info("Tweet posted: id=%s", tweet_id)
        else:
            tweet_ids = _post_thread(client, content.tweets)

        # Update state
        state = _increment_tweet_count(state)
        if "twitter_posted_ids" not in state:
            state["twitter_posted_ids"] = []
        state["twitter_posted_ids"].extend(tweet_ids)
        # Keep only last 500 IDs
        state["twitter_posted_ids"] = state["twitter_posted_ids"][-500:]
        _save_state(cfg.SOCIAL_STATE_FILE, state)

        return tweet_ids

    except Exception as exc:
        log.error("Twitter post failed for %s: %s", domain, exc)
        return None
