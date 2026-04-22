"""Content-based ranker — OpenAI embeddings with Jaccard fallback.

When OPENAI_API_KEY is set:
  - embed the criteria vector (cached in ~/.hedwig/embed_cache/criteria.json)
  - embed each post title+content[:500]
  - cosine similarity → score

When no API key (quickstart), falls back to Jaccard token overlap. This
keeps quickstart free while upgrading relevance automatically once a key
is configured.

Embedding cache is content-addressed: SHA1 of the input text. Cache file
lives at `HEDWIG_EMBED_CACHE` or `~/.hedwig/embed_cache.json`.
"""
from __future__ import annotations

import hashlib
import json
import logging
import math
import os
import re
from pathlib import Path

from hedwig.config import OPENAI_API_KEY, load_criteria
from hedwig.models import RawPost

logger = logging.getLogger(__name__)


EMBED_MODEL = os.getenv("HEDWIG_EMBED_MODEL", "text-embedding-3-small")
CACHE_PATH = Path(os.getenv("HEDWIG_EMBED_CACHE", str(Path.home() / ".hedwig" / "embed_cache.json")))


# ---------------------------------------------------------------------------
# Jaccard fallback (quickstart / no-API mode)
# ---------------------------------------------------------------------------

def _tokenize(text: str) -> set[str]:
    return {t for t in re.split(r"[^a-z0-9]+", (text or "").lower()) if len(t) >= 3}


def _criteria_tokens() -> set[str]:
    crit = load_criteria() or {}
    care = crit.get("signal_preferences", {}).get("care_about", []) or []
    interests = crit.get("context", {}).get("interests", []) or []
    projects = crit.get("context", {}).get("current_projects", []) or []
    tokens: set[str] = set()
    for seed in list(care) + list(interests) + list(projects):
        tokens |= _tokenize(str(seed))
    return tokens


def _jaccard_score(post: RawPost, pref_tokens: set[str]) -> float:
    haystack = _tokenize(f"{post.title} {post.content[:1000]}")
    if not haystack:
        return 0.0
    overlap = len(pref_tokens & haystack) / max(len(pref_tokens | haystack), 1)
    return min(1.0, overlap * 5.0)


# ---------------------------------------------------------------------------
# Embedding cache
# ---------------------------------------------------------------------------

def _load_cache() -> dict[str, list[float]]:
    try:
        return json.loads(CACHE_PATH.read_text())
    except Exception:
        return {}


def _save_cache(cache: dict[str, list[float]]) -> None:
    try:
        CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        CACHE_PATH.write_text(json.dumps(cache))
    except Exception as e:
        logger.debug("embed cache write failed: %s", e)


def _hash_key(text: str) -> str:
    return hashlib.sha1(f"{EMBED_MODEL}|{text}".encode("utf-8")).hexdigest()


async def _embed(texts: list[str]) -> list[list[float]]:
    """Return embeddings for the given texts, using + updating the cache."""
    cache = _load_cache()
    to_fetch: list[tuple[int, str]] = []
    results: list[list[float] | None] = [None] * len(texts)
    for i, t in enumerate(texts):
        key = _hash_key(t)
        hit = cache.get(key)
        if hit:
            results[i] = hit
        else:
            to_fetch.append((i, t))

    if to_fetch and OPENAI_API_KEY:
        try:
            from openai import AsyncOpenAI
            client = AsyncOpenAI(api_key=OPENAI_API_KEY)
            resp = await client.embeddings.create(
                model=EMBED_MODEL,
                input=[t for _, t in to_fetch],
            )
            for (i, t), item in zip(to_fetch, resp.data):
                emb = list(item.embedding)
                results[i] = emb
                cache[_hash_key(t)] = emb
            _save_cache(cache)
        except Exception as e:
            logger.warning("embedding fetch failed, using fallback: %s", e)

    # Any still-None means both cache miss + API failure
    return [r if r is not None else [] for r in results]


def _cosine(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na <= 0 or nb <= 0:
        return 0.0
    return dot / (na * nb)


def _criteria_text() -> str:
    crit = load_criteria() or {}
    care = crit.get("signal_preferences", {}).get("care_about", []) or []
    interests = crit.get("context", {}).get("interests", []) or []
    projects = crit.get("context", {}).get("current_projects", []) or []
    role = crit.get("identity", {}).get("role", "") or ""
    parts = [role] + list(care) + list(interests) + list(projects)
    return " · ".join(str(p) for p in parts if p)


class ContentRanker:
    name = "content_based"

    async def score_posts(self, posts: list[RawPost], context: dict | None = None) -> list[float]:
        if not posts:
            return []

        # Path A — OpenAI embeddings
        if OPENAI_API_KEY and os.getenv("HEDWIG_DISABLE_EMBEDDINGS") != "1":
            crit_text = _criteria_text()
            if crit_text:
                texts = [crit_text] + [f"{p.title}\n{p.content[:500]}" for p in posts]
                vectors = await _embed(texts)
                crit_vec = vectors[0]
                if crit_vec:
                    out = []
                    for i, post in enumerate(posts, start=1):
                        v = vectors[i]
                        if v:
                            out.append(max(0.0, min(1.0, _cosine(crit_vec, v))))
                        else:
                            # Fallback Jaccard for this single post
                            out.append(_jaccard_score(post, _criteria_tokens()))
                    return out

        # Path B — Jaccard fallback
        pref_tokens: set[str] = set()
        if context:
            kw = context.get("criteria_keywords") or []
            for k in kw:
                pref_tokens |= _tokenize(str(k))
        if not pref_tokens:
            pref_tokens = _criteria_tokens()
        if not pref_tokens:
            return [0.0] * len(posts)
        return [_jaccard_score(post, pref_tokens) for post in posts]
