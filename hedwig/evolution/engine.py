"""
Evolution Engine — autoresearch-style self-improvement for Hedwig.

Pattern (Karpathy autoresearch applied to information curation):
  criteria vN → collect/filter/deliver → user feedback → analyze → criteria vN+1
  Keep if fitness improves, discard if it regresses.

Two loops:
  - Daily: micro-mutations (criteria weight tuning, urgency threshold adjustment)
  - Weekly: macro-mutations (source add/remove, interpretation shift, new exploration directions)
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import yaml

from hedwig.models import (
    CriteriaVersion,
    EvolutionCycleType,
    EvolutionLog,
    Feedback,
    UserMemory,
    VoteType,
)

logger = logging.getLogger(__name__)


def compute_source_reliability(
    platform_feedback_counts: dict[str, dict[str, int | float]],
) -> dict[str, float]:
    """Convert recent per-platform up/down vote counts into 0.0-1.0 reliability scores."""
    scores: dict[str, float] = {}

    for platform, counts in platform_feedback_counts.items():
        platform_name = str(platform or "").strip()
        if not platform_name:
            continue

        upvotes = int(
            counts.get("upvotes", counts.get(VoteType.UP.value, 0)) or 0
        )
        downvotes = int(
            counts.get("downvotes", counts.get(VoteType.DOWN.value, 0)) or 0
        )
        total_votes = upvotes + downvotes
        if total_votes <= 0:
            continue

        score = upvotes / total_votes
        scores[platform_name] = max(0.0, min(1.0, score))

    return scores

DAILY_EVOLUTION_PROMPT = """\
You are Hedwig's Evolution Engine running the DAILY evolution cycle.

ROLE: Analyze today's user feedback and micro-tune the filtering criteria.

TODAY'S FEEDBACK:
{feedback_summary}

CURRENT CRITERIA (version {version}):
{current_criteria}

CURRENT FITNESS (upvote ratio): {fitness:.2f}

TASK:
1. Analyze patterns in upvoted vs downvoted signals
2. Identify what the user consistently likes/dislikes
3. Generate a SMALL, targeted mutation to the criteria
4. Explain your reasoning

OUTPUT (JSON):
```json
{{
  "analysis": "what patterns you found",
  "mutations": ["list of specific changes"],
  "updated_criteria": {{ ... the full updated criteria ... }},
  "expected_improvement": "why this should improve fitness"
}}
```

RULES:
- Make SMALL changes — one or two adjustments, not a rewrite
- If fitness is already > 0.8, be conservative
- If feedback is insufficient (< 3 votes), skip mutation and return {{"skip": true, "reason": "..."}}
- Never remove the Devil's Advocate requirement
"""

WEEKLY_EVOLUTION_PROMPT = """\
You are Hedwig's Evolution Engine running the WEEKLY deep evolution cycle.

ROLE: Deep analysis of the past week. Evolve ALL dimensions:
criteria, sources, interpretation style, and exploration directions.

WEEK SUMMARY:
- Total signals delivered: {total_signals}
- Total feedback received: {total_feedback}
- Upvote ratio trend: {fitness_trend}
- Natural language feedback: {nl_feedback}

CURRENT CRITERIA (version {version}):
{current_criteria}

USER MEMORY (long-horizon profile):
{user_memory}

SOURCE RELIABILITY SCORES:
{source_scores}

TASK:
1. Identify TASTE TRAJECTORY — how has the user's interest shifted?
2. SOURCE EVOLUTION — which sources consistently produce upvoted signals? Which produce noise?
3. INTERPRETATION EVOLUTION — does the user prefer more technical depth? More business angle?
4. EXPLORATION EVOLUTION — what new directions should Hedwig explore that the user hasn't asked for?
5. Generate comprehensive mutations

OUTPUT (JSON):
```json
{{
  "taste_trajectory": "narrative of how preferences shifted this week",
  "confirmed_interests": ["topics that got consistent upvotes"],
  "rejected_topics": ["topics that got consistent downvotes"],
  "source_mutations": {{
    "boost": ["sources to prioritize"],
    "demote": ["sources producing noise"],
    "discover": ["new sources/subreddits/feeds to try"]
  }},
  "interpretation_mutations": ["changes to how signals are explained"],
  "exploration_suggestions": ["new directions to explore"],
  "updated_criteria": {{ ... full updated criteria ... }},
  "mutations_applied": ["list of all changes"],
  "expected_improvement": "why these changes should help"
}}
```

RULES:
- This is the BIG evolution step — be thorough but grounded in data
- New exploration suggestions should be adjacent to confirmed interests, not random
- Source discovery should reference specific subreddits, RSS feeds, or channels
- Never remove Devil's Advocate
- If the week had very little feedback, focus on exploration over optimization
"""


class EvolutionEngine:
    """Manages the self-improvement loop for Hedwig's recommendation algorithm."""

    def __init__(
        self,
        llm_client=None,
        criteria_path: Optional[Path] = None,
        evolution_log_path: Optional[Path] = None,
    ):
        self._llm = llm_client
        self._criteria_path = criteria_path or Path("criteria.yaml")
        self._log_path = evolution_log_path or Path("evolution_log.jsonl")
        self._cycle_count = self._load_cycle_count()

    # ------------------------------------------------------------------
    # Daily evolution loop
    # ------------------------------------------------------------------

    async def run_daily(self, feedbacks: list[Feedback]) -> EvolutionLog:
        """Run daily micro-evolution based on today's feedback."""
        current_criteria = self._load_criteria()
        version_before = current_criteria.get("_version", 0)
        fitness = self._compute_fitness(feedbacks)

        feedback_summary = self._summarize_feedback(feedbacks)

        if not self._llm:
            return self._log_skip("no_llm_client", version_before)

        prompt = DAILY_EVOLUTION_PROMPT.format(
            feedback_summary=feedback_summary,
            version=version_before,
            current_criteria=yaml.dump(current_criteria, allow_unicode=True),
            fitness=fitness,
        )

        response = await self._llm.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "system", "content": prompt}],
            temperature=0.3,
            max_tokens=2000,
        )
        reply = response.choices[0].message.content or ""
        result = self._parse_json(reply)

        if not result or result.get("skip"):
            reason = result.get("reason", "insufficient_feedback") if result else "parse_error"
            return self._log_skip(reason, version_before)

        # Apply mutation
        updated = result.get("updated_criteria", current_criteria)
        version_after = version_before + 1
        updated["_version"] = version_after

        mutations = result.get("mutations", [])
        analysis = result.get("analysis", "")

        self._save_criteria(updated)

        log = EvolutionLog(
            cycle_type=EvolutionCycleType.DAILY,
            cycle_number=self._cycle_count,
            criteria_version_before=version_before,
            criteria_version_after=version_after,
            mutations_applied=mutations,
            fitness_before=fitness,
            kept=True,
            analysis_summary=analysis,
        )
        self._append_log(log)
        self._cycle_count += 1

        logger.info(f"Daily evolution: v{version_before} → v{version_after}, {len(mutations)} mutations, fitness={fitness:.2f}")
        return log

    # ------------------------------------------------------------------
    # Weekly evolution loop
    # ------------------------------------------------------------------

    async def run_weekly(
        self,
        week_feedbacks: list[Feedback],
        total_signals: int,
        user_memory: Optional[UserMemory] = None,
        source_scores: Optional[dict[str, float]] = None,
        platform_feedback_counts: Optional[dict[str, dict[str, int | float]]] = None,
    ) -> tuple[EvolutionLog, Optional[UserMemory]]:
        """Run weekly deep evolution — all dimensions."""
        current_criteria = self._load_criteria()
        version_before = current_criteria.get("_version", 0)
        fitness = self._compute_fitness(week_feedbacks)
        computed_source_scores = compute_source_reliability(platform_feedback_counts or {})
        if computed_source_scores:
            source_scores = computed_source_scores

            try:
                import hedwig.storage as storage

                if not storage.save_source_reliability(source_scores):
                    logger.warning("Failed to persist source reliability scores to storage backend")
            except Exception as e:
                logger.warning(f"Failed to persist source reliability scores: {e}")

        # Compute fitness trend from recent logs
        recent_logs = self._load_recent_logs(7)
        fitness_values = [l.get("fitness_before", 0) for l in recent_logs if l.get("fitness_before")]
        fitness_trend = f"{fitness_values}" if fitness_values else "no data"

        nl_feedback = [f.natural_language for f in week_feedbacks if f.natural_language]

        if not self._llm:
            return self._log_skip("no_llm_client", version_before), None

        prompt = WEEKLY_EVOLUTION_PROMPT.format(
            total_signals=total_signals,
            total_feedback=len(week_feedbacks),
            fitness_trend=fitness_trend,
            nl_feedback=json.dumps(nl_feedback, ensure_ascii=False) if nl_feedback else "없음",
            version=version_before,
            current_criteria=yaml.dump(current_criteria, allow_unicode=True),
            user_memory=yaml.dump(user_memory.model_dump(), allow_unicode=True) if user_memory else "없음 (첫 주간 분석)",
            source_scores=json.dumps(source_scores or {}, ensure_ascii=False),
        )

        response = await self._llm.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "system", "content": prompt}],
            temperature=0.4,
            max_tokens=3000,
        )
        reply = response.choices[0].message.content or ""
        result = self._parse_json(reply)

        if not result:
            return self._log_skip("parse_error", version_before), None

        # Apply mutations
        updated = result.get("updated_criteria", current_criteria)
        version_after = version_before + 1
        updated["_version"] = version_after
        self._save_criteria(updated)

        mutations = result.get("mutations_applied", [])
        analysis = result.get("taste_trajectory", "")

        log = EvolutionLog(
            cycle_type=EvolutionCycleType.WEEKLY,
            cycle_number=self._cycle_count,
            criteria_version_before=version_before,
            criteria_version_after=version_after,
            mutations_applied=mutations,
            fitness_before=fitness,
            kept=True,
            analysis_summary=analysis,
        )
        self._append_log(log)
        self._cycle_count += 1

        # Build updated user memory
        from datetime import date
        week_str = date.today().isocalendar()
        new_memory = UserMemory(
            snapshot_week=f"{week_str[0]}-W{week_str[1]:02d}",
            confirmed_interests=result.get("confirmed_interests", []),
            rejected_topics=result.get("rejected_topics", []),
            taste_trajectory=result.get("taste_trajectory", ""),
            context=current_criteria.get("context", {}),
            natural_language_feedback=nl_feedback[:20],
        )

        logger.info(
            f"Weekly evolution: v{version_before} → v{version_after}, "
            f"{len(mutations)} mutations, fitness={fitness:.2f}"
        )
        return log, new_memory

    # ------------------------------------------------------------------
    # Rollback — if fitness drops, revert
    # ------------------------------------------------------------------

    async def maybe_rollback(self, new_fitness: float, log: EvolutionLog) -> bool:
        """If fitness dropped significantly, rollback the last mutation."""
        if log.fitness_before is not None and new_fitness < log.fitness_before - 0.1:
            # Significant regression — rollback
            logger.warning(
                f"Fitness regression: {log.fitness_before:.2f} → {new_fitness:.2f}. "
                f"Rolling back v{log.criteria_version_after} → v{log.criteria_version_before}"
            )
            log.kept = False
            log.fitness_after = new_fitness
            self._append_log(log)
            return True
        log.fitness_after = new_fitness
        return False

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _compute_fitness(self, feedbacks: list[Feedback]) -> float:
        if not feedbacks:
            return 0.0
        ups = sum(1 for f in feedbacks if f.vote == VoteType.UP)
        return ups / len(feedbacks)

    def _summarize_feedback(self, feedbacks: list[Feedback]) -> str:
        ups = [f for f in feedbacks if f.vote == VoteType.UP]
        downs = [f for f in feedbacks if f.vote == VoteType.DOWN]
        nl = [f.natural_language for f in feedbacks if f.natural_language]

        lines = [
            f"Total: {len(feedbacks)} votes ({len(ups)} up, {len(downs)} down)",
            f"Upvote ratio: {len(ups)/len(feedbacks):.2f}" if feedbacks else "No feedback",
        ]
        if nl:
            lines.append(f"Natural language feedback: {json.dumps(nl[:10], ensure_ascii=False)}")
        return "\n".join(lines)

    def _load_criteria(self) -> dict:
        if self._criteria_path.exists():
            return yaml.safe_load(self._criteria_path.read_text()) or {}
        return {}

    def _save_criteria(self, criteria: dict):
        with open(self._criteria_path, "w") as f:
            yaml.dump(criteria, f, default_flow_style=False, allow_unicode=True)

    def _parse_json(self, text: str) -> Optional[dict]:
        try:
            start = text.index("{")
            end = text.rindex("}") + 1
            return json.loads(text[start:end])
        except (ValueError, json.JSONDecodeError):
            logger.warning("Failed to parse evolution LLM response as JSON")
            return None

    def _append_log(self, log: EvolutionLog):
        with open(self._log_path, "a") as f:
            f.write(log.model_dump_json() + "\n")

    def _load_recent_logs(self, n: int) -> list[dict]:
        if not self._log_path.exists():
            return []
        lines = self._log_path.read_text().strip().split("\n")
        logs = []
        for line in lines[-n:]:
            try:
                logs.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return logs

    def _load_cycle_count(self) -> int:
        if not self._log_path.exists():
            return 0
        return sum(1 for _ in self._log_path.read_text().strip().split("\n") if _.strip())

    def _log_skip(self, reason: str, version: int) -> EvolutionLog:
        log = EvolutionLog(
            cycle_type=EvolutionCycleType.DAILY,
            cycle_number=self._cycle_count,
            criteria_version_before=version,
            criteria_version_after=version,
            mutations_applied=[],
            kept=False,
            analysis_summary=f"Skipped: {reason}",
        )
        self._append_log(log)
        return log
