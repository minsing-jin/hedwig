"""
Pre-scorer — numeric signal scoring BEFORE LLM evaluation.

Inspired by last30days multi-signal composite scoring:
  - Engagement velocity (platform-normalized)
  - Source authority weight
  - Temporal recency decay
  - Cross-platform convergence detection
  - Text relevance to user criteria

Signals that score below threshold are filtered out before expensive LLM calls.
"""
from __future__ import annotations

import math
import re
from datetime import datetime, timezone
from typing import Optional

from hedwig.models import RawPost


# ---------------------------------------------------------------------------
# Platform-specific engagement normalization baselines
# ---------------------------------------------------------------------------

ENGAGEMENT_BASELINES = {
    "hackernews": {"score": 100, "comments": 50},
    "reddit": {"score": 200, "comments": 50},
    "twitter": {"score": 50, "comments": 10},
    "bluesky": {"score": 20, "comments": 5},
    "youtube": {"score": 1000, "comments": 50},
    "polymarket": {"score": 10000, "comments": 0},  # volume-based
    "arxiv": {"score": 0, "comments": 0},  # no engagement metrics
    "semantic_scholar": {"score": 10, "comments": 0},  # citation-based
}

# Source authority weights (higher = more trusted for AI signals)
SOURCE_AUTHORITY = {
    "hackernews": 0.9,
    "arxiv": 0.95,
    "semantic_scholar": 0.9,
    "papers_with_code": 0.9,
    "reddit": 0.7,
    "twitter": 0.75,
    "bluesky": 0.6,
    "youtube": 0.7,
    "polymarket": 0.8,
    "linkedin": 0.65,
    "geeknews": 0.7,
    "threads": 0.5,
    "newsletter": 0.7,
    "web_search": 0.6,
    "tiktok": 0.4,
    "instagram": 0.4,
    "custom": 0.5,
}


def compute_engagement_velocity(post: RawPost) -> float:
    """Normalize engagement relative to platform baseline. Returns 0.0-1.0."""
    platform = post.platform.value
    baseline = ENGAGEMENT_BASELINES.get(platform, {"score": 100, "comments": 20})

    score_ratio = post.score / max(baseline["score"], 1)
    comment_ratio = post.comments_count / max(baseline["comments"], 1) if baseline["comments"] else 0

    # Weighted combination, clamped to 0.0-1.0
    velocity = max(0.0, min(1.0, (score_ratio * 0.6 + comment_ratio * 0.4)))
    return velocity


def compute_recency_decay(post: RawPost, half_life_hours: float = 48.0) -> float:
    """Exponential decay based on post age. Returns 0.0-1.0."""
    now = datetime.now(tz=timezone.utc)
    age_hours = max(0, (now - post.published_at).total_seconds() / 3600)
    return math.exp(-0.693 * age_hours / half_life_hours)


def compute_source_authority(post: RawPost) -> float:
    """Return source authority weight. 0.0-1.0."""
    return SOURCE_AUTHORITY.get(post.platform.value, 0.5)


def compute_text_relevance(post: RawPost, keywords: list[str]) -> float:
    """Simple keyword-based relevance. Returns 0.0-1.0."""
    if not keywords:
        return 0.5

    text = f"{post.title} {post.content}".lower()
    matches = sum(1 for kw in keywords if kw.lower() in text)
    return min(1.0, matches / max(len(keywords) * 0.3, 1))


def detect_cross_platform_convergence(
    post: RawPost, all_posts: list[RawPost], threshold: float = 0.3
) -> float:
    """Detect if similar content appears across multiple platforms.

    Uses trigram overlap for fuzzy matching. Returns 0.0-1.0 convergence score.
    """
    post_trigrams = _trigrams(post.title.lower())
    if not post_trigrams:
        return 0.0

    other_platforms = set()
    for other in all_posts:
        if other.platform == post.platform:
            continue
        if other.external_id == post.external_id:
            continue
        other_trigrams = _trigrams(other.title.lower())
        if not other_trigrams:
            continue
        overlap = len(post_trigrams & other_trigrams) / max(len(post_trigrams | other_trigrams), 1)
        if overlap >= threshold:
            other_platforms.add(other.platform.value)

    # More platforms mentioning similar content = higher convergence
    return min(1.0, len(other_platforms) * 0.3)


def _trigrams(text: str) -> set[str]:
    """Extract character trigrams from text."""
    words = re.sub(r"[^\w\s]", "", text).split()
    joined = " ".join(words)
    if len(joined) < 3:
        return set()
    return {joined[i : i + 3] for i in range(len(joined) - 2)}


def pre_score(
    post: RawPost,
    all_posts: list[RawPost],
    criteria_keywords: list[str],
) -> float:
    """Compute composite pre-score. Returns 0.0-1.0.

    Formula (inspired by last30days):
      0.25 * text_relevance
    + 0.20 * engagement_velocity
    + 0.20 * source_authority
    + 0.20 * recency
    + 0.15 * cross_platform_convergence
    """
    text_rel = compute_text_relevance(post, criteria_keywords)
    engagement = compute_engagement_velocity(post)
    authority = compute_source_authority(post)
    recency = compute_recency_decay(post)
    convergence = detect_cross_platform_convergence(post, all_posts)

    score = (
        0.25 * text_rel
        + 0.20 * engagement
        + 0.20 * authority
        + 0.20 * recency
        + 0.15 * convergence
    )
    # Defence-in-depth: guarantee 0.0-1.0 contract
    return round(max(0.0, min(1.0, score)), 4)


def pre_filter(
    posts: list[RawPost],
    criteria_keywords: list[str],
    threshold: float = 0.15,
) -> list[tuple[RawPost, float]]:
    """Pre-score all posts and filter below threshold.

    Returns sorted list of (post, pre_score) tuples, highest first.
    """
    scored = []
    for post in posts:
        score = pre_score(post, posts, criteria_keywords)
        if score >= threshold:
            scored.append((post, score))

    scored.sort(key=lambda x: x[1], reverse=True)
    return scored
