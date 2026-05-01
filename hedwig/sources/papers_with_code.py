"""Trending AI papers — sourced from Hugging Face Daily Papers.

Originally pulled from paperswithcode.com but that endpoint started
permanently redirecting to huggingface.co/papers/trending (a JS SPA, no
JSON). HuggingFace exposes the curated daily list as a clean JSON
endpoint at https://huggingface.co/api/daily_papers — same intent,
better signal: each item has title, abstract, ai_summary, ai_keywords,
upvotes, github repo links.

The plugin_id is kept as ``papers_with_code`` for registry stability —
existing settings rows + tests don't need to migrate. We do flag the
upstream change in metadata.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

import httpx

from hedwig.models import FetchMethod, Platform, RawPost
from hedwig.sources.base import Source, register_source

logger = logging.getLogger(__name__)


HF_DAILY_PAPERS = "https://huggingface.co/api/daily_papers"


@register_source
class PapersWithCodeSource(Source):
    """Trending AI/ML papers — HuggingFace Daily Papers (curated).

    plugin_id stays as 'papers_with_code' for registry/settings backwards
    compat. The actual upstream is now HF Daily Papers.
    """
    platform = Platform.PAPERS_WITH_CODE
    plugin_id = "papers_with_code"
    display_name = "HF Daily Papers (curated)"
    fetch_method = FetchMethod.API

    async def fetch(self, limit: int = 20) -> list[RawPost]:
        posts: list[RawPost] = []
        try:
            async with httpx.AsyncClient(timeout=20, follow_redirects=True) as client:
                resp = await client.get(HF_DAILY_PAPERS, params={"limit": limit})
            if resp.status_code != 200:
                logger.warning("HF papers API status %s", resp.status_code)
                return []
            data = resp.json()
        except Exception as e:
            logger.warning("HF papers fetch failed: %s", e)
            return []

        if not isinstance(data, list):
            return []

        for item in data[:limit]:
            paper = item.get("paper") or {}
            arxiv_id = paper.get("id") or item.get("id") or ""
            title = paper.get("title") or item.get("title") or ""
            summary = (paper.get("summary") or item.get("summary") or "")[:2000]
            ai_summary = paper.get("ai_summary") or ""
            keywords = paper.get("ai_keywords") or []
            authors = [a.get("name", "") for a in (paper.get("authors") or [])][:5]
            github = paper.get("githubRepo") or ""
            upvotes = paper.get("upvotes") or item.get("upvotes") or 0
            comments = item.get("numComments") or 0

            published_str = (
                paper.get("publishedAt")
                or item.get("publishedAt")
                or paper.get("submittedOnDailyAt")
                or ""
            )
            try:
                published = datetime.fromisoformat(
                    str(published_str).replace("Z", "+00:00")
                ) if published_str else datetime.now(tz=timezone.utc)
                if published.tzinfo is None:
                    published = published.replace(tzinfo=timezone.utc)
            except Exception:
                published = datetime.now(tz=timezone.utc)

            parts = [summary]
            if ai_summary and ai_summary not in summary:
                parts.append(f"AI summary: {ai_summary}")
            if keywords:
                parts.append("Keywords: " + ", ".join(keywords[:8]))
            content = "\n\n".join(p for p in parts if p)[:3000]

            url = f"https://huggingface.co/papers/{arxiv_id}" if arxiv_id else ""

            posts.append(RawPost(
                platform=Platform.PAPERS_WITH_CODE,
                external_id=str(arxiv_id) or title[:80],
                title=title,
                url=url,
                content=content,
                author=", ".join(authors),
                score=int(upvotes or 0),
                comments_count=int(comments or 0),
                published_at=published,
                extra={
                    "github": github,
                    "ai_keywords": keywords,
                    "source_endpoint": "hf_daily_papers",
                },
            ))
        return posts
