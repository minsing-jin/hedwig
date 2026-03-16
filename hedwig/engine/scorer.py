from __future__ import annotations

import json
import logging

from openai import AsyncOpenAI

from hedwig.config import OPENAI_API_KEY, OPENAI_MODEL_FAST, load_criteria
from hedwig.models import RawPost, ScoredSignal, UrgencyLevel

logger = logging.getLogger(__name__)

client = AsyncOpenAI(api_key=OPENAI_API_KEY)

BATCH_SIZE = 20


def _build_scoring_prompt(criteria: dict) -> str:
    focus = ", ".join(criteria.get("identity", {}).get("focus", []))
    care = "\n".join(f"- {c}" for c in criteria.get("signal_preferences", {}).get("care_about", []))
    ignore = "\n".join(f"- {i}" for i in criteria.get("signal_preferences", {}).get("ignore", []))
    context_projects = "\n".join(
        f"- {p}" for p in criteria.get("context", {}).get("current_projects", [])
    )
    context_interests = "\n".join(
        f"- {i}" for i in criteria.get("context", {}).get("interests", [])
    )

    return f"""You are an AI signal analyst for a personal intelligence radar.

## User Profile
Role: {criteria.get('identity', {}).get('role', 'AI builder')}
Focus areas: {focus}

## What the user cares about:
{care}

## What to IGNORE (noise):
{ignore}

## Current context:
Projects: {context_projects}
Interests: {context_interests}

## Your Task
For each post, return a JSON object with:
- "relevance_score": float 0.0-1.0 (how relevant to this user)
- "urgency": "alert" | "digest" | "skip"
- "why_relevant": 1-2 sentences explaining WHY this matters to this user (in Korean)
- "devils_advocate": 1 sentence counter-perspective or hype warning (in Korean)

Respond with a JSON array. One object per post, in the same order as input.
Be STRICT: most posts should score below 0.5. Only genuinely important signals get > 0.7.
"""


def _format_posts_for_scoring(posts: list[RawPost]) -> str:
    items = []
    for i, p in enumerate(posts):
        items.append(
            f"[{i}] [{p.platform.value}] {p.title}\n"
            f"    score={p.score} comments={p.comments_count} author={p.author}\n"
            f"    {p.content[:300]}"
        )
    return "\n\n".join(items)


async def score_posts(posts: list[RawPost]) -> list[ScoredSignal]:
    if not posts:
        return []

    criteria = load_criteria()
    system_prompt = _build_scoring_prompt(criteria)
    scored: list[ScoredSignal] = []

    for i in range(0, len(posts), BATCH_SIZE):
        batch = posts[i : i + BATCH_SIZE]
        user_content = _format_posts_for_scoring(batch)

        try:
            resp = await client.chat.completions.create(
                model=OPENAI_MODEL_FAST,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_content},
                ],
                response_format={"type": "json_object"},
                temperature=0.3,
            )
            raw_json = resp.choices[0].message.content or "[]"
            parsed = json.loads(raw_json)

            # Handle both {"results": [...]} and direct [...]
            if isinstance(parsed, dict):
                results = parsed.get("results", parsed.get("signals", []))
            else:
                results = parsed

            for j, result in enumerate(results):
                if j >= len(batch):
                    break
                urgency_str = result.get("urgency", "skip").lower()
                try:
                    urgency = UrgencyLevel(urgency_str)
                except ValueError:
                    urgency = UrgencyLevel.SKIP

                scored.append(
                    ScoredSignal(
                        raw=batch[j],
                        relevance_score=float(result.get("relevance_score", 0)),
                        urgency=urgency,
                        why_relevant=result.get("why_relevant", ""),
                        devils_advocate=result.get("devils_advocate", ""),
                    )
                )
        except Exception as e:
            logger.error(f"Scoring batch failed: {e}")
            for post in batch:
                scored.append(ScoredSignal(raw=post))

    return scored
