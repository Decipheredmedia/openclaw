"""
social/instagram_bot.py — Posts promotional content to Instagram via Graph API.

Uses the Instagram Graph API (requires a Facebook/Meta Business account with
an Instagram Professional account connected).

Endpoints used:
  POST /{ig-user-id}/media          — create a media container
  POST /{ig-user-id}/media_publish  — publish the container
  GET  /{ig-user-id}/media          — list recent posts (for daily count)
"""

from __future__ import annotations

import json
import logging
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

log = logging.getLogger(__name__)

SOCIAL_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SOCIAL_DIR.parent))

_GRAPH_BASE = "https://graph.facebook.com/v19.0"


def _api_call(
    method: str,
    path: str,
    params: Optional[dict] = None,
    data: Optional[dict] = None,
    access_token: Optional[str] = None,
) -> dict[str, Any]:
    """Make a call to the Instagram Graph API."""
    qs = {"access_token": access_token or "", **(params or {})}
    url = f"{_GRAPH_BASE}/{path.lstrip('/')}?{urllib.parse.urlencode(qs)}"

    if data:
        payload = urllib.parse.urlencode(data).encode()
        req = urllib.request.Request(url, data=payload, method=method)
        req.add_header("Content-Type", "application/x-www-form-urlencoded")
    else:
        req = urllib.request.Request(url, method=method)

    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read())


def _get_today_post_count(account_id: str, access_token: str) -> int:
    """Count posts published today (UTC) to enforce daily limit."""
    try:
        result = _api_call(
            "GET",
            f"{account_id}/media",
            params={"fields": "timestamp", "limit": "50"},
            access_token=access_token,
        )
        today = datetime.now(timezone.utc).date()
        count = 0
        for item in result.get("data", []):
            ts = item.get("timestamp", "")
            try:
                post_date = datetime.fromisoformat(ts.replace("Z", "+00:00")).date()
                if post_date == today:
                    count += 1
            except Exception:
                pass
        return count
    except Exception as exc:
        log.warning("Could not fetch today's post count: %s", exc)
        return 0


def _create_media_container(
    account_id: str,
    access_token: str,
    image_url: str,
    caption: str,
) -> Optional[str]:
    """
    Step 1: Create an Instagram media container.
    Returns the container ID on success, None on failure.
    """
    try:
        result = _api_call(
            "POST",
            f"{account_id}/media",
            data={"image_url": image_url, "caption": caption},
            access_token=access_token,
        )
        container_id = result.get("id")
        if container_id:
            log.info("Instagram media container created: %s", container_id)
            return container_id
        log.error("No container ID returned: %s", result)
        return None
    except Exception as exc:
        log.error("Failed to create Instagram media container: %s", exc)
        return None


def _publish_container(
    account_id: str,
    access_token: str,
    container_id: str,
) -> Optional[str]:
    """
    Step 2: Publish the media container.
    Returns the published media ID on success.
    """
    try:
        result = _api_call(
            "POST",
            f"{account_id}/media_publish",
            data={"creation_id": container_id},
            access_token=access_token,
        )
        media_id = result.get("id")
        if media_id:
            log.info("Instagram post published: media_id=%s", media_id)
            return media_id
        log.error("No media ID returned after publish: %s", result)
        return None
    except Exception as exc:
        log.error("Failed to publish Instagram container %s: %s", container_id, exc)
        return None


def post_to_instagram(domain: str) -> Optional[str]:
    """
    Generate content and post it to Instagram for the given *domain*.

    Returns the published media ID on success, None on failure.
    """
    from config import cfg  # noqa: PLC0415
    from social.content_generator import generate_instagram_content  # noqa: PLC0415

    if not cfg.SOCIAL_ENABLED:
        log.info("Social posting disabled (SOCIAL_ENABLED=false).")
        return None

    if not cfg.INSTAGRAM_ACCESS_TOKEN or not cfg.INSTAGRAM_ACCOUNT_ID:
        log.warning("Instagram credentials not configured — skipping.")
        return None

    # Check daily limit
    today_count = _get_today_post_count(cfg.INSTAGRAM_ACCOUNT_ID, cfg.INSTAGRAM_ACCESS_TOKEN)
    if today_count >= cfg.INSTAGRAM_MAX_POSTS_PER_DAY:
        log.warning(
            "Instagram daily post limit reached (%d/%d) — skipping.",
            today_count, cfg.INSTAGRAM_MAX_POSTS_PER_DAY,
        )
        return None

    # Generate content
    content = generate_instagram_content(domain)
    image_url = content.image_url or cfg.INSTAGRAM_DEFAULT_IMAGE_URL
    if not image_url:
        log.error("No image URL configured for Instagram post — skipping.")
        return None

    if cfg.SOCIAL_DRY_RUN:
        log.info("[DRY RUN] Would post to Instagram for %s:\n%s", domain, content.full_caption)
        return "dry-run"

    container_id = _create_media_container(
        cfg.INSTAGRAM_ACCOUNT_ID,
        cfg.INSTAGRAM_ACCESS_TOKEN,
        image_url,
        content.full_caption,
    )
    if not container_id:
        return None

    return _publish_container(cfg.INSTAGRAM_ACCOUNT_ID, cfg.INSTAGRAM_ACCESS_TOKEN, container_id)
