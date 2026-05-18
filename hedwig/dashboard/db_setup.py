"""
Supabase table auto-setup — creates all required tables via SQL REST endpoint.
"""
from __future__ import annotations

from pathlib import Path

import httpx

from hedwig.storage.supabase import SCHEMA_SQL


LOCAL_SQLITE_REQUIRED_SCHEMA = {
    "signals": {
        "id",
        "platform",
        "external_id",
        "title",
        "url",
        "content",
        "author",
        "relevance_score",
        "urgency",
        "collected_at",
        "judgment_id",
    },
    "feedback": {
        "id",
        "signal_id",
        "vote",
        "natural_language",
        "source_channel",
        "captured_at",
        "attribution",
        "delivered_signal_id",
    },
    "run_history": {"id", "cycle_type", "run_at"},
    "collection_runs": {
        "id",
        "run_type",
        "status",
        "posts_collected",
        "posts_filtered",
        "signals_scored",
        "signals_saved",
        "errors",
        "started_at",
        "last_updated_at",
    },
    "evolution_logs": {
        "id",
        "cycle_type",
        "cycle_number",
        "timestamp",
        "scope",
        "axis",
        "inputs",
        "outputs",
        "evaluator_verdict",
    },
    "criteria_versions": {"id", "version", "criteria", "created_by", "created_at"},
    "user_memory": {
        "id",
        "snapshot_week",
        "confirmed_interests",
        "rejected_topics",
        "context",
        "natural_language_feedback",
    },
    "source_reliability": {"platform", "reliability_score", "updated_at"},
    "evolution_signal": {"id", "channel", "kind", "payload", "weight"},
    "chat_conversations": {"id", "title", "created_at", "last_message_at"},
    "chat_messages": {"id", "conversation_id", "role", "content", "created_at"},
    "judgments": {"id", "signal_id", "score", "urgency", "criteria_version"},
    "behavior_events": {"id", "signal_id", "event_type", "captured_at", "feed_mode"},
    "behavior_rewards": {
        "id",
        "signal_id",
        "event_type",
        "reward_value",
        "signal_strength",
        "feed_mode",
    },
    "delivered_signals": {"id", "signal_id", "channel", "delivered_at"},
    "interpretation_styles": {"id", "version", "prompt_template", "is_active"},
    "briefings": {"id", "cycle_type", "content", "generated_at", "structured"},
    "algorithm_versions": {"id", "version", "config", "created_by", "origin"},
}


async def create_tables(url: str, key: str) -> tuple[bool, str]:
    """Execute SCHEMA_SQL against Supabase via pg-meta or REST endpoint.

    Note: Supabase REST doesn't allow arbitrary SQL via anon key.
    This function attempts best-effort via the pg-meta endpoint if available,
    or returns instructions for manual setup.
    """
    if not url or not key:
        return False, "Supabase URL and key required"

    # Try the pg-meta API (requires service_role key)
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{url.rstrip('/')}/rest/v1/rpc/exec_sql",
                headers={
                    "apikey": key,
                    "Authorization": f"Bearer {key}",
                    "Content-Type": "application/json",
                },
                json={"sql": SCHEMA_SQL},
            )
            if resp.status_code in (200, 204):
                return True, "Tables created successfully"
    except Exception:
        pass

    # Fallback: provide the SQL for manual execution
    return False, "auto_setup_unavailable"


def get_schema_sql() -> str:
    """Return the SQL schema for manual execution."""
    return SCHEMA_SQL


def inspect_local_sqlite_schema(db_path: Path | None = None) -> dict:
    """Return readiness details for the local first-run SQLite app schema."""
    import sqlite3

    from hedwig.storage import local as local_storage

    path = Path(db_path) if db_path is not None else local_storage._db_path()
    table_columns: dict[str, list[str]] = {}
    missing_tables: list[str] = []
    missing_columns: dict[str, list[str]] = {}

    if path.exists():
        with sqlite3.connect(str(path)) as conn:
            for table_name, required_columns in LOCAL_SQLITE_REQUIRED_SCHEMA.items():
                rows = conn.execute(f"PRAGMA table_info({table_name})").fetchall()
                columns = sorted(str(row[1]) for row in rows)
                table_columns[table_name] = columns
                if not columns:
                    missing_tables.append(table_name)
                    continue
                missing = sorted(required_columns - set(columns))
                if missing:
                    missing_columns[table_name] = missing
    else:
        missing_tables = sorted(LOCAL_SQLITE_REQUIRED_SCHEMA)

    return {
        "db_path": str(path),
        "db_exists": path.exists(),
        "schema_ready": not missing_tables and not missing_columns,
        "required_tables": sorted(LOCAL_SQLITE_REQUIRED_SCHEMA),
        "table_count": len(table_columns),
        "missing_tables": missing_tables,
        "missing_columns": missing_columns,
        "tables": table_columns,
    }


def ensure_local_sqlite_schema() -> dict:
    """Create or migrate the local SQLite schema used by setup and /feed."""
    from hedwig.storage import local as local_storage

    local_storage.init_db()
    return inspect_local_sqlite_schema(local_storage._db_path())
