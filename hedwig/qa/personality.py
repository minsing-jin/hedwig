"""Feed personality weekly aggregator (Phase 7 S9).

Reads behavior_events + feedback over the last N days and returns a
"feed personality" summary surfaced on /profile and in the weekly brief.
"""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta, timezone


def compute_feed_personality(days: int = 7) -> dict:
    try:
        from hedwig.storage import get_behavior_events, get_feedback_since
    except ImportError:
        return {}

    since = datetime.now(tz=timezone.utc) - timedelta(days=days)
    feedback = []
    try:
        feedback = get_feedback_since(since=since) or []
    except Exception:
        feedback = []

    events = get_behavior_events(limit=2000) or []
    # Filter by captured_at since
    events = [
        e for e in events
        if (e.get("captured_at") or "") >= since.isoformat()
    ]

    # Up/Down counts
    up = sum(1 for f in feedback if f.get("vote") == "up")
    down = sum(1 for f in feedback if f.get("vote") == "down")
    upvote_ratio = up / (up + down) if (up + down) else 0.0

    # Time-of-day bucket (UTC hour)
    hour_counter: Counter[int] = Counter()
    for f in feedback:
        ts = (f.get("captured_at") or "")[:19]
        if len(ts) >= 13:
            try:
                h = int(ts[11:13])
                hour_counter[h] += 1
            except Exception:
                pass

    fav_hour = max(hour_counter, key=hour_counter.get) if hour_counter else None

    # Dwell stats from behavior_events
    dwells = [int(e.get("dwell_ms") or 0) for e in events
               if e.get("event_type") == "dwell" and (e.get("dwell_ms") or 0) > 0]
    avg_dwell = (sum(dwells) / len(dwells)) if dwells else 0
    skip_count = sum(1 for e in events if e.get("event_type") == "skip")
    save_count = sum(1 for e in events if e.get("event_type") == "save")
    share_count = sum(1 for e in events if e.get("event_type") == "share")
    view_count = sum(1 for e in events if e.get("event_type") == "view_end")

    # Top platforms — by behavior beacon mostly empty (signal_id only),
    # so derive from upvoted signals' platforms
    plat_counter: Counter[str] = Counter()
    if up > 0:
        try:
            from hedwig.storage import get_recent_signals
            sigs = get_recent_signals(days=days) or []
            up_ids = {str(f.get("signal_id", "")) for f in feedback if f.get("vote") == "up"}
            for s in sigs:
                if str(s.get("id", "")) in up_ids and s.get("platform"):
                    plat_counter[s["platform"]] += 1
        except Exception:
            pass

    skip_ratio = (skip_count / max(1, view_count)) if view_count else 0.0

    return {
        "days": days,
        "upvote_ratio": round(upvote_ratio, 3),
        "feedback_count": up + down,
        "favorite_hour_utc": fav_hour,
        "avg_dwell_ms": int(avg_dwell),
        "view_count": view_count,
        "skip_count": skip_count,
        "save_count": save_count,
        "share_count": share_count,
        "skip_ratio": round(skip_ratio, 3),
        "top_platforms": [{"platform": p, "count": c}
                           for p, c in plat_counter.most_common(5)],
    }
