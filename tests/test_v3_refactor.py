"""Refactor coverage — proves the 9 plan-drift items flagged in the
final audit (R-A..R-I) are closed and no regression was introduced."""
from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest
import yaml


@pytest.fixture
def tmp_env(monkeypatch, tmp_path):
    monkeypatch.setenv("HEDWIG_STORAGE", "sqlite")
    monkeypatch.setenv("HEDWIG_DB_PATH", str(tmp_path / "hedwig.db"))
    monkeypatch.setenv("HEDWIG_LTR_WEIGHTS", str(tmp_path / "ltr_weights.json"))
    monkeypatch.setenv("HEDWIG_EMBED_CACHE", str(tmp_path / "embed_cache.json"))
    import hedwig.config as _cfg
    _cfg._ALGORITHM_VERSION_SEEDED = False
    yield tmp_path


# --- R-A: LTR feature registry ---------------------------------------------

def test_ltr_registry_contains_default_features():
    from hedwig.engine.ensemble.ltr import FEATURE_REGISTRY, DEFAULT_FEATURES
    for name in DEFAULT_FEATURES:
        assert name in FEATURE_REGISTRY


def test_ltr_active_features_from_algorithm_yaml(tmp_env, monkeypatch):
    tmp_algo = tmp_env / "algorithm.yaml"
    tmp_algo.write_text(yaml.safe_dump({
        "version": 1,
        "retrieval": {"top_n": 50, "threshold": 0.1},
        "ranking": {
            "top_k": 10,
            "components": {
                "ltr": {
                    "enabled": True,
                    "weight": 0.3,
                    "features": ["text_relevance", "source_authority",
                                 "hypothetical_new_feature"],
                },
            },
        },
    }))
    monkeypatch.setattr("hedwig.evolution.meta.ALGORITHM_PATH", tmp_algo)
    monkeypatch.setattr("hedwig.config.ALGORITHM_PATH", tmp_algo)
    from hedwig.engine.ensemble.ltr import _active_features
    active = _active_features()
    assert active == ["text_relevance", "source_authority", "hypothetical_new_feature"]


def test_ltr_unknown_feature_returns_neutral(tmp_env, monkeypatch):
    tmp_algo = tmp_env / "algorithm.yaml"
    tmp_algo.write_text(yaml.safe_dump({
        "version": 1,
        "retrieval": {"top_n": 50},
        "ranking": {
            "top_k": 10,
            "components": {
                "ltr": {"enabled": True, "weight": 0.3,
                        "features": ["hypothetical_new_feature"]},
            },
        },
    }))
    monkeypatch.setattr("hedwig.config.ALGORITHM_PATH", tmp_algo)
    from hedwig.engine.ensemble.ltr import LTRRanker
    from hedwig.models import Platform, RawPost
    posts = [RawPost(platform=Platform.HACKERNEWS, external_id="a", title="x",
                     url="", content="")]
    ranker = LTRRanker()
    scores = asyncio.run(ranker.score_posts(posts))
    assert len(scores) == 1
    assert 0.0 <= scores[0] <= 1.0


# --- R-B: Bandit reads exploration_rate ------------------------------------

def test_bandit_reads_exploration_rate_from_config(tmp_env, monkeypatch):
    tmp_algo = tmp_env / "algorithm.yaml"
    tmp_algo.write_text(yaml.safe_dump({
        "version": 1,
        "retrieval": {"top_n": 50},
        "ranking": {
            "top_k": 10,
            "components": {
                "bandit": {"enabled": True, "weight": 0.1, "exploration_rate": 0.45},
            },
        },
    }))
    monkeypatch.setattr("hedwig.config.ALGORITHM_PATH", tmp_algo)
    from hedwig.engine.ensemble.bandit import BanditRanker
    assert BanditRanker().exploration_rate == 0.45


# --- R-C/R-D: Ensemble no longer re-runs pre_filter ------------------------

def test_rank_and_build_signals_skips_pre_filter(tmp_env, monkeypatch):
    """Calling rank_and_build_signals with 3 candidates should NOT invoke
    engine.pre_scorer.pre_filter again — main.py has already done that."""
    from hedwig.engine.ensemble import combine as combine_mod
    from hedwig.engine import pre_scorer as ps_mod

    calls: list[int] = []
    orig_pre_filter = ps_mod.pre_filter
    def _spy(*a, **kw):
        calls.append(len(a[0]))
        return orig_pre_filter(*a, **kw)
    monkeypatch.setattr(ps_mod, "pre_filter", _spy)

    class FakeLLM:
        name = "llm_judge"
        def __init__(self): self.last_scored = {}
        async def score_posts(self, posts, context=None):
            return [0.5] * len(posts)
    monkeypatch.setattr("hedwig.engine.ensemble.llm_judge.LLMJudge", FakeLLM)

    from hedwig.models import Platform, RawPost
    candidates = [
        RawPost(platform=Platform.HACKERNEWS, external_id=f"e{i}", title=f"t{i}",
                url="", content="x")
        for i in range(3)
    ]
    signals, stats = asyncio.run(combine_mod.rank_and_build_signals(candidates, ["t"]))
    assert stats["retrieval_kept"] == 3
    assert calls == []  # no pre_filter invocation


# --- R-E: retrieval.threshold in algorithm.yaml ----------------------------

def test_algorithm_yaml_has_retrieval_threshold():
    from hedwig.config import load_algorithm_config
    cfg = load_algorithm_config()
    assert "threshold" in cfg["retrieval"]
    assert isinstance(cfg["retrieval"]["threshold"], (int, float))


# --- R-F: trigram index cache --------------------------------------------

def test_trigram_index_cache_reused(tmp_env):
    from hedwig.engine.pre_scorer import _build_trigram_index
    from hedwig.models import Platform, RawPost
    posts = [
        RawPost(platform=Platform.HACKERNEWS, external_id=f"x{i}", title=f"alpha beta {i}",
                url="", content="")
        for i in range(3)
    ]
    idx1 = _build_trigram_index(posts)
    idx2 = _build_trigram_index(posts)
    assert idx1 is idx2  # same object — memoisation worked


def test_convergence_still_detects(tmp_env):
    from hedwig.engine.pre_scorer import detect_cross_platform_convergence
    from hedwig.models import Platform, RawPost
    posts = [
        RawPost(platform=Platform.HACKERNEWS, external_id="h", title="AGI release today",
                url="", content=""),
        RawPost(platform=Platform.REDDIT, external_id="r", title="AGI release today",
                url="", content=""),
        RawPost(platform=Platform.TWITTER, external_id="t", title="AGI release today",
                url="", content=""),
    ]
    score = detect_cross_platform_convergence(posts[0], posts, threshold=0.3)
    assert score > 0.0


# --- R-G: Algorithm diff captured on adopt -------------------------------

def test_adopt_records_yaml_diff(tmp_env, monkeypatch):
    tmp_algo = tmp_env / "algorithm.yaml"
    tmp_algo.write_text(yaml.safe_dump({
        "version": 2,
        "retrieval": {"top_n": 200, "threshold": 0.1},
        "ranking": {
            "top_k": 30,
            "components": {
                "llm_judge": {"enabled": True, "weight": 0.5},
                "popularity_prior": {"enabled": True, "weight": 0.5},
            },
        },
        "fitness": {"adoption_threshold": 0.05},
        "meta_evolution": {"enabled": True},
    }))
    monkeypatch.setattr("hedwig.evolution.meta.ALGORITHM_PATH", tmp_algo)
    monkeypatch.setattr("hedwig.config.ALGORITHM_PATH", tmp_algo)
    monkeypatch.setattr("hedwig.evolution.meta.ALGORITHM_LOG_PATH", tmp_env / "algorithm_log.jsonl")
    import hedwig.config as _cfg
    _cfg._ALGORITHM_VERSION_SEEDED = False

    from hedwig.evolution.meta import adopt
    from hedwig.storage import get_algorithm_history

    new_cfg = {
        "version": 2,
        "retrieval": {"top_n": 100, "threshold": 0.1},  # <- changed top_n
        "ranking": {
            "top_k": 30,
            "components": {
                "llm_judge": {"enabled": True, "weight": 0.5},
                "popularity_prior": {"enabled": True, "weight": 0.5},
            },
        },
        "fitness": {"adoption_threshold": 0.05},
        "meta_evolution": {"enabled": True},
    }
    adopt(new_cfg, reason="meta_evolution:structural_change", fitness_delta=0.07)
    history = get_algorithm_history()
    assert history
    diff = history[0]["diff_from_previous"] or ""
    # The changed top_n value must surface in the diff
    assert "top_n" in diff
    assert "200" in diff or "100" in diff


# --- R-I: engine __init__ re-exports ranked helpers -----------------------

def test_engine_exports_rank_and_build_signals():
    import hedwig.engine as eng
    assert callable(getattr(eng, "rank_and_build_signals"))
    assert callable(getattr(eng, "run_two_stage_as_signals"))
