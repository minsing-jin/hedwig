"""arXiv recommender-systems monitor (v3, Phase 5) — self-referential loop.

Hedwig monitors recent papers in the recsys/IR space so its own absorption
backlog stays current. Matches docs/VISION_v3.md §11.

Implementation notes:
  - Reuses arxiv's atom API with recsys-focused keyword + category query
  - Paper triage (applicable / reference / ignore) is left to the LLM
    scorer — we only fetch candidates here. A human reviews quarterly.
  - Results land in the regular signals table tagged platform=arxiv; the
    LLM judge can then route them to the absorption_backlog via the
    `exploration_tags` field.

The search predicate is tuned for recommender/ranking/retrieval papers in
cs.IR and cs.LG. When the arXiv API is unreachable, returns [].
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from xml.etree import ElementTree

import httpx

from hedwig.models import FetchMethod, Platform, RawPost
from hedwig.sources.base import Source, register_source

logger = logging.getLogger(__name__)


ARXIV_API = "http://export.arxiv.org/api/query"
ATOM_NS = "{http://www.w3.org/2005/Atom}"

RECSYS_KEYWORDS = [
    "recommender", "recommendation", "ranking", "retrieval",
    "collaborative filtering", "CTR prediction", "learning to rank",
    "contextual bandit", "sequential recommendation", "conversational recommendation",
]


@register_source
class ArxivRecSysSource(Source):
    """Recent recsys/IR papers from arXiv. Feeds the self-referential
    absorption loop — Hedwig's own pipeline monitors recsys literature.
    """
    platform = Platform.ARXIV
    plugin_id = "arxiv_recsys"
    display_name = "arXiv (RecSys self-referential)"
    fetch_method = FetchMethod.API
    default_limit = 20

    def __init__(self, extra_keywords: list[str] | None = None):
        self.keywords = RECSYS_KEYWORDS + (extra_keywords or [])

    def _build_query(self) -> str:
        kw_clause = " OR ".join(f'abs:"{kw}"' for kw in self.keywords)
        cat_clause = "(cat:cs.IR OR cat:cs.LG)"
        return f"({cat_clause}) AND ({kw_clause})"

    async def fetch(self, limit: int = 20) -> list[RawPost]:
        params = {
            "search_query": self._build_query(),
            "sortBy": "submittedDate",
            "sortOrder": "descending",
            "max_results": limit,
        }
        posts: list[RawPost] = []
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.get(ARXIV_API, params=params)
                if resp.status_code != 200:
                    logger.warning("arxiv_recsys: status %s", resp.status_code)
                    return []
                root = ElementTree.fromstring(resp.text)
        except Exception as e:
            logger.warning("arxiv_recsys fetch failed: %s", e)
            return []

        for entry in root.findall(f"{ATOM_NS}entry"):
            title = (entry.findtext(f"{ATOM_NS}title") or "").strip().replace("\n", " ")
            summary = (entry.findtext(f"{ATOM_NS}summary") or "").strip()[:2000]
            arxiv_id = (entry.findtext(f"{ATOM_NS}id") or "").strip()
            published_str = entry.findtext(f"{ATOM_NS}published") or ""
            try:
                published = datetime.fromisoformat(published_str.replace("Z", "+00:00"))
            except ValueError:
                published = datetime.now(tz=timezone.utc)
            authors = [
                (a.findtext(f"{ATOM_NS}name") or "").strip()
                for a in entry.findall(f"{ATOM_NS}author")
            ]
            external_id = arxiv_id.rsplit("/", 1)[-1] if arxiv_id else title[:60]
            posts.append(
                RawPost(
                    platform=Platform.ARXIV,
                    external_id=f"recsys:{external_id}",
                    title=f"[RECSYS] {title}",
                    url=arxiv_id,
                    content=summary,
                    author=", ".join(authors[:4]),
                    score=0,
                    comments_count=0,
                    published_at=published,
                    extra={"absorption_candidate": True, "origin": "arxiv_recsys"},
                )
            )
        return posts
