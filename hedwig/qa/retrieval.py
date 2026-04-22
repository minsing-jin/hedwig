"""RAG retrieval over collected signals.

Phase 1 implementation: simple SQLite LIKE / FTS over recent signals.
Phase 2+: add embedding similarity, reranking.
"""
from __future__ import annotations

from typing import Iterable


def retrieve_from_db(query: str, limit: int = 10) -> list[dict]:
    """Search recent signals for relevance to query. Returns ranked rows."""
    from hedwig.storage import search_signals

    try:
        return search_signals(query=query.strip(), limit=limit)
    except Exception:
        return []


def format_context(rows: Iterable[dict]) -> str:
    """Turn retrieved rows into a compact context block for LLM answering."""
    chunks = []
    for i, row in enumerate(rows):
        title = row.get("title", "")
        platform = row.get("platform", "")
        url = row.get("url", "")
        content = (row.get("content") or "")[:500]
        why = row.get("why_relevant", "")
        chunks.append(
            f"[{i}] [{platform}] {title}\n  URL: {url}\n  "
            f"Why: {why}\n  Excerpt: {content}"
        )
    return "\n\n".join(chunks)
