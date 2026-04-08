from __future__ import annotations

import os
from datetime import datetime, timezone

import httpx

from hedwig.models import FetchMethod, Platform, RawPost
from hedwig.sources.base import Source, register_source

SCRAPECREATORS_TIKTOK = "https://api.scrapecreators.com/v2/tiktok/search"


@register_source
class TikTokSource(Source):
    """AI signals from TikTok via ScrapeCreators API."""
    platform = Platform.TIKTOK
    plugin_id = "tiktok"
    display_name = "TikTok"
    fetch_method = FetchMethod.SCRAPE

    def __init__(self, queries: list[str] | None = None):
        self.queries = queries or ["AI tools", "machine learning", "ChatGPT"]
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
                        SCRAPECREATORS_TIKTOK,
                        headers={"x-api-key": self.api_key},
                        params={"query": query, "count": per_query},
                    )
                    if resp.status_code != 200:
                        continue
                    data = resp.json()
                    for item in data.get("data", []):
                        created = item.get("createTime", 0)
                        published = datetime.fromtimestamp(created, tz=timezone.utc) if created else datetime.now(tz=timezone.utc)
                        posts.append(RawPost(
                            platform=Platform.TIKTOK,
                            external_id=str(item.get("id", "")),
                            title=item.get("desc", "")[:200],
                            url=f"https://www.tiktok.com/@{item.get('author', {}).get('uniqueId', '')}/video/{item.get('id', '')}",
                            content=item.get("desc", "")[:2000],
                            author=item.get("author", {}).get("uniqueId", ""),
                            score=item.get("stats", {}).get("diggCount", 0),
                            comments_count=item.get("stats", {}).get("commentCount", 0),
                            published_at=published,
                        ))
                except Exception:
                    continue
        return posts[:limit]
