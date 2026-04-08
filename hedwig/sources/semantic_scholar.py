from __future__ import annotations

from datetime import datetime, timezone

import httpx

from hedwig.models import FetchMethod, Platform, RawPost
from hedwig.sources.base import Source, register_source

SS_SEARCH = "https://api.semanticscholar.org/graph/v1/paper/search"

AI_QUERIES = [
    "large language model",
    "AI agents",
    "transformer architecture",
    "reinforcement learning from human feedback",
]


@register_source
class SemanticScholarSource(Source):
    """Recent AI/ML papers from Semantic Scholar."""
    platform = Platform.SEMANTIC_SCHOLAR
    plugin_id = "semantic_scholar"
    display_name = "Semantic Scholar"
    fetch_method = FetchMethod.API

    def __init__(self, queries: list[str] | None = None):
        self.queries = queries or AI_QUERIES

    async def fetch(self, limit: int = 20) -> list[RawPost]:
        posts: list[RawPost] = []
        per_query = max(5, limit // len(self.queries))

        async with httpx.AsyncClient(timeout=20) as client:
            for query in self.queries:
                try:
                    resp = await client.get(SS_SEARCH, params={
                        "query": query,
                        "limit": per_query,
                        "fields": "title,abstract,authors,url,year,citationCount,publicationDate",
                        "sort": "publicationDate:desc",
                    })
                    if resp.status_code != 200:
                        continue
                    data = resp.json()
                    for paper in data.get("data", []):
                        pub_date = paper.get("publicationDate") or ""
                        try:
                            published = datetime.fromisoformat(pub_date)
                            if published.tzinfo is None:
                                published = published.replace(tzinfo=timezone.utc)
                        except (ValueError, AttributeError):
                            published = datetime.now(tz=timezone.utc)
                        authors = [a.get("name", "") for a in (paper.get("authors") or [])[:3]]
                        posts.append(RawPost(
                            platform=Platform.SEMANTIC_SCHOLAR,
                            external_id=paper.get("paperId", ""),
                            title=paper.get("title", ""),
                            url=paper.get("url", ""),
                            content=(paper.get("abstract") or "")[:2000],
                            author=", ".join(authors),
                            score=paper.get("citationCount", 0),
                            published_at=published,
                            extra={"year": paper.get("year"), "query": query},
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
