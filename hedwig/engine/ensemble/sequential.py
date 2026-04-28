"""Sequential ranker (S8.2) — SASRec-inspired without torch.

Idea: rank candidates by similarity to the user's recent dwell/save
sequence. Real SASRec learns a transformer over sequences; we approximate
by token-overlap similarity weighted by recency. For Hedwig's single-user
scale (~hundreds of items / day), this captures "you just dwelled on
agent frameworks → next slot favors related items" without the torch
infra.

Activate via algorithm.yaml:
    ranking:
      components:
        sequential:
          enabled: true
          weight: 0.15
          history_size: 12
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta, timezone

from hedwig.config import load_algorithm_config
from hedwig.models import RawPost

logger = logging.getLogger(__name__)


def _tokens(text: str) -> set[str]:
    return {t for t in re.split(r"[^a-z0-9]+", (text or "").lower()) if len(t) >= 3}


def _recent_engagement_sequence(history_size: int = 12, days: int = 14) -> list[set[str]]:
    """Return recent positively-engaged signal token sets, newest first.

    Sources of engagement (in order of strength): save / share > dwell ≥ 3s > upvote.
    """
    since = datetime.now(tz=timezone.utc) - timedelta(days=days)
    try:
        from hedwig.storage import (
            get_behavior_events,
            get_feedback_since,
            get_recent_signals,
        )
    except ImportError:
        return []

    events = []
    try:
        evs = get_behavior_events(limit=600) or []
        events = [
            e for e in evs
            if (e.get("captured_at") or "") >= since.isoformat()
            and e.get("event_type") in ("save", "share", "dwell")
        ]
    except Exception:
        pass

    fb = []
    try:
        fb = get_feedback_since(since=since) or []
    except Exception:
        pass

    # Compose ordered list of (signal_id, weight) — newer/heavier first
    keyed: dict[str, float] = {}
    for e in events:
        sid = str(e.get("signal_id") or "")
        if not sid:
            continue
        if e.get("event_type") in ("save", "share"):
            keyed[sid] = max(keyed.get(sid, 0.0), 1.0)
        elif e.get("event_type") == "dwell" and (e.get("dwell_ms") or 0) >= 3000:
            keyed[sid] = max(keyed.get(sid, 0.0), 0.7)
    for r in fb:
        if r.get("vote") == "up":
            sid = str(r.get("signal_id") or "")
            if sid:
                keyed[sid] = max(keyed.get(sid, 0.0), 0.6)
    if not keyed:
        return []

    # Map signal_id → tokens via stored signal rows
    try:
        sigs = get_recent_signals(days=days) or []
    except Exception:
        sigs = []
    sig_tokens: dict[str, set[str]] = {}
    for s in sigs:
        sid = str(s.get("id", ""))
        if sid in keyed:
            sig_tokens[sid] = _tokens(f"{s.get('title','')} {(s.get('content') or '')[:300]}")

    # Order by weight desc, take top history_size
    ordered = sorted(keyed.items(), key=lambda kv: kv[1], reverse=True)[:history_size]
    return [sig_tokens.get(sid, set()) for sid, _ in ordered if sig_tokens.get(sid)]


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    inter = len(a & b)
    union = len(a | b)
    return inter / union if union else 0.0


class SequentialRanker:
    name = "sequential"

    def __init__(self) -> None:
        cfg = load_algorithm_config()
        spec = (cfg.get("ranking", {}).get("components", {}).get("sequential", {})) or {}
        self.history_size = int(spec.get("history_size", 12))
        self._history = _recent_engagement_sequence(history_size=self.history_size)

    async def score_posts(self, posts: list[RawPost], context: dict | None = None) -> list[float]:
        if not posts:
            return []
        if not self._history:
            # No history yet — neutral score so component doesn't bias
            return [0.5] * len(posts)

        # Recency-weighted Jaccard against the sequence (newest items weigh more)
        weights = [
            0.5 ** i  # 1.0, 0.5, 0.25 ... — recency decay over the sequence
            for i in range(len(self._history))
        ]
        wsum = sum(weights) or 1.0

        scores: list[float] = []
        for p in posts:
            cand = _tokens(f"{p.title} {(p.content or '')[:300]}")
            if not cand:
                scores.append(0.0)
                continue
            agg = sum(w * _jaccard(cand, h) for w, h in zip(weights, self._history))
            scores.append(min(1.0, agg / wsum * 4.0))   # scale up since Jaccards are small
        return scores
