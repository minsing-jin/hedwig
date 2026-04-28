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


def _persist_judgment(
    *,
    signal_id: str,
    relevance: float,
    urgency: str,
    why: str,
    devil: str,
    opp: str = "",
    confidence: float | None = None,
    exploration_tags: list | None = None,
) -> None:
    """Persist a first-class Judgment row with version provenance (G1)."""
    try:
        from hedwig.models import Judgment, UrgencyLevel
        from hedwig.storage import (
            get_active_interpretation_style,
            get_criteria_versions,
            save_judgment,
        )
        crit_ver = None
        try:
            cv = get_criteria_versions(limit=1) or []
            if cv:
                crit_ver = int(cv[0].get("version", 0)) or None
        except Exception:
            pass
        style_id = None
        try:
            active = get_active_interpretation_style() or {}
            style_id = active.get("id")
        except Exception:
            pass

        try:
            urg = UrgencyLevel(urgency)
        except Exception:
            urg = UrgencyLevel.SKIP

        save_judgment(Judgment(
            signal_id=signal_id,
            score=float(relevance),
            urgency=urg,
            rationale=why or None,
            devil_advocate=devil or None,
            opportunity_note=opp or None,
            confidence=confidence,
            exploration_tags=list(exploration_tags or []),
            criteria_version=crit_ver,
            interpretation_style_id=style_id,
        ))
    except Exception:
        pass


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

                why = result.get("why_relevant", "")
                devil = result.get("devils_advocate", "")
                tags = _parse_exploration_tags(result.get("exploration_tags", []))
                relevance = float(result.get("relevance_score", 0))

                signal = ScoredSignal(
                    raw=batch[j],
                    relevance_score=relevance,
                    urgency=urgency,
                    why_relevant=why,
                    devils_advocate=devil,
                    exploration_tags=tags,
                )
                scored.append(signal)

                # G1 — also persist a first-class Judgment row tagged with
                # the criteria + interpretation_style version that produced it.
                try:
                    _persist_judgment(
                        signal_id=batch[j].external_id,
                        relevance=relevance,
                        urgency=urgency.value,
                        why=why,
                        devil=devil,
                        opp=str(result.get("opportunity_note") or ""),
                        confidence=result.get("confidence"),
                        exploration_tags=tags,
                    )
                except Exception as e:
                    logger.debug("Judgment persist skipped: %s", e)
        except Exception as e:
            logger.error(f"Scoring batch failed: {e}")
            for post in batch:
                scored.append(ScoredSignal(raw=post))

    return scored
