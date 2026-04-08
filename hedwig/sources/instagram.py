from __future__ import annotations

import os
from datetime import datetime, timezone

import httpx

from hedwig.models import FetchMethod, Platform, RawPost
from hedwig.sources.base import Source, register_source

SCRAPECREATORS_IG = "https://api.scrapecreators.com/v2/instagram/search"


@register_source
class InstagramSource(Source):
    """AI signals from Instagram via ScrapeCreators API."""
    platform = Platform.INSTAGRAM
    plugin_id = "instagram"
    display_name = "Instagram"
    fetch_method = FetchMethod.SCRAPE

    def __init__(self, queries: list[str] | None = None):
        self.queries = queries or ["AI tools", "machine learning", "tech"]
        self.api_key = os.getenv("SCRAPECREATORS_API_KEY", "")

    async def fetch(self, limit: int = 15) -> list[RawPost]:
        if not self.api_key:
            return []

        posts: list[RawPost] = []
        per_query = max(3, limit // len(self.queries))

        async with httpx.AsyncClient(timeout=20) as client:
            for query in self.queries:
                try:
                    resp = await client.get(
                        SCRAPECREATORS_IG,
                        headers={"x-api-key": self.api_key},
                        params={"query": query, "count": per_query},
                    )
                    if resp.status_code != 200:
                        continue
                    data = resp.json()
                    for item in data.get("data", []):
                        created = item.get("taken_at", 0)
                        published = datetime.fromtimestamp(created, tz=timezone.utc) if created else datetime.now(tz=timezone.utc)
                        posts.append(RawPost(
                            platform=Platform.INSTAGRAM,
                            external_id=str(item.get("id", "")),
                            title=(item.get("caption", {}).get("text", "") or "")[:200],
                            url=f"https://www.instagram.com/p/{item.get('shortcode', '')}",
                            content=(item.get("caption", {}).get("text", "") or "")[:2000],
                            author=item.get("user", {}).get("username", ""),
                            score=item.get("like_count", 0),
                            comments_count=item.get("comment_count", 0),
                            published_at=published,
                        ))
                except Exception:
                    continue
        return posts[:limit]
