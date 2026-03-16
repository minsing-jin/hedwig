from __future__ import annotations

from datetime import datetime, timezone

import feedparser
import httpx

from hedwig.models import Platform, RawPost
from hedwig.sources.base import Source

GEEKNEWS_RSS = "https://news.hada.io/rss/news"


class GeekNewsSource(Source):
    async def fetch(self, limit: int = 30) -> list[RawPost]:
        async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
            resp = await client.get(GEEKNEWS_RSS)

        feed = feedparser.parse(resp.text)
        posts = []
        for entry in feed.entries[:limit]:
            published = datetime.now(tz=timezone.utc)
            if hasattr(entry, "published_parsed") and entry.published_parsed:
                from calendar import timegm
                published = datetime.fromtimestamp(
                    timegm(entry.published_parsed), tz=timezone.utc
                )

            posts.append(
                RawPost(
                    platform=Platform.GEEKNEWS,
                    external_id=entry.get("id", entry.get("link", "")),
                    title=entry.get("title", ""),
                    url=entry.get("link", ""),
                    content=entry.get("summary", "")[:2000],
                    author=entry.get("author", ""),
                    published_at=published,
                )
            )
        return posts
