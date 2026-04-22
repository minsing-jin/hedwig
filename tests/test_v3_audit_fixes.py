"""Audit-pass tests — proves each of the 8 drift items is closed.

See docs/phase_reports/audit_v3.md for the table.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
import yaml


@pytest.fixture
def tmp_env(monkeypatch, tmp_path):
    monkeypatch.setenv("HEDWIG_STORAGE", "sqlite")
    monkeypatch.setenv("HEDWIG_DB_PATH", str(tmp_path / "hedwig.db"))
    monkeypatch.setenv("HEDWIG_LTR_WEIGHTS", str(tmp_path / "ltr_weights.json"))
    monkeypatch.setenv("HEDWIG_EMBED_CACHE", str(tmp_path / "embed_cache.json"))
    # Reset the algorithm version seed flag so the test gets a clean start
    import hedwig.config as _cfg
    _cfg._ALGORITHM_VERSION_SEEDED = False
    yield tmp_path


# ---------------------------------------------------------------------------
# D1 — algorithm.yaml default is a true 4-component hybrid
# ---------------------------------------------------------------------------

def test_default_algorithm_is_true_hybrid():
    from hedwig.config import load_algorithm_config
    cfg = load_algorithm_config()
    components = cfg["ranking"]["components"]
    enabled = [n for n, s in components.items() if s.get("enabled")]
    assert set(enabled) >= {"llm_judge", "ltr", "content_based", "popularity_prior"}, (
        f"expected ≥4 hybrid components enabled by default, got {enabled}"
    )


# ---------------------------------------------------------------------------
# D2 — NL editor versions criteria edits
# ---------------------------------------------------------------------------

def test_nl_editor_confirm_writes_criteria_version(tmp_env, monkeypatch):
    tmp_criteria = tmp_env / "criteria.yaml"
    tmp_criteria.write_text(yaml.safe_dump({"signal_preferences": {"care_about": []}}))
    monkeypatch.setattr("hedwig.onboarding.nl_editor.CRITERIA_PATH", tmp_criteria)

    from hedwig.onboarding.nl_editor import confirm_edit
    from hedwig.storage import get_criteria_versions

    r = confirm_edit(
        [{"op": "add", "path": "signal_preferences.care_about", "value": "agent"}],
        intent="add agent",
    )
    assert r["ok"]
    assert r.get("version") == 1
    assert r.get("diff")

    # second edit bumps version
    r2 = confirm_edit(
        [{"op": "add", "path": "signal_preferences.care_about", "value": "mcp"}],
        intent="add mcp",
    )
    assert r2["version"] == 2

    versions = get_criteria_versions()
    assert len(versions) == 2
    # newest first
    assert versions[0]["version"] == 2
    assert versions[0]["created_by"] == "user_nl_editor"
    assert versions[0]["diff_from_previous"]


# ---------------------------------------------------------------------------
# D3 — synthesize_fitness honors algorithm.yaml fitness spec
# ---------------------------------------------------------------------------

def test_synthesize_fitness_reads_weights(tmp_env):
    from hedwig.evolution.sandbox import synthesize_fitness

    cfg = {
        "ranking": {"components": {"a": {"enabled": True, "weight": 0.5}}},
        "fitness": {
            "short_horizon": {"weight": 1.0},
            "long_horizon": {"weight": 0.0},
            "diversity_bonus": {"enabled": False},
        },
    }
    events = [{"kind": "upvote"}, {"kind": "upvote"}, {"kind": "downvote"}]
    out = synthesize_fitness(cfg, recent_events=events)
    # short-only, upvote=2/3 ≈ 0.666...
    assert abs(out["predicted_fitness"] - (2 / 3)) < 1e-3


def test_synthesize_fitness_long_horizon_retention_acceptance(tmp_env):
    from hedwig.evolution.sandbox import synthesize_fitness

    cfg = {
        "ranking": {"components": {"a": {"enabled": True, "weight": 0.3},
                                   "b": {"enabled": True, "weight": 0.3},
                                   "c": {"enabled": True, "weight": 0.3}}},
        "fitness": {
            "short_horizon": {"weight": 0.0},
            "long_horizon": {"weight": 1.0},
            "diversity_bonus": {"enabled": False},
        },
    }
    # Simulate feedback across 14 distinct days + 2 accepts out of 4 asks
    now = datetime.now(tz=timezone.utc)
    events = []
    for d in range(14):
        events.append({"kind": "upvote", "captured_at": (now - timedelta(days=d)).isoformat()})
    events.extend([
        {"kind": "qa_accept", "captured_at": now.isoformat()},
        {"kind": "qa_accept", "captured_at": now.isoformat()},
        {"kind": "qa_ask", "captured_at": now.isoformat()},
        {"kind": "qa_reject", "captured_at": now.isoformat()},
    ])
    out = synthesize_fitness(cfg, recent_events=events)
    assert out["retention"] == pytest.approx(14 / 28, abs=1e-3)
    assert out["acceptance"] == pytest.approx(2 / 4, abs=1e-3)
    expected = out["retention"] * out["acceptance"]
    assert out["predicted_fitness"] == pytest.approx(expected, abs=1e-3)


# ---------------------------------------------------------------------------
# D4 — Platform.PODCAST exists and is used
# ---------------------------------------------------------------------------

def test_platform_podcast_enum_exists():
    from hedwig.models import Platform
    assert Platform.PODCAST.value == "podcast"


def test_podcast_source_uses_podcast_platform():
    from hedwig.sources.podcast import PodcastSource
    assert PodcastSource.platform.value == "podcast"


def test_pre_scorer_knows_podcast():
    from hedwig.engine.pre_scorer import ENGAGEMENT_BASELINES, SOURCE_AUTHORITY
    assert "podcast" in ENGAGEMENT_BASELINES
    assert SOURCE_AUTHORITY["podcast"] > 0


# ---------------------------------------------------------------------------
# D5 — algorithm_versions seeded on first config load
# ---------------------------------------------------------------------------

def test_algorithm_version_seeds_on_first_load(tmp_env):
    from hedwig.config import load_algorithm_config
    from hedwig.storage import get_algorithm_history

    assert get_algorithm_history() == []
    load_algorithm_config()
    history = get_algorithm_history()
    assert len(history) == 1
    assert history[0]["version"] == 1
    assert history[0]["origin"] in ("initial_default_v3_hybrid", "initial_default")


def test_algorithm_version_seed_idempotent(tmp_env):
    from hedwig.config import load_algorithm_config
    from hedwig.storage import get_algorithm_history
    load_algorithm_config()
    load_algorithm_config()
    load_algorithm_config()
    assert len(get_algorithm_history()) == 1


# ---------------------------------------------------------------------------
# D6 — LLM judge applies only to top_k (expensive stage is bounded)
# ---------------------------------------------------------------------------

def test_llm_judge_applies_to_top_k_only(tmp_env, monkeypatch):
    from hedwig.engine.ensemble import combine as combine_mod
    from hedwig.engine.ensemble import llm_judge as llm_mod
    from hedwig.models import Platform, RawPost

    call_sizes: list[int] = []

    class FakeLLM:
        name = "llm_judge"
        def __init__(self):
            self.last_scored = {}
        async def score_posts(self, posts, context=None):
            call_sizes.append(len(posts))
            return [0.9] * len(posts)

    monkeypatch.setattr(llm_mod, "LLMJudge", FakeLLM)

    posts = [
        RawPost(
            platform=Platform.HACKERNEWS,
            external_id=f"e{i}",
            title=f"Post {i}",
            url="",
            content="body",
            score=10,
            comments_count=2,
        )
        for i in range(50)
    ]
    ranked = asyncio.run(combine_mod.rank_with_ensemble(posts, top_k=10))
    assert len(ranked) == 50
    # LLM judge should have been invoked exactly once with top_k=10 posts
    assert call_sizes == [10], f"expected one LLM call of size 10, got {call_sizes}"


# ---------------------------------------------------------------------------
# D7 — adopt() uses ISO datetime on updated_at
# ---------------------------------------------------------------------------

def test_meta_adopt_updated_at_is_iso(tmp_env, monkeypatch):
    tmp_algo = tmp_env / "algorithm.yaml"
    tmp_algo.write_text(yaml.safe_dump({
        "version": 7,
        "retrieval": {"top_n": 200},
        "ranking": {"top_k": 30, "components": {"a": {"enabled": True, "weight": 0.5}}},
        "fitness": {"adoption_threshold": 0.05},
        "meta_evolution": {"enabled": True},
    }))
    monkeypatch.setattr("hedwig.evolution.meta.ALGORITHM_PATH", tmp_algo)
    monkeypatch.setattr("hedwig.evolution.meta.ALGORITHM_LOG_PATH", tmp_env / "algorithm_log.jsonl")

    from hedwig.evolution.meta import adopt
    out = adopt({"version": 7, "ranking": {"components": {}}}, reason="test", fitness_delta=0.1)
    assert out["version"] == 8
    # ISO datetime -> contains 'T' and ends with offset
    assert "T" in str(out["updated_at"])


# ---------------------------------------------------------------------------
# D8 — Content ranker consumes criteria_keywords from context
# ---------------------------------------------------------------------------

def test_content_ranker_uses_criteria_keywords_context(tmp_env, monkeypatch):
    monkeypatch.setattr("hedwig.engine.ensemble.content.OPENAI_API_KEY", "")
    monkeypatch.setattr(
        "hedwig.engine.ensemble.content.load_criteria",
        lambda: {},
    )
    from hedwig.engine.ensemble.content import ContentRanker
    from hedwig.models import Platform, RawPost

    posts = [
        RawPost(platform=Platform.HACKERNEWS, external_id="a", title="zigzag about agents",
                url="", content=""),
        RawPost(platform=Platform.HACKERNEWS, external_id="b", title="totally different stuff",
                url="", content=""),
    ]
    scores = asyncio.run(ContentRanker().score_posts(
        posts, context={"criteria_keywords": ["agents"]},
    ))
    assert scores[0] > scores[1]
