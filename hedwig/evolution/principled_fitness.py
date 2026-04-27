"""Principled fitness — applies seed.yaml.evaluation_principles weights (G9).

seed.yaml declares 6 evaluation principles with explicit weights:
  signal_quality 0.25, self_improvement 0.25, interpretation_depth 0.15,
  source_coverage 0.15, opportunity_insight 0.10, noise_reduction 0.10

The legacy ``synthesize_fitness`` proxy (upvote_ratio + diversity bonus)
ignored these principles. This module computes each principle as a 0..1
score from concrete signals + feedback + briefings, then blends with the
declared weights so meta-evolution shadow-mode actually optimizes the
thing the spec asked for.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import yaml


SEED_PATH = Path(__file__).resolve().parent.parent.parent / "seed.yaml"


def _principles_from_seed() -> list[dict]:
    try:
        seed = yaml.safe_load(SEED_PATH.read_text())
        return list(seed.get("evaluation_principles") or [])
    except Exception:
        # Fallback to the documented defaults
        return [
            {"name": "signal_quality", "weight": 0.25,
             "description": "Filtered signals are genuinely relevant — upvote ratio > 70%"},
            {"name": "self_improvement", "weight": 0.25,
             "description": "Upvote ratio measurably increases over consecutive weeks"},
            {"name": "interpretation_depth", "weight": 0.15,
             "description": "Each signal includes actionable why + counter-perspective"},
            {"name": "source_coverage", "weight": 0.15,
             "description": "No major AI event missed across platforms"},
            {"name": "opportunity_insight", "weight": 0.10,
             "description": "Weekly briefings surface actionable opportunities"},
            {"name": "noise_reduction", "weight": 0.10,
             "description": "User spends less time filtering"},
        ]


def _signal_quality(feedback: list[dict]) -> float:
    up = sum(1 for f in feedback if f.get("vote") == "up")
    down = sum(1 for f in feedback if f.get("vote") == "down")
    return up / (up + down) if (up + down) else 0.0


def _self_improvement(feedback: list[dict]) -> float:
    """Compare upvote ratio of newer half vs older half. > 0 = improving."""
    if len(feedback) < 6:
        return 0.5  # not enough to judge — neutral
    sorted_fb = sorted(feedback, key=lambda f: f.get("captured_at") or "")
    half = len(sorted_fb) // 2
    older = sorted_fb[:half]
    newer = sorted_fb[half:]
    older_ratio = _signal_quality(older)
    newer_ratio = _signal_quality(newer)
    # Map delta in [-1, 1] to [0, 1] with 0.5 = no change
    delta = newer_ratio - older_ratio
    return max(0.0, min(1.0, 0.5 + delta))


def _interpretation_depth(signals: list[dict]) -> float:
    """Share of recent signals with both why_relevant and devils_advocate populated."""
    if not signals:
        return 0.0
    rich = sum(1 for s in signals
               if (s.get("why_relevant") or "").strip()
               and (s.get("devils_advocate") or "").strip())
    return rich / len(signals)


def _source_coverage(signals: list[dict], registered_count: int) -> float:
    """Fraction of registered sources that produced at least one signal."""
    if registered_count <= 0:
        return 0.0
    seen = {s.get("platform") for s in signals if s.get("platform")}
    return min(1.0, len(seen) / max(8, registered_count))   # 8 minimum to count as coverage


def _opportunity_insight(briefings: list[dict]) -> float:
    """Share of weekly briefings that contain opportunity-laden phrases."""
    weekly = [b for b in briefings if b.get("cycle_type") == "weekly"]
    if not weekly:
        return 0.0
    needles = ("기회", "opportunity", "기회 포착", "opportunity_note",
               "exploration", "약신호")
    hits = 0
    for b in weekly:
        text = (b.get("content") or "").lower()
        if any(n.lower() in text for n in needles):
            hits += 1
    return hits / len(weekly)


def _noise_reduction(signals: list[dict]) -> float:
    """Average relevance_score of delivered signals — higher means we shipped fewer junk items."""
    if not signals:
        return 0.0
    total = sum(float(s.get("relevance_score") or 0) for s in signals)
    return min(1.0, total / len(signals))


def compute_principled_fitness(
    feedback: list[dict] | None = None,
    signals: list[dict] | None = None,
    briefings: list[dict] | None = None,
    registered_count: int | None = None,
) -> dict:
    """Return per-principle scores + weighted total. Loads stats if args missing."""
    if feedback is None:
        try:
            from hedwig.storage import get_feedback_since
            since = datetime.now(tz=timezone.utc) - timedelta(days=28)
            feedback = get_feedback_since(since=since) or []
        except Exception:
            feedback = []
    if signals is None:
        try:
            from hedwig.storage import get_recent_signals
            signals = get_recent_signals(days=14) or []
        except Exception:
            signals = []
    if briefings is None:
        try:
            from hedwig.storage import get_briefings
            briefings = get_briefings(limit=50) or []
        except Exception:
            briefings = []
    if registered_count is None:
        try:
            from hedwig.sources import get_registered_sources
            registered_count = len(get_registered_sources() or {})
        except Exception:
            registered_count = 0

    scores = {
        "signal_quality": _signal_quality(feedback),
        "self_improvement": _self_improvement(feedback),
        "interpretation_depth": _interpretation_depth(signals),
        "source_coverage": _source_coverage(signals, registered_count),
        "opportunity_insight": _opportunity_insight(briefings),
        "noise_reduction": _noise_reduction(signals),
    }

    principles = _principles_from_seed()
    weighted_total = 0.0
    breakdown = []
    for p in principles:
        name = p.get("name")
        weight = float(p.get("weight", 0.0))
        score = float(scores.get(name, 0.0))
        contribution = weight * score
        weighted_total += contribution
        breakdown.append({
            "name": name,
            "weight": weight,
            "score": round(score, 4),
            "contribution": round(contribution, 4),
            "description": p.get("description", ""),
        })

    return {
        "weighted_total": round(weighted_total, 4),
        "breakdown": breakdown,
        "scores": {k: round(v, 4) for k, v in scores.items()},
    }
