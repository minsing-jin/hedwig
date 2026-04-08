from __future__ import annotations

from calendar import timegm
from datetime import datetime, timezone
from typing import Optional
from xml.etree import ElementTree

import httpx

from hedwig.models import FetchMethod, Platform, RawPost
from hedwig.sources.base import Source, register_source

ARXIV_API = "http://export.arxiv.org/api/query"

AI_CATEGORIES = [
    "cs.AI", "cs.CL", "cs.LG", "cs.CV", "cs.MA",
    "stat.ML",
]

ATOM_NS = "{http://www.w3.org/2005/Atom}"


@register_source
class ArxivSource(Source):
    """Recent AI/ML papers from arXiv API."""
    platform = Platform.ARXIV
    plugin_id = "arxiv"
    display_name = "arXiv"
    fetch_method = FetchMethod.API

    def __init__(self, categories: list[str] | None = None):
        self.categories = categories or AI_CATEGORIES

    async def fetch(self, limit: int = 30) -> list[RawPost]:
        cat_query = " OR ".join(f"cat:{c}" for c in self.categories)
        params = {
            "search_query": cat_query,
            "sortBy": "submittedDate",
            "sortOrder": "descending",
            "max_results": limit,
        }
        posts: list[RawPost] = []
        async with httpx.AsyncClient(timeout=30) as client:
            try:
                resp = await client.get(ARXIV_API, params=params)
                if resp.status_code != 200:
                    return []
                root = ElementTree.fromstring(resp.text)
                for entry in root.findall(f"{ATOM_NS}entry"):
                    title = (entry.findtext(f"{ATOM_NS}title") or "").strip().replace("\n", " ")
                    summary = (entry.findtext(f"{ATOM_NS}summary") or "").strip()[:2000]
                    arxiv_id = (entry.findtext(f"{ATOM_NS}id") or "")
                    published_str = entry.findtext(f"{ATOM_NS}published") or ""
                    try:
                        published = datetime.fromisoformat(published_str.replace("Z", "+00:00"))
                    except ValueError:
                        published = datetime.now(tz=timezone.utc)
                    authors = [a.findtext(f"{ATOM_NS}name") or "" for a in entry.findall(f"{ATOM_NS}author")]
                    pdf_link = ""
                    for link in entry.findall(f"{ATOM_NS}link"):
                        if link.get("title") == "pdf":
                            pdf_link = link.get("href", "")
                    categories = [c.get("term", "") for c in entry.findall("{http://arxiv.org/schemas/atom}primary_category")]
                    posts.append(RawPost(
                        platform=Platform.ARXIV,
                        external_id=arxiv_id,
                        title=title,
                        url=pdf_link or arxiv_id,
                        content=summary,
                        author=", ".join(authors[:3]),
                        published_at=published,
                        extra={"categories": categories},
                    ))
            except Exception:
                pass
        return posts[:limit]
