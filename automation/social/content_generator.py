"""
social/content_generator.py — Generates platform-specific promotional content via OpenAI.

Produces:
  - Instagram captions + hashtags
  - Reddit post title + body
  - Twitter/X tweet (or thread of up to 5 tweets)

All content is tailored to the site description and audience defined in config.
"""

from __future__ import annotations

import json
import logging
import sys
import textwrap
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)

SOCIAL_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SOCIAL_DIR.parent))


@dataclass
class InstagramContent:
    caption: str
    hashtags: list[str]
    image_url: str = ""

    @property
    def full_caption(self) -> str:
        tags = " ".join(f"#{h.lstrip('#')}" for h in self.hashtags[:30])
        return f"{self.caption}\n\n{tags}"


@dataclass
class RedditContent:
    title: str
    body: str
    subreddit_hint: str = ""  # suggested subreddit from AI


@dataclass
class TwitterContent:
    tweets: list[str]  # one element = single tweet; multiple = thread

    @property
    def first_tweet(self) -> str:
        return self.tweets[0] if self.tweets else ""


def _get_client():
    try:
        from openai import OpenAI  # type: ignore[import]
    except ImportError:
        raise ImportError("openai package not installed. Run: pip install openai")
    from config import cfg  # noqa: PLC0415
    if not cfg.OPENAI_API_KEY:
        raise EnvironmentError("OPENAI_API_KEY is not set in config.env")
    return OpenAI(api_key=cfg.OPENAI_API_KEY), cfg


def _chat(client, cfg, system: str, user: str) -> str:
    """Call OpenAI chat and return the response text."""
    response = client.chat.completions.create(
        model=cfg.OPENAI_MODEL,
        max_tokens=min(cfg.OPENAI_MAX_TOKENS, 1000),
        temperature=cfg.OPENAI_TEMPERATURE,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    )
    return response.choices[0].message.content.strip()


def generate_instagram_content(domain: str) -> InstagramContent:
    """Generate an Instagram caption and hashtag list for *domain*."""
    from config import cfg  # noqa: PLC0415
    client, cfg = _get_client()

    description = cfg.get_description_for(domain)
    audience = cfg.get_audience_for(domain)

    system = textwrap.dedent("""\
        You are a professional Instagram marketing copywriter.
        Output ONLY valid JSON matching this schema:
        {
          "caption": "engaging multi-line caption (max 200 words, ends with a CTA)",
          "hashtags": ["hashtag1", "hashtag2", ...],  // 20-25 relevant hashtags, no # prefix
          "image_prompt": "a single sentence describing an ideal image for this post"
        }
        Do not include markdown fences or any text outside the JSON.
    """)

    user = textwrap.dedent(f"""\
        Website: https://{domain}
        Description: {description}
        Target audience: {audience}

        Generate a compelling Instagram post for this business.
    """)

    raw = _chat(client, cfg, system, user)
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        log.warning("OpenAI returned non-JSON for Instagram content: %s", raw[:200])
        data = {
            "caption": f"Check out {domain} — {description}",
            "hashtags": ["business", "entrepreneur", "growth"],
            "image_prompt": f"professional photo representing {description}",
        }

    return InstagramContent(
        caption=data.get("caption", ""),
        hashtags=data.get("hashtags", []),
        image_url=cfg.INSTAGRAM_DEFAULT_IMAGE_URL,
    )


def generate_reddit_content(domain: str, subreddit: str = "") -> RedditContent:
    """Generate a Reddit post for *domain* targeting the optional *subreddit*."""
    from config import cfg  # noqa: PLC0415
    client, cfg = _get_client()

    description = cfg.get_description_for(domain)
    audience = cfg.get_audience_for(domain)
    subreddit_hint = f" targeting r/{subreddit}" if subreddit else ""

    system = textwrap.dedent("""\
        You are a Reddit marketing expert. Write authentic, value-first posts that
        do not feel like spam. Output ONLY valid JSON:
        {
          "title": "catchy Reddit post title (max 300 chars, no clickbait)",
          "body": "post body — provide genuine value, mention the site naturally at the end",
          "suggested_subreddit": "subreddit name without r/"
        }
    """)

    user = textwrap.dedent(f"""\
        Website: https://{domain}
        Description: {description}
        Target audience: {audience}{subreddit_hint}

        Write an authentic Reddit post that provides value and naturally mentions the site.
    """)

    raw = _chat(client, cfg, system, user)
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        log.warning("OpenAI returned non-JSON for Reddit content: %s", raw[:200])
        data = {
            "title": f"I built {domain} to help {audience} — feedback welcome",
            "body": f"{description}\n\nCheck it out at https://{domain}",
            "suggested_subreddit": subreddit or "entrepreneur",
        }

    return RedditContent(
        title=data.get("title", ""),
        body=data.get("body", ""),
        subreddit_hint=data.get("suggested_subreddit", subreddit),
    )


def generate_twitter_content(domain: str) -> TwitterContent:
    """
    Generate a tweet or thread for *domain*.
    Returns multiple tweets if thread mode is enabled and content exceeds 280 chars.
    """
    from config import cfg  # noqa: PLC0415
    client, cfg = _get_client()

    description = cfg.get_description_for(domain)
    audience = cfg.get_audience_for(domain)
    thread_note = (
        "If the message is long, split it into up to 5 tweets for a thread."
        if cfg.TWITTER_THREAD_ENABLED
        else "Keep it to a single tweet under 280 characters."
    )

    system = textwrap.dedent(f"""\
        You are a Twitter/X growth expert. Write punchy, engaging promotional content.
        {thread_note}
        Output ONLY valid JSON:
        {{
          "tweets": ["tweet 1 text", "tweet 2 text", ...]
        }}
        Each tweet must be under 280 characters. Include the URL only in the last tweet.
    """)

    user = textwrap.dedent(f"""\
        Website: https://{domain}
        Description: {description}
        Target audience: {audience}

        Write a compelling tweet (or thread) promoting this website.
    """)

    raw = _chat(client, cfg, system, user)
    try:
        data = json.loads(raw)
        tweets = data.get("tweets", [])
    except json.JSONDecodeError:
        log.warning("OpenAI returned non-JSON for Twitter content: %s", raw[:200])
        tweets = [f"{description} — check it out at https://{domain}"]

    # Enforce 280-char limit per tweet
    valid_tweets = []
    for tweet in tweets:
        if len(tweet) <= 280:
            valid_tweets.append(tweet)
        else:
            valid_tweets.append(tweet[:277] + "…")

    if not valid_tweets:
        valid_tweets = [f"{description} — https://{domain}"]

    return TwitterContent(tweets=valid_tweets)
