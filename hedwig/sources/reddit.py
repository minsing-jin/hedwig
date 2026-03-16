from __future__ import annotations

from datetime import datetime, timezone

import httpx

from hedwig.models import Platform, RawPost
from hedwig.sources.base import Source

AI_SUBREDDITS = [
    "MachineLearning",
    "LocalLLaMA",
    "artificial",
    "ChatGPT",
    "OpenAI",
    "ClaudeAI",
    "LangChain",
    "singularity",
    "MLOps",
    "deeplearning",
    "agi",
    "StableDiffusion",
]

USER_AGENT = "hedwig-signal-radar/0.1 (personal tool)"


class RedditSource(Source):
    def __init__(self, subreddits: list[str] | None = None):
        self.subreddits = subreddits or AI_SUBREDDITS

    async def fetch(self, limit: int = 50) -> list[RawPost]:
        posts: list[RawPost] = []
        per_sub = max(5, limit // len(self.subreddits))

        async with httpx.AsyncClient(
            timeout=15,
            headers={"User-Agent": USER_AGENT},
            follow_redirects=True,
        ) as client:
            for sub in self.subreddits:
                try:
                    sub_posts = await self._fetch_subreddit(client, sub, per_sub)
                    posts.extend(sub_posts)
                except Exception:
                    continue

        seen = set()
        unique = []
        for p in posts:
            if p.external_id not in seen:
                seen.add(p.external_id)
                unique.append(p)
        return unique[:limit]

    async def _fetch_subreddit(
        self, client: httpx.AsyncClient, subreddit: str, limit: int
    ) -> list[RawPost]:
        url = f"https://www.reddit.com/r/{subreddit}/hot.json?limit={limit}"
        resp = await client.get(url)
        data = resp.json()

        posts = []
        for child in data.get("data", {}).get("children", []):
            d = child.get("data", {})
            if d.get("stickied"):
                continue
            posts.append(
                RawPost(
                    platform=Platform.REDDIT,
                    external_id=d.get("id", ""),
                    title=d.get("title", ""),
                    url=f"https://reddit.com{d.get('permalink', '')}",
                    content=d.get("selftext", "")[:2000],
                    author=d.get("author", ""),
                    score=d.get("score", 0),
                    comments_count=d.get("num_comments", 0),
                    published_at=datetime.fromtimestamp(
                        d.get("created_utc", 0), tz=timezone.utc
                    ),
                    extra={"subreddit": subreddit},
                )
            )
        return posts
