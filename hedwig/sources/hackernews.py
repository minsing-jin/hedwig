from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import httpx

from hedwig.models import FetchMethod, Platform, RawPost
from hedwig.sources.base import Source, register_source

HN_TOP = "https://hacker-news.firebaseio.com/v0/topstories.json"
HN_BEST = "https://hacker-news.firebaseio.com/v0/beststories.json"
HN_ITEM = "https://hacker-news.firebaseio.com/v0/item/{}.json"


@register_source
class HackerNewsSource(Source):
    platform = Platform.HACKERNEWS
    plugin_id = "hackernews"
    display_name = "Hacker News"
    fetch_method = FetchMethod.API

    async def fetch(self, limit: int = 50) -> list[RawPost]:
        async with httpx.AsyncClient(timeout=15) as client:
            top_resp = await client.get(HN_TOP)
            best_resp = await client.get(HN_BEST)
            ids = list(dict.fromkeys(
                top_resp.json()[:limit] + best_resp.json()[:30]
            ))[:limit]
            tasks = [self._fetch_item(client, item_id) for item_id in ids]
            results = await asyncio.gather(*tasks, return_exceptions=True)
        return [r for r in results if isinstance(r, RawPost)]

    async def _fetch_item(self, client: httpx.AsyncClient, item_id: int) -> RawPost:
        resp = await client.get(HN_ITEM.format(item_id))
        data = resp.json()
        return RawPost(
            platform=Platform.HACKERNEWS,
            external_id=str(item_id),
            title=data.get("title", ""),
            url=data.get("url", f"https://news.ycombinator.com/item?id={item_id}"),
            content=data.get("text", ""),
            author=data.get("by", ""),
            score=data.get("score", 0),
            comments_count=data.get("descendants", 0),
            published_at=datetime.fromtimestamp(data.get("time", 0), tz=timezone.utc),
        )
