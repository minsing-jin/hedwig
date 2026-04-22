"""last30days-inspired signal enrichment (v3, Phase 1 L2 absorption).

Upstream: https://github.com/mvanhorn/last30days-skill

Ideas absorbed:
  1. **Cross-temporal persistence** — topics that keep appearing over
     multiple days get a boost (sustained interest is signal).
  2. **Saturation penalty** — the N-th occurrence of a near-duplicate
     same-day topic gets exponentially dampened (kills echo-chamber spam).
  3. **Velocity-over-volume** — engagement acceleration matters more than
     raw count; a fast-rising niche topic can beat a slow mainstream one.

These enrichments feed `engagement_velocity` and `cross_platform_convergence`
in `engine/pre_scorer.py`. The base pre_scorer formula is unchanged; this
module supplies richer inputs when historical context is available.
"""
from __future__ import annotations

import math
import re
from collections import Counter
from datetime import datetime, timedelta, timezone

from hedwig.models import RawPost


def _title_key(post: RawPost) -> str:
    """Canonical representation used for near-duplicate detection."""
    return re.sub(r"[^a-z0-9]+", " ", (post.title or "").lower()).strip()


def topic_persistence_score(
    post: RawPost,
    historical_posts: list[RawPost],
    lookback_days: int = 14,
) -> float:
    """Returns 0..1 — how persistently this topic has appeared in history.

    A topic that shows up on many distinct days scores higher than one that
    spiked once. Uses token-overlap as a fast proxy for topic identity.
    """
    if not historical_posts:
        return 0.0

    tokens = set(_title_key(post).split())
    if not tokens:
        return 0.0

    cutoff = datetime.now(tz=timezone.utc) - timedelta(days=lookback_days)
    days_with_match: set[str] = set()

    for other in historical_posts:
        if other.published_at < cutoff:
            continue
        other_tokens = set(_title_key(other).split())
        if not other_tokens:
            continue
        overlap = len(tokens & other_tokens) / max(len(tokens | other_tokens), 1)
        if overlap >= 0.3:
            days_with_match.add(other.published_at.date().isoformat())

    # Log-scale: 1 day = ~0, 3 days = ~0.5, 7+ days → ~1
    return min(1.0, math.log1p(len(days_with_match)) / math.log1p(lookback_days / 2))


def saturation_penalty(
    post: RawPost,
    same_cycle_posts: list[RawPost],
) -> float:
    """Returns a multiplier in (0, 1] — penalizes repeated same-day duplicates.

    The first occurrence keeps weight 1.0; each additional near-duplicate in
    the same cycle drops it exponentially. This suppresses echo-chamber spam
    and platform-reposts without removing them outright.
    """
    tokens = set(_title_key(post).split())
    if not tokens:
        return 1.0

    near_dup_count = 0
    for other in same_cycle_posts:
        if other is post:
            continue
        other_tokens = set(_title_key(other).split())
        if not other_tokens:
            continue
        overlap = len(tokens & other_tokens) / max(len(tokens | other_tokens), 1)
        if overlap >= 0.5:
            near_dup_count += 1

    # each near-dup cuts the weight by ~30%
    return max(0.2, math.exp(-0.35 * near_dup_count))


def velocity_bonus(
    post: RawPost,
    platform_activity_history: dict[str, list[float]] | None = None,
) -> float:
    """Returns 0..0.3 extra points — rewards fast-rising content.

    Needs a dict of historical engagement-per-hour samples to compute
    acceleration. When history is unavailable, returns 0.0 (no bonus).
    """
    if not platform_activity_history:
        return 0.0
    samples = platform_activity_history.get(post.platform.value) or []
    if len(samples) < 2:
        return 0.0
    baseline = sum(samples) / len(samples)
    latest = samples[-1]
    if baseline <= 0:
        return 0.0
    ratio = latest / baseline
    # 1.5x baseline → 0.15, 3x → 0.3, clamp to 0.3
    return max(0.0, min(0.3, (ratio - 1.0) * 0.15))


def enrich_score(
    post: RawPost,
    base_score: float,
    same_cycle_posts: list[RawPost],
    historical_posts: list[RawPost] | None = None,
    platform_activity_history: dict[str, list[float]] | None = None,
) -> float:
    """Apply last30days-inspired enrichment to an existing pre_score.

    Args:
        post: The post being scored.
        base_score: Output of engine.pre_scorer.pre_score (0..1).
        same_cycle_posts: All posts collected in the current cycle.
        historical_posts: Posts from prior cycles (optional).
        platform_activity_history: Per-platform engagement time-series (optional).

    Returns:
        Adjusted score in [0, 1].
    """
    persistence = topic_persistence_score(post, historical_posts or [])
    saturation = saturation_penalty(post, same_cycle_posts)
    velocity = velocity_bonus(post, platform_activity_history)

    # Persistence adds up to +0.15, velocity adds up to +0.3, saturation multiplies.
    adjusted = base_score * saturation + 0.15 * persistence + velocity
    return round(max(0.0, min(1.0, adjusted)), 4)
