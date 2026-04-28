"""Multi-task fitness — MMOE-lite (S8.5).

Real MMOE shares experts across tasks via a neural net. We approximate
without torch by computing 4 task scores from the same event stream and
blending with declared weights:

  - engagement     : upvote_ratio
  - retention      : days_active / 28
  - save_rate      : saves / view_count
  - share_rate     : shares / view_count

Configurable through algorithm.yaml.fitness.multi_task.weights:
    fitness:
      multi_task:
        enabled: true
        weights:
          engagement: 0.4
          retention: 0.3
          save_rate: 0.15
          share_rate: 0.15
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

DEFAULT_WEIGHTS = {
    "engagement": 0.5,
    "retention": 0.25,
    "save_rate": 0.15,
    "share_rate": 0.10,
}


def _load_events(days: int = 28) -> tuple[list[dict], list[dict]]:
    since = datetime.now(tz=timezone.utc) - timedelta(days=days)
    feedback: list[dict] = []
    behavior: list[dict] = []
    try:
        from hedwig.storage import get_behavior_events, get_feedback_since
    except ImportError:
        return feedback, behavior
    try:
        feedback = get_feedback_since(since=since) or []
    except Exception:
        feedback = []
    try:
        behavior = get_behavior_events(limit=2500) or []
        behavior = [
            e for e in behavior
            if (e.get("captured_at") or "") >= since.isoformat()
        ]
    except Exception:
        pass
    return feedback, behavior


def _engagement(feedback: list[dict]) -> float:
    up = sum(1 for f in feedback if f.get("vote") == "up")
    down = sum(1 for f in feedback if f.get("vote") == "down")
    return up / (up + down) if (up + down) else 0.0


def _retention(feedback: list[dict]) -> float:
    days: set[str] = set()
    for f in feedback:
        ts = (f.get("captured_at") or "")[:10]
        if ts:
            days.add(ts)
    return min(1.0, len(days) / 28.0)


def _ratio(events: list[dict], numerator_type: str) -> float:
    views = sum(1 for e in events if e.get("event_type") == "view_end")
    target = sum(1 for e in events if e.get("event_type") == numerator_type)
    return min(1.0, target / views) if views else 0.0


def compute_multi_task_fitness(
    config: dict | None = None,
    days: int = 28,
) -> dict:
    """Return per-task scores + weighted blend.

    config: algorithm.yaml dict (passes fitness.multi_task spec through).
    """
    if config is None:
        try:
            from hedwig.config import load_algorithm_config
            config = load_algorithm_config() or {}
        except Exception:
            config = {}

    spec = (config.get("fitness", {}).get("multi_task") or {})
    weights = {**DEFAULT_WEIGHTS, **(spec.get("weights") or {})}

    feedback, behavior = _load_events(days=days)
    scores = {
        "engagement": _engagement(feedback),
        "retention": _retention(feedback),
        "save_rate": _ratio(behavior, "save"),
        "share_rate": _ratio(behavior, "share"),
    }

    total_w = sum(weights.values()) or 1.0
    weighted = sum(weights.get(k, 0.0) * v for k, v in scores.items()) / total_w

    return {
        "scores": {k: round(v, 4) for k, v in scores.items()},
        "weights": {k: round(weights.get(k, 0.0) / total_w, 4) for k in scores},
        "weighted_total": round(weighted, 4),
        "n_feedback": len(feedback),
        "n_behavior": len(behavior),
    }
