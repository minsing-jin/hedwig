"""Critical layer — the Instant tier of the 4-tier temporal lattice.

Runs a lightweight poll loop every `poll_interval_minutes` (default 20)
separate from the daily/weekly pipelines. Uses the existing sources but
with:
  - aggressive recency decay (half-life 6h vs 48h)
  - stricter convergence requirement (≥2 platforms)
  - relevance threshold 0.75+
  - LLM judge applied only to top-3 candidates

Hit the threshold → push to Critical delivery channels. That's it. This
intentionally does NOT run the evolution cycle.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from hedwig.engine.pre_scorer import (
    compute_engagement_velocity,
    compute_recency_decay,
    compute_source_authority,
    detect_cross_platform_convergence,
)
from hedwig.models import RawPost

logger = logging.getLogger(__name__)


def critical_score(
    post: RawPost,
    cohort: list[RawPost],
) -> tuple[float, dict]:
    """Compute a critical-layer priority score (0..1) + its factor breakdown."""
    engagement = compute_engagement_velocity(post)
    authority = compute_source_authority(post)
    recency = compute_recency_decay(post, half_life_hours=6.0)
    convergence = detect_cross_platform_convergence(post, cohort, threshold=0.3)

    # Critical demands both velocity AND cross-platform presence
    score = (
        0.35 * engagement
        + 0.15 * authority
        + 0.30 * recency
        + 0.20 * convergence
    )
    factors = {
        "engagement": round(engagement, 3),
        "authority": round(authority, 3),
        "recency_6h_halflife": round(recency, 3),
        "convergence": round(convergence, 3),
    }
    return round(max(0.0, min(1.0, score)), 4), factors


def filter_critical(
    posts: list[RawPost],
    threshold: float = 0.75,
    min_convergence_platforms: int = 2,
) -> list[tuple[RawPost, float, dict]]:
    """Return only posts that qualify as Critical (instant-tier)."""
    out: list[tuple[RawPost, float, dict]] = []
    for post in posts:
        score, factors = critical_score(post, posts)
        # Hard gate on convergence — critical means *multi-platform agreement*
        if factors["convergence"] < (min_convergence_platforms * 0.3):
            continue
        if score >= threshold:
            out.append((post, score, factors))
    out.sort(key=lambda t: t[1], reverse=True)
    return out


async def run_critical_cycle(
    *,
    sources_registry=None,
    deliver=None,
    max_delivered: int = 5,
) -> dict:
    """One run of the critical poll. Returns summary dict.

    Args:
        sources_registry: callable returning {plugin_id: source_class}. When
            None, imports from hedwig.sources at call time so the engine
            package itself doesn't hard-link to the sources registry.
        deliver: optional async callable `(ScoredSignal) -> None` that the
            engine calls for each qualified item. Supplied by the host app
            (dashboard or CLI) so the engine package remains delivery-agnostic.
        max_delivered: cap on how many top signals to deliver this cycle.
    """
    if sources_registry is None:
        from hedwig.sources import get_registered_sources
        sources_registry = get_registered_sources

    registry = sources_registry() or {}
    collected: list[RawPost] = []
    for plugin_id, source_cls in registry.items():
        try:
            inst = source_cls()
            posts = await inst.fetch(limit=10)
            collected.extend(posts)
        except Exception as e:
            logger.debug("critical: source %s skipped (%s)", plugin_id, e)

    qualified = filter_critical(collected)
    logger.info(
        "Critical cycle: %d posts scanned, %d qualified (threshold=0.75, 2+ platforms)",
        len(collected), len(qualified),
    )

    delivered = 0
    if qualified and deliver is not None:
        from hedwig.models import ScoredSignal, UrgencyLevel
        for post, score, factors in qualified[:max_delivered]:
            signal = ScoredSignal(
                raw=post,
                relevance_score=score,
                urgency=UrgencyLevel.ALERT,
                why_relevant="Critical-layer: convergence + recency + engagement",
                devils_advocate=f"factors={factors}",
            )
            try:
                await deliver(signal)
                delivered += 1
            except Exception as e:
                logger.warning("critical deliver callback failed: %s", e)

    return {
        "scanned": len(collected),
        "qualified": len(qualified),
        "delivered": delivered,
        "ran_at": datetime.now(tz=timezone.utc).isoformat(),
    }
