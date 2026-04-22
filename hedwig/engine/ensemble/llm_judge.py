"""LLM-as-judge — thin ensemble wrapper around `engine.scorer.score_posts`.

Runs the expensive LLM pass only on the top-K candidates forwarded by
Stage A. Returns the LLM's relevance_score per post in the input order,
so the ensemble can blend it with the cheap components.
"""
from __future__ import annotations

import logging

from hedwig.models import RawPost

logger = logging.getLogger(__name__)


class LLMJudge:
    """LLM judge ensemble component.

    Side effect: caches the full ScoredSignal list from the last invocation on
    ``self.last_scored`` so downstream orchestrators (run_two_stage_as_signals)
    can preserve LLM-generated fields (why_relevant, devils_advocate, tags).
    """
    name = "llm_judge"

    def __init__(self) -> None:
        self.last_scored: dict[str, object] = {}  # external_id -> ScoredSignal

    async def score_posts(self, posts: list[RawPost], context: dict | None = None) -> list[float]:
        if not posts:
            return []
        try:
            from hedwig.engine.scorer import score_posts as _score
        except Exception as e:
            logger.warning("LLM scorer unavailable: %s", e)
            return [0.0] * len(posts)

        try:
            scored = await _score(posts)
        except Exception as e:
            logger.warning("LLM scoring failed: %s", e)
            return [0.0] * len(posts)

        self.last_scored = {s.raw.external_id: s for s in scored}
        return [
            self.last_scored[p.external_id].relevance_score if p.external_id in self.last_scored else 0.0
            for p in posts
        ]
