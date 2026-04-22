"""Per-signal score trace — "Why this signal?" instrumentation (v3, Phase 2).

Given a signal row and the current criteria, returns a human-readable
breakdown of which criteria tokens matched, which authority/recency/
convergence factors applied, and what ensemble components contributed.

This is the transparency pillar of Algorithm Sovereignty: users must be
able to see *why* something surfaced.
"""
from __future__ import annotations

import re

from hedwig.config import load_criteria


def _tokenize(text: str) -> set[str]:
    return {t for t in re.split(r"[^a-z0-9]+", (text or "").lower()) if len(t) >= 3}


def trace_signal(row: dict) -> dict:
    """Build a Why trace for a stored signal row.

    Returns:
        {
          "signal_id": str,
          "relevance_score": float,
          "matched_care_about": [str],
          "matched_ignore": [str],
          "factors": {
            "source_authority": str explanation,
            "recency": str explanation,
            "engagement": str explanation,
            "convergence_tags": [str],
          },
          "llm_reasoning": str ("why_relevant" from scorer),
          "devils_advocate": str,
          "exploration_tags": [str],
        }
    """
    criteria = load_criteria() or {}
    care = criteria.get("signal_preferences", {}).get("care_about", []) or []
    ignore = criteria.get("signal_preferences", {}).get("ignore", []) or []

    haystack = _tokenize(
        f"{row.get('title', '')} {row.get('content', '')[:2000]}"
    )

    matched_care = sorted(
        {
            c
            for c in care
            if any(tok in haystack for tok in _tokenize(str(c)))
        }
    )
    matched_ignore = sorted(
        {
            i
            for i in ignore
            if any(tok in haystack for tok in _tokenize(str(i)))
        }
    )

    import json as _json
    try:
        exploration = _json.loads(row.get("exploration_tags") or "[]")
    except Exception:
        exploration = []

    factors = {
        "source_authority": f"Platform={row.get('platform')} — authority weight applied by pre_scorer",
        "recency": f"Published {row.get('published_at', '?')}, decay-weighted",
        "engagement": f"score={row.get('platform_score', 0)}, comments={row.get('comments_count', 0)}",
        "convergence_tags": exploration,
    }

    return {
        "signal_id": str(row.get("id", "")),
        "title": row.get("title", ""),
        "url": row.get("url", ""),
        "platform": row.get("platform", ""),
        "relevance_score": row.get("relevance_score", 0.0),
        "matched_care_about": matched_care,
        "matched_ignore": matched_ignore,
        "factors": factors,
        "llm_reasoning": row.get("why_relevant", ""),
        "devils_advocate": row.get("devils_advocate", ""),
        "exploration_tags": exploration,
    }
