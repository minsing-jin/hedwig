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


def _table_columns(conn: sqlite3.Connection, table_name: str) -> set[str]:
    return {
        str(row[1])
        for row in conn.execute(f"PRAGMA table_info({table_name})").fetchall()
    }


def _ensure_column(
    conn: sqlite3.Connection,
    table_name: str,
    column_name: str,
    column_definition: str,
) -> None:
    if column_name in _table_columns(conn, table_name):
        return
    conn.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_definition}")


def _run_schema_migrations(conn: sqlite3.Connection) -> None:
    """Idempotently add columns introduced after the first SQLite schema."""
    migrations = (
        ("feedback", "attribution", "attribution TEXT DEFAULT NULL"),
        (
            "feedback",
            "delivered_signal_id",
            "delivered_signal_id INTEGER DEFAULT NULL",
        ),
        ("evolution_logs", "scope", "scope TEXT DEFAULT NULL"),
        ("evolution_logs", "axis", "axis TEXT DEFAULT NULL"),
        ("evolution_logs", "inputs", "inputs TEXT DEFAULT '{}'"),
        ("evolution_logs", "outputs", "outputs TEXT DEFAULT '{}'"),
        (
            "evolution_logs",
            "evaluator_verdict",
            "evaluator_verdict TEXT DEFAULT NULL",
        ),
        ("briefings", "structured", "structured TEXT DEFAULT '{}'"),
        ("signals", "judgment_id", "judgment_id INTEGER DEFAULT NULL"),
        ("behavior_events", "feed_mode", "feed_mode TEXT DEFAULT 'grid'"),
        ("behavior_rewards", "polarity", "polarity TEXT DEFAULT 'neutral'"),
        (
            "behavior_rewards",
            "strength_class",
            "strength_class TEXT DEFAULT 'weak'",
        ),
        ("behavior_rewards", "confidence", "confidence REAL DEFAULT 0.0"),
        (
            "behavior_rewards",
            "uncertainty_reason",
            "uncertainty_reason TEXT DEFAULT ''",
        ),
        (
            "behavior_rewards",
            "derivation_rule_version",
            "derivation_rule_version TEXT DEFAULT 'personal_algorithm_reward_v1'",
        ),
        (
            "behavior_rewards",
            "source_event_ids",
            "source_event_ids TEXT DEFAULT '[]'",
        ),
        ("behavior_rewards", "policy_version", "policy_version INTEGER DEFAULT 1"),
        ("behavior_rewards", "feed_mode", "feed_mode TEXT DEFAULT 'grid'"),
        ("behavior_rewards", "source", "source TEXT DEFAULT 'personal_algorithm'"),
    )
    for table_name, column_name, column_definition in migrations:
        _ensure_column(conn, table_name, column_name, column_definition)


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

        CREATE TABLE IF NOT EXISTS collection_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_type TEXT NOT NULL DEFAULT 'daily',
            status TEXT NOT NULL DEFAULT 'queued',
            posts_collected INTEGER DEFAULT 0,
            posts_filtered INTEGER DEFAULT 0,
            signals_scored INTEGER DEFAULT 0,
            signals_saved INTEGER DEFAULT 0,
            alerts_count INTEGER DEFAULT 0,
            digest_count INTEGER DEFAULT 0,
            skipped_count INTEGER DEFAULT 0,
            errors TEXT DEFAULT '[]',
            metadata TEXT DEFAULT '{}',
            started_at TEXT DEFAULT CURRENT_TIMESTAMP,
            last_updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
            completed_at TEXT DEFAULT NULL
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

        -- v3: ChatGPT-style chat persistence (single entry point per user
        -- emphasis #1 + #3: 정보 홍수 → 한 화면 / 인지 부하 0).
        CREATE TABLE IF NOT EXISTS chat_conversations (
            id TEXT PRIMARY KEY,
            title TEXT NOT NULL DEFAULT 'New chat',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            last_message_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS chat_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            conversation_id TEXT NOT NULL,
            role TEXT NOT NULL CHECK (role IN ('user','assistant','tool','system')),
            content TEXT NOT NULL,
            tool_calls TEXT DEFAULT NULL,    -- JSON when assistant invoked tools
            tool_name TEXT DEFAULT NULL,     -- when role='tool'
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (conversation_id) REFERENCES chat_conversations(id)
        );

        -- v3 G1: judgment first-class artifact (seed.yaml ontology).
        -- Decouples LLM judgment from inline signal columns so each judgment
        -- can be traced back to the criteria/interpretation_style version
        -- that produced it (cross-version fitness attribution).
        CREATE TABLE IF NOT EXISTS judgments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            signal_id TEXT NOT NULL,
            score REAL NOT NULL,
            urgency TEXT NOT NULL,
            rationale TEXT,
            devil_advocate TEXT,
            opportunity_note TEXT,
            confidence REAL,
            exploration_tags TEXT DEFAULT '[]',
            criteria_version INTEGER,
            interpretation_style_id TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(signal_id, criteria_version, interpretation_style_id)
        );

        -- v3 Phase 7: behavior_events — implicit-passive feedback channel.
        -- Ambient delivery surfaces reuse this raw-event schema downstream of
        -- ranking; rewards remain derived separately in behavior_rewards.
        CREATE TABLE IF NOT EXISTS behavior_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            signal_id TEXT NOT NULL,
            event_type TEXT NOT NULL CHECK (event_type IN (
                'view_start','view_end','dwell','skip','share','save',
                'expand_source','click_link','open_qa','card_impression',
                'viewed_card','open','swipe_left','swipe_right','swipe_next',
                'not_interested','delivery_decision',
                'delivered','opened','dismissed','snoozed','saved','clicked'
            )),
            dwell_ms INTEGER,
            position_in_feed INTEGER,
            feed_id TEXT DEFAULT 'default',
            feed_mode TEXT DEFAULT 'grid',
            device TEXT,
            captured_at TEXT DEFAULT CURRENT_TIMESTAMP
        );

        -- User-owned derived reward interpretations. Raw events remain in
        -- behavior_events; this table can be recomputed when policy changes.
        CREATE TABLE IF NOT EXISTS behavior_rewards (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            signal_id TEXT NOT NULL,
            raw_event_id INTEGER,
            event_type TEXT NOT NULL,
            reward_value REAL NOT NULL,
            signal_strength TEXT NOT NULL,
            polarity TEXT DEFAULT 'neutral',
            strength_class TEXT DEFAULT 'weak',
            confidence REAL DEFAULT 0.0,
            uncertainty_reason TEXT DEFAULT '',
            derivation_rule_version TEXT DEFAULT 'personal_algorithm_reward_v1',
            source_event_ids TEXT DEFAULT '[]',
            policy_version INTEGER DEFAULT 1,
            feed_mode TEXT DEFAULT 'grid',
            source TEXT DEFAULT 'personal_algorithm',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );

        -- v3 Phase 7 G6: delivered_signals — first-class delivery row so
        -- feedback can bind to a specific delivery instance per channel
        -- (seed.yaml ontology delivery entity).
        CREATE TABLE IF NOT EXISTS delivered_signals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            signal_id TEXT NOT NULL,
            channel TEXT NOT NULL CHECK (channel IN (
                'slack','discord','email','dashboard','feed','critical'
            )),
            delivered_at TEXT DEFAULT CURRENT_TIMESTAMP,
            message_ref TEXT,
            acknowledged INTEGER DEFAULT 0
        );

        -- v3: First-class interpretation_style (seed.yaml ontology).
        -- HOW signals are explained. Evolved weekly separately from criteria.
        CREATE TABLE IF NOT EXISTS interpretation_styles (
            id TEXT PRIMARY KEY,
            version INTEGER NOT NULL,
            tone TEXT DEFAULT 'mixed',
            depth TEXT DEFAULT 'deep',
            jargon_level TEXT DEFAULT 'medium',
            prompt_template TEXT NOT NULL,
            parent_version INTEGER,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            is_active INTEGER DEFAULT 0
        );

        -- v3: Persisted daily/weekly briefings (engine 계기판 — users must be
        -- able to read their brief on the web even without Slack/Discord)
        CREATE TABLE IF NOT EXISTS briefings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cycle_type TEXT NOT NULL CHECK (cycle_type IN ('daily','weekly','critical')),
            content TEXT NOT NULL,
            signal_count INTEGER DEFAULT 0,
            generated_at TEXT DEFAULT CURRENT_TIMESTAMP
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
        """)

        # Migrations must run before indexes because older local databases may
        # miss columns (for example behavior_events.feed_mode) used by indexes.
        _run_schema_migrations(conn)

        conn.executescript("""
        CREATE INDEX IF NOT EXISTS idx_signals_collected ON signals(collected_at DESC);
        CREATE INDEX IF NOT EXISTS idx_signals_relevance ON signals(relevance_score DESC);
        CREATE INDEX IF NOT EXISTS idx_feedback_captured ON feedback(captured_at DESC);
        CREATE INDEX IF NOT EXISTS idx_run_history_run_at ON run_history(run_at DESC);
        CREATE INDEX IF NOT EXISTS idx_run_history_cycle_type ON run_history(cycle_type);
        CREATE INDEX IF NOT EXISTS idx_collection_runs_updated ON collection_runs(last_updated_at DESC);
        CREATE INDEX IF NOT EXISTS idx_collection_runs_status ON collection_runs(status);
        CREATE INDEX IF NOT EXISTS idx_source_reliability_updated_at ON source_reliability(updated_at DESC);
        CREATE INDEX IF NOT EXISTS idx_evolution_signal_captured ON evolution_signal(captured_at DESC);
        CREATE INDEX IF NOT EXISTS idx_evolution_signal_channel ON evolution_signal(channel);
        CREATE INDEX IF NOT EXISTS idx_algorithm_versions_created ON algorithm_versions(created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_briefings_generated ON briefings(generated_at DESC);
        CREATE INDEX IF NOT EXISTS idx_behavior_signal ON behavior_events(signal_id, captured_at DESC);
        CREATE INDEX IF NOT EXISTS idx_behavior_type ON behavior_events(event_type, captured_at DESC);
        CREATE INDEX IF NOT EXISTS idx_behavior_mode ON behavior_events(feed_mode, captured_at DESC);
        CREATE INDEX IF NOT EXISTS idx_reward_signal ON behavior_rewards(signal_id, created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_reward_strength ON behavior_rewards(signal_strength, created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_delivered_signal ON delivered_signals(signal_id, delivered_at DESC);
        CREATE INDEX IF NOT EXISTS idx_chat_msg_convo ON chat_messages(conversation_id, id);
        CREATE INDEX IF NOT EXISTS idx_chat_convo_last ON chat_conversations(last_message_at DESC);
        CREATE INDEX IF NOT EXISTS idx_judgments_signal ON judgments(signal_id, created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_judgments_versions ON judgments(criteria_version, interpretation_style_id);
        """)


def _now() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


def _json_dict(value: object) -> dict:
    if isinstance(value, dict):
        return value
    if not value:
        return {}
    try:
        parsed = json.loads(str(value))
    except Exception:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _json_list(value: object) -> list:
    if isinstance(value, list):
        return value
    if not value:
        return []
    try:
        parsed = json.loads(str(value))
    except Exception:
        return []
    return parsed if isinstance(parsed, list) else []


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

_COLLECTION_RUN_COUNT_FIELDS = {
    "posts_collected",
    "posts_filtered",
    "signals_scored",
    "signals_saved",
    "alerts_count",
    "digest_count",
    "skipped_count",
}
_COLLECTION_RUN_TERMINAL_STATUSES = {"completed", "failed", "no_items"}


def _collection_run_from_row(row: sqlite3.Row | None) -> dict:
    if row is None:
        return {}
    data = dict(row)
    data["errors"] = _json_list(data.get("errors"))
    data["metadata"] = _json_dict(data.get("metadata"))
    data["last_updated_at"] = data.get("last_updated_at") or data.get("started_at")
    data["feed_items_available"] = int(data.get("signals_saved") or 0) > 0
    return data


def start_collection_run(
    run_type: str = "daily",
    *,
    status: str = "queued",
    metadata: dict | None = None,
) -> int:
    """Create a backend-visible collection progress record."""
    init_db()
    now = _now()
    with _conn() as conn:
        cursor = conn.execute(
            """
            INSERT INTO collection_runs (
                run_type, status, metadata, started_at, last_updated_at
            ) VALUES (?,?,?,?,?)
            """,
            (
                str(run_type or "daily"),
                str(status or "queued"),
                json.dumps(metadata or {}),
                now,
                now,
            ),
        )
        return int(cursor.lastrowid)


def update_collection_run(
    run_id: int | str | None,
    *,
    status: str | None = None,
    counts: dict[str, int] | None = None,
    error: str | Exception | None = None,
    metadata: dict | None = None,
) -> dict:
    """Update collection progress with counts, errors, and fresh timestamp."""
    if not run_id:
        return {}
    try:
        normalized_run_id = int(run_id)
    except (TypeError, ValueError):
        return {}

    init_db()
    now = _now()
    with _conn() as conn:
        row = conn.execute(
            "SELECT * FROM collection_runs WHERE id = ?",
            (normalized_run_id,),
        ).fetchone()
        if row is None:
            return {}

        existing = _collection_run_from_row(row)
        merged_metadata = existing["metadata"]
        if metadata:
            merged_metadata.update(metadata)
        errors = existing["errors"]
        if error:
            errors.append(
                {
                    "message": str(error),
                    "captured_at": now,
                }
            )

        assignments = [
            "last_updated_at = ?",
            "metadata = ?",
            "errors = ?",
        ]
        values: list[object] = [
            now,
            json.dumps(merged_metadata),
            json.dumps(errors),
        ]
        if status:
            assignments.append("status = ?")
            values.append(str(status))
            if status in _COLLECTION_RUN_TERMINAL_STATUSES:
                assignments.append("completed_at = COALESCE(completed_at, ?)")
                values.append(now)
        for key, value in (counts or {}).items():
            if key not in _COLLECTION_RUN_COUNT_FIELDS:
                continue
            assignments.append(f"{key} = ?")
            values.append(max(0, int(value or 0)))

        values.append(normalized_run_id)
        conn.execute(
            f"""
            UPDATE collection_runs
            SET {", ".join(assignments)}
            WHERE id = ?
            """,
            values,
        )
        updated = conn.execute(
            "SELECT * FROM collection_runs WHERE id = ?",
            (normalized_run_id,),
        ).fetchone()
        return _collection_run_from_row(updated)


def finish_collection_run(
    run_id: int | str | None,
    *,
    status: str = "completed",
    counts: dict[str, int] | None = None,
    error: str | Exception | None = None,
    metadata: dict | None = None,
) -> dict:
    return update_collection_run(
        run_id,
        status=status,
        counts=counts,
        error=error,
        metadata=metadata,
    )


def get_latest_collection_progress(run_type: str | None = None) -> dict:
    """Return the latest collection run for setup/feed progress polling."""
    init_db()
    with _conn() as conn:
        if run_type:
            row = conn.execute(
                """
                SELECT * FROM collection_runs
                WHERE run_type = ?
                ORDER BY last_updated_at DESC, id DESC
                LIMIT 1
                """,
                (str(run_type),),
            ).fetchone()
        else:
            row = conn.execute(
                """
                SELECT * FROM collection_runs
                ORDER BY last_updated_at DESC, id DESC
                LIMIT 1
                """
            ).fetchone()
    return _collection_run_from_row(row)


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

def save_feedback(feedback: Feedback, user_id: str | None = None, **_kwargs) -> bool:
    """Persist a feedback row.

    ``user_id`` is accepted for parity with the supabase backend (which is
    multi-tenant). The local SQLite backend is single-user, so the value
    is intentionally ignored — callers can pass it without a guard.

    ``**_kwargs`` absorbs any future kwargs the supabase backend grows so
    the storage dispatcher never raises TypeError on signature drift.
    """
    init_db()
    _ = user_id  # silence linters; documented above
    # Compute attribution lazily — which criterion keywords + which platform
    # were associated with the signal. Stored as JSON so the evolution loop
    # can later attribute fitness deltas back to specific criterion entries
    # (G5 from interview_gap_audit).
    attribution_json = None
    try:
        attribution_json = json.dumps(_compute_feedback_attribution(feedback.signal_id),
                                       ensure_ascii=False)
    except Exception:
        attribution_json = "{}"

    delivered_id = getattr(feedback, "delivered_signal_id", None)

    try:
        with _conn() as conn:
            conn.execute("""
                INSERT INTO feedback
                  (signal_id, vote, natural_language, source_channel, captured_at,
                   attribution, delivered_signal_id)
                VALUES (?,?,?,?,?,?,?)
            """, (
                feedback.signal_id,
                feedback.vote.value,
                feedback.natural_language,
                feedback.source_channel,
                feedback.captured_at.isoformat(),
                attribution_json,
                delivered_id,
            ))
        return True
    except Exception as e:
        logger.error(f"save_feedback: {e}")
        return False


def _compute_feedback_attribution(signal_id: str) -> dict:
    """Best-effort attribution payload — which criterion items + platform
    are associated with this signal. Used by G5."""
    out: dict = {"criterion_keywords": [], "platform": None}
    try:
        with _conn() as conn:
            row = conn.execute(
                "SELECT platform, title, content FROM signals WHERE id = ? OR external_id = ? LIMIT 1",
                (str(signal_id), str(signal_id)),
            ).fetchone()
        if not row:
            return out
        out["platform"] = row["platform"]

        from hedwig.config import load_criteria
        crit = load_criteria() or {}
        keywords = crit.get("signal_preferences", {}).get("care_about", []) or []
        haystack = f"{row['title']} {(row['content'] or '')[:500]}".lower()
        out["criterion_keywords"] = [
            kw for kw in keywords if str(kw).lower() in haystack
        ]
    except Exception:
        pass
    return out


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


def save_cycle_log(
    cycle_type: str,
    cycle_number: int,
    *,
    scope: str | None = None,           # micro | macro | meta
    axis: str | None = None,            # criteria | source | interpretation | exploration
    inputs: dict | None = None,
    outputs: dict | None = None,
    mutations_applied: list | None = None,
    fitness_before: float | None = None,
    fitness_after: float | None = None,
    kept: bool = True,
    analysis_summary: str = "",
    evaluator_verdict: str | None = None,
    criteria_version_before: int | None = None,
    criteria_version_after: int | None = None,
) -> bool:
    """Structured cycle log per seed.yaml ontology (G7).

    Backwards-compatible with the legacy evolution_logs columns; new columns
    were added via ALTER TABLE in init_db.
    """
    init_db()
    try:
        with _conn() as conn:
            conn.execute("""
                INSERT INTO evolution_logs
                  (cycle_type, cycle_number, criteria_version_before,
                   criteria_version_after, mutations_applied, fitness_before,
                   fitness_after, kept, analysis_summary, scope, axis,
                   inputs, outputs, evaluator_verdict)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, (
                cycle_type, int(cycle_number),
                criteria_version_before, criteria_version_after,
                json.dumps(mutations_applied or [], ensure_ascii=False),
                fitness_before, fitness_after,
                1 if kept else 0,
                analysis_summary,
                scope, axis,
                json.dumps(inputs or {}, ensure_ascii=False, default=str),
                json.dumps(outputs or {}, ensure_ascii=False, default=str),
                evaluator_verdict,
            ))
        return True
    except Exception as e:
        logger.error("save_cycle_log: %s", e)
        return False


def get_cycle_logs(scope: str | None = None, limit: int = 100) -> list[dict]:
    init_db()
    if scope:
        q = ("SELECT * FROM evolution_logs WHERE scope = ? "
             "ORDER BY timestamp DESC, id DESC LIMIT ?")
        params: tuple = (scope, limit)
    else:
        q = "SELECT * FROM evolution_logs ORDER BY timestamp DESC, id DESC LIMIT ?"
        params = (limit,)
    with _conn() as conn:
        rows = conn.execute(q, params).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        for jf in ("mutations_applied", "inputs", "outputs"):
            try:
                d[jf] = json.loads(d.get(jf) or ("[]" if jf == "mutations_applied" else "{}"))
            except Exception:
                pass
        out.append(d)
    return out


def create_conversation(conversation_id: str, title: str = "New chat") -> bool:
    init_db()
    try:
        with _conn() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO chat_conversations (id, title) VALUES (?, ?)",
                (conversation_id, title),
            )
        return True
    except Exception as e:
        logger.error("create_conversation: %s", e)
        return False


def list_conversations(limit: int = 50) -> list[dict]:
    init_db()
    with _conn() as conn:
        rows = conn.execute(
            """SELECT id, title, created_at, last_message_at
               FROM chat_conversations
               ORDER BY last_message_at DESC LIMIT ?""",
            (limit,),
        ).fetchall()
    return [dict(r) for r in rows]


def update_conversation_title(conversation_id: str, title: str) -> bool:
    init_db()
    try:
        with _conn() as conn:
            conn.execute(
                "UPDATE chat_conversations SET title = ? WHERE id = ?",
                (title, conversation_id),
            )
        return True
    except Exception as e:
        logger.error("update_conversation_title: %s", e)
        return False


def delete_conversation(conversation_id: str) -> bool:
    init_db()
    try:
        with _conn() as conn:
            conn.execute("DELETE FROM chat_messages WHERE conversation_id = ?",
                         (conversation_id,))
            conn.execute("DELETE FROM chat_conversations WHERE id = ?",
                         (conversation_id,))
        return True
    except Exception as e:
        logger.error("delete_conversation: %s", e)
        return False


def append_chat_message(
    conversation_id: str,
    role: str,
    content: str,
    *,
    tool_calls: list | None = None,
    tool_name: str | None = None,
) -> int | None:
    if role not in ("user", "assistant", "tool", "system"):
        return None
    init_db()
    try:
        with _conn() as conn:
            cur = conn.execute(
                """INSERT INTO chat_messages
                   (conversation_id, role, content, tool_calls, tool_name)
                   VALUES (?, ?, ?, ?, ?)""",
                (
                    conversation_id, role, content,
                    json.dumps(tool_calls, ensure_ascii=False) if tool_calls else None,
                    tool_name,
                ),
            )
            conn.execute(
                "UPDATE chat_conversations SET last_message_at = CURRENT_TIMESTAMP WHERE id = ?",
                (conversation_id,),
            )
            return cur.lastrowid
    except Exception as e:
        logger.error("append_chat_message: %s", e)
        return None


def get_chat_messages(conversation_id: str, limit: int = 200) -> list[dict]:
    init_db()
    with _conn() as conn:
        rows = conn.execute(
            """SELECT id, role, content, tool_calls, tool_name, created_at
               FROM chat_messages WHERE conversation_id = ?
               ORDER BY id ASC LIMIT ?""",
            (conversation_id, limit),
        ).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        if d.get("tool_calls"):
            try:
                d["tool_calls"] = json.loads(d["tool_calls"])
            except Exception:
                pass
        out.append(d)
    return out


def save_behavior_event(
    signal_id: str,
    event_type: str,
    dwell_ms: int | None = None,
    position_in_feed: int | None = None,
    feed_id: str = "default",
    feed_mode: str = "grid",
    device: str | None = None,
) -> bool:
    """Record one /feed UI interaction event."""
    init_db()
    try:
        with _conn() as conn:
            conn.execute(
                """INSERT INTO behavior_events
                   (signal_id, event_type, dwell_ms, position_in_feed, feed_id, feed_mode, device)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (str(signal_id), event_type, dwell_ms, position_in_feed, feed_id, feed_mode, device),
            )
        return True
    except Exception as e:
        logger.error("save_behavior_event: %s", e)
        return False


def save_behavior_events_batch(events: list[dict]) -> int:
    """Bulk-insert beacon batch. Returns count successfully saved."""
    init_db()
    saved = 0
    valid_types = {
        "view_start", "view_end", "dwell", "skip", "share", "save",
        "expand_source", "click_link", "open_qa", "card_impression",
        "viewed_card", "open", "swipe_left", "swipe_right", "swipe_next",
        "not_interested", "delivery_decision",
        "delivered", "opened", "dismissed", "snoozed", "saved", "clicked",
    }
    with _conn() as conn:
        for ev in events:
            etype = ev.get("event_type")
            sid = ev.get("signal_id")
            if etype not in valid_types or not sid:
                continue
            try:
                cur = conn.execute(
                    """INSERT INTO behavior_events
                       (signal_id, event_type, dwell_ms, position_in_feed, feed_id, feed_mode, device)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (
                        str(sid), etype,
                        ev.get("dwell_ms"), ev.get("position_in_feed"),
                        str(ev.get("feed_id") or "default"),
                        str(ev.get("feed_mode") or ev.get("mode") or "grid"),
                        ev.get("device"),
                    ),
                )
                ev["id"] = cur.lastrowid
                saved += 1
            except Exception as e:
                logger.warning("behavior batch row failed: %s", e)
    return saved


def get_behavior_events(
    signal_id: str | None = None,
    event_types: list[str] | None = None,
    feed_mode: str | None = None,
    limit: int = 200,
) -> list[dict]:
    init_db()
    q = "SELECT * FROM behavior_events"
    conds = []
    params: list = []
    if signal_id:
        conds.append("signal_id = ?")
        params.append(str(signal_id))
    if event_types:
        placeholders = ",".join("?" for _ in event_types)
        conds.append(f"event_type IN ({placeholders})")
        params.extend(event_types)
    if feed_mode:
        conds.append("feed_mode = ?")
        params.append(feed_mode)
    if conds:
        q += " WHERE " + " AND ".join(conds)
    q += " ORDER BY captured_at DESC, id DESC LIMIT ?"
    params.append(limit)
    with _conn() as conn:
        rows = conn.execute(q, params).fetchall()
    out = []
    for row in rows:
        item = dict(row)
        try:
            item["source_event_ids"] = json.loads(item.get("source_event_ids") or "[]")
        except Exception:
            item["source_event_ids"] = []
        out.append(item)
    return out


def save_behavior_reward(reward: dict) -> bool:
    init_db()
    try:
        with _conn() as conn:
            conn.execute(
                """INSERT INTO behavior_rewards
                   (signal_id, raw_event_id, event_type, reward_value,
                    signal_strength, polarity, strength_class, confidence,
                    uncertainty_reason, derivation_rule_version, source_event_ids,
                    policy_version, feed_mode, source)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    str(reward.get("signal_id")),
                    reward.get("raw_event_id"),
                    str(reward.get("event_type")),
                    float(reward.get("reward_value") or 0),
                    str(reward.get("signal_strength") or "weak"),
                    str(reward.get("polarity") or "neutral"),
                    str(reward.get("strength_class") or reward.get("signal_strength") or "weak"),
                    float(reward.get("confidence") or 0),
                    str(reward.get("uncertainty_reason") or ""),
                    str(reward.get("derivation_rule_version") or "personal_algorithm_reward_v1"),
                    json.dumps(list(reward.get("source_event_ids") or []), ensure_ascii=False),
                    int(reward.get("policy_version") or 1),
                    str(reward.get("feed_mode") or "grid"),
                    str(reward.get("source") or "personal_algorithm"),
                ),
            )
        return True
    except Exception as e:
        logger.error("save_behavior_reward: %s", e)
        return False


def save_behavior_rewards_batch(rewards: list[dict]) -> int:
    saved = 0
    for reward in rewards or []:
        if save_behavior_reward(reward):
            saved += 1
    return saved


def get_behavior_rewards(
    signal_id: str | None = None,
    signal_strength: str | None = None,
    feed_mode: str | None = None,
    limit: int = 200,
) -> list[dict]:
    init_db()
    q = "SELECT * FROM behavior_rewards"
    conds = []
    params: list = []
    if signal_id:
        conds.append("signal_id = ?")
        params.append(str(signal_id))
    if signal_strength:
        conds.append("signal_strength = ?")
        params.append(str(signal_strength))
    if feed_mode:
        conds.append("feed_mode = ?")
        params.append(str(feed_mode))
    if conds:
        q += " WHERE " + " AND ".join(conds)
    q += " ORDER BY created_at DESC, id DESC LIMIT ?"
    params.append(limit)
    with _conn() as conn:
        rows = conn.execute(q, params).fetchall()
    out = []
    for row in rows:
        item = dict(row)
        try:
            item["source_event_ids"] = json.loads(item.get("source_event_ids") or "[]")
        except Exception:
            item["source_event_ids"] = []
        out.append(item)
    return out


def get_usage_metrics_by_mode(days: int = 7) -> dict:
    init_db()
    cutoff = (datetime.now(tz=timezone.utc) - timedelta(days=days)).isoformat()
    with _conn() as conn:
        rows = conn.execute(
            """SELECT feed_mode, event_type, COUNT(*) AS count,
                      COALESCE(SUM(dwell_ms), 0) AS dwell_ms
               FROM behavior_events
               WHERE captured_at >= ?
               GROUP BY feed_mode, event_type""",
            (cutoff,),
        ).fetchall()
    out: dict[str, dict[str, int]] = {}
    for row in rows:
        mode = row["feed_mode"] or "grid"
        bucket = out.setdefault(mode, {"events": 0, "dwell_ms": 0})
        bucket[str(row["event_type"])] = int(row["count"] or 0)
        bucket["events"] += int(row["count"] or 0)
        bucket["dwell_ms"] += int(row["dwell_ms"] or 0)
    for mode in ("grid", "detail_swipe", "dense_reader"):
        out.setdefault(mode, {"events": 0, "dwell_ms": 0})
    for mode, bucket in out.items():
        impressions = max(1, int(bucket.get("card_impression", 0)))
        sessions = max(1, int(bucket.get("session_start", 0)) or 1)
        viewed = max(1, int(bucket.get("viewed_card", 0)))
        raw_counts = {k: v for k, v in bucket.items() if isinstance(v, int)}
        bucket["raw_counts"] = raw_counts
        bucket["normalized_rates"] = {
            key: {
                "per_impression_rate": round(value / impressions, 6),
                "per_session_rate": round(value / sessions, 6),
                "per_viewed_card_rate": round(value / viewed, 6),
            }
            for key, value in raw_counts.items()
        }
        bucket["usage_metric"] = {
            "session_id": "aggregate",
            "feed_mode": mode,
            "time_window_days": days,
            "raw_count": int(bucket.get("events", 0)),
            "per_impression_rate": round(int(bucket.get("events", 0)) / impressions, 6),
            "per_session_rate": round(int(bucket.get("events", 0)) / sessions, 6),
            "per_viewed_card_rate": round(int(bucket.get("events", 0)) / viewed, 6),
        }
    return out


def save_delivered_signal(
    signal_id: str,
    channel: str,
    message_ref: str | None = None,
) -> int | None:
    """Record one delivery event so feedback can bind to it (G6)."""
    if channel not in ("slack", "discord", "email", "dashboard", "feed", "critical"):
        logger.warning("delivered_signal: invalid channel %s", channel)
        return None
    init_db()
    try:
        with _conn() as conn:
            cur = conn.execute(
                """INSERT INTO delivered_signals (signal_id, channel, message_ref)
                   VALUES (?, ?, ?)""",
                (str(signal_id), channel, message_ref),
            )
            return cur.lastrowid
    except Exception as e:
        logger.error("save_delivered_signal: %s", e)
        return None


def get_delivered_signals(
    signal_id: str | None = None,
    limit: int = 100,
) -> list[dict]:
    init_db()
    if signal_id:
        q = ("SELECT * FROM delivered_signals WHERE signal_id = ? "
             "ORDER BY delivered_at DESC, id DESC LIMIT ?")
        params: tuple = (str(signal_id), limit)
    else:
        q = ("SELECT * FROM delivered_signals "
             "ORDER BY delivered_at DESC, id DESC LIMIT ?")
        params = (limit,)
    with _conn() as conn:
        rows = conn.execute(q, params).fetchall()
    return [dict(r) for r in rows]


def save_judgment(judgment) -> int | None:
    """Persist a first-class Judgment row (G1) and return its rowid.

    Idempotent on (signal_id, criteria_version, interpretation_style_id).
    """
    init_db()
    try:
        with _conn() as conn:
            cur = conn.execute(
                """INSERT OR REPLACE INTO judgments
                   (signal_id, score, urgency, rationale, devil_advocate,
                    opportunity_note, confidence, exploration_tags,
                    criteria_version, interpretation_style_id)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    str(judgment.signal_id),
                    float(judgment.score),
                    judgment.urgency.value if hasattr(judgment.urgency, "value") else str(judgment.urgency),
                    judgment.rationale,
                    judgment.devil_advocate,
                    judgment.opportunity_note,
                    judgment.confidence,
                    json.dumps(list(judgment.exploration_tags or []), ensure_ascii=False),
                    judgment.criteria_version,
                    judgment.interpretation_style_id,
                ),
            )
            jid = cur.lastrowid
        # Backfill signals.judgment_id pointer when we know the signal row
        try:
            with _conn() as conn2:
                conn2.execute(
                    "UPDATE signals SET judgment_id = ? "
                    "WHERE id = ? OR external_id = ?",
                    (jid, str(judgment.signal_id), str(judgment.signal_id)),
                )
        except Exception:
            pass
        return jid
    except Exception as e:
        logger.error("save_judgment: %s", e)
        return None


def get_judgments_for_signal(signal_id: str, limit: int = 10) -> list[dict]:
    init_db()
    with _conn() as conn:
        rows = conn.execute(
            """SELECT * FROM judgments WHERE signal_id = ?
               ORDER BY created_at DESC, id DESC LIMIT ?""",
            (str(signal_id), limit),
        ).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        try:
            d["exploration_tags"] = json.loads(d.get("exploration_tags") or "[]")
        except Exception:
            d["exploration_tags"] = []
        out.append(d)
    return out


def save_interpretation_style(style) -> bool:
    init_db()
    try:
        with _conn() as conn:
            conn.execute(
                """INSERT OR REPLACE INTO interpretation_styles
                   (id, version, tone, depth, jargon_level, prompt_template,
                    parent_version, created_at, is_active)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0)""",
                (
                    style.id, style.version, style.tone, style.depth,
                    style.jargon_level, style.prompt_template,
                    style.parent_version,
                    style.created_at.isoformat(),
                ),
            )
        return True
    except Exception as e:
        logger.error("save_interpretation_style: %s", e)
        return False


def set_active_interpretation_style(style_id: str) -> bool:
    init_db()
    try:
        with _conn() as conn:
            conn.execute("UPDATE interpretation_styles SET is_active = 0")
            conn.execute(
                "UPDATE interpretation_styles SET is_active = 1 WHERE id = ?",
                (style_id,),
            )
        return True
    except Exception as e:
        logger.error("set_active_interpretation_style: %s", e)
        return False


def get_active_interpretation_style() -> dict | None:
    init_db()
    with _conn() as conn:
        row = conn.execute(
            """SELECT id, version, tone, depth, jargon_level, prompt_template,
                      parent_version, created_at
               FROM interpretation_styles
               WHERE is_active = 1 LIMIT 1"""
        ).fetchone()
    return dict(row) if row else None


def get_interpretation_style_history(limit: int = 30) -> list[dict]:
    init_db()
    with _conn() as conn:
        rows = conn.execute(
            """SELECT id, version, tone, depth, jargon_level, parent_version,
                      created_at, is_active
               FROM interpretation_styles
               ORDER BY version DESC, id DESC LIMIT ?""",
            (limit,),
        ).fetchall()
    return [dict(r) for r in rows]


def save_briefing(cycle_type: str, content: str, signal_count: int = 0) -> int | None:
    """Persist a generated briefing so the web UI can show it.

    Also parses ``content`` into the structured ontology fields declared
    in seed.yaml briefing entity (G10) and stores them in the
    ``structured`` JSON column.
    """
    if cycle_type not in ("daily", "weekly", "critical"):
        logger.warning("save_briefing: invalid cycle_type %s", cycle_type)
        return None
    init_db()
    structured_json = "{}"
    try:
        from hedwig.engine.briefing_parser import parse_briefing
        parsed = parse_briefing(content or "")
        # Drop the verbose raw_sections to keep DB rows compact
        if isinstance(parsed, dict):
            parsed.pop("raw_sections", None)
        structured_json = json.dumps(parsed, ensure_ascii=False)
    except Exception as e:
        logger.debug("briefing parser skipped: %s", e)
    try:
        with _conn() as conn:
            cur = conn.execute(
                """INSERT INTO briefings (cycle_type, content, signal_count, structured)
                   VALUES (?, ?, ?, ?)""",
                (cycle_type, content or "", int(signal_count or 0), structured_json),
            )
            return cur.lastrowid
    except Exception as e:
        logger.error("save_briefing: %s", e)
        return None


def get_briefings(cycle_type: str | None = None, limit: int = 30) -> list[dict]:
    init_db()
    if cycle_type:
        q = ("""SELECT id, cycle_type, content, signal_count, generated_at, structured
               FROM briefings WHERE cycle_type = ?
               ORDER BY generated_at DESC, id DESC LIMIT ?""")
        params: tuple = (cycle_type, limit)
    else:
        q = ("""SELECT id, cycle_type, content, signal_count, generated_at, structured
               FROM briefings
               ORDER BY generated_at DESC, id DESC LIMIT ?""")
        params = (limit,)
    with _conn() as conn:
        rows = conn.execute(q, params).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        try:
            d["structured"] = json.loads(d.get("structured") or "{}")
        except Exception:
            d["structured"] = {}
        out.append(d)
    return out


def get_briefing(briefing_id: int) -> dict | None:
    init_db()
    with _conn() as conn:
        row = conn.execute(
            """SELECT id, cycle_type, content, signal_count, generated_at
               FROM briefings WHERE id = ?""",
            (briefing_id,),
        ).fetchone()
    return dict(row) if row else None


def get_algorithm_history(limit: int = 50) -> list[dict]:
    init_db()
    with _conn() as conn:
        # Order by version DESC (tiebreak on id DESC) so newer adoptions beat
        # same-timestamp seed rows that the default CURRENT_TIMESTAMP shares.
        rows = conn.execute(
            """SELECT version, config, created_at, created_by, origin, fitness_score,
                      diff_from_previous
               FROM algorithm_versions
               ORDER BY version DESC, id DESC LIMIT ?""",
            (limit,),
        ).fetchall()
    out = []
    for row in rows:
        item = dict(row)
        try:
            item["config"] = json.loads(item.get("config") or "{}")
        except Exception:
            item["config"] = {}
        out.append(item)
    return out
