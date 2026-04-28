"""Admin operations — data reset.

Used to wipe collected data so the user can test from scratch without
losing their config (criteria.yaml / algorithm.yaml / sovereignty.yaml /
feeds.yaml stay intact).

Scopes:
  - 'signals'  : signals + feedback + behavior_events + delivered_signals only
  - 'evolution': adds evolution_signal + evolution_logs + algorithm_versions +
                 criteria_versions + interpretation_styles + briefings +
                 user_memory
  - 'chat'     : chat_conversations + chat_messages
  - 'all'      : everything except the YAML configs (default)
"""
from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)


SIGNAL_TABLES = ("signals", "feedback", "behavior_events", "delivered_signals")
EVOLUTION_TABLES = (
    "evolution_signal", "evolution_logs", "algorithm_versions",
    "criteria_versions", "interpretation_styles", "briefings",
    "user_memory",
)
CHAT_TABLES = ("chat_messages", "chat_conversations")
JSONL_FILES = ("evolution_log.jsonl", "user_memory.jsonl", "algorithm_log.jsonl")


def reset_data(scope: str = "all") -> dict:
    """Wipe collected data while preserving YAML configs.

    Returns a dict reporting how many rows were deleted per table.
    Idempotent — re-running on empty store returns zero counts.
    """
    from hedwig.storage.local import _conn, init_db

    init_db()
    targets: list[str] = []
    if scope in ("all", "signals"):
        targets += list(SIGNAL_TABLES)
    if scope in ("all", "evolution"):
        targets += list(EVOLUTION_TABLES)
    if scope in ("all", "chat"):
        targets += list(CHAT_TABLES)
    if not targets:
        return {"scope": scope, "error": f"unknown scope {scope!r}"}

    deleted: dict[str, int] = {}
    with _conn() as conn:
        for table in targets:
            try:
                cur = conn.execute(f"DELETE FROM {table}")
                deleted[table] = cur.rowcount or 0
            except Exception as e:
                logger.debug("reset: %s skipped (%s)", table, e)
                deleted[table] = -1

    # JSONL artifacts (evolution log etc.) — only when scope='all' or 'evolution'
    files_removed: list[str] = []
    if scope in ("all", "evolution"):
        try:
            from hedwig.config import EVOLUTION_LOG_PATH, USER_MEMORY_PATH, ALGORITHM_LOG_PATH
            for path in (EVOLUTION_LOG_PATH, USER_MEMORY_PATH, ALGORITHM_LOG_PATH):
                if path and Path(path).exists():
                    Path(path).unlink()
                    files_removed.append(str(path))
        except Exception as e:
            logger.debug("reset: jsonl cleanup skipped (%s)", e)

    return {"scope": scope, "deleted": deleted, "files_removed": files_removed}
