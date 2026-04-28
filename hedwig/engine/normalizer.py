"""
Content normalizer — converts raw URLs/HTML to clean LLM-ready markdown.

Uses r.jina.ai as primary backend (free, production-ready, handles JS-rendered pages).
Falls back to raw content if jina is unavailable or times out.
"""
from __future__ import annotations

import logging

import httpx

from hedwig.models import RawPost

logger = logging.getLogger(__name__)

import os

JINA_READER = "https://r.jina.ai/"
JINA_SEARCH = "https://s.jina.ai/"

# Default timeout in seconds for Jina API calls
DEFAULT_TIMEOUT = 10.0

# Authenticated requests get 100× higher rate limits
JINA_API_KEY = os.getenv("JINA_API_KEY", "")


async def fetch_clean_markdown(url: str, timeout: float = DEFAULT_TIMEOUT) -> str | None:
    """Fetch clean markdown for an arbitrary URL.

    Strategy:
      1. r.jina.ai (handles JS-rendered SPAs, free with key)
      2. trafilatura local extraction (no rate limit, OSS)
      3. None (caller decides fallback)
    """
    if not url or url.startswith("https://r.jina.ai"):
        return None

    # 1. Jina
    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(timeout, connect=min(timeout, 5.0)),
            follow_redirects=True,
        ) as client:
            headers = {"Accept": "text/markdown", "x-respond-with": "markdown"}
            if JINA_API_KEY:
                headers["Authorization"] = f"Bearer {JINA_API_KEY}"
            resp = await client.get(f"{JINA_READER}{url}", headers=headers)
            if resp.status_code == 200 and len(resp.text) > 50:
                return resp.text[:5000]
            if resp.status_code == 429:
                logger.debug("Jina rate-limited for %s — trying trafilatura", url)
    except (httpx.TimeoutException, httpx.ConnectError) as e:
        logger.debug("Jina unavailable (%s) — trying trafilatura", e)
    except Exception as e:
        logger.debug("Jina failed (%s) — trying trafilatura", e)

    # 2. trafilatura
    try:
        return await _trafilatura_extract(url, timeout=timeout)
    except Exception as e:
        logger.debug("trafilatura also failed for %s: %s", url, e)
    return None


async def _trafilatura_extract(url: str, timeout: float = DEFAULT_TIMEOUT) -> str | None:
    """OSS local content extraction (handles non-JS HTML well)."""
    try:
        import trafilatura
    except ImportError:
        return None
    import asyncio

    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(timeout, connect=min(timeout, 5.0)),
            follow_redirects=True,
        ) as client:
            resp = await client.get(url, headers={"User-Agent": "Mozilla/5.0 Hedwig"})
        if resp.status_code != 200:
            return None
        html = resp.text
    except Exception:
        return None

    def _extract():
        return trafilatura.extract(
            html, include_links=False, include_formatting=True,
            include_tables=False, output_format="markdown", favor_recall=False,
        )
    text = await asyncio.to_thread(_extract)
    return (text or "")[:5000] if text else None


async def normalize_content(post: RawPost, timeout: float = DEFAULT_TIMEOUT) -> str:
    """Compatibility wrapper used by normalize_batch — preserves post.content fallback."""
    cleaned = await fetch_clean_markdown(post.url, timeout=timeout) if post.url else None
    return cleaned or post.content


async def normalize_batch(
    posts: list[RawPost],
    max_concurrent: int = 5,
    timeout: float = DEFAULT_TIMEOUT,
) -> list[RawPost]:
    """Normalize content for a batch of posts. Mutates posts in-place.

    Individual failures (including timeouts) are silently caught — the post
    retains its original content and the batch continues.
    """
    import asyncio

    sem = asyncio.Semaphore(max_concurrent)

    async def _normalize(post: RawPost):
        async with sem:
            normalized = await normalize_content(post, timeout=timeout)
            if normalized and len(normalized) > len(post.content):
                post.content = normalized[:5000]

    await asyncio.gather(*[_normalize(p) for p in posts], return_exceptions=True)
    return posts


async def search_web(
    query: str,
    num_results: int = 5,
    timeout: float = 15.0,
) -> list[dict]:
    """Use s.jina.ai for semantic web search. Returns list of {title, url, content}.

    On timeout or any error, returns an empty list rather than raising.
    """
    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(timeout, connect=min(timeout, 5.0)),
            follow_redirects=True,
        ) as client:
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
    except httpx.TimeoutException:
        logger.warning(
            "Jina search timed out after %.1fs for '%s'",
            timeout,
            query,
        )
    except httpx.ConnectError:
        logger.warning("Jina search connection failed for '%s'", query)
    except Exception as e:
        logger.debug("Jina search failed for '%s': %s", query, e)
    return []
