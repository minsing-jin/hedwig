"""Evolution timeline — unified view of criteria + algorithm + event history.

Reads three sources and merges them into a chronological feed:
  - criteria_versions
  - algorithm_versions
  - evolution_signal (accepted explicit edits, qa events)
  - evolution_logs (daily/weekly mutation cycles)

This is what the user sees to answer "how did my algorithm drift over time?"
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone

logger = logging.getLogger(__name__)


def _parse_ts(value) -> datetime:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except Exception:
        return datetime.now(tz=timezone.utc)


def build_timeline(days: int = 30, limit: int = 100) -> list[dict]:
    """Merged timeline of evolution events, newest first."""
    since = datetime.now(tz=timezone.utc) - timedelta(days=days)
    events: list[dict] = []

    try:
        from hedwig.storage import get_evolution_signals, get_algorithm_history
    except ImportError:
        return []

    # Explicit edits + semi-explicit Q&A
    for ev in get_evolution_signals(limit=limit * 2):
        events.append({
            "type": ev.get("kind", ""),
            "channel": ev.get("channel", ""),
            "at": ev.get("captured_at"),
            "payload": ev.get("payload", {}),
            "weight": ev.get("weight", 1.0),
        })

    # Algorithm config versions
    for av in get_algorithm_history(limit=50):
        events.append({
            "type": "algorithm_version",
            "channel": "meta",
            "at": av.get("created_at"),
            "version": av.get("version"),
            "origin": av.get("origin"),
            "fitness": av.get("fitness_score"),
            "diff": av.get("diff_from_previous"),
        })

    # Criteria config versions (user explicit edits)
    try:
        from hedwig.storage import get_criteria_versions
        for cv in get_criteria_versions(limit=50):
            events.append({
                "type": "criteria_version",
                "channel": "explicit",
                "at": cv.get("created_at"),
                "version": cv.get("version"),
                "origin": cv.get("created_by"),
                "fitness": cv.get("fitness_score"),
                "diff": cv.get("diff_from_previous"),
            })
    except Exception as e:
        logger.debug("timeline: criteria_versions read skipped (%s)", e)

    # Daily/weekly evolution cycles from jsonl (best-effort)
    try:
        from hedwig.config import EVOLUTION_LOG_PATH
        if EVOLUTION_LOG_PATH.exists():
            for line in EVOLUTION_LOG_PATH.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except Exception:
                    continue
                events.append({
                    "type": "evolution_cycle",
                    "channel": row.get("cycle_type", "daily"),
                    "at": row.get("timestamp"),
                    "mutations_applied": row.get("mutations_applied", []),
                    "analysis_summary": row.get("analysis_summary", ""),
                })
    except Exception as e:
        logger.debug("timeline: evolution_log read skipped (%s)", e)

    # Filter by lookback window, sort desc, truncate
    scoped = [e for e in events if _parse_ts(e.get("at") or since) >= since]
    scoped.sort(key=lambda e: _parse_ts(e.get("at")), reverse=True)
    return scoped[:limit]
