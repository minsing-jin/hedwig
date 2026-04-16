"""
Local SQLite storage backend — zero-setup alternative to Supabase.

Use when HEDWIG_STORAGE=sqlite (default when SUPABASE_URL is empty).
Mirrors the supabase.py public API so callers don't need to change.
Data lives in a single file (default: ~/.hedwig/hedwig.db).
"""
from __future__ import annotations

import json
import logging
import os
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from hedwig.models import (
    CriteriaVersion,
    EvolutionLog,
    Feedback,
    ScoredSignal,
    UserMemory,
)

logger = logging.getLogger(__name__)

DEFAULT_DB_PATH = Path(os.getenv("HEDWIG_DB_PATH", str(Path.home() / ".hedwig" / "hedwig.db")))


def _db_path() -> Path:
    p = Path(os.getenv("HEDWIG_DB_PATH", str(DEFAULT_DB_PATH)))
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(str(_db_path()))
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Create all required tables if they don't exist."""
    with _conn() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS signals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            platform TEXT NOT NULL,
            external_id TEXT NOT NULL,
            title TEXT NOT NULL,
            url TEXT,
            content TEXT,
            author TEXT,
            platform_score INTEGER DEFAULT 0,
            comments_count INTEGER DEFAULT 0,
            published_at TEXT,
            relevance_score REAL DEFAULT 0,
            urgency TEXT DEFAULT 'skip',
            why_relevant TEXT,
            devils_advocate TEXT,
            opportunity_note TEXT,
            exploration_tags TEXT DEFAULT '[]',
            extra TEXT DEFAULT '{}',
            collected_at TEXT DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(platform, external_id)
        );

        CREATE TABLE IF NOT EXISTS feedback (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            signal_id TEXT NOT NULL,
            vote TEXT NOT NULL CHECK (vote IN ('up', 'down')),
            natural_language TEXT,
            source_channel TEXT DEFAULT '',
            captured_at TEXT DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS evolution_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cycle_type TEXT NOT NULL,
            cycle_number INTEGER NOT NULL,
            criteria_version_before INTEGER,
            criteria_version_after INTEGER,
            mutations_applied TEXT DEFAULT '[]',
            fitness_before REAL,
            fitness_after REAL,
            kept INTEGER DEFAULT 1,
            analysis_summary TEXT,
            timestamp TEXT DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS criteria_versions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            version INTEGER NOT NULL UNIQUE,
            criteria TEXT NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            created_by TEXT DEFAULT 'system',
            diff_from_previous TEXT,
            fitness_score REAL
        );

        CREATE TABLE IF NOT EXISTS user_memory (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            snapshot_week TEXT NOT NULL,
            confirmed_interests TEXT DEFAULT '[]',
            rejected_topics TEXT DEFAULT '[]',
            taste_trajectory TEXT,
            context TEXT DEFAULT '{}',
            natural_language_feedback TEXT DEFAULT '[]',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );

        CREATE INDEX IF NOT EXISTS idx_signals_collected ON signals(collected_at DESC);
        CREATE INDEX IF NOT EXISTS idx_signals_relevance ON signals(relevance_score DESC);
        CREATE INDEX IF NOT EXISTS idx_feedback_captured ON feedback(captured_at DESC);
        """)


def _now() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Signals
# ---------------------------------------------------------------------------

def save_signals(signals: list[ScoredSignal], user_id: str | None = None) -> int:
    if not signals:
        return 0
    init_db()
    saved = 0
    with _conn() as conn:
        for s in signals:
            try:
                conn.execute("""
                    INSERT OR REPLACE INTO signals (
                        platform, external_id, title, url, content, author,
                        platform_score, comments_count, published_at,
                        relevance_score, urgency, why_relevant, devils_advocate,
                        opportunity_note, exploration_tags, extra, collected_at
                    ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """, (
                    s.raw.platform.value,
                    s.raw.external_id,
                    s.raw.title,
                    s.raw.url,
                    s.raw.content[:5000],
                    s.raw.author,
                    s.raw.score,
                    s.raw.comments_count,
                    s.raw.published_at.isoformat(),
                    s.relevance_score,
                    s.urgency.value,
                    s.why_relevant,
                    s.devils_advocate,
                    s.opportunity_note,
                    json.dumps(s.exploration_tags),
                    json.dumps(s.raw.extra),
                    _now(),
                ))
                saved += 1
            except Exception as e:
                logger.warning(f"Failed to save signal: {e}")
    return saved


def get_recent_signals(days: int = 7) -> list[dict]:
    init_db()
    cutoff = (datetime.now(tz=timezone.utc) - timedelta(days=days)).isoformat()
    with _conn() as conn:
        rows = conn.execute("""
            SELECT * FROM signals
            WHERE collected_at >= ?
            ORDER BY relevance_score DESC
            LIMIT 200
        """, (cutoff,)).fetchall()
        return [dict(r) for r in rows]


def get_latest_signals(limit: int = 100) -> list[dict]:
    if limit <= 0:
        return []
    init_db()
    with _conn() as conn:
        rows = conn.execute("""
            SELECT id, platform, title, url, content, author,
                   relevance_score, urgency, published_at, collected_at
            FROM signals
            ORDER BY collected_at DESC
            LIMIT ?
        """, (limit,)).fetchall()
        return [dict(r) for r in rows]


def search_signals(query: str, limit: int = 100) -> list[dict]:
    q = query.strip()
    if not q or limit <= 0:
        return []
    init_db()
    pattern = f"%{q}%"
    with _conn() as conn:
        rows = conn.execute("""
            SELECT id, platform, title, url, content, author,
                   relevance_score, urgency, published_at, collected_at
            FROM signals
            WHERE title LIKE ? OR content LIKE ?
            ORDER BY collected_at DESC
            LIMIT ?
        """, (pattern, pattern, limit)).fetchall()
        return [dict(r) for r in rows]


def is_duplicate(platform: str, external_id: str) -> bool:
    init_db()
    with _conn() as conn:
        row = conn.execute(
            "SELECT 1 FROM signals WHERE platform = ? AND external_id = ? LIMIT 1",
            (platform, external_id),
        ).fetchone()
        return row is not None


# ---------------------------------------------------------------------------
# Feedback
# ---------------------------------------------------------------------------

def save_feedback(feedback: Feedback) -> bool:
    init_db()
    try:
        with _conn() as conn:
            conn.execute("""
                INSERT INTO feedback (signal_id, vote, natural_language, source_channel, captured_at)
                VALUES (?,?,?,?,?)
            """, (
                feedback.signal_id,
                feedback.vote.value,
                feedback.natural_language,
                feedback.source_channel,
                feedback.captured_at.isoformat(),
            ))
        return True
    except Exception as e:
        logger.error(f"save_feedback: {e}")
        return False


async def save_feedback_batch(feedbacks: list[Feedback]) -> int:
    if not feedbacks:
        return 0
    saved = 0
    for f in feedbacks:
        if save_feedback(f):
            saved += 1
    return saved


def get_feedback_since(days: int = 1) -> list[dict]:
    init_db()
    cutoff = (datetime.now(tz=timezone.utc) - timedelta(days=days)).isoformat()
    with _conn() as conn:
        rows = conn.execute(
            "SELECT * FROM feedback WHERE captured_at >= ?",
            (cutoff,),
        ).fetchall()
        return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Evolution logs
# ---------------------------------------------------------------------------

def save_evolution_log(log: EvolutionLog) -> bool:
    init_db()
    try:
        with _conn() as conn:
            conn.execute("""
                INSERT INTO evolution_logs (
                    cycle_type, cycle_number, criteria_version_before, criteria_version_after,
                    mutations_applied, fitness_before, fitness_after, kept, analysis_summary, timestamp
                ) VALUES (?,?,?,?,?,?,?,?,?,?)
            """, (
                log.cycle_type.value,
                log.cycle_number,
                log.criteria_version_before,
                log.criteria_version_after,
                json.dumps(log.mutations_applied),
                log.fitness_before,
                log.fitness_after,
                1 if log.kept else 0,
                log.analysis_summary,
                log.timestamp.isoformat(),
            ))
        return True
    except Exception as e:
        logger.error(f"save_evolution_log: {e}")
        return False


# ---------------------------------------------------------------------------
# Criteria versions
# ---------------------------------------------------------------------------

def save_criteria_version(cv: CriteriaVersion) -> bool:
    init_db()
    try:
        with _conn() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO criteria_versions (
                    version, criteria, created_at, created_by, diff_from_previous, fitness_score
                ) VALUES (?,?,?,?,?,?)
            """, (
                cv.version,
                json.dumps(cv.criteria),
                cv.created_at.isoformat(),
                cv.created_by,
                cv.diff_from_previous,
                cv.fitness_score,
            ))
        return True
    except Exception as e:
        logger.error(f"save_criteria_version: {e}")
        return False


# ---------------------------------------------------------------------------
# User memory
# ---------------------------------------------------------------------------

def save_user_memory(memory: UserMemory) -> bool:
    init_db()
    try:
        with _conn() as conn:
            conn.execute("""
                INSERT INTO user_memory (
                    snapshot_week, confirmed_interests, rejected_topics,
                    taste_trajectory, context, natural_language_feedback, created_at
                ) VALUES (?,?,?,?,?,?,?)
            """, (
                memory.snapshot_week,
                json.dumps(memory.confirmed_interests),
                json.dumps(memory.rejected_topics),
                memory.taste_trajectory,
                json.dumps(memory.context),
                json.dumps(memory.natural_language_feedback),
                memory.created_at.isoformat(),
            ))
        return True
    except Exception as e:
        logger.error(f"save_user_memory: {e}")
        return False


# ---------------------------------------------------------------------------
# SaaS subscription persistence
# ---------------------------------------------------------------------------

def save_subscription_update(
    *,
    user_id: str | None = None,
    tier: str | None = None,
    stripe_customer_id: str | None = None,
    stripe_subscription_id: str | None = None,
    status: str | None = None,
    current_period_end: object | None = None,
    cancel_at_period_end: bool | None = None,
) -> bool:
    """SQLite stub for SaaS subscription updates in local mode."""
    return True


# ---------------------------------------------------------------------------
# Dashboard stats (single-user, no user scoping)
# ---------------------------------------------------------------------------

def get_dashboard_activity_stats(user_id: str | None = None) -> dict:
    """Return stats for /dashboard/stats endpoint. Ignores user_id in local mode."""
    init_db()
    with _conn() as conn:
        total = conn.execute("SELECT COUNT(*) FROM signals").fetchone()[0] or 0
        ups = conn.execute("SELECT COUNT(*) FROM feedback WHERE vote = 'up'").fetchone()[0] or 0
        downs = conn.execute("SELECT COUNT(*) FROM feedback WHERE vote = 'down'").fetchone()[0] or 0
        evo = conn.execute("SELECT COUNT(*) FROM evolution_logs").fetchone()[0] or 0
        top = conn.execute("""
            SELECT platform, COUNT(*) as cnt FROM signals
            GROUP BY platform ORDER BY cnt DESC LIMIT 5
        """).fetchall()
        first = conn.execute("SELECT MIN(collected_at) FROM signals").fetchone()[0]

    upvote_ratio = ups / max(ups + downs, 1) if (ups + downs) else 0.0
    days_active = 0
    if first:
        try:
            first_dt = datetime.fromisoformat(first.replace("Z", "+00:00")) if "T" in first else datetime.fromisoformat(first)
            if first_dt.tzinfo is None:
                first_dt = first_dt.replace(tzinfo=timezone.utc)
            days_active = max(1, (datetime.now(tz=timezone.utc) - first_dt).days)
        except Exception:
            days_active = 0

    return {
        "total_signals": total,
        "upvote_ratio": round(upvote_ratio, 3),
        "evolution_cycles": evo,
        "top_5_sources": [{"platform": r[0], "count": r[1]} for r in top],
        "days_active": days_active,
    }
