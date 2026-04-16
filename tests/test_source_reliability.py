"""
AC-3: source reliability auto-evolution.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def test_compute_source_reliability_handles_extremes():
    """Platforms with all upvotes or all downvotes should score near the bounds."""
    from hedwig.evolution.engine import compute_source_reliability

    scores = compute_source_reliability(
        {
            "reddit": {"upvotes": 10, "downvotes": 0},
            "twitter": {"upvotes": 0, "downvotes": 10},
        }
    )

    assert scores["reddit"] == pytest.approx(1.0, abs=0.01)
    assert scores["twitter"] == pytest.approx(0.0, abs=0.01)


@pytest.mark.asyncio
async def test_weekly_evolution_persists_computed_source_reliability(monkeypatch, tmp_path):
    """Weekly evolution should compute and persist source reliability scores."""
    from hedwig.evolution.engine import EvolutionEngine
    from hedwig.models import VoteType
    from hedwig.storage import supabase as supabase_mod

    captured: dict[str, float] = {}

    def fake_save_source_reliability(scores: dict[str, float]) -> bool:
        captured.update(scores)
        return True

    monkeypatch.setattr(
        supabase_mod,
        "save_source_reliability",
        fake_save_source_reliability,
    )

    class _FakeCompletions:
        async def create(self, **kwargs):
            return type(
                "Response",
                (),
                {
                    "choices": [
                        type(
                            "Choice",
                            (),
                            {
                                "message": type(
                                    "Message",
                                    (),
                                    {
                                        "content": json.dumps(
                                            {
                                                "taste_trajectory": "AI infra interest is strengthening.",
                                                "confirmed_interests": ["ai infra"],
                                                "rejected_topics": ["generic hype"],
                                                "updated_criteria": {"focus": ["ai infra"]},
                                                "mutations_applied": ["boost reddit"],
                                            }
                                        )
                                    },
                                )()
                            },
                        )()
                    ]
                },
            )()

    class _FakeChat:
        def __init__(self):
            self.completions = _FakeCompletions()

    class _FakeLLM:
        def __init__(self):
            self.chat = _FakeChat()

    engine = EvolutionEngine(
        llm_client=_FakeLLM(),
        criteria_path=tmp_path / "criteria.yaml",
        evolution_log_path=tmp_path / "evolution_log.jsonl",
    )

    log, new_memory = await engine.run_weekly(
        week_feedbacks=[],
        total_signals=12,
        platform_feedback_counts={
            "reddit": {
                VoteType.UP.value: 10,
                VoteType.DOWN.value: 0,
            },
            "twitter": {
                VoteType.UP.value: 0,
                VoteType.DOWN.value: 10,
            },
        },
    )

    assert log.cycle_type.value == "weekly"
    assert new_memory is not None
    assert captured["reddit"] == pytest.approx(1.0, abs=0.01)
    assert captured["twitter"] == pytest.approx(0.0, abs=0.01)


@pytest.mark.asyncio
async def test_run_evolution_weekly_aggregates_feedback_without_recent_signal_cap(
    monkeypatch,
    tmp_path,
):
    """Weekly aggregation should use all feedback-linked signals, not the capped recent-signals query."""
    from hedwig import config as config_mod
    from hedwig import evolution as evolution_mod
    from hedwig import main as main_mod
    from hedwig import memory as memory_mod
    from hedwig.models import EvolutionCycleType, EvolutionLog, VoteType
    from hedwig.storage import supabase as supabase_mod

    raw_feedback = []
    signal_platforms: dict[str, str] = {}

    for idx in range(205):
        signal_id = f"twitter-{idx}"
        raw_feedback.append({"signal_id": signal_id, "vote": VoteType.DOWN.value})
        signal_platforms[signal_id] = "twitter"

    for idx in range(10):
        signal_id = f"reddit-{idx}"
        raw_feedback.append({"signal_id": signal_id, "vote": VoteType.UP.value})
        signal_platforms[signal_id] = "reddit"

    captured: dict[str, object] = {}

    class FakeEvolutionEngine:
        def __init__(self, *args, **kwargs):
            pass

        async def run_weekly(
            self,
            week_feedbacks,
            total_signals,
            user_memory=None,
            source_scores=None,
            platform_feedback_counts=None,
        ):
            captured["feedback_count"] = len(week_feedbacks)
            captured["platform_feedback_counts"] = platform_feedback_counts
            return (
                EvolutionLog(
                    cycle_type=EvolutionCycleType.WEEKLY,
                    cycle_number=0,
                    criteria_version_before=0,
                    criteria_version_after=1,
                ),
                None,
            )

    class FakeMemoryStore:
        def __init__(self, *args, **kwargs):
            pass

        def get_latest(self):
            return None

        def save_snapshot(self, memory):
            raise AssertionError("save_snapshot should not run when no new memory is returned")

    def fail_if_recent_signals_requested(*args, **kwargs):
        raise AssertionError("run_evolution_weekly should not use get_recent_signals for aggregation")

    monkeypatch.setattr(config_mod, "OPENAI_API_KEY", "")
    monkeypatch.setattr(config_mod, "CRITERIA_PATH", tmp_path / "criteria.yaml")
    monkeypatch.setattr(config_mod, "EVOLUTION_LOG_PATH", tmp_path / "evolution_log.jsonl")
    monkeypatch.setattr(config_mod, "USER_MEMORY_PATH", tmp_path / "user_memory.json")
    monkeypatch.setattr(evolution_mod, "EvolutionEngine", FakeEvolutionEngine)
    monkeypatch.setattr(memory_mod, "MemoryStore", FakeMemoryStore)
    monkeypatch.setattr(supabase_mod, "get_feedback_since", lambda days=7: raw_feedback)
    monkeypatch.setattr(
        supabase_mod,
        "get_signal_platforms",
        lambda signal_ids: {
            signal_id: signal_platforms[signal_id]
            for signal_id in signal_ids
            if signal_id in signal_platforms
        },
    )
    monkeypatch.setattr(supabase_mod, "get_recent_signals", fail_if_recent_signals_requested)
    monkeypatch.setattr(supabase_mod, "save_evolution_log", lambda log: True)

    await main_mod.run_evolution_weekly(total_signals=215)

    assert captured["feedback_count"] == 215
    assert captured["platform_feedback_counts"] == {
        "reddit": {"upvotes": 10, "downvotes": 0},
        "twitter": {"upvotes": 0, "downvotes": 205},
    }


@pytest.mark.asyncio
async def test_agent_collect_passes_saved_source_reliability_to_strategy(monkeypatch):
    """Collection strategy should consume persisted reliability scores from storage."""
    from hedwig import main as main_mod
    from hedwig.engine import agent_collector as collector_mod
    from hedwig.memory import store as memory_store_mod
    from hedwig.storage import supabase as supabase_mod

    captured: dict[str, object] = {}

    monkeypatch.setattr(
        supabase_mod,
        "get_source_reliability",
        lambda: {"reddit": 0.91, "twitter": 0.12},
    )
    monkeypatch.setattr(memory_store_mod.MemoryStore, "get_latest", lambda self: None)

    async def fake_generate_strategy(
        self,
        source_reliability=None,
        user_memory_summary="",
    ):
        captured["source_reliability"] = source_reliability
        captured["user_memory_summary"] = user_memory_summary
        return {
            "priority_sources": ["reddit"],
            "source_configs": {"reddit": {"limit": 5}},
            "explore_sources": [],
            "skip_sources": [],
            "focus_keywords": [],
            "exploration_queries": [],
        }

    async def fake_collect_with_strategy(self, strategy):
        captured["strategy"] = strategy
        return []

    monkeypatch.setattr(collector_mod.AgentCollector, "generate_strategy", fake_generate_strategy)
    monkeypatch.setattr(collector_mod.AgentCollector, "collect_with_strategy", fake_collect_with_strategy)

    posts, strategy = await main_mod.agent_collect(llm_client=None)

    assert posts == []
    assert strategy["priority_sources"] == ["reddit"]
    assert captured["source_reliability"] == {"reddit": 0.91, "twitter": 0.12}
    assert captured["user_memory_summary"] == ""


def test_local_source_reliability_round_trip(monkeypatch, tmp_path):
    """SQLite storage should persist and return source reliability scores."""
    from hedwig.storage import local as local_storage

    monkeypatch.setenv("HEDWIG_DB_PATH", str(tmp_path / "hedwig.db"))

    assert local_storage.save_source_reliability({"reddit": 1.0, "twitter": 0.0})

    scores = local_storage.get_source_reliability()

    assert scores["reddit"] == pytest.approx(1.0, abs=0.01)
    assert scores["twitter"] == pytest.approx(0.0, abs=0.01)
