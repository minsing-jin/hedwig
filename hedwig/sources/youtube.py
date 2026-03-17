from __future__ import annotations

from calendar import timegm
from datetime import datetime, timezone

import feedparser
import httpx

from hedwig.models import Platform, RawPost
from hedwig.sources.base import Source

# YouTube channels focused on AI — using RSS feeds (no API key needed)
# Format: https://www.youtube.com/feeds/videos.xml?channel_id=CHANNEL_ID
AI_YOUTUBE_CHANNELS = [
    ("UCbfYPyITQ-7l4upoX8nvctg", "Two Minute Papers"),
    ("UCWN3xxRkmTPphYit_FYl6Ag", "AI Explained"),
    ("UCZHmQk67mSJgfCCTn7xBfew", "Bycloud"),
    ("UCMLtBahI5DMrt0NPvDSoIRQ", "Machine Learning Street Talk"),
    ("UCKlA7JlBEFMuAbBpYFkKsdg", "Matt Wolfe"),
    ("UCbRP3c757lWg9M-U7TyEkXA", "Yannic Kilcher"),
    ("UCVhQ2NnY5Rskt6UjCFkNq-A", "AI Jason"),
    ("UCwBmNDEDLnVn2fRYHnaBaOg", "The AI Advantage"),
    ("UC-8QAzbLcRglXeN_MY9blyw", "Ben's Bites"),
    ("UCM548bIwKK-m5FkKKJcBQhg", "Wes Roth"),
]


class YouTubeSource(Source):
    """Collects recent AI videos from YouTube channels via RSS."""

    def __init__(self, channels: list[tuple[str, str]] | None = None):
        self.channels = channels or AI_YOUTUBE_CHANNELS

    async def fetch(self, limit: int = 30) -> list[RawPost]:
        posts: list[RawPost] = []

        async with httpx.AsyncClient(timeout=20, follow_redirects=True) as client:
            for channel_id, channel_name in self.channels:
                try:
                    rss_url = f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"
                    resp = await client.get(rss_url)
                    if resp.status_code != 200:
                        continue
                    feed = feedparser.parse(resp.text)
                    for entry in feed.entries[:3]:
                        published = datetime.now(tz=timezone.utc)
                        if hasattr(entry, "published_parsed") and entry.published_parsed:
                            published = datetime.fromtimestamp(
                                timegm(entry.published_parsed), tz=timezone.utc
                            )

                        # Extract video description from media group
                        description = ""
                        if hasattr(entry, "media_group"):
                            for mg in entry.media_group:
                                if hasattr(mg, "content"):
                                    description = mg.get("content", "")
                        if not description:
                            description = entry.get("summary", "")

                        posts.append(
                            RawPost(
                                platform=Platform.YOUTUBE,
                                external_id=entry.get("yt_videoid", entry.get("id", "")),
                                title=entry.get("title", ""),
                                url=entry.get("link", ""),
                                content=description[:2000],
                                author=channel_name,
                                published_at=published,
                                extra={"channel_id": channel_id},
                            )
                        )
                except Exception:
                    continue

        return posts[:limit]
