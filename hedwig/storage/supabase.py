from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from supabase import create_client

from hedwig.config import SUPABASE_KEY, SUPABASE_URL
from hedwig.models import (
    CriteriaVersion,
    EvolutionLog,
    Feedback,
    ScoredSignal,
    UserMemory,
    VoteType,
)

logger = logging.getLogger(__name__)

SIGNAL_EXPORT_FIELDS = (
    "id",
    "platform",
    "title",
    "url",
    "content",
    "author",
    "relevance_score",
    "urgency",
    "published_at",
    "collected_at",
)
SIGNAL_EXPORT_SELECT = ",".join(SIGNAL_EXPORT_FIELDS)


def _get_client():
    return create_client(SUPABASE_URL, SUPABASE_KEY)


# ---------------------------------------------------------------------------
# Signals
# ---------------------------------------------------------------------------

def save_signals(signals: list[ScoredSignal]) -> int:
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
            "exploration_tags": s.exploration_tags,
            "extra": s.raw.extra,
            "collected_at": datetime.now(tz=timezone.utc).isoformat(),
        })
    try:
        result = client.table("signals").upsert(rows, on_conflict="platform,external_id").execute()
        return len(result.data) if result.data else 0
    except Exception as e:
        logger.error(f"Failed to save signals: {e}")
        return 0


def get_recent_signals(days: int = 7) -> list[dict]:
    client = _get_client()
    cutoff = (datetime.now(tz=timezone.utc) - timedelta(days=days)).isoformat()
    try:
        result = (
            client.table("signals")
            .select("*")
            .gte("collected_at", cutoff)
            .order("relevance_score", desc=True)
            .limit(200)
            .execute()
        )
        return result.data or []
    except Exception as e:
        logger.error(f"Failed to get recent signals: {e}")
        return []


def get_latest_signals(limit: int = 100) -> list[dict]:
    if limit <= 0:
        return []

    client = _get_client()
    try:
        result = (
            client.table("signals")
            .select(SIGNAL_EXPORT_SELECT)
            .order("collected_at", desc=True)
            .limit(limit)
            .execute()
        )
        return result.data or []
    except Exception as e:
        logger.error(f"Failed to get latest signals: {e}")
        return []


def is_duplicate(platform: str, external_id: str) -> bool:
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


# ---------------------------------------------------------------------------
# Feedback (v2: boolean + natural language)
# ---------------------------------------------------------------------------

def save_feedback(feedback: Feedback) -> bool:
    client = _get_client()
    try:
        client.table("feedback").insert({
            "signal_id": feedback.signal_id,
            "vote": feedback.vote.value,
            "natural_language": feedback.natural_language,
            "source_channel": feedback.source_channel,
            "captured_at": feedback.captured_at.isoformat(),
        }).execute()
        return True
    except Exception as e:
        logger.error(f"Failed to save feedback: {e}")
        return False


async def save_feedback_batch(feedbacks: list[Feedback]) -> int:
    if not feedbacks:
        return 0
    client = _get_client()
    rows = [{
        "signal_id": f.signal_id,
        "vote": f.vote.value,
        "natural_language": f.natural_language,
        "source_channel": f.source_channel,
        "captured_at": f.captured_at.isoformat(),
    } for f in feedbacks]
    try:
        result = client.table("feedback").insert(rows).execute()
        return len(result.data) if result.data else 0
    except Exception as e:
        logger.error(f"Failed to save feedback batch: {e}")
        return 0


def get_feedback_since(days: int = 1) -> list[dict]:
    client = _get_client()
    cutoff = (datetime.now(tz=timezone.utc) - timedelta(days=days)).isoformat()
    try:
        result = (
            client.table("feedback")
            .select("*")
            .gte("captured_at", cutoff)
            .execute()
        )
        return result.data or []
    except Exception as e:
        logger.error(f"Failed to get feedback: {e}")
        return []


# ---------------------------------------------------------------------------
# Evolution logs
# ---------------------------------------------------------------------------

def save_evolution_log(log: EvolutionLog) -> bool:
    client = _get_client()
    try:
        client.table("evolution_logs").insert({
            "cycle_type": log.cycle_type.value,
            "cycle_number": log.cycle_number,
            "criteria_version_before": log.criteria_version_before,
            "criteria_version_after": log.criteria_version_after,
            "mutations_applied": log.mutations_applied,
            "fitness_before": log.fitness_before,
            "fitness_after": log.fitness_after,
            "kept": log.kept,
            "analysis_summary": log.analysis_summary,
            "timestamp": log.timestamp.isoformat(),
        }).execute()
        return True
    except Exception as e:
        logger.error(f"Failed to save evolution log: {e}")
        return False


# ---------------------------------------------------------------------------
# Criteria versions
# ---------------------------------------------------------------------------

def save_criteria_version(cv: CriteriaVersion) -> bool:
    client = _get_client()
    try:
        client.table("criteria_versions").insert({
            "version": cv.version,
            "criteria": cv.criteria,
            "created_at": cv.created_at.isoformat(),
            "created_by": cv.created_by,
            "diff_from_previous": cv.diff_from_previous,
            "fitness_score": cv.fitness_score,
        }).execute()
        return True
    except Exception as e:
        logger.error(f"Failed to save criteria version: {e}")
        return False


# ---------------------------------------------------------------------------
# User memory
# ---------------------------------------------------------------------------

def save_user_memory(memory: UserMemory) -> bool:
    client = _get_client()
    try:
        client.table("user_memory").insert({
            "snapshot_week": memory.snapshot_week,
            "confirmed_interests": memory.confirmed_interests,
            "rejected_topics": memory.rejected_topics,
            "taste_trajectory": memory.taste_trajectory,
            "context": memory.context,
            "natural_language_feedback": memory.natural_language_feedback,
            "created_at": memory.created_at.isoformat(),
        }).execute()
        return True
    except Exception as e:
        logger.error(f"Failed to save user memory: {e}")
        return False


# ---------------------------------------------------------------------------
# Schema SQL — run in Supabase SQL editor
# ---------------------------------------------------------------------------

SCHEMA_SQL = """
-- Signals (extended with exploration_tags)
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
    exploration_tags JSONB DEFAULT '[]',
    extra JSONB DEFAULT '{}',
    collected_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(platform, external_id)
);

-- Feedback (v2: boolean vote + natural language)
CREATE TABLE IF NOT EXISTS feedback (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    signal_id TEXT NOT NULL,
    vote TEXT NOT NULL CHECK (vote IN ('up', 'down')),
    natural_language TEXT,
    source_channel TEXT DEFAULT '',
    captured_at TIMESTAMPTZ DEFAULT NOW()
);

-- Evolution logs
CREATE TABLE IF NOT EXISTS evolution_logs (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    cycle_type TEXT NOT NULL CHECK (cycle_type IN ('daily', 'weekly')),
    cycle_number INTEGER NOT NULL,
    criteria_version_before INTEGER,
    criteria_version_after INTEGER,
    mutations_applied JSONB DEFAULT '[]',
    fitness_before FLOAT,
    fitness_after FLOAT,
    kept BOOLEAN DEFAULT TRUE,
    analysis_summary TEXT,
    timestamp TIMESTAMPTZ DEFAULT NOW()
);

-- Criteria version history
CREATE TABLE IF NOT EXISTS criteria_versions (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    version INTEGER NOT NULL UNIQUE,
    criteria JSONB NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    created_by TEXT DEFAULT 'system',
    diff_from_previous TEXT,
    fitness_score FLOAT
);

-- User memory (long-horizon preference model)
CREATE TABLE IF NOT EXISTS user_memory (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    snapshot_week TEXT NOT NULL,
    confirmed_interests JSONB DEFAULT '[]',
    rejected_topics JSONB DEFAULT '[]',
    taste_trajectory TEXT,
    context JSONB DEFAULT '{}',
    natural_language_feedback JSONB DEFAULT '[]',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_signals_collected ON signals(collected_at DESC);
CREATE INDEX IF NOT EXISTS idx_signals_relevance ON signals(relevance_score DESC);
CREATE INDEX IF NOT EXISTS idx_signals_platform ON signals(platform);
CREATE INDEX IF NOT EXISTS idx_feedback_captured ON feedback(captured_at DESC);
CREATE INDEX IF NOT EXISTS idx_feedback_signal ON feedback(signal_id);
CREATE INDEX IF NOT EXISTS idx_evolution_timestamp ON evolution_logs(timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_criteria_version ON criteria_versions(version DESC);
CREATE INDEX IF NOT EXISTS idx_memory_week ON user_memory(snapshot_week);
"""
