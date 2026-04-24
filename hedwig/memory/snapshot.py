"""Weekly user_memory snapshot builder.

Closes G3 from docs/phase_reports/interview_gap_audit.md: seed.yaml
promised weekly append-only user_memory snapshots (portable identity
anchor for the algorithm-sovereignty moat) but no code wrote them.

This module aggregates 7 days of feedback + Q&A events into a structured
``UserMemory`` row and persists it through both:
  - SQLite ``user_memory`` table (via storage.save_user_memory)
  - JSONL file (via memory.MemoryStore) — for portability/export

LLM-assisted taste trajectory when OPENAI_API_KEY is set; falls back to a
pure heuristic summary otherwise.
"""
from __future__ import annotations

import logging
from collections import Counter
from datetime import datetime, timedelta, timezone

from hedwig.models import UserMemory

logger = logging.getLogger(__name__)


def _week_key(now: datetime | None = None) -> str:
    now = now or datetime.now(tz=timezone.utc)
    iso_year, iso_week, _ = now.isocalendar()
    return f"{iso_year}-W{iso_week:02d}"


def _load_recent(days: int = 7):
    since = datetime.now(tz=timezone.utc) - timedelta(days=days)
    feedback: list[dict] = []
    qa_events: list[dict] = []
    signals: list[dict] = []

    try:
        from hedwig.storage import (
            get_evolution_signals,
            get_feedback_since,
            get_recent_signals,
        )
    except ImportError:
        return feedback, qa_events, signals

    try:
        feedback = get_feedback_since(since=since) or []
    except Exception:
        feedback = []
    try:
        qa_events = get_evolution_signals(channel="semi", since=since, limit=200) or []
    except Exception:
        qa_events = []
    try:
        signals = get_recent_signals(days=days) or []
    except Exception:
        signals = []
    return feedback, qa_events, signals


def _platforms_from_signals(signal_ids: list[str], signals: list[dict]) -> list[str]:
    idx = {str(s.get("id", "")): s.get("platform", "") for s in signals}
    return [idx.get(sid, "") for sid in signal_ids if idx.get(sid)]


def _aggregate(feedback, qa_events, signals) -> dict:
    up_ids = [str(r.get("signal_id", "")) for r in feedback if r.get("vote") == "up"]
    down_ids = [str(r.get("signal_id", "")) for r in feedback if r.get("vote") == "down"]
    up = len(up_ids)
    down = len(down_ids)

    id_to_title = {str(s.get("id", "")): s.get("title", "") for s in signals}
    confirmed_titles = [id_to_title[i] for i in up_ids if i in id_to_title][:20]
    rejected_titles = [id_to_title[i] for i in down_ids if i in id_to_title][:20]

    platform_counts = Counter(_platforms_from_signals(up_ids, signals))
    top_platforms = [p for p, _ in platform_counts.most_common(5)]

    nl_hints = [
        str(r.get("natural_language"))
        for r in feedback
        if r.get("natural_language")
    ]
    qa_questions = [
        str((e.get("payload") or {}).get("question", ""))
        for e in qa_events
        if (e.get("payload") or {}).get("question")
    ][:10]

    return {
        "n_feedback": len(feedback),
        "n_qa": len(qa_events),
        "upvote_ratio": round(up / (up + down), 3) if (up + down) else 0.0,
        "confirmed_interests": confirmed_titles,
        "rejected_topics": rejected_titles,
        "top_platforms": top_platforms,
        "natural_language_feedback": nl_hints,
        "qa_questions": qa_questions,
    }


async def _llm_taste_trajectory(agg: dict) -> str:
    """Optional — summarize the week's taste drift via OpenAI. Empty on fail."""
    from hedwig.config import OPENAI_API_KEY, OPENAI_MODEL_FAST
    if not OPENAI_API_KEY:
        return ""
    try:
        from openai import AsyncOpenAI
    except ImportError:
        return ""
    prompt = f"""You are Hedwig's long-horizon memory writer.

Based on this week's user feedback, produce a 2-3 sentence "taste trajectory"
in Korean describing where the user's attention is drifting. Be specific —
cite topics from the signals, not generalities.

Upvote ratio: {agg['upvote_ratio']}
Confirmed interests (titles user upvoted):
{chr(10).join('- ' + t for t in agg['confirmed_interests'][:8])}
Rejected topics (downvoted):
{chr(10).join('- ' + t for t in agg['rejected_topics'][:5])}
NL feedback:
{chr(10).join('- ' + t for t in agg['natural_language_feedback'][:5])}
Recent Q&A questions:
{chr(10).join('- ' + t for t in agg['qa_questions'][:5])}

Respond with plain Korean text (no JSON, no markdown).
"""
    try:
        client = AsyncOpenAI(api_key=OPENAI_API_KEY)
        resp = await client.chat.completions.create(
            model=OPENAI_MODEL_FAST,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.4,
            max_tokens=300,
        )
        return (resp.choices[0].message.content or "").strip()
    except Exception as e:
        logger.debug("LLM taste trajectory skipped: %s", e)
        return ""


def create_weekly_snapshot(week: str | None = None) -> dict:
    """Build and persist one weekly user_memory row. Returns a summary dict.

    Called from run_weekly after evolution has run. Idempotent per-week:
    if the same week already has a snapshot, this will still append (table
    is append-only by design — never overwrite history).
    """
    week = week or _week_key()
    feedback, qa_events, signals = _load_recent(days=7)
    agg = _aggregate(feedback, qa_events, signals)

    # Run the LLM summary synchronously via a throwaway event loop if possible.
    import asyncio
    trajectory = ""
    try:
        trajectory = asyncio.run(_llm_taste_trajectory(agg))
    except RuntimeError:
        # Inside an already-running loop (e.g., pytest-asyncio) — synthesize
        loop = asyncio.new_event_loop()
        try:
            trajectory = loop.run_until_complete(_llm_taste_trajectory(agg))
        finally:
            loop.close()
    except Exception as e:
        logger.debug("trajectory skipped: %s", e)

    memory = UserMemory(
        snapshot_week=week,
        confirmed_interests=agg["confirmed_interests"],
        rejected_topics=agg["rejected_topics"],
        taste_trajectory=trajectory or (
            f"Week {week}: {agg['n_feedback']} feedback, upvote_ratio={agg['upvote_ratio']}. "
            f"Top platforms: {', '.join(agg['top_platforms']) or 'none'}."
        ),
        context={"top_platforms": agg["top_platforms"]},
        natural_language_feedback=agg["natural_language_feedback"],
    )

    persisted_db = False
    try:
        from hedwig.storage import save_user_memory
        persisted_db = bool(save_user_memory(memory))
    except Exception as e:
        logger.warning("save_user_memory failed: %s", e)

    persisted_jsonl = False
    try:
        from hedwig.config import USER_MEMORY_PATH
        from hedwig.memory.store import MemoryStore
        MemoryStore(path=USER_MEMORY_PATH).save_snapshot(memory)
        persisted_jsonl = True
    except Exception as e:
        logger.debug("MemoryStore jsonl write skipped: %s", e)

    return {
        "week": week,
        "n_feedback": agg["n_feedback"],
        "upvote_ratio": agg["upvote_ratio"],
        "taste_trajectory_chars": len(memory.taste_trajectory or ""),
        "persisted_db": persisted_db,
        "persisted_jsonl": persisted_jsonl,
    }
