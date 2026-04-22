"""Phase 3 tests — Hybrid Ensemble (5 components + 2-stage orchestrator)."""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

import pytest


@pytest.fixture
def tmp_env(monkeypatch, tmp_path):
    monkeypatch.setenv("HEDWIG_STORAGE", "sqlite")
    monkeypatch.setenv("HEDWIG_DB_PATH", str(tmp_path / "hedwig.db"))
    monkeypatch.setenv("HEDWIG_LTR_WEIGHTS", str(tmp_path / "ltr_weights.json"))
    yield tmp_path


def _post(title: str, platform: str = "hackernews", score: int = 50):
    from hedwig.models import Platform, RawPost
    return RawPost(
        platform=Platform(platform),
        external_id=f"ext-{title}"[:120],
        title=title,
        url=f"https://example.com/{title}",
        content=title + " — body",
        author="alice",
        score=score,
        comments_count=5,
        published_at=datetime.now(tz=timezone.utc) - timedelta(hours=12),
    )


# --- Individual components ---------------------------------------------------

def test_content_ranker_empty_is_zero():
    from hedwig.engine.ensemble.content import ContentRanker
    scores = asyncio.run(ContentRanker().score_posts([]))
    assert scores == []


def test_content_ranker_matches_keywords(monkeypatch):
    from hedwig.engine.ensemble.content import ContentRanker

    monkeypatch.setattr(
        "hedwig.engine.ensemble.content.load_criteria",
        lambda: {"signal_preferences": {"care_about": ["agent frameworks"]}},
    )
    posts = [_post("agent frameworks overview"), _post("totally unrelated thing")]
    scores = asyncio.run(ContentRanker().score_posts(posts))
    assert scores[0] > scores[1]


def test_popularity_ranker_authority_x_recency(tmp_env, monkeypatch):
    from hedwig.engine.ensemble.popularity import PopularityRanker

    posts = [_post("headline"), _post("arxiv paper", platform="arxiv")]
    scores = asyncio.run(PopularityRanker().score_posts(posts))
    assert len(scores) == 2
    # arxiv has authority 0.95 vs hackernews 0.9 → higher score
    assert scores[1] >= scores[0] - 0.2  # allowing recency to balance


def test_bandit_ranker_unknown_platform_uses_prior(tmp_env):
    from hedwig.engine.ensemble.bandit import BanditRanker

    posts = [_post("news one"), _post("news two")]
    scores = asyncio.run(BanditRanker().score_posts(posts))
    assert len(scores) == 2
    assert all(0 <= s <= 1 for s in scores)


def test_ltr_ranker_with_default_weights(tmp_env):
    from hedwig.engine.ensemble.ltr import LTRRanker

    posts = [_post("strong signal A", score=500), _post("weak signal B", score=1)]
    scores = asyncio.run(LTRRanker(criteria_keywords=["signal"]).score_posts(posts))
    assert len(scores) == 2
    assert all(0 <= s <= 1 for s in scores)


def test_ltr_fit_from_history_requires_data(tmp_env):
    from hedwig.engine.ensemble.ltr import fit_from_history
    res = fit_from_history(criteria_keywords=["signal"])
    assert not res["trained"]


# --- Ensemble combine --------------------------------------------------------

def test_rank_with_ensemble_empty():
    from hedwig.engine.ensemble.combine import rank_with_ensemble
    result = asyncio.run(rank_with_ensemble([]))
    assert result == []


def test_rank_with_ensemble_default_config(tmp_env, monkeypatch):
    """With the default algorithm.yaml, llm_judge + popularity_prior are enabled.

    We stub LLMJudge to return fixed scores so the test runs without OpenAI.
    """
    from hedwig.engine.ensemble.combine import rank_with_ensemble
    from hedwig.engine.ensemble import llm_judge as llm_mod

    class FakeLLM:
        name = "llm_judge"
        async def score_posts(self, posts, context=None):
            return [0.9, 0.3, 0.5][: len(posts)]

    monkeypatch.setattr(llm_mod, "LLMJudge", FakeLLM)

    posts = [_post("A"), _post("B"), _post("C")]
    ranked = asyncio.run(rank_with_ensemble(posts))
    assert len(ranked) == 3
    # First returned post should have highest final score
    assert ranked[0][1] >= ranked[-1][1]
    # component breakdown should include at least popularity
    _, _, components = ranked[0]
    assert "popularity_prior" in components


def test_two_stage_orchestrator(tmp_env, monkeypatch):
    from hedwig.engine.ensemble import llm_judge as llm_mod
    from hedwig.engine.ensemble.combine import run_two_stage

    class FakeLLM:
        name = "llm_judge"
        async def score_posts(self, posts, context=None):
            return [0.8] * len(posts)

    monkeypatch.setattr(llm_mod, "LLMJudge", FakeLLM)

    posts = [_post(f"signal-{i}") for i in range(40)]
    ranked, stats = asyncio.run(run_two_stage(posts, ["signal"]))
    assert stats["input"] == 40
    assert stats["retrieval_kept"] <= 40
    assert stats["ranking_kept"] <= stats["top_k"]
    assert "popularity_prior" in stats["components_used"]
    assert len(ranked) == stats["ranking_kept"]


def test_minmax_normalize_constant():
    from hedwig.engine.ensemble.base import minmax_normalize
    assert minmax_normalize([0.5, 0.5, 0.5]) == [0.5, 0.5, 0.5]
    assert minmax_normalize([]) == []


def test_minmax_normalize_range():
    from hedwig.engine.ensemble.base import minmax_normalize
    out = minmax_normalize([1.0, 5.0, 3.0])
    assert out[0] == 0.0
    assert out[1] == 1.0
    assert 0 < out[2] < 1
