"""
Content normalizer — converts raw URLs/HTML to clean LLM-ready markdown.

Uses r.jina.ai as primary backend (free, production-ready, handles JS-rendered pages).
Falls back to raw content if jina is unavailable.
"""
from __future__ import annotations

import logging

import httpx

from hedwig.models import RawPost

logger = logging.getLogger(__name__)

JINA_READER = "https://r.jina.ai/"
JINA_SEARCH = "https://s.jina.ai/"


async def normalize_content(post: RawPost, timeout: float = 10.0) -> str:
    """Fetch clean markdown for a post's URL via r.jina.ai.

    Returns normalized content or falls back to post.content if jina fails.
    """
    if not post.url or post.url.startswith("https://r.jina.ai"):
        return post.content

    try:
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            resp = await client.get(
                f"{JINA_READER}{post.url}",
                headers={
                    "Accept": "text/markdown",
                    "x-respond-with": "markdown",
                },
            )
            if resp.status_code == 200 and len(resp.text) > 50:
                return resp.text[:5000]
    except Exception as e:
        logger.debug(f"Jina normalization failed for {post.url}: {e}")

    return post.content


async def normalize_batch(posts: list[RawPost], max_concurrent: int = 5) -> list[RawPost]:
    """Normalize content for a batch of posts. Mutates posts in-place."""
    import asyncio

    sem = asyncio.Semaphore(max_concurrent)

    async def _normalize(post: RawPost):
        async with sem:
            normalized = await normalize_content(post)
            if normalized and len(normalized) > len(post.content):
                post.content = normalized[:5000]

    await asyncio.gather(*[_normalize(p) for p in posts], return_exceptions=True)
    return posts


async def search_web(query: str, num_results: int = 5) -> list[dict]:
    """Use s.jina.ai for semantic web search. Returns list of {title, url, content}."""
    try:
        async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
            resp = await client.get(
                f"{JINA_SEARCH}{query}",
                headers={"Accept": "application/json"},
            )
            if resp.status_code == 200:
                data = resp.json()
                results = []
                for item in data.get("data", [])[:num_results]:
                    results.append({
                        "title": item.get("title", ""),
                        "url": item.get("url", ""),
                        "content": item.get("content", "")[:2000],
                    })
                return results
    except Exception as e:
        logger.debug(f"Jina search failed for '{query}': {e}")
    return []
