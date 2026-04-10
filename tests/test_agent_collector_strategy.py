"""Integration test — Agent collector default strategy returns valid plan structure.

AC 9: When no LLM client is provided, AgentCollector.generate_strategy()
must return a dict with all required plan keys, correct types, and values
that are compatible with collect_with_strategy().
"""
from __future__ import annotations

import asyncio
import pytest

from hedwig.engine.agent_collector import AgentCollector


# ---------------------------------------------------------------------------
# Required plan structure keys and their expected types
# ---------------------------------------------------------------------------

REQUIRED_KEYS = {
    "priority_sources": list,
    "source_configs": dict,
    "explore_sources": list,
    "skip_sources": list,
    "focus_keywords": list,
    "exploration_queries": list,
}


def _run(coro):
    """Helper to run async coroutines in tests."""
    return asyncio.get_event_loop().run_until_complete(coro)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestDefaultStrategy:
    """Verify the default (no-LLM) strategy returns a valid plan."""

    def test_has_all_required_keys(self):
        """Plan must contain every key that collect_with_strategy() reads."""
        collector = AgentCollector(llm_client=None)
        strategy = _run(collector.generate_strategy())
        for key in REQUIRED_KEYS:
            assert key in strategy, f"Missing required key: {key}"

    def test_no_extra_keys(self):
        """Plan should not have unexpected keys."""
        collector = AgentCollector(llm_client=None)
        strategy = _run(collector.generate_strategy())
        extra = set(strategy.keys()) - set(REQUIRED_KEYS.keys())
        assert extra == set(), f"Unexpected keys in strategy: {extra}"

    def test_correct_types(self):
        """Each plan key must have the expected type."""
        collector = AgentCollector(llm_client=None)
        strategy = _run(collector.generate_strategy())
        for key, expected_type in REQUIRED_KEYS.items():
            assert isinstance(strategy[key], expected_type), (
                f"Key '{key}' should be {expected_type.__name__}, "
                f"got {type(strategy[key]).__name__}"
            )

    def test_priority_sources_non_empty(self):
        """Default strategy must include at least one priority source."""
        collector = AgentCollector(llm_client=None)
        strategy = _run(collector.generate_strategy())
        assert len(strategy["priority_sources"]) > 0, (
            "priority_sources must not be empty"
        )

    def test_priority_sources_all_strings(self):
        """All entries in priority_sources must be strings (source IDs)."""
        collector = AgentCollector(llm_client=None)
        strategy = _run(collector.generate_strategy())
        for src in strategy["priority_sources"]:
            assert isinstance(src, str), f"Source ID must be str, got {type(src)}"

    def test_source_configs_match_priority(self):
        """Every priority source should have a corresponding config entry."""
        collector = AgentCollector(llm_client=None)
        strategy = _run(collector.generate_strategy())
        for src in strategy["priority_sources"]:
            assert src in strategy["source_configs"], (
                f"priority source '{src}' missing from source_configs"
            )

    def test_source_configs_have_limit(self):
        """Each source config must include a positive 'limit' integer."""
        collector = AgentCollector(llm_client=None)
        strategy = _run(collector.generate_strategy())
        for src, cfg in strategy["source_configs"].items():
            assert "limit" in cfg, f"Config for '{src}' missing 'limit'"
            assert isinstance(cfg["limit"], int), (
                f"limit for '{src}' must be int, got {type(cfg['limit'])}"
            )
            assert cfg["limit"] > 0, f"limit for '{src}' must be positive"

    def test_includes_registered_sources(self):
        """Default strategy should include all registered source plugins."""
        from hedwig.sources import get_registered_sources

        collector = AgentCollector(llm_client=None)
        strategy = _run(collector.generate_strategy())
        registered = set(get_registered_sources().keys())
        planned = set(strategy["priority_sources"])
        assert registered == planned, (
            f"Mismatch: registered={registered - planned}, "
            f"unregistered in plan={planned - registered}"
        )


class TestDefaultStrategyWithReliability:
    """Verify reliability scores affect source ordering."""

    def test_high_reliability_comes_first(self):
        """Sources with higher reliability should appear earlier."""
        collector = AgentCollector(llm_client=None)
        reliability = {
            "hackernews": 0.95,
            "arxiv": 0.85,
            "reddit": 0.20,
            "twitter": 0.10,
        }
        strategy = _run(
            collector.generate_strategy(source_reliability=reliability)
        )
        sources = strategy["priority_sources"]
        hn_idx = sources.index("hackernews")
        rd_idx = sources.index("reddit")
        tw_idx = sources.index("twitter")
        assert hn_idx < rd_idx, "hackernews (0.95) should rank before reddit (0.20)"
        assert rd_idx < tw_idx, "reddit (0.20) should rank before twitter (0.10)"

    def test_unknown_sources_get_default_reliability(self):
        """Sources without reliability data should default to 0.5."""
        collector = AgentCollector(llm_client=None)
        reliability = {"hackernews": 1.0, "twitter": 0.0}
        strategy = _run(
            collector.generate_strategy(source_reliability=reliability)
        )
        sources = strategy["priority_sources"]
        # hackernews (1.0) should be first
        assert sources[0] == "hackernews"
        # twitter (0.0) should be last
        assert sources[-1] == "twitter"

    def test_structure_valid_with_reliability(self):
        """Plan structure should be valid regardless of reliability input."""
        collector = AgentCollector(llm_client=None)
        reliability = {"hackernews": 0.9, "arxiv": 0.1}
        strategy = _run(
            collector.generate_strategy(source_reliability=reliability)
        )
        for key, expected_type in REQUIRED_KEYS.items():
            assert key in strategy, f"Missing key: {key}"
            assert isinstance(strategy[key], expected_type)


class TestDefaultStrategyWithUserMemory:
    """Verify user_memory_summary doesn't break default strategy."""

    def test_with_empty_memory(self):
        collector = AgentCollector(llm_client=None)
        strategy = _run(
            collector.generate_strategy(user_memory_summary="")
        )
        assert set(strategy.keys()) == set(REQUIRED_KEYS.keys())

    def test_with_memory_string(self):
        collector = AgentCollector(llm_client=None)
        strategy = _run(
            collector.generate_strategy(
                user_memory_summary="User interested in AI agents and LLM tooling"
            )
        )
        assert set(strategy.keys()) == set(REQUIRED_KEYS.keys())
        assert len(strategy["priority_sources"]) > 0


class TestStrategyCompatibleWithCollect:
    """Verify the default strategy works as input to collect_with_strategy."""

    def test_strategy_keys_consumed_correctly(self):
        """Simulate what collect_with_strategy does with the strategy dict."""
        collector = AgentCollector(llm_client=None)
        strategy = _run(collector.generate_strategy())

        # These are the exact accesses collect_with_strategy makes:
        source_configs = strategy.get("source_configs", {})
        priority_sources = strategy.get("priority_sources", [])
        explore_sources = strategy.get("explore_sources", [])
        skip_sources = set(strategy.get("skip_sources", []))

        assert isinstance(source_configs, dict)
        assert isinstance(priority_sources, list)
        assert isinstance(explore_sources, list)
        assert isinstance(skip_sources, set)

        # Verify combined iteration works (mimics collect_with_strategy loop)
        combined = priority_sources + explore_sources
        assert len(combined) >= len(priority_sources)

        for source_id in combined:
            if source_id in skip_sources:
                continue
            config = source_configs.get(source_id, {})
            limit = config.get("limit", 30)
            assert isinstance(limit, int)
            assert limit > 0
