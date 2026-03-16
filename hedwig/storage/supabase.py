from __future__ import annotations

import logging
from datetime import datetime, timezone

from supabase import create_client

from hedwig.config import SUPABASE_KEY, SUPABASE_URL
from hedwig.models import Feedback, ScoredSignal

logger = logging.getLogger(__name__)


def _get_client():
    return create_client(SUPABASE_URL, SUPABASE_KEY)


def save_signals(signals: list[ScoredSignal]) -> int:
    """Save scored signals to Supabase. Returns count saved."""
    if not signals:
        return 0

    client = _get_client()
    rows = []
    for s in signals:
        rows.append({
            "platform": s.raw.platform.value,
            "external_id": s.raw.external_id,
            "title": s.raw.title,
            "url": s.raw.url,
            "content": s.raw.content[:5000],
            "author": s.raw.author,
            "platform_score": s.raw.score,
            "comments_count": s.raw.comments_count,
            "published_at": s.raw.published_at.isoformat(),
            "relevance_score": s.relevance_score,
            "urgency": s.urgency.value,
            "why_relevant": s.why_relevant,
            "devils_advocate": s.devils_advocate,
            "opportunity_note": s.opportunity_note,
            "extra": s.raw.extra,
            "collected_at": datetime.now(tz=timezone.utc).isoformat(),
        })

    try:
        result = client.table("signals").upsert(
            rows, on_conflict="platform,external_id"
        ).execute()
        return len(result.data) if result.data else 0
    except Exception as e:
        logger.error(f"Failed to save signals: {e}")
        return 0


def save_feedback(feedback: Feedback) -> bool:
    """Save user feedback from Slack."""
    client = _get_client()
    try:
        client.table("feedback").insert({
            "signal_id": feedback.signal_id,
            "reaction_type": feedback.reaction_type,
            "content": feedback.content,
            "sentiment": feedback.sentiment,
            "captured_at": feedback.captured_at.isoformat(),
        }).execute()
        return True
    except Exception as e:
        logger.error(f"Failed to save feedback: {e}")
        return False


def get_recent_signals(days: int = 7) -> list[dict]:
    """Get signals from the last N days for weekly briefing."""
    client = _get_client()
    cutoff = datetime.now(tz=timezone.utc).isoformat()
    try:
        result = (
            client.table("signals")
            .select("*")
            .gte("collected_at", cutoff)
            .order("relevance_score", desc=True)
            .limit(100)
            .execute()
        )
        return result.data or []
    except Exception as e:
        logger.error(f"Failed to get recent signals: {e}")
        return []


def is_duplicate(platform: str, external_id: str) -> bool:
    """Check if a signal has already been collected."""
    client = _get_client()
    try:
        result = (
            client.table("signals")
            .select("id")
            .eq("platform", platform)
            .eq("external_id", external_id)
            .limit(1)
            .execute()
        )
        return bool(result.data)
    except Exception:
        return False


# SQL to create tables in Supabase:
SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS signals (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    platform TEXT NOT NULL,
    external_id TEXT NOT NULL,
    title TEXT NOT NULL,
    url TEXT,
    content TEXT,
    author TEXT,
    platform_score INTEGER DEFAULT 0,
    comments_count INTEGER DEFAULT 0,
    published_at TIMESTAMPTZ,
    relevance_score FLOAT DEFAULT 0,
    urgency TEXT DEFAULT 'skip',
    why_relevant TEXT,
    devils_advocate TEXT,
    opportunity_note TEXT,
    extra JSONB DEFAULT '{}',
    collected_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(platform, external_id)
);

CREATE TABLE IF NOT EXISTS feedback (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    signal_id TEXT NOT NULL,
    reaction_type TEXT NOT NULL,
    content TEXT,
    sentiment TEXT,
    captured_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_signals_collected ON signals(collected_at DESC);
CREATE INDEX IF NOT EXISTS idx_signals_relevance ON signals(relevance_score DESC);
CREATE INDEX IF NOT EXISTS idx_signals_platform ON signals(platform);
"""
