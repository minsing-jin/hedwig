from __future__ import annotations

from datetime import datetime, timezone

import httpx

from hedwig.models import FetchMethod, Platform, RawPost
from hedwig.sources.base import Source, register_source

BSKY_SEARCH = "https://public.api.bsky.app/xrpc/app.bsky.feed.searchPosts"


@register_source
class BlueskySource(Source):
    """AI signals from Bluesky via public AT Protocol API."""
    platform = Platform.BLUESKY
    plugin_id = "bluesky"
    display_name = "Bluesky"
    fetch_method = FetchMethod.API

    def __init__(self, queries: list[str] | None = None):
        self.queries = queries or [
            "AI agents", "LLM", "machine learning", "GPT",
            "Claude", "transformer", "deep learning",
        ]

    async def fetch(self, limit: int = 30) -> list[RawPost]:
        posts: list[RawPost] = []
        per_query = max(5, limit // len(self.queries))

        async with httpx.AsyncClient(timeout=15) as client:
            for query in self.queries:
                try:
                    resp = await client.get(
                        BSKY_SEARCH,
                        params={"q": query, "limit": per_query, "sort": "latest"},
                    )
                    if resp.status_code != 200:
                        continue
                    data = resp.json()
                    for post in data.get("posts", []):
                        record = post.get("record", {})
                        author_obj = post.get("author", {})
                        created = record.get("createdAt", "")
                        try:
                            published = datetime.fromisoformat(created.replace("Z", "+00:00"))
                        except (ValueError, AttributeError):
                            published = datetime.now(tz=timezone.utc)

                        posts.append(RawPost(
                            platform=Platform.BLUESKY,
                            external_id=post.get("uri", ""),
                            title=record.get("text", "")[:200],
                            url=f"https://bsky.app/profile/{author_obj.get('handle', '')}/post/{post.get('uri', '').split('/')[-1]}",
                            content=record.get("text", "")[:2000],
                            author=author_obj.get("handle", ""),
                            score=post.get("likeCount", 0),
                            comments_count=post.get("replyCount", 0),
                            published_at=published,
                        ))
                except Exception:
                    continue

        seen: set[str] = set()
        unique: list[RawPost] = []
        for p in posts:
            if p.external_id not in seen:
                seen.add(p.external_id)
                unique.append(p)
        return unique[:limit]
