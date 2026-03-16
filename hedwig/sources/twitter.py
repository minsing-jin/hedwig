from __future__ import annotations

from calendar import timegm
from datetime import datetime, timezone

import feedparser
import httpx

from hedwig.models import Platform, RawPost
from hedwig.sources.base import Source

# Strategy: Since Nitter instances are mostly dead and X API is paid,
# we use RSS feeds from AI-focused blogs/newsletters commonly shared on X.
# These capture the same signal types that trend on AI Twitter.
AI_RSS_FEEDS = [
    # AI researchers & builders who cross-post
    ("https://karpathy.github.io/feed.xml", "karpathy"),
    ("https://www.interconnects.ai/feed", "interconnects"),
    ("https://www.latent.space/feed", "latent.space"),
    ("https://simonwillison.net/atom/everything/", "simonwillison"),
    ("https://lilianweng.github.io/index.xml", "lilianweng"),
    ("https://newsletter.theaiedge.io/feed", "theaiedge"),
    # AI news aggregators (catch what's trending on X)
    ("https://buttondown.com/ainews/rss", "ainews"),
    ("https://jack-clark.net/feed/", "importai"),
    ("https://thegradient.pub/rss/", "thegradient"),
]


class TwitterSource(Source):
    """Collects AI signals from blogs/newsletters that mirror X/Twitter discourse."""

    async def fetch(self, limit: int = 50) -> list[RawPost]:
        posts: list[RawPost] = []

        async with httpx.AsyncClient(timeout=20, follow_redirects=True) as client:
            for feed_url, author in AI_RSS_FEEDS:
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
                                platform=Platform.TWITTER,
                                external_id=entry.get("id", entry.get("link", "")),
                                title=entry.get("title", "")[:200],
                                url=entry.get("link", ""),
                                content=entry.get("summary", "")[:2000],
                                author=author,
                                published_at=published,
                            )
                        )
                except Exception:
                    continue

        return posts[:limit]
