from __future__ import annotations

from calendar import timegm
from datetime import datetime, timezone

import feedparser
import httpx

from hedwig.models import Platform, RawPost
from hedwig.sources.base import Source

# LinkedIn has no public feed API.
# Strategy: RSS feeds from AI newsletters popular on LinkedIn.
LINKEDIN_RSS_FEEDS = [
    ("https://blog.google/technology/ai/rss/", "google-ai"),
    ("https://openai.com/blog/rss.xml", "openai-blog"),
    ("https://ai.meta.com/blog/rss/", "meta-ai"),
    ("https://www.deeplearning.ai/blog/feed/", "deeplearning.ai"),
    ("https://huggingface.co/blog/feed.xml", "huggingface"),
]


class LinkedInSource(Source):
    """Collects AI signals from corporate blogs commonly shared on LinkedIn."""

    async def fetch(self, limit: int = 20) -> list[RawPost]:
        posts: list[RawPost] = []

        async with httpx.AsyncClient(timeout=20, follow_redirects=True) as client:
            for feed_url, author in LINKEDIN_RSS_FEEDS:
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
                                platform=Platform.LINKEDIN,
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
