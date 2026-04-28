"""REINFORCE-lite RLHF for LTR weights (S8.6).

Real RLHF needs PPO + reward model + value function. We compress to the
single-user case:

  - Policy: the LTR logistic ranker. Each candidate gets π(a|s) = σ(w·x).
  - Action: rank candidates and "deliver" the top-k.
  - Reward: per-candidate signed reward in [-1, 1] derived from observed
    feedback (upvote=+1, save=+1, dwell≥3s=+0.5, downvote=-1, skip=-0.3).
  - Update: REINFORCE — Δw ∝ Σ (r_i - baseline) · ∇log π(a_i|s).

Runs once per weekly cycle. Weights are persisted via the existing
`save_weights` so the next LTRRanker instance picks them up.
"""
from __future__ import annotations

import logging
import math
from datetime import datetime, timedelta, timezone

logger = logging.getLogger(__name__)


def _rewards_from_recent(days: int = 14) -> dict[str, float]:
    """signal_id → reward in [-1, 1]."""
    since = datetime.now(tz=timezone.utc) - timedelta(days=days)
    rewards: dict[str, float] = {}
    try:
        from hedwig.storage import get_behavior_events, get_feedback_since
    except ImportError:
        return rewards

    try:
        for r in get_feedback_since(since=since) or []:
            sid = str(r.get("signal_id") or "")
            if not sid:
                continue
            if r.get("vote") == "up":
                rewards[sid] = max(rewards.get(sid, 0.0), 1.0)
            elif r.get("vote") == "down":
                rewards[sid] = min(rewards.get(sid, 0.0), -1.0)
    except Exception:
        pass

    try:
        evs = get_behavior_events(limit=2500) or []
        for e in evs:
            if (e.get("captured_at") or "") < since.isoformat():
                continue
            sid = str(e.get("signal_id") or "")
            if not sid:
                continue
            et = e.get("event_type")
            if et in ("save", "share"):
                rewards[sid] = max(rewards.get(sid, 0.0), 1.0)
            elif et == "dwell" and (e.get("dwell_ms") or 0) >= 3000:
                rewards[sid] = max(rewards.get(sid, 0.0), 0.5)
            elif et == "skip":
                rewards[sid] = min(rewards.get(sid, 0.0), -0.3)
    except Exception:
        pass

    return rewards


def reinforce_update(
    criteria_keywords: list[str],
    days: int = 14,
    learning_rate: float = 0.05,
) -> dict:
    """One REINFORCE step on the active LTR weights.

    Returns a status dict; caller (weekly cycle) logs it.
    """
    rewards = _rewards_from_recent(days=days)
    if len(rewards) < 5:
        return {"updated": False, "reason": "not enough rewards (<5)"}

    try:
        from hedwig.engine.ensemble.ltr import (
            DEFAULT_PRIOR_WEIGHTS,
            FEATURE_REGISTRY,
            _active_features,
            _feature_vector,
            _load_feedback_token_sets,
            _predict,
            load_weights,
            save_weights,
        )
        from hedwig.models import Platform, RawPost
        from hedwig.storage import get_recent_signals
    except ImportError:
        return {"updated": False, "reason": "ltr unavailable"}

    signals = get_recent_signals(days=days) or []
    id_to_row = {str(s.get("id", "")): s for s in signals}
    matched = [(sid, r) for sid, r in rewards.items() if sid in id_to_row]
    if len(matched) < 5:
        return {"updated": False, "reason": "no matched signal+reward pairs"}

    features = _active_features()
    pos_tokens, neg_tokens = _load_feedback_token_sets(days=days)

    # Reconstruct RawPosts for feature extraction
    reconstructed: list[RawPost] = []
    sid_to_idx: dict[str, int] = {}
    for sid, _ in matched:
        s = id_to_row[sid]
        try:
            reconstructed.append(RawPost(
                platform=Platform(s.get("platform", "custom")),
                external_id=str(s.get("external_id") or s.get("id") or ""),
                title=s.get("title", ""), url=s.get("url", ""),
                content=s.get("content", ""), author=s.get("author", ""),
                score=s.get("platform_score", 0) or 0,
                comments_count=s.get("comments_count", 0) or 0,
            ))
            sid_to_idx[sid] = len(reconstructed) - 1
        except Exception:
            pass

    base_ctx = {
        "criteria_keywords": criteria_keywords,
        "same_cycle_posts": reconstructed,
        "positive_tokens": pos_tokens,
        "negative_tokens": neg_tokens,
    }

    # Compute baseline = mean reward (variance-reduction trick)
    avg_r = sum(r for _, r in matched) / max(1, len(matched))

    weights, bias = load_weights()
    for name in features:
        weights.setdefault(name, DEFAULT_PRIOR_WEIGHTS.get(name, 0.5))

    # REINFORCE: Δw_k = Σ (r_i - avg_r) · (y_i - π_i) · x_ik
    # where y_i = 1 if r_i > 0 else 0 (treated as taken-action target).
    n_steps = 0
    for sid, r in matched:
        idx = sid_to_idx.get(sid)
        if idx is None:
            continue
        post = reconstructed[idx]
        feats = _feature_vector(post, features, base_ctx)
        pi = _predict(feats, weights, bias)
        y = 1.0 if r > 0 else 0.0
        advantage = r - avg_r
        err = (y - pi) * advantage
        bias += learning_rate * err
        for fname, fval in feats.items():
            weights[fname] = weights.get(fname, 0.0) + learning_rate * err * fval
        n_steps += 1

    save_weights(weights, bias, meta={
        "trained_at": datetime.now(tz=timezone.utc).isoformat(),
        "method": "reinforce_lite",
        "n_steps": n_steps,
        "lr": learning_rate,
        "baseline": avg_r,
    })
    return {
        "updated": True, "n_steps": n_steps, "baseline": round(avg_r, 4),
        "lr": learning_rate, "weights_keys": list(weights.keys()),
    }
