"""Ensemble component protocol + shared utilities.

Each ranking component takes a list of candidate posts + context and returns
per-candidate scores in [0, 1]. The ensemble combines them by weighted sum
(after per-component normalization).
"""
from __future__ import annotations

from typing import Protocol, runtime_checkable

from hedwig.models import RawPost


@runtime_checkable
class RankingComponent(Protocol):
    """Each ranking component must implement `score_posts`."""

    name: str

    async def score_posts(
        self,
        posts: list[RawPost],
        context: dict | None = None,
    ) -> list[float]:
        ...


def minmax_normalize(scores: list[float]) -> list[float]:
    """Map an arbitrary score vector into [0, 1] via min-max normalization."""
    if not scores:
        return []
    lo, hi = min(scores), max(scores)
    if hi - lo < 1e-9:
        return [0.5] * len(scores)
    return [(s - lo) / (hi - lo) for s in scores]
