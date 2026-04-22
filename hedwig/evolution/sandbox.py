"""Mutation sandbox — preview the effect of a candidate algorithm.yaml change.

Given a set of fake-feedback events + a candidate algorithm config, compute a
synthetic fitness score without touching the live config. Used for:
  - User's "what if I doubled bandit weight?" exploration
  - Meta-Evolution shadow-mode decisions (Phase 4 consumer)

This is pure Python and does not require any ML library — it scores based on
the signed upvote/downvote events already persisted plus optional injected
events.
"""
from __future__ import annotations

import copy
from datetime import datetime, timedelta, timezone


def _upvote_ratio_from_events(events: list[dict]) -> float:
    up = sum(1 for e in events if e.get("kind") in ("upvote", "qa_accept"))
    down = sum(1 for e in events if e.get("kind") in ("downvote", "qa_reject"))
    total = up + down
    return up / total if total else 0.0


def _retention_from_events(events: list[dict]) -> float:
    """Unique active days in the event stream, normalized to [0, 1] over 28."""
    days: set[str] = set()
    for e in events:
        at = e.get("captured_at") or e.get("at") or ""
        if isinstance(at, str) and len(at) >= 10:
            days.add(at[:10])
    return min(1.0, len(days) / 28.0)


def _acceptance_rate_from_events(events: list[dict]) -> float:
    """Share of Q&A interactions that were explicitly accepted."""
    asks = sum(1 for e in events if e.get("kind") in ("qa_ask", "qa_accept", "qa_reject"))
    accepts = sum(1 for e in events if e.get("kind") == "qa_accept")
    if asks <= 0:
        return 0.0
    return min(1.0, accepts / asks)


def _weight_sum_normalization_bonus(algo_config: dict, magnitude: float = 0.1) -> float:
    """Reward balanced ensemble, penalize monoculture (single component > 0.8 share)."""
    ranking = algo_config.get("ranking", {}).get("components", {}) or {}
    weights = [c.get("weight", 0) for c in ranking.values() if c.get("enabled")]
    total = sum(weights) or 1.0
    max_share = max((w / total for w in weights), default=0.0)
    if max_share > 0.8:
        return -magnitude
    if 0.3 <= max_share <= 0.5:
        return magnitude * 0.5
    return 0.0


def synthesize_fitness(
    candidate_config: dict,
    recent_events: list[dict] | None = None,
    injected_events: list[dict] | None = None,
) -> dict:
    """Compute synthetic fitness using the weights declared in algorithm.yaml.

    Reads ``candidate_config.fitness``:
      short_horizon.weight × upvote_ratio
      + long_horizon.weight × (retention × acceptance)
      + diversity bonus (if enabled)

    When an event stream has no Q&A/vote activity, retention and acceptance
    collapse to 0 and the prediction degrades gracefully toward 0. This is
    the cheap shadow-mode scorer; full replay-based fitness belongs to a
    future offline evaluator (tracked in VISION §14).
    """
    events = list(recent_events or [])
    events.extend(injected_events or [])

    fitness_cfg = candidate_config.get("fitness", {}) or {}
    sh_w = float(fitness_cfg.get("short_horizon", {}).get("weight", 0.6))
    lh_w = float(fitness_cfg.get("long_horizon", {}).get("weight", 0.4))
    total_w = sh_w + lh_w or 1.0
    sh_w, lh_w = sh_w / total_w, lh_w / total_w

    upvote_ratio = _upvote_ratio_from_events(events)
    retention = _retention_from_events(events)
    acceptance = _acceptance_rate_from_events(events)
    long_horizon_score = retention * acceptance

    diversity_cfg = fitness_cfg.get("diversity_bonus", {}) or {}
    div_bonus = 0.0
    if diversity_cfg.get("enabled", True):
        div_bonus = _weight_sum_normalization_bonus(
            candidate_config,
            magnitude=float(diversity_cfg.get("magnitude", 0.1)),
        )

    predicted = sh_w * upvote_ratio + lh_w * long_horizon_score + div_bonus
    predicted = max(0.0, min(1.0, predicted))

    return {
        "upvote_ratio": round(upvote_ratio, 4),
        "retention": round(retention, 4),
        "acceptance": round(acceptance, 4),
        "long_horizon_score": round(long_horizon_score, 4),
        "diversity_bonus": round(div_bonus, 4),
        "predicted_fitness": round(predicted, 4),
        "weights": {"short_horizon": round(sh_w, 4), "long_horizon": round(lh_w, 4)},
        "n_events": len(events),
    }


def load_recent_events(days: int = 28, limit: int = 500) -> list[dict]:
    """Pull actual recent feedback + Q&A events for sandbox input."""
    since = datetime.now(tz=timezone.utc) - timedelta(days=days)
    events: list[dict] = []

    try:
        from hedwig.storage import get_evolution_signals
    except ImportError:
        return events

    for ev in get_evolution_signals(since=since, limit=limit):
        events.append({
            "kind": ev.get("kind"),
            "weight": ev.get("weight", 1.0),
            "captured_at": ev.get("captured_at"),
        })

    # Upvote/downvote events live in the legacy `feedback` table
    try:
        from hedwig.storage import get_feedback_since
        for row in get_feedback_since(since=since) or []:
            vote = row.get("vote")
            if vote in ("up", "down"):
                events.append({
                    "kind": "upvote" if vote == "up" else "downvote",
                    "weight": 1.0,
                    "captured_at": row.get("captured_at"),
                })
    except Exception:
        pass

    return events


def run_sandbox(
    candidate_config: dict,
    baseline_config: dict,
    injected_events: list[dict] | None = None,
) -> dict:
    """Compare candidate vs. baseline config on the same event pool."""
    events = load_recent_events()
    baseline = synthesize_fitness(baseline_config, recent_events=events)
    candidate = synthesize_fitness(
        candidate_config, recent_events=events, injected_events=injected_events or [],
    )
    delta = candidate["predicted_fitness"] - baseline["predicted_fitness"]
    return {
        "baseline": baseline,
        "candidate": candidate,
        "delta": round(delta, 4),
        "recommend": "adopt" if delta >= 0.05 else ("reject" if delta < 0 else "inconclusive"),
    }


def make_candidate(baseline: dict, perturbations: dict[str, float]) -> dict:
    """Produce a candidate config by adjusting ranking component weights.

    Args:
        baseline: original algorithm.yaml dict
        perturbations: {component_name: new_weight}, e.g. {"bandit": 0.3}
    """
    out = copy.deepcopy(baseline)
    comps = out.setdefault("ranking", {}).setdefault("components", {})
    for name, new_weight in perturbations.items():
        spec = comps.setdefault(name, {"enabled": True, "weight": 0.0})
        spec["weight"] = float(new_weight)
        # auto-enable any component we explicitly touch
        spec["enabled"] = True
    return out
