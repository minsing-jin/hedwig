"""
Agent Collector — AI-driven intelligent collection strategy.

Instead of mechanically polling all 16 sources with static queries,
the agent decides:
  1. Which sources to prioritize this cycle (based on reliability + criteria)
  2. What queries/keywords to use per source (based on evolving criteria)
  3. How deep to go per source (budget allocation)
  4. Which new sources to explore (based on weekly evolution suggestions)

The agent uses criteria + user memory + source reliability scores
to generate a collection plan, then executes it.
"""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import yaml

from hedwig.models import RawPost

logger = logging.getLogger(__name__)

STRATEGY_PROMPT = """\
You are Hedwig's Collection Strategy Agent.

Given the user's criteria and source reliability data, generate an optimal
collection plan for this cycle.

USER CRITERIA:
{criteria}

SOURCE RELIABILITY (from past cycles):
{source_reliability}

USER MEMORY (recent interests):
{user_memory}

AVAILABLE SOURCES:
{available_sources}

TASK: Generate a collection plan as JSON.

```json
{{
  "priority_sources": ["top sources to collect from, ordered by expected value"],
  "source_configs": {{
    "<source_id>": {{
      "limit": <number of posts to fetch>,
      "queries": ["specific search queries if applicable"],
      "reason": "why this source matters this cycle"
    }}
  }},
  "explore_sources": ["sources to try for discovery, even if low reliability"],
  "skip_sources": ["sources to skip this cycle and why"],
  "focus_keywords": ["key terms to watch across all sources"],
  "exploration_queries": ["new search directions to try"]
}}
```

RULES:
- Allocate more budget to high-reliability, high-relevance sources
- Always include at least one exploration source for discovery
- Keep total post count under 500 to manage LLM scoring costs
- Focus keywords should reflect the user's CURRENT interests, not generic AI terms
- exploration_queries should push into adjacent areas the user might not have considered
"""


class AgentCollector:
    """AI-driven collection strategy engine."""

    def __init__(self, llm_client=None, criteria_path: Optional[Path] = None):
        self._llm = llm_client
        self._criteria_path = criteria_path or Path("criteria.yaml")

    async def generate_strategy(
        self,
        source_reliability: dict[str, float] | None = None,
        user_memory_summary: str = "",
    ) -> dict:
        """Use LLM to generate collection strategy based on criteria."""
        criteria = self._load_criteria()

        from hedwig.sources import settings as source_settings

        available = list(source_settings.filter_registered_sources().keys())

        if not self._llm:
            return self._default_strategy(available, source_reliability)

        prompt = STRATEGY_PROMPT.format(
            criteria=yaml.dump(criteria, allow_unicode=True),
            source_reliability=json.dumps(source_reliability or {}, ensure_ascii=False),
            user_memory=user_memory_summary or "없음 (첫 실행)",
            available_sources=json.dumps(available),
        )

        try:
            response = await self._llm.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "system", "content": prompt}],
                temperature=0.3,
                max_tokens=1500,
            )
            reply = response.choices[0].message.content or ""
            strategy = self._parse_json(reply)
            if strategy:
                logger.info(f"Agent strategy: {len(strategy.get('priority_sources', []))} priority sources")
                return strategy
        except Exception as e:
            logger.warning(f"Strategy generation failed: {e}")

        return self._default_strategy(available, source_reliability)

    async def collect_with_strategy(self, strategy: dict) -> list[RawPost]:
        """Execute collection based on agent-generated strategy."""
        from hedwig.sources import settings as source_settings

        registry = source_settings.filter_registered_sources()
        all_posts: list[RawPost] = []

        source_configs = strategy.get("source_configs", {})
        priority_sources = strategy.get("priority_sources", list(registry.keys()))
        explore_sources = strategy.get("explore_sources", [])
        skip_sources = set(strategy.get("skip_sources", []))

        # Collect from priority sources
        tasks = []
        names = []
        for source_id in priority_sources + explore_sources:
            if source_id in skip_sources:
                continue
            if source_id not in registry:
                continue

            config = source_configs.get(source_id, {})
            limit = config.get("limit", 30)

            # Build source instance with custom queries if supported
            kwargs = {}
            if "queries" in config:
                kwargs["queries"] = config["queries"]

            try:
                instance = registry[source_id](**kwargs) if kwargs else registry[source_id]()
            except TypeError:
                instance = registry[source_id]()

            names.append(source_id)
            tasks.append(self._fetch_with_timeout(instance, limit))

        results = await asyncio.gather(*tasks, return_exceptions=True)

        for name, result in zip(names, results):
            if isinstance(result, Exception):
                logger.warning(f"[{name}] collection failed: {result}")
            else:
                logger.info(f"[{name}] {len(result)} posts collected")
                all_posts.extend(result)

        # Deduplicate by URL
        seen: set[str] = set()
        unique: list[RawPost] = []
        for post in all_posts:
            key = post.url or post.external_id
            if key not in seen:
                seen.add(key)
                unique.append(post)

        logger.info(
            f"Agent collection complete: {len(unique)} unique posts "
            f"from {len(names)} sources"
        )
        return unique

    async def _fetch_with_timeout(self, source, limit: int, timeout: float = 30.0):
        """Fetch with timeout wrapper."""
        return await asyncio.wait_for(source.fetch(limit=limit), timeout=timeout)

    def _default_strategy(
        self, available: list[str], reliability: dict[str, float] | None
    ) -> dict:
        """Fallback strategy when LLM is unavailable."""
        rel = reliability or {}
        sorted_sources = sorted(available, key=lambda s: rel.get(s, 0.5), reverse=True)

        return {
            "priority_sources": sorted_sources,
            "source_configs": {s: {"limit": 30} for s in sorted_sources},
            "explore_sources": [],
            "skip_sources": [],
            "focus_keywords": [],
            "exploration_queries": [],
        }

    def _load_criteria(self) -> dict:
        if self._criteria_path.exists():
            return yaml.safe_load(self._criteria_path.read_text()) or {}
        return {}

    def _parse_json(self, text: str) -> Optional[dict]:
        try:
            start = text.index("{")
            end = text.rindex("}") + 1
            return json.loads(text[start:end])
        except (ValueError, json.JSONDecodeError):
            return None
