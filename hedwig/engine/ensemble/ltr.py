"""Learning-to-Rank ranker — pure-Python logistic with a **name-keyed** feature registry.

Why name-keyed: meta-evolution can add new features to algorithm.yaml's
``ranking.components.ltr.features`` list. A positional weight vector would
silently break on reshape. Here, weights live as ``{feature_name: weight}``
and the active feature list is driven by algorithm.yaml. Missing weights
default to a mild positive prior (+0.5) so new features contribute rather
than erase.

Feature registry
----------------
Each feature has an extractor registered in :data:`FEATURE_REGISTRY` with
signature ``f(post, context) -> float in [0, 1]``. Built-in features:

    text_relevance, source_authority, engagement_velocity, recency_decay,
    convergence_count, past_upvote_similarity, past_downvote_similarity,
    dwell_time_proxy

Additional features proposed by meta-evolution will be listed in
algorithm.yaml but have no extractor until a human adds one — they score
as a neutral 0.5 so the weighted sum is defined.

Training
--------
``fit_from_history`` runs SGD using only the features currently listed in
algorithm.yaml. Weights are persisted to ``HEDWIG_LTR_WEIGHTS`` (JSON).
"""
from __future__ import annotations

import json
import logging
import math
import os
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable

from hedwig.config import load_algorithm_config
from hedwig.engine.pre_scorer import (
    compute_engagement_velocity,
    compute_recency_decay,
    compute_source_authority,
    compute_text_relevance,
    detect_cross_platform_convergence,
)
from hedwig.models import RawPost

logger = logging.getLogger(__name__)

WEIGHTS_PATH = Path(os.getenv(
    "HEDWIG_LTR_WEIGHTS",
    str(Path.home() / ".hedwig" / "ltr_weights.json"),
))

DEFAULT_FEATURES = [
    "text_relevance",
    "source_authority",
    "engagement_velocity",
    "recency_decay",
    "convergence_count",
    "past_upvote_similarity",
    "past_downvote_similarity",
    "dwell_time_proxy",
]


def _tokens(text: str) -> set[str]:
    return {t for t in re.split(r"[^a-z0-9]+", (text or "").lower()) if len(t) >= 3}


def _similarity(a_tokens: set[str], b_tokens: set[str]) -> float:
    if not a_tokens or not b_tokens:
        return 0.0
    inter = len(a_tokens & b_tokens)
    union = len(a_tokens | b_tokens)
    return inter / union if union else 0.0


def _sigmoid(x: float) -> float:
    if x >= 0:
        z = math.exp(-x)
        return 1.0 / (1.0 + z)
    z = math.exp(x)
    return z / (1.0 + z)


# ---------------------------------------------------------------------------
# Feature registry
# ---------------------------------------------------------------------------

FEATURE_REGISTRY: dict[str, Callable[[RawPost, dict], float]] = {
    "text_relevance": lambda post, ctx: compute_text_relevance(
        post, ctx.get("criteria_keywords") or []
    ),
    "source_authority": lambda post, ctx: compute_source_authority(post),
    "engagement_velocity": lambda post, ctx: compute_engagement_velocity(post),
    "recency_decay": lambda post, ctx: compute_recency_decay(post),
    "convergence_count": lambda post, ctx: detect_cross_platform_convergence(
        post, ctx.get("same_cycle_posts") or []
    ),
    "past_upvote_similarity": lambda post, ctx: _similarity(
        _tokens(f"{post.title} {post.content[:500]}"),
        ctx.get("positive_tokens") or set(),
    ),
    "past_downvote_similarity": lambda post, ctx: _similarity(
        _tokens(f"{post.title} {post.content[:500]}"),
        ctx.get("negative_tokens") or set(),
    ),
    "dwell_time_proxy": lambda post, ctx: min(
        1.0, len(post.content or "") / 3000.0
    ),
}


DEFAULT_PRIOR_WEIGHTS: dict[str, float] = {
    "text_relevance": 1.0,
    "source_authority": 0.8,
    "engagement_velocity": 0.6,
    "recency_decay": 0.5,
    "convergence_count": 0.7,
    "past_upvote_similarity": 1.0,
    "past_downvote_similarity": -1.0,
    "dwell_time_proxy": 0.3,
}
DEFAULT_BIAS = -0.5


def _active_features() -> list[str]:
    """Read the ltr.features list from algorithm.yaml, falling back to defaults."""
    cfg = load_algorithm_config()
    features = (
        cfg.get("ranking", {})
        .get("components", {})
        .get("ltr", {})
        .get("features")
    )
    if isinstance(features, list) and features:
        return [str(f) for f in features]
    return list(DEFAULT_FEATURES)


def load_weights() -> tuple[dict[str, float], float]:
    """Return (feature_weights, bias). Unknown features get the prior."""
    try:
        data = json.loads(WEIGHTS_PATH.read_text())
        weights = {str(k): float(v) for k, v in (data.get("weights") or {}).items()}
        bias = float(data.get("bias", DEFAULT_BIAS))
        return weights, bias
    except Exception:
        return dict(DEFAULT_PRIOR_WEIGHTS), DEFAULT_BIAS


def save_weights(weights: dict[str, float], bias: float, meta: dict | None = None) -> None:
    try:
        WEIGHTS_PATH.parent.mkdir(parents=True, exist_ok=True)
        WEIGHTS_PATH.write_text(json.dumps({
            "weights": weights,
            "bias": bias,
            "meta": meta or {},
        }))
    except Exception as e:
        logger.warning("save_weights failed: %s", e)


def _feature_vector(
    post: RawPost,
    features: list[str],
    context: dict,
) -> dict[str, float]:
    out: dict[str, float] = {}
    for name in features:
        extractor = FEATURE_REGISTRY.get(name)
        if extractor is None:
            # Unknown feature from a meta-evolution proposal — neutral value
            out[name] = 0.5
            continue
        try:
            out[name] = float(extractor(post, context))
        except Exception as e:
            logger.debug("LTR feature %s failed: %s", name, e)
            out[name] = 0.0
    return out


def _predict(
    feats: dict[str, float],
    weights: dict[str, float],
    bias: float,
) -> float:
    logit = bias
    for name, value in feats.items():
        logit += value * weights.get(name, DEFAULT_PRIOR_WEIGHTS.get(name, 0.5))
    return _sigmoid(logit)


class LTRRanker:
    name = "ltr"

    def __init__(self, criteria_keywords: list[str] | None = None) -> None:
        self.weights, self.bias = load_weights()
        self.criteria_keywords = criteria_keywords or []
        self.features = _active_features()

    async def score_posts(self, posts: list[RawPost], context: dict | None = None) -> list[float]:
        if not posts:
            return []
        context = dict(context or {})
        context.setdefault("criteria_keywords", self.criteria_keywords)
        context.setdefault("same_cycle_posts", posts)
        pos_tokens, neg_tokens = _load_feedback_token_sets()
        context.setdefault("positive_tokens", pos_tokens)
        context.setdefault("negative_tokens", neg_tokens)

        return [
            _predict(_feature_vector(p, self.features, context), self.weights, self.bias)
            for p in posts
        ]


def _load_feedback_token_sets(days: int = 28) -> tuple[set[str], set[str]]:
    since = datetime.now(tz=timezone.utc) - timedelta(days=days)
    pos_tokens: set[str] = set()
    neg_tokens: set[str] = set()

    try:
        from hedwig.storage import get_feedback_since, get_recent_signals
    except ImportError:
        return pos_tokens, neg_tokens

    try:
        rows = get_feedback_since(since=since) or []
    except Exception:
        rows = []

    up_ids = {str(r["signal_id"]) for r in rows if r.get("vote") == "up"}
    down_ids = {str(r["signal_id"]) for r in rows if r.get("vote") == "down"}
    try:
        signals = get_recent_signals(days=days) or []
    except Exception:
        signals = []

    for s in signals:
        sid = str(s.get("id", ""))
        tokens = _tokens(f"{s.get('title', '')} {s.get('content', '')[:300]}")
        if sid in up_ids:
            pos_tokens |= tokens
        if sid in down_ids:
            neg_tokens |= tokens
    return pos_tokens, neg_tokens


def fit_from_history(
    criteria_keywords: list[str],
    lookback_days: int = 90,
    lr: float = 0.05,
    epochs: int = 10,
) -> dict:
    """One-pass SGD over stored feedback. Safe to call any time."""
    since = datetime.now(tz=timezone.utc) - timedelta(days=lookback_days)

    try:
        from hedwig.storage import get_feedback_since, get_recent_signals
    except ImportError:
        return {"trained": False, "reason": "storage not available"}

    try:
        rows = get_feedback_since(since=since) or []
    except Exception:
        rows = []

    if len(rows) < 5:
        return {"trained": False, "reason": "not enough feedback events (<5)"}

    try:
        signals = get_recent_signals(days=lookback_days) or []
    except Exception:
        signals = []

    features = _active_features()
    pos_tokens, neg_tokens = _load_feedback_token_sets(days=lookback_days)

    from hedwig.models import Platform, RawPost as _RP
    reconstructed: list[RawPost] = []
    id_to_index: dict[str, int] = {}
    for idx, s in enumerate(signals):
        try:
            reconstructed.append(_RP(
                platform=Platform(s.get("platform", "custom")),
                external_id=str(s.get("external_id") or s.get("id") or ""),
                title=s.get("title", ""),
                url=s.get("url", ""),
                content=s.get("content", ""),
                author=s.get("author", ""),
                score=s.get("platform_score", 0) or 0,
                comments_count=s.get("comments_count", 0) or 0,
            ))
            id_to_index[str(s.get("id", ""))] = idx
        except Exception:
            continue

    base_ctx = {
        "criteria_keywords": criteria_keywords,
        "same_cycle_posts": reconstructed,
        "positive_tokens": pos_tokens,
        "negative_tokens": neg_tokens,
    }

    examples: list[tuple[dict[str, float], int]] = []
    for r in rows:
        sid = str(r.get("signal_id", ""))
        idx = id_to_index.get(sid)
        if idx is None:
            continue
        post = reconstructed[idx]
        label = 1 if r.get("vote") == "up" else 0
        feats = _feature_vector(post, features, base_ctx)
        examples.append((feats, label))

    if not examples:
        return {"trained": False, "reason": "no matched signal+feedback pairs"}

    weights, bias = load_weights()
    # Seed any missing feature weights with the prior before training
    for name in features:
        weights.setdefault(name, DEFAULT_PRIOR_WEIGHTS.get(name, 0.5))

    for _ in range(epochs):
        for feats, y in examples:
            p = _predict(feats, weights, bias)
            err = y - p
            bias += lr * err
            for name, value in feats.items():
                weights[name] = weights.get(name, 0.0) + lr * err * value

    save_weights(weights, bias, meta={
        "trained_at": datetime.now(tz=timezone.utc).isoformat(),
        "n_examples": len(examples),
        "features": features,
        "epochs": epochs,
        "lr": lr,
    })
    return {
        "trained": True,
        "n_examples": len(examples),
        "features": features,
        "bias": bias,
        "weights": weights,
    }
