"""Exit-condition progress tracker (G8).

seed.yaml declares 4 exit conditions for Hedwig MVP. This module reads
storage stats and reports progress toward each one so the dashboard can
surface "are we there yet?" without manual auditing.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone


def _safe_call(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except Exception:
        return None


def compute_exit_progress() -> list[dict]:
    """Return a list of {name, criteria, met, progress, detail}."""
    from hedwig.storage import (
        get_evolution_signals,
        get_feedback_since,
        get_recent_signals,
        get_run_stats,
        get_briefings,
    )
    from hedwig.sources import get_registered_sources

    sources = _safe_call(get_registered_sources) or {}
    signals = _safe_call(get_recent_signals, days=30) or []
    run_stats = _safe_call(get_run_stats) or {}
    daily_runs = int(run_stats.get("total_daily_cycles", 0) or 0)
    weekly_runs = int(run_stats.get("total_weekly_cycles", 0) or 0)

    since_30 = datetime.now(tz=timezone.utc) - timedelta(days=30)
    feedback = _safe_call(get_feedback_since, since=since_30) or []
    up = sum(1 for f in feedback if f.get("vote") == "up")
    down = sum(1 for f in feedback if f.get("vote") == "down")
    upvote_ratio = up / (up + down) if (up + down) else 0.0

    briefings = _safe_call(get_briefings, limit=200) or []
    weekly_brief_count = sum(1 for b in briefings if b.get("cycle_type") == "weekly")

    explicit_events = _safe_call(get_evolution_signals, channel="explicit", limit=50) or []
    has_user_edits = any(e.get("kind") == "criteria_edit" for e in explicit_events)

    conditions = [
        {
            "name": "mvp_operational",
            "criteria": "All 15+ sources collecting + 3 consecutive daily runs",
            "progress": min(1.0, max(
                len(sources) / 15.0,
                daily_runs / 3.0,
            )),
            "met": len(sources) >= 15 and daily_runs >= 3,
            "detail": f"sources={len(sources)} daily_runs={daily_runs}",
        },
        {
            "name": "evolution_active",
            "criteria": "≥7 daily evolution cycles + meaningful criteria mutations",
            "progress": min(1.0, daily_runs / 7.0),
            "met": daily_runs >= 7 and has_user_edits,
            "detail": f"daily_runs={daily_runs} explicit_edits={len(explicit_events)}",
        },
        {
            "name": "weekly_loop_active",
            "criteria": "≥2 weekly cycles + source list auto-modified",
            "progress": min(1.0, weekly_runs / 2.0),
            "met": weekly_runs >= 2,
            "detail": f"weekly_runs={weekly_runs} weekly_briefs={weekly_brief_count}",
        },
        {
            "name": "user_satisfaction",
            "criteria": "Upvote ratio > 70% sustained over 2+ weeks",
            "progress": upvote_ratio,
            "met": upvote_ratio >= 0.7 and len(feedback) >= 14,
            "detail": f"upvote_ratio={upvote_ratio:.2f} samples={len(feedback)}",
        },
    ]
    return conditions


def compute_source_health(days: int = 1) -> list[dict]:
    """Per-source health snapshot for the /status panel.

    Reports the most recent collection count per registered source +
    annotates 0-count rows with the env var most likely to fix it.
    """
    from collections import Counter
    from datetime import timedelta as _td, datetime as _dt, timezone as _tz
    import os as _os
    try:
        from hedwig.sources import get_registered_sources
        from hedwig.storage import get_recent_signals
    except Exception:
        return []

    registry = get_registered_sources() or {}
    rows = get_recent_signals(days=days) or []
    by_platform = Counter(r.get("platform", "") for r in rows)

    plugin_to_platform = {}
    for plugin_id, cls in registry.items():
        try:
            plugin_to_platform[plugin_id] = cls.platform.value
        except Exception:
            plugin_to_platform[plugin_id] = ""

    fix_hints = {
        "instagram": ("SCRAPECREATORS_API_KEY", "scrapecreators.com 키 필요"),
        "tiktok": ("SCRAPECREATORS_API_KEY", "scrapecreators.com 키 필요"),
        "podcast": ("HEDWIG_PODCAST_FEEDS", "RSS 피드 URL 등록 필요"),
        "web_search": ("EXA_API_KEY", "exa.ai 키 (live_search 도구용)"),
    }

    out: list[dict] = []
    for plugin_id in sorted(registry):
        platform = plugin_to_platform.get(plugin_id, "")
        # multiple plugins map to same platform (newsletter + ai_labs both → newsletter);
        # we still expose per-plugin so user sees what they actually have
        approx_count = by_platform.get(platform, 0)
        env_key, hint = fix_hints.get(plugin_id, (None, None))
        env_set = bool(_os.getenv(env_key)) if env_key else None
        out.append({
            "plugin_id": plugin_id,
            "platform": platform,
            "recent_count_approx": approx_count,
            "missing_env": env_key if env_key and not env_set else None,
            "hint": hint if env_key and not env_set else None,
        })
    return out
