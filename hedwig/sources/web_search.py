from __future__ import annotations

import os
from datetime import datetime, timezone

import httpx

from hedwig.models import FetchMethod, Platform, RawPost
from hedwig.sources.base import Source, register_source

EXA_SEARCH = "https://api.exa.ai/search"


@register_source
class WebSearchSource(Source):
    """Semantic web search via Exa AI (free tier: 1000/mo)."""
    platform = Platform.WEB_SEARCH
    plugin_id = "web_search"
    display_name = "Web Search (Exa)"
    fetch_method = FetchMethod.API

    def __init__(self, queries: list[str] | None = None):
        self.queries = queries or [
            "AI agents new tool release",
            "LLM breakthrough research",
            "AI startup funding",
        ]
        self.api_key = os.getenv("EXA_API_KEY", "")

    async def fetch(self, limit: int = 15) -> list[RawPost]:
        if not self.api_key:
            return []

        posts: list[RawPost] = []
        per_query = max(3, limit // len(self.queries))

        async with httpx.AsyncClient(timeout=20) as client:
            for query in self.queries:
                try:
                    resp = await client.post(
                        EXA_SEARCH,
                        headers={"x-api-key": self.api_key, "Content-Type": "application/json"},
                        json={
                            "query": query,
                            "numResults": per_query,
                            "useAutoprompt": True,
                            "type": "auto",
                            "contents": {"text": {"maxCharacters": 2000}},
                        },
                    )
                    if resp.status_code != 200:
                        continue
                    data = resp.json()
                    for result in data.get("results", []):
                        pub_date = result.get("publishedDate", "")
                        try:
                            published = datetime.fromisoformat(pub_date.replace("Z", "+00:00"))
                        except (ValueError, AttributeError):
                            published = datetime.now(tz=timezone.utc)
                        posts.append(RawPost(
                            platform=Platform.WEB_SEARCH,
                            external_id=result.get("id", result.get("url", "")),
                            title=result.get("title", ""),
                            url=result.get("url", ""),
                            content=(result.get("text") or "")[:2000],
                            author=result.get("author", ""),
                            score=int(result.get("score", 0) * 100),
                            published_at=published,
                            extra={"query": query},
                        ))
                except Exception:
                    continue
        return posts[:limit]
