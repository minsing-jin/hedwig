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
    """Build scorer system prompt from the active InterpretationStyle.

    Per seed.yaml ontology, `interpretation_style` is first-class and
    evolves separately from criteria. The active style's prompt_template
    is used verbatim with criteria values interpolated — so weekly style
    evolution actually changes how signals are interpreted.
    """
    focus = ", ".join(criteria.get("identity", {}).get("focus", []))
    care = "\n".join(f"- {c}" for c in criteria.get("signal_preferences", {}).get("care_about", []))
    ignore = "\n".join(f"- {i}" for i in criteria.get("signal_preferences", {}).get("ignore", []))
    context_projects = "\n".join(
        f"- {p}" for p in criteria.get("context", {}).get("current_projects", [])
    )
    context_interests = "\n".join(
        f"- {i}" for i in criteria.get("context", {}).get("interests", [])
    )
    role = criteria.get("identity", {}).get("role", "AI builder")

    try:
        from hedwig.evolution.interpretation import DEFAULT_PROMPT_TEMPLATE, ensure_default_style
        active = ensure_default_style()
        template = active.get("prompt_template") or DEFAULT_PROMPT_TEMPLATE
    except Exception:
        from hedwig.evolution.interpretation import DEFAULT_PROMPT_TEMPLATE
        template = DEFAULT_PROMPT_TEMPLATE

    try:
        return template.format(
            role=role, focus=focus, care=care, ignore=ignore,
            context_projects=context_projects, context_interests=context_interests,
        )
    except Exception:
        # If a user-edited template introduced bad placeholders, fall back
        from hedwig.evolution.interpretation import DEFAULT_PROMPT_TEMPLATE
        return DEFAULT_PROMPT_TEMPLATE.format(
            role=role, focus=focus, care=care, ignore=ignore,
            context_projects=context_projects, context_interests=context_interests,
        )


def _format_posts_for_scoring(posts: list[RawPost]) -> str:
    items = []
    for i, p in enumerate(posts):
        items.append(
            f"[{i}] [{p.platform.value}] {p.title}\n"
            f"    score={p.score} comments={p.comments_count} author={p.author}\n"
            f"    {p.content[:300]}"
        )
    return "\n\n".join(items)


def _parse_exploration_tags(value: object) -> list[str]:
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list):
        return []

    tags: list[str] = []
    for item in value:
        if not isinstance(item, str):
            continue
        tag = item.strip()
        if not tag:
            continue
        tags.append(tag)
        if len(tags) == 3:
            break
    return tags


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
                        exploration_tags=_parse_exploration_tags(
                            result.get("exploration_tags", [])
                        ),
                    )
                )
        except Exception as e:
            logger.error(f"Scoring batch failed: {e}")
            for post in batch:
                scored.append(ScoredSignal(raw=post))

    return scored
