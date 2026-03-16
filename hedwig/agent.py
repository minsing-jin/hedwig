"""
Hedwig Agent Interface

Agent-friendly entry point for AI agents (OpenClaw, Codex, Claude Code, etc.)
to use Hedwig as a tool.

Usage:
    # CLI: returns JSON to stdout
    python -m hedwig.agent                     # Collect + score all
    python -m hedwig.agent --source hackernews  # Single source
    python -m hedwig.agent --top 10            # Top N signals only
    python -m hedwig.agent --briefing daily     # Generate briefing text
    python -m hedwig.agent --raw               # Raw posts (no scoring)

    # Python API:
    from hedwig.agent import collect, score, briefing, pipeline
    signals = await pipeline(top=10)
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import datetime, timezone

from hedwig.models import Platform, RawPost, ScoredSignal


async def collect(sources: list[str] | None = None) -> list[dict]:
    """Collect raw posts from specified sources (or all).

    Returns list of dicts (JSON-serializable).
    """
    from hedwig.sources.geeknews import GeekNewsSource
    from hedwig.sources.hackernews import HackerNewsSource
    from hedwig.sources.linkedin import LinkedInSource
    from hedwig.sources.reddit import RedditSource
    from hedwig.sources.threads import ThreadsSource
    from hedwig.sources.twitter import TwitterSource

    source_map = {
        "hackernews": HackerNewsSource,
        "reddit": RedditSource,
        "geeknews": GeekNewsSource,
        "twitter": TwitterSource,
        "linkedin": LinkedInSource,
        "threads": ThreadsSource,
    }

    active = sources or list(source_map.keys())
    all_posts: list[RawPost] = []

    for name in active:
        if name not in source_map:
            continue
        try:
            src = source_map[name]()
            posts = await src.fetch()
            all_posts.extend(posts)
        except Exception:
            continue

    return [_post_to_dict(p) for p in all_posts]


async def score(posts_dicts: list[dict] | None = None, top: int = 0) -> list[dict]:
    """Score posts with LLM. If posts_dicts is None, collects first.

    Returns list of scored signal dicts, sorted by relevance.
    """
    from hedwig.engine.scorer import score_posts

    if posts_dicts is None:
        posts_dicts = await collect()

    posts = [_dict_to_post(d) for d in posts_dicts]
    scored = await score_posts(posts)
    scored.sort(key=lambda s: s.relevance_score, reverse=True)

    if top > 0:
        scored = scored[:top]

    return [_signal_to_dict(s) for s in scored]


async def briefing(kind: str = "daily") -> str:
    """Generate a briefing. kind: 'daily' or 'weekly'."""
    from hedwig.engine.briefing import generate_daily_briefing, generate_weekly_briefing

    signals_dicts = await score(top=25)
    signals = [_dict_to_signal(d) for d in signals_dicts]

    if kind == "weekly":
        return await generate_weekly_briefing(signals)
    return await generate_daily_briefing(signals)


async def pipeline(
    sources: list[str] | None = None,
    top: int = 20,
    include_raw: bool = False,
) -> list[dict]:
    """Full pipeline: collect → score → return top N signals as dicts.

    This is the main function for agent integration.
    """
    posts = await collect(sources)
    scored = await score(posts, top=top)

    if not include_raw:
        for s in scored:
            s.pop("raw_content", None)

    return scored


# --- Serialization helpers ---

def _post_to_dict(p: RawPost) -> dict:
    return {
        "platform": p.platform.value,
        "external_id": p.external_id,
        "title": p.title,
        "url": p.url,
        "content": p.content[:1000],
        "author": p.author,
        "score": p.score,
        "comments_count": p.comments_count,
        "published_at": p.published_at.isoformat(),
        "extra": p.extra,
    }


def _dict_to_post(d: dict) -> RawPost:
    return RawPost(
        platform=Platform(d["platform"]),
        external_id=d["external_id"],
        title=d["title"],
        url=d.get("url", ""),
        content=d.get("content", ""),
        author=d.get("author", ""),
        score=d.get("score", 0),
        comments_count=d.get("comments_count", 0),
        published_at=datetime.fromisoformat(d["published_at"]) if d.get("published_at") else datetime.now(tz=timezone.utc),
        extra=d.get("extra", {}),
    )


def _signal_to_dict(s: ScoredSignal) -> dict:
    return {
        "platform": s.raw.platform.value,
        "title": s.raw.title,
        "url": s.raw.url,
        "author": s.raw.author,
        "relevance_score": s.relevance_score,
        "urgency": s.urgency.value,
        "why_relevant": s.why_relevant,
        "devils_advocate": s.devils_advocate,
        "opportunity_note": s.opportunity_note,
        "platform_score": s.raw.score,
        "comments_count": s.raw.comments_count,
        "published_at": s.raw.published_at.isoformat(),
        "raw_content": s.raw.content[:500],
    }


def _dict_to_signal(d: dict) -> ScoredSignal:
    from hedwig.models import UrgencyLevel
    raw = RawPost(
        platform=Platform(d["platform"]),
        external_id=d.get("url", ""),
        title=d["title"],
        url=d.get("url", ""),
        author=d.get("author", ""),
        score=d.get("platform_score", 0),
        comments_count=d.get("comments_count", 0),
    )
    return ScoredSignal(
        raw=raw,
        relevance_score=d.get("relevance_score", 0),
        urgency=UrgencyLevel(d.get("urgency", "digest")),
        why_relevant=d.get("why_relevant", ""),
        devils_advocate=d.get("devils_advocate", ""),
        opportunity_note=d.get("opportunity_note", ""),
    )


def main():
    parser = argparse.ArgumentParser(description="Hedwig Agent Interface")
    parser.add_argument("--source", type=str, help="Single source: hackernews, reddit, geeknews, twitter, linkedin, threads")
    parser.add_argument("--top", type=int, default=20, help="Return top N signals (default: 20)")
    parser.add_argument("--raw", action="store_true", help="Raw posts only (no LLM scoring)")
    parser.add_argument("--briefing", type=str, choices=["daily", "weekly"], help="Generate briefing text")
    args = parser.parse_args()

    if args.briefing:
        result = asyncio.run(briefing(args.briefing))
        print(result)
    elif args.raw:
        sources = [args.source] if args.source else None
        result = asyncio.run(collect(sources))
        print(json.dumps(result[:args.top], ensure_ascii=False, indent=2))
    else:
        sources = [args.source] if args.source else None
        result = asyncio.run(pipeline(sources=sources, top=args.top))
        print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
