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

JINA_READER = "https://r.jina.ai/"
JINA_SEARCH = "https://s.jina.ai/"

# Default timeout in seconds for Jina API calls
DEFAULT_TIMEOUT = 10.0


async def normalize_content(post: RawPost, timeout: float = DEFAULT_TIMEOUT) -> str:
    """Fetch clean markdown for a post's URL via r.jina.ai.

    Returns normalized content or falls back to post.content if jina fails.
    Handles timeouts, connection errors, and HTTP errors gracefully — the
    caller always receives usable content (original post.content at worst).
    """
    if not post.url or post.url.startswith("https://r.jina.ai"):
        return post.content

    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(timeout, connect=min(timeout, 5.0)),
            follow_redirects=True,
        ) as client:
            resp = await client.get(
                f"{JINA_READER}{post.url}",
                headers={
                    "Accept": "text/markdown",
                    "x-respond-with": "markdown",
                },
            )
            if resp.status_code == 200 and len(resp.text) > 50:
                return resp.text[:5000]
            logger.debug(
                "Jina returned status=%s len=%d for %s",
                resp.status_code,
                len(resp.text),
                post.url,
            )
    except httpx.TimeoutException:
        logger.warning(
            "Jina normalization timed out after %.1fs for %s — falling back to raw content",
            timeout,
            post.url,
        )
    except httpx.ConnectError:
        logger.warning(
            "Jina connection failed for %s — falling back to raw content",
            post.url,
        )
    except Exception as e:
        logger.debug("Jina normalization failed for %s: %s", post.url, e)

    return post.content


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
