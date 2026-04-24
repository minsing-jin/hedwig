"""Interpretation-style evolution — the 4th self-improvement axis.

seed.yaml calls out `interpretation_evolution` as one of four axes
(criteria / source / interpretation / exploration). Prior to this module
only the other three had any code path. This module closes that gap.

What evolves: tone (technical|business|mixed), depth (surface|deep),
jargon_level (low|medium|high), prompt_template. Changes are applied to
the active InterpretationStyle once per weekly cycle and produce a new
version row so judgment.produced_by_interpretation_style_id remains
attribution-ready.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from hedwig.models import InterpretationStyle

logger = logging.getLogger(__name__)


DEFAULT_PROMPT_TEMPLATE = """You are an AI signal analyst for a personal intelligence radar.

## User Profile
Role: {role}
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
- "exploration_tags": array of 1-3 short tags for adjacent areas or new categories worth exploring

Respond with a JSON array. One object per post, in the same order as input.
Be STRICT: most posts should score below 0.5. Only genuinely important signals get > 0.7.
"""


def ensure_default_style() -> dict:
    """Seed the `interpretation_styles` table with a v1 default if empty.

    Returns the active style row as a dict.
    """
    from hedwig.storage import (
        get_active_interpretation_style,
        get_interpretation_style_history,
        save_interpretation_style,
        set_active_interpretation_style,
    )

    active = get_active_interpretation_style()
    if active:
        return active

    existing = get_interpretation_style_history(limit=1)
    if existing:
        # History exists but nothing active — activate the newest row
        newest_id = existing[0]["id"]
        set_active_interpretation_style(newest_id)
        return get_active_interpretation_style() or existing[0]

    style = InterpretationStyle(
        id=str(uuid.uuid4()),
        version=1,
        tone="mixed",
        depth="deep",
        jargon_level="medium",
        prompt_template=DEFAULT_PROMPT_TEMPLATE,
        parent_version=None,
        created_at=datetime.now(tz=timezone.utc),
    )
    save_interpretation_style(style)
    set_active_interpretation_style(style.id)
    return get_active_interpretation_style() or style.model_dump()


def _mutate_template(active: dict, tone: str, depth: str, jargon: str) -> str:
    """Produce a new prompt_template reflecting the chosen style axes."""
    base = active.get("prompt_template") or DEFAULT_PROMPT_TEMPLATE
    tail = (
        f"\n\n## Style (auto-tuned weekly)\n"
        f"- tone: {tone}\n- depth: {depth}\n- jargon: {jargon}\n"
    )
    # Replace any existing style block
    if "## Style (auto-tuned weekly)" in base:
        idx = base.find("## Style (auto-tuned weekly)")
        base = base[:idx].rstrip()
    return base + tail


def evolve_style_from_signals(
    recent_feedback_ratio: float,
    natural_language_hints: list[str] | None = None,
    force: bool = False,
) -> dict:
    """Propose and persist a new InterpretationStyle for this week.

    Heuristic rules (explainable, auditable):
      - upvote_ratio < 0.4 → shift toward user's stated preferences (deeper tone, less jargon)
      - upvote_ratio > 0.7 → keep current (no churn)
      - natural-language hints containing "간결", "짧게" → tone=mixed, depth=surface
      - hints containing "기술", "deep dive" → tone=technical, depth=deep

    The mutation is intentionally simple — we want it legible in /evolution
    so the user can always see why the style changed.
    """
    active = ensure_default_style()

    tone = active.get("tone", "mixed")
    depth = active.get("depth", "deep")
    jargon = active.get("jargon_level", "medium")
    changed_reasons: list[str] = []

    if recent_feedback_ratio < 0.4:
        # User is unhappy → try a lower-jargon, more actionable voice
        if jargon != "low":
            jargon = "low"
            changed_reasons.append("upvote_ratio low → jargon_level=low")
        if depth == "deep":
            depth = "surface"
            changed_reasons.append("upvote_ratio low → depth=surface (be more concise)")
    elif recent_feedback_ratio > 0.7:
        # Working well → optional small refinement only
        pass

    for hint in natural_language_hints or []:
        h = (hint or "").lower()
        if "간결" in hint or "짧" in hint or "concise" in h:
            if depth != "surface":
                depth = "surface"
                changed_reasons.append("NL hint → depth=surface")
        if "기술" in hint or "deep" in h or "technical" in h:
            if tone != "technical":
                tone = "technical"
                changed_reasons.append("NL hint → tone=technical")
        if "business" in h or "사업" in hint:
            if tone != "business":
                tone = "business"
                changed_reasons.append("NL hint → tone=business")

    if not changed_reasons and not force:
        return {"evolved": False, "style_id": active["id"], "reasons": []}

    from hedwig.storage import (
        save_evolution_signal,
        save_interpretation_style,
        set_active_interpretation_style,
    )

    new_style = InterpretationStyle(
        id=str(uuid.uuid4()),
        version=int(active.get("version", 1)) + 1,
        tone=tone,
        depth=depth,
        jargon_level=jargon,
        prompt_template=_mutate_template(active, tone, depth, jargon),
        parent_version=int(active.get("version", 1)),
        created_at=datetime.now(tz=timezone.utc),
    )
    save_interpretation_style(new_style)
    set_active_interpretation_style(new_style.id)

    # Log as weekly-scope evolution signal so /evolution timeline shows it
    try:
        save_evolution_signal(
            channel="semi",
            kind="interpretation_evolve",
            payload={
                "from_version": active.get("version"),
                "to_version": new_style.version,
                "reasons": changed_reasons,
                "tone": tone, "depth": depth, "jargon_level": jargon,
            },
            weight=1.5,
        )
    except Exception as e:
        logger.debug("evolution_signal(interpretation_evolve) skipped: %s", e)

    return {
        "evolved": True,
        "style_id": new_style.id,
        "from_version": active.get("version"),
        "to_version": new_style.version,
        "reasons": changed_reasons,
        "tone": tone,
        "depth": depth,
        "jargon_level": jargon,
    }
