"""Semi-explicit feedback capture for the on-demand Q&A layer.

When a user accepts / rejects a Q&A answer, or asks a follow-up that
acknowledges the answer was useful ("more like that"), it flows here and
is persisted to the evolution_signal table as a 'semi' channel event.
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def record_qa_event(kind: str, payload: dict | None = None, weight: float = 1.0) -> bool:
    """Record a Q&A interaction event.

    kind: one of
      - 'qa_accept'   : user marked the answer helpful
      - 'qa_reject'   : user marked it unhelpful
      - 'qa_ask'      : raw question (low weight; for curiosity logs)
      - 'qa_more_like': "show me more like this" directive
      - 'qa_less_like': "this is not what I want" directive
    """
    from hedwig.storage import save_evolution_signal

    return save_evolution_signal(
        channel="semi", kind=kind, payload=payload or {}, weight=weight,
    )
