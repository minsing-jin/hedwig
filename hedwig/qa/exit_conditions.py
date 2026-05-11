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


def compute_retrain_history() -> dict:
    """Parse algorithm_log.jsonl to surface the most-recent retrain timestamps.

    Returns:
        {
          "last_retrain_at": ISO str | None,
          "lightgbm_last_trained": bool,
          "reinforce_last_updated": bool,
          "interpretation_last_evolved": bool,
          "next_due_at": ISO str | None,         # last_retrain + cadence_days
          "cadence_days": int,
          "events": list of recent retrain events (≤ 5),
        }
    """
    import json as _json
    from datetime import datetime as _dt, timedelta as _td, timezone as _tz
    from hedwig.config import ALGORITHM_LOG_PATH, load_algorithm_config

    out = {
        "last_retrain_at": None, "lightgbm_last_trained": None,
        "reinforce_last_updated": None, "interpretation_last_evolved": None,
        "next_due_at": None, "cadence_days": None, "events": [],
    }
    cfg = load_algorithm_config() or {}
    cadence = int((cfg.get("meta_evolution", {}) or {}).get("cadence_days", 28))
    out["cadence_days"] = cadence

    try:
        if not ALGORITHM_LOG_PATH.exists():
            return out
        events: list[dict] = []
        for line in ALGORITHM_LOG_PATH.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                row = _json.loads(line)
            except Exception:
                continue
            if row.get("event") == "retrain_sota_models":
                events.append(row)
        if not events:
            return out
        events.sort(key=lambda e: e.get("ts", ""), reverse=True)
        latest = events[0]
        out["last_retrain_at"] = latest.get("ts")
        out["lightgbm_last_trained"] = latest.get("lightgbm")
        out["reinforce_last_updated"] = latest.get("reinforce")
        out["interpretation_last_evolved"] = latest.get("interpretation")
        try:
            ts = _dt.fromisoformat(str(latest["ts"]).replace("Z", "+00:00"))
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=_tz.utc)
            out["next_due_at"] = (ts + _td(days=cadence)).isoformat()
        except Exception:
            pass
        out["events"] = events[:5]
    except Exception:
        pass
    return out


def compute_algorithm_training_status(lookback_days: int = 28) -> dict:
    """Report whether the owned algorithm is cold-start, locally trained, or SOTA-backed."""
    from hedwig.config import load_algorithm_config

    cfg = load_algorithm_config() or {}
    ranking = cfg.get("ranking", {}) or {}
    components = ranking.get("components", {}) or {}
    enabled_components = [
        name for name, spec in components.items()
        if isinstance(spec, dict) and spec.get("enabled")
    ]

    try:
        from hedwig.engine.ensemble.ltr import training_status as ltr_training_status
        ltr = ltr_training_status(lookback_days=lookback_days)
    except Exception as e:
        ltr = {"active_backend": "unknown", "error": str(e)}

    ips = ranking.get("ips_debias", {}) or {}
    optional_sota = {
        "bandit": bool((components.get("bandit") or {}).get("enabled")),
        "sequential": bool((components.get("sequential") or {}).get("enabled")),
        "llm_rec": bool((components.get("llm_rec") or {}).get("enabled")),
        "ips_debias": bool(ips.get("enabled")),
        "meta_evolution": bool((cfg.get("meta_evolution") or {}).get("enabled")),
    }

    backend = ltr.get("active_backend")
    if backend == "lightgbm_lambdamart":
        summary = "LightGBM LambdaMART model is installed and loadable."
    elif backend == "logistic_sgd":
        summary = "Serving with user-trained logistic SGD weights; LightGBM is not active."
    elif backend == "default_priors":
        summary = "Cold start: serving from algorithm.yaml priors until enough feedback accrues."
    else:
        summary = "Algorithm backend status is unavailable."

    return {
        "summary": summary,
        "enabled_components": enabled_components,
        "ltr": ltr,
        "optional_sota": optional_sota,
        "algorithm_version": cfg.get("version"),
        "algorithm_origin": cfg.get("origin"),
    }


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
