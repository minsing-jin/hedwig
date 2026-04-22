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

        CREATE TABLE IF NOT EXISTS run_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cycle_type TEXT NOT NULL CHECK (cycle_type IN ('daily', 'weekly')),
            run_at TEXT DEFAULT CURRENT_TIMESTAMP
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

        CREATE TABLE IF NOT EXISTS source_reliability (
            platform TEXT PRIMARY KEY,
            reliability_score REAL NOT NULL,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        );

        -- v3: Triple-input evolution signals (explicit/semi/implicit unified stream)
        CREATE TABLE IF NOT EXISTS evolution_signal (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            channel TEXT NOT NULL CHECK (channel IN ('explicit','semi','implicit')),
            kind TEXT NOT NULL,        -- e.g. 'criteria_edit','qa_accept','qa_reject','upvote','downvote'
            payload TEXT DEFAULT '{}', -- JSON blob with details (question, signal_id, diff, etc.)
            weight REAL DEFAULT 1.0,   -- meta-evolution can tune how heavily each kind counts
            captured_at TEXT DEFAULT CURRENT_TIMESTAMP
        );

        -- v3: Algorithm config version history (peer to criteria_versions)
        CREATE TABLE IF NOT EXISTS algorithm_versions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            version INTEGER NOT NULL UNIQUE,
            config TEXT NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            created_by TEXT DEFAULT 'system',
            diff_from_previous TEXT,
            fitness_score REAL,
            origin TEXT DEFAULT 'manual'   -- manual | meta_evolution | paper_absorb
        );

        CREATE INDEX IF NOT EXISTS idx_signals_collected ON signals(collected_at DESC);
        CREATE INDEX IF NOT EXISTS idx_signals_relevance ON signals(relevance_score DESC);
        CREATE INDEX IF NOT EXISTS idx_feedback_captured ON feedback(captured_at DESC);
        CREATE INDEX IF NOT EXISTS idx_run_history_run_at ON run_history(run_at DESC);
        CREATE INDEX IF NOT EXISTS idx_run_history_cycle_type ON run_history(cycle_type);
        CREATE INDEX IF NOT EXISTS idx_source_reliability_updated_at ON source_reliability(updated_at DESC);
        CREATE INDEX IF NOT EXISTS idx_evolution_signal_captured ON evolution_signal(captured_at DESC);
        CREATE INDEX IF NOT EXISTS idx_evolution_signal_channel ON evolution_signal(channel);
        CREATE INDEX IF NOT EXISTS idx_algorithm_versions_created ON algorithm_versions(created_at DESC);
        """)


def _now() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


def _coerce_timestamp(value: object) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        parsed = value
    else:
        text = str(value).strip()
        if not text:
            return None
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            return None

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _empty_run_stats() -> dict[str, object]:
    return {
        "consecutive_daily_runs": 0,
        "total_daily_cycles": 0,
        "total_weekly_cycles": 0,
        "last_daily_at": None,
        "last_weekly_at": None,
    }


def _summarize_run_rows(rows: list[dict]) -> dict[str, object]:
    stats = _empty_run_stats()
    daily_times: list[datetime] = []
    weekly_times: list[datetime] = []

    for row in rows:
        cycle_type = str(row.get("cycle_type") or "").strip().lower()
        run_at = _coerce_timestamp(row.get("run_at"))
        if run_at is None:
            continue
        if cycle_type == "daily":
            daily_times.append(run_at)
        elif cycle_type == "weekly":
            weekly_times.append(run_at)

    if daily_times:
        stats["total_daily_cycles"] = len(daily_times)
        stats["last_daily_at"] = max(daily_times).isoformat()

        streak = 0
        expected_day = None
        for run_day in sorted({run_at.date() for run_at in daily_times}, reverse=True):
            if expected_day is None or run_day == expected_day:
                streak += 1
                expected_day = run_day - timedelta(days=1)
                continue
            break
        stats["consecutive_daily_runs"] = streak

    if weekly_times:
        stats["total_weekly_cycles"] = len(weekly_times)
        stats["last_weekly_at"] = max(weekly_times).isoformat()

    return stats


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


def get_signal_platforms(signal_ids: list[str]) -> dict[str, str]:
    """Resolve signal ids or external ids to their source platform."""
    normalized_ids = sorted({str(signal_id).strip() for signal_id in signal_ids if str(signal_id).strip()})
    if not normalized_ids:
        return {}

    init_db()
    placeholders = ",".join("?" for _ in normalized_ids)
    query = f"""
        SELECT id, external_id, platform
        FROM signals
        WHERE CAST(id AS TEXT) IN ({placeholders})
           OR external_id IN ({placeholders})
    """

    with _conn() as conn:
        rows = conn.execute(query, normalized_ids + normalized_ids).fetchall()

    mapping: dict[str, str] = {}
    for row in rows:
        platform = str(row["platform"] or "").strip()
        if not platform:
            continue
        signal_id = str(row["id"] or "").strip()
        external_id = str(row["external_id"] or "").strip()
        if signal_id:
            mapping[signal_id] = platform
        if external_id:
            mapping[external_id] = platform
    return mapping


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
        timestamp = _coerce_timestamp(log.timestamp)
        run_at = timestamp.isoformat() if timestamp is not None else _now()
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
                run_at,
            ))
            conn.execute("""
                INSERT INTO run_history (cycle_type, run_at)
                VALUES (?,?)
            """, (
                log.cycle_type.value,
                run_at,
            ))
        return True
    except Exception as e:
        logger.error(f"save_evolution_log: {e}")
        return False


def get_run_stats() -> dict[str, object]:
    init_db()
    with _conn() as conn:
        rows = conn.execute("""
            SELECT cycle_type, run_at
            FROM run_history
            ORDER BY run_at DESC
        """).fetchall()
        if not rows:
            rows = conn.execute("""
                SELECT cycle_type, timestamp AS run_at
                FROM evolution_logs
                ORDER BY timestamp DESC
            """).fetchall()
    return _summarize_run_rows([dict(row) for row in rows])


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


def get_criteria_versions(limit: int = 50) -> list[dict]:
    """Return criteria version rows, newest first."""
    init_db()
    with _conn() as conn:
        rows = conn.execute(
            """SELECT version, created_at, created_by, diff_from_previous, fitness_score
               FROM criteria_versions
               ORDER BY version DESC LIMIT ?""",
            (limit,),
        ).fetchall()
    return [dict(r) for r in rows]


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
# Source reliability
# ---------------------------------------------------------------------------

def save_source_reliability(scores: dict[str, float]) -> bool:
    init_db()
    if not scores:
        return True

    try:
        updated_at = _now()
        with _conn() as conn:
            for platform, score in scores.items():
                platform_name = str(platform or "").strip()
                if not platform_name:
                    continue
                conn.execute("""
                    INSERT INTO source_reliability (platform, reliability_score, updated_at)
                    VALUES (?,?,?)
                    ON CONFLICT(platform) DO UPDATE SET
                        reliability_score = excluded.reliability_score,
                        updated_at = excluded.updated_at
                """, (
                    platform_name,
                    max(0.0, min(1.0, float(score))),
                    updated_at,
                ))
        return True
    except Exception as e:
        logger.error(f"save_source_reliability: {e}")
        return False


def get_source_reliability() -> dict[str, float]:
    init_db()
    try:
        with _conn() as conn:
            rows = conn.execute("""
                SELECT platform, reliability_score
                FROM source_reliability
                ORDER BY updated_at DESC
            """).fetchall()
    except Exception as e:
        logger.error(f"get_source_reliability: {e}")
        return {}

    scores: dict[str, float] = {}
    for row in rows:
        platform = str(row["platform"] or "").strip()
        if not platform:
            continue
        scores[platform] = max(0.0, min(1.0, float(row["reliability_score"])))
    return scores


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


# ---------------------------------------------------------------------------
# Evolution signals — Triple-input unified stream (v3)
# ---------------------------------------------------------------------------

def save_evolution_signal(
    channel: str,
    kind: str,
    payload: dict | None = None,
    weight: float = 1.0,
) -> bool:
    """Record one triple-input feedback event.

    Args:
        channel: 'explicit' | 'semi' | 'implicit'
        kind: event kind (e.g. 'criteria_edit', 'qa_accept', 'upvote')
        payload: free-form JSON details
        weight: optional weighting for meta-evolution
    """
    if channel not in ("explicit", "semi", "implicit"):
        logger.warning("evolution_signal: invalid channel %s", channel)
        return False
    init_db()
    try:
        with _conn() as conn:
            conn.execute(
                """INSERT INTO evolution_signal (channel, kind, payload, weight)
                   VALUES (?,?,?,?)""",
                (channel, kind, json.dumps(payload or {}, ensure_ascii=False), weight),
            )
        return True
    except Exception as e:
        logger.error("save_evolution_signal: %s", e)
        return False


def get_evolution_signals(
    channel: str | None = None,
    since: datetime | None = None,
    limit: int = 200,
) -> list[dict]:
    init_db()
    q = "SELECT * FROM evolution_signal"
    conds = []
    params: list = []
    if channel:
        conds.append("channel = ?")
        params.append(channel)
    if since:
        conds.append("captured_at >= ?")
        params.append(since.astimezone(timezone.utc).isoformat())
    if conds:
        q += " WHERE " + " AND ".join(conds)
    q += " ORDER BY captured_at DESC LIMIT ?"
    params.append(limit)
    with _conn() as conn:
        rows = conn.execute(q, params).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        try:
            d["payload"] = json.loads(d.get("payload") or "{}")
        except Exception:
            d["payload"] = {}
        out.append(d)
    return out


# ---------------------------------------------------------------------------
# Algorithm versions (v3)
# ---------------------------------------------------------------------------

def save_algorithm_version(
    version: int,
    config: dict,
    created_by: str = "system",
    origin: str = "manual",
    diff_from_previous: str | None = None,
    fitness_score: float | None = None,
) -> bool:
    init_db()
    try:
        with _conn() as conn:
            conn.execute(
                """INSERT OR REPLACE INTO algorithm_versions
                   (version, config, created_by, diff_from_previous, fitness_score, origin)
                   VALUES (?,?,?,?,?,?)""",
                (
                    version,
                    json.dumps(config, ensure_ascii=False),
                    created_by,
                    diff_from_previous,
                    fitness_score,
                    origin,
                ),
            )
        return True
    except Exception as e:
        logger.error("save_algorithm_version: %s", e)
        return False


def get_algorithm_history(limit: int = 50) -> list[dict]:
    init_db()
    with _conn() as conn:
        # Order by version DESC (tiebreak on id DESC) so newer adoptions beat
        # same-timestamp seed rows that the default CURRENT_TIMESTAMP shares.
        rows = conn.execute(
            """SELECT version, created_at, created_by, origin, fitness_score,
                      diff_from_previous
               FROM algorithm_versions
               ORDER BY version DESC, id DESC LIMIT ?""",
            (limit,),
        ).fetchall()
    return [dict(r) for r in rows]
