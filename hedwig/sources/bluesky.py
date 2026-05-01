"""Bluesky source — handle-based RSS aggregation.

The previous implementation used the public AT Protocol search endpoint
(``public.api.bsky.app/xrpc/app.bsky.feed.searchPosts``), which now
returns 403 to unauthenticated callers. Switched to the per-profile RSS
endpoint (``https://bsky.app/profile/<handle>/rss``) which is still
public and stable.

Tracked handles default to a curated AI builder list. Users can override
with ``HEDWIG_BSKY_HANDLES=alice.bsky.social,bob.bsky.social`` env or
by passing ``handles=`` to the constructor.
"""
from __future__ import annotations

import logging
import os
from calendar import timegm
from datetime import datetime, timezone
from typing import Optional

import feedparser
import httpx

from hedwig.models import FetchMethod, Platform, RawPost
from hedwig.sources.base import Source, register_source

logger = logging.getLogger(__name__)


DEFAULT_HANDLES = [
    "karpathy.bsky.social",
    "ylecun.bsky.social",
    "dbreunig.com",
    "samim.bsky.social",
    "swyx.bsky.social",
]


def _parse_env_handles() -> list[str]:
    raw = os.getenv("HEDWIG_BSKY_HANDLES", "").strip()
    if not raw:
        return []
    return [h.strip().lstrip("@") for h in raw.split(",") if h.strip()]


@register_source
class BlueskySource(Source):
    """AI signals from Bluesky via per-handle public RSS feeds."""
    platform = Platform.BLUESKY
    plugin_id = "bluesky"
    display_name = "Bluesky"
    fetch_method = FetchMethod.RSS

    def __init__(self, handles: Optional[list[str]] = None):
        if handles is not None:
            self.handles = handles
        else:
            from_env = _parse_env_handles()
            self.handles = from_env or list(DEFAULT_HANDLES)

    async def fetch(self, limit: int = 30) -> list[RawPost]:
        if not self.handles:
            return []
        per_handle = max(3, limit // max(1, len(self.handles)))
        posts: list[RawPost] = []
        async with httpx.AsyncClient(
            timeout=15, follow_redirects=True,
            headers={"User-Agent": "Mozilla/5.0 (compatible; Hedwig/3.0)"},
        ) as client:
            for handle in self.handles:
                url = f"https://bsky.app/profile/{handle}/rss"
                try:
                    resp = await client.get(url)
                    if resp.status_code != 200:
                        logger.debug("bluesky %s status %s", handle, resp.status_code)
                        continue
                    feed = feedparser.parse(resp.text)
                except Exception as e:
                    logger.debug("bluesky %s failed: %s", handle, e)
                    continue

                for entry in feed.entries[:per_handle]:
                    published = datetime.now(tz=timezone.utc)
                    if getattr(entry, "published_parsed", None):
                        published = datetime.fromtimestamp(
                            timegm(entry.published_parsed), tz=timezone.utc,
                        )
                    text = entry.get("description") or entry.get("summary") or ""
                    posts.append(RawPost(
                        platform=Platform.BLUESKY,
                        external_id=entry.get("link") or entry.get("id") or "",
                        title=text[:140] or f"@{handle}",
                        url=entry.get("link", ""),
                        content=text[:2000],
                        author=handle,
                        score=0,
                        comments_count=0,
                        published_at=published,
                    ))
        return posts[:limit]
