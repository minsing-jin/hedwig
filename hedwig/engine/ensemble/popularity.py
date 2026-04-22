"""Popularity prior — source authority × recency decay.

This reuses the existing pre_scorer factors but isolates them so the
ensemble can weight popularity independently (users may want to down-weight
"what's trending" in favor of "what matches me").
"""
from __future__ import annotations

from hedwig.config import load_algorithm_config
from hedwig.engine.pre_scorer import compute_recency_decay, compute_source_authority
from hedwig.models import RawPost


class PopularityRanker:
    name = "popularity_prior"

    async def score_posts(self, posts: list[RawPost], context: dict | None = None) -> list[float]:
        if not posts:
            return []
        cfg = load_algorithm_config().get("ranking", {}).get("components", {}).get("popularity_prior", {})
        decay_hours = float(cfg.get("decay_hours", 48))
        out = []
        for post in posts:
            authority = compute_source_authority(post)
            recency = compute_recency_decay(post, half_life_hours=decay_hours)
            out.append(0.6 * authority + 0.4 * recency)
        return out
