"""LLM-as-recommender (S8.3) — generative reranker, distinct from llm_judge.

Where ``llm_judge`` asks the model "score this signal", LLM-rec asks the
model "given my recent history + 30 candidates, give me the order that
matches my taste right now". This is the P5 / RecLLM / InstructRec
pattern adapted to single-user personal curation.

Activation: enable ``ranking.components.llm_rec`` in algorithm.yaml with
``apply_to: top_k`` so it only runs on the cheap-component shortlist.
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timedelta, timezone

from hedwig.config import OPENAI_API_KEY, load_criteria
from hedwig.models import RawPost

logger = logging.getLogger(__name__)


def _recent_history_summary(limit: int = 8) -> str:
    """Compose a short string of the user's recent upvoted titles."""
    try:
        from hedwig.storage import get_feedback_since, get_recent_signals
    except ImportError:
        return ""
    since = datetime.now(tz=timezone.utc) - timedelta(days=14)
    try:
        rows = get_feedback_since(since=since) or []
    except Exception:
        rows = []
    up_ids = {str(r.get("signal_id", "")) for r in rows if r.get("vote") == "up"}
    if not up_ids:
        return ""
    try:
        sigs = get_recent_signals(days=14) or []
    except Exception:
        sigs = []
    titles = [s.get("title", "") for s in sigs if str(s.get("id", "")) in up_ids][:limit]
    return "\n".join(f"- {t}" for t in titles if t)


_PROMPT = """You are Hedwig's personalized reranker.

User's recent upvoted titles (taste hint):
{history}

User criteria (care_about):
{care}

Candidate signals (numbered):
{items}

Task: Return JSON with one key, "ranking", whose value is a list of
{n} integers — the candidate indices in your preferred order, best first.
ONLY use the numbers shown above; do not invent indices.
Tie-break by recency. No explanation, JSON only.
"""


class LLMRecRanker:
    name = "llm_rec"

    async def score_posts(self, posts: list[RawPost], context: dict | None = None) -> list[float]:
        if not posts:
            return []
        if not OPENAI_API_KEY:
            return [0.5] * len(posts)
        try:
            from openai import AsyncOpenAI
        except ImportError:
            return [0.5] * len(posts)

        crit = load_criteria() or {}
        care = ", ".join(
            (crit.get("signal_preferences", {}).get("care_about") or [])[:8]
        )
        history = _recent_history_summary()
        items_str = "\n".join(
            f"[{i}] [{p.platform.value}] {p.title}" for i, p in enumerate(posts)
        )
        prompt = _PROMPT.format(
            history=history or "(no upvotes yet)",
            care=care or "(no care_about set)",
            items=items_str,
            n=len(posts),
        )

        try:
            client = AsyncOpenAI(api_key=OPENAI_API_KEY)
            resp = await client.chat.completions.create(
                model=os.getenv("OPENAI_MODEL_FAST", "gpt-4o-mini"),
                messages=[{"role": "user", "content": prompt}],
                temperature=0.2, max_tokens=600,
                response_format={"type": "json_object"},
            )
            data = json.loads(resp.choices[0].message.content or "{}")
        except Exception as e:
            logger.warning("LLM-rec failed: %s", e)
            return [0.5] * len(posts)

        ranking = data.get("ranking") or []
        if not isinstance(ranking, list):
            return [0.5] * len(posts)

        # Convert positional ranking → score in [0,1] (rank 0 = best = 1.0)
        n = len(posts)
        scores = [0.5] * n
        for position, idx in enumerate(ranking):
            try:
                idx_int = int(idx)
            except (TypeError, ValueError):
                continue
            if 0 <= idx_int < n:
                scores[idx_int] = max(0.0, 1.0 - (position / max(1, n - 1)))
        return scores
