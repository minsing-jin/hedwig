from __future__ import annotations

from calendar import timegm
from datetime import datetime, timezone

import feedparser
import httpx

from hedwig.models import Platform, RawPost
from hedwig.sources.base import Source

# Threads has no public API.
# Strategy: RSS from AI community newsletters and indie AI blogs.
THREADS_RSS_FEEDS = [
    ("https://www.bensbites.com/feed", "bensbites"),
    ("https://www.superhuman.ai/feed", "superhuman-ai"),
    ("https://techcrunch.com/category/artificial-intelligence/feed/", "techcrunch-ai"),
    ("https://the-decoder.com/feed/", "the-decoder"),
]


class ThreadsSource(Source):
    """Collects AI signals from indie newsletters and tech press."""

    async def fetch(self, limit: int = 20) -> list[RawPost]:
        posts: list[RawPost] = []

        async with httpx.AsyncClient(timeout=20, follow_redirects=True) as client:
            for feed_url, author in THREADS_RSS_FEEDS:
                try:
                    resp = await client.get(feed_url)
                    if resp.status_code != 200:
                        continue
                    feed = feedparser.parse(resp.text)
                    for entry in feed.entries[:5]:
                        published = datetime.now(tz=timezone.utc)
                        if hasattr(entry, "published_parsed") and entry.published_parsed:
                            published = datetime.fromtimestamp(
                                timegm(entry.published_parsed), tz=timezone.utc
                            )
                        posts.append(
                            RawPost(
                                platform=Platform.THREADS,
                                external_id=entry.get("id", entry.get("link", "")),
                                title=entry.get("title", ""),
                                url=entry.get("link", ""),
                                content=entry.get("summary", "")[:2000],
                                author=author,
                                published_at=published,
                            )
                        )
                except Exception:
                    continue

        return posts[:limit]
