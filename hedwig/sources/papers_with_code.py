from __future__ import annotations

from datetime import datetime, timezone

import httpx

from hedwig.models import FetchMethod, Platform, RawPost
from hedwig.sources.base import Source, register_source

PWC_API = "https://paperswithcode.com/api/v1/papers/"


@register_source
class PapersWithCodeSource(Source):
    """Trending AI/ML papers from Papers With Code."""
    platform = Platform.PAPERS_WITH_CODE
    plugin_id = "papers_with_code"
    display_name = "Papers With Code"
    fetch_method = FetchMethod.API

    async def fetch(self, limit: int = 20) -> list[RawPost]:
        posts: list[RawPost] = []
        async with httpx.AsyncClient(timeout=20) as client:
            try:
                resp = await client.get(PWC_API, params={
                    "ordering": "-published",
                    "items_per_page": limit,
                })
                if resp.status_code != 200:
                    return []
                data = resp.json()
                for paper in data.get("results", []):
                    pub_date = paper.get("published") or ""
                    try:
                        published = datetime.fromisoformat(pub_date)
                        if published.tzinfo is None:
                            published = published.replace(tzinfo=timezone.utc)
                    except (ValueError, AttributeError):
                        published = datetime.now(tz=timezone.utc)
                    authors = [a for a in (paper.get("authors") or [])[:3]]
                    posts.append(RawPost(
                        platform=Platform.PAPERS_WITH_CODE,
                        external_id=paper.get("id", paper.get("paper_url", "")),
                        title=paper.get("title", ""),
                        url=paper.get("paper_url", paper.get("url_abs", "")),
                        content=(paper.get("abstract") or "")[:2000],
                        author=", ".join(authors) if isinstance(authors[0], str) else "",
                        published_at=published,
                        extra={"stars": paper.get("repository_stars", 0)},
                    ))
            except Exception:
                pass
        return posts[:limit]
