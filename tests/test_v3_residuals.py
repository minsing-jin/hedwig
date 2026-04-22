"""Post-Phase residual tests — the items that were originally documented as
deferred in FINAL.md. Each test proves the gap is now closed."""
from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient


@pytest.fixture
def tmp_env(monkeypatch, tmp_path):
    monkeypatch.setenv("HEDWIG_STORAGE", "sqlite")
    monkeypatch.setenv("HEDWIG_DB_PATH", str(tmp_path / "hedwig.db"))
    monkeypatch.setenv("HEDWIG_LTR_WEIGHTS", str(tmp_path / "ltr_weights.json"))
    monkeypatch.setenv("HEDWIG_EMBED_CACHE", str(tmp_path / "embed_cache.json"))
    monkeypatch.setenv("HEDWIG_TRANSCRIPT_CACHE", str(tmp_path / "transcripts"))
    yield tmp_path


# --- R1: embeddings w/ Jaccard fallback when no API key ---------------------

def test_content_ranker_falls_back_when_no_api_key(tmp_env, monkeypatch):
    monkeypatch.setattr("hedwig.engine.ensemble.content.OPENAI_API_KEY", "")
    monkeypatch.setattr(
        "hedwig.engine.ensemble.content.load_criteria",
        lambda: {"signal_preferences": {"care_about": ["alpha"]}},
    )
    from hedwig.engine.ensemble.content import ContentRanker
    from hedwig.models import Platform, RawPost
    posts = [
        RawPost(platform=Platform.HACKERNEWS, external_id="a", title="alpha beta gamma",
                url="", content=""),
        RawPost(platform=Platform.HACKERNEWS, external_id="b", title="unrelated text",
                url="", content=""),
    ]
    scores = asyncio.run(ContentRanker().score_posts(posts))
    assert scores[0] > scores[1]


def test_content_ranker_disable_embeddings_flag(tmp_env, monkeypatch):
    monkeypatch.setattr("hedwig.engine.ensemble.content.OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("HEDWIG_DISABLE_EMBEDDINGS", "1")
    monkeypatch.setattr(
        "hedwig.engine.ensemble.content.load_criteria",
        lambda: {"signal_preferences": {"care_about": ["agent"]}},
    )
    from hedwig.engine.ensemble.content import ContentRanker
    from hedwig.models import Platform, RawPost
    posts = [
        RawPost(platform=Platform.HACKERNEWS, external_id="a", title="agent",
                url="", content=""),
    ]
    # Must not touch OpenAI — just Jaccard path
    scores = asyncio.run(ContentRanker().score_posts(posts))
    assert len(scores) == 1


# --- R2: run_two_stage_as_signals produces ScoredSignal list ----------------

def test_two_stage_as_signals(tmp_env, monkeypatch):
    from hedwig.engine.ensemble import llm_judge as llm_mod
    class FakeLLM:
        name = "llm_judge"
        def __init__(self):
            self.last_scored = {}
        async def score_posts(self, posts, context=None):
            return [0.8] * len(posts)
    monkeypatch.setattr(llm_mod, "LLMJudge", FakeLLM)

    from hedwig.engine.ensemble.combine import run_two_stage_as_signals
    from hedwig.models import Platform, RawPost, ScoredSignal
    posts = [
        RawPost(
            platform=Platform.HACKERNEWS,
            external_id=f"e{i}",
            title=f"headline {i}",
            url="",
            content="body",
            score=50,
            comments_count=5,
            published_at=datetime.now(tz=timezone.utc),
        )
        for i in range(6)
    ]
    signals, stats = asyncio.run(run_two_stage_as_signals(posts, ["headline"]))
    assert all(isinstance(s, ScoredSignal) for s in signals)
    assert stats["signals_produced"] == len(signals)


# --- R3: MCP HTTP adapter parses a mock response ---------------------------

def test_mcp_adapter_parses_json_rpc(monkeypatch):
    """Route the adapter to a stubbed httpx client that returns a fake JSON-RPC body."""
    from hedwig.sources._mcp_adapter import MCPSourceAdapter
    import httpx

    class _Resp:
        status_code = 200
        def raise_for_status(self): pass
        def json(self): return {
            "jsonrpc": "2.0",
            "id": 1,
            "result": {
                "items": [
                    {"id": "1", "title": "Hello", "link": "https://ex.com/1",
                     "summary": "body", "author": "alice", "points": 10},
                    {"id": "2", "title": "World", "link": "https://ex.com/2",
                     "summary": "body2", "author": "bob", "points": 3},
                ],
            },
        }

    class _Client:
        def __init__(self, *a, **kw): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def post(self, *a, **kw): return _Resp()

    monkeypatch.setattr(httpx, "AsyncClient", _Client)

    adapter = MCPSourceAdapter(
        mcp_url="http://fake/mcp",
        tool_name="list_items",
        mapping={"external_id": "$.id", "title": "$.title", "url": "$.link",
                 "content": "$.summary", "author": "$.author", "score": "$.points"},
    )
    posts = asyncio.run(adapter.fetch(limit=10))
    assert len(posts) == 2
    assert posts[0].title == "Hello"
    assert posts[0].score == 10
    assert posts[1].url == "https://ex.com/2"


# --- R4: Skill adapter loads a collect() module --------------------------

def test_skill_adapter_loads_module(tmp_path):
    skill_dir = tmp_path / "my_skill"
    skill_dir.mkdir()
    (skill_dir / "collect.py").write_text(
        "async def collect(limit=10):\n"
        "    return [\n"
        "        {'id': 'x', 'title': 'From skill', 'url': 'https://sk/1', 'content': 'c', 'author': 'a', 'score': 5}\n"
        "    ]\n"
    )
    from hedwig.sources._skill_adapter import SkillSourceAdapter
    adapter = SkillSourceAdapter(skill_path=skill_dir)
    posts = asyncio.run(adapter.fetch(limit=10))
    assert len(posts) == 1
    assert posts[0].title == "From skill"


def test_skill_adapter_missing_dir_returns_empty(tmp_path):
    from hedwig.sources._skill_adapter import SkillSourceAdapter
    adapter = SkillSourceAdapter(skill_path=tmp_path / "nope")
    posts = asyncio.run(adapter.fetch(limit=5))
    assert posts == []


# --- R5: feature_suggest_from_papers mutation ------------------------------

def test_feature_suggest_from_papers_no_api_key_noops(tmp_env, monkeypatch):
    monkeypatch.setattr("hedwig.config.OPENAI_API_KEY", "")
    from hedwig.evolution.meta import generate_candidate
    baseline = {
        "version": 1,
        "ranking": {"components": {"ltr": {"enabled": False, "weight": 0.0, "features": ["a"]}}},
    }
    cand, strat = generate_candidate(baseline, strategy="feature_suggest_from_papers")
    assert strat == "feature_suggest_from_papers"
    # Without a key the strategy must return cfg unchanged
    assert cand["ranking"]["components"]["ltr"]["features"] == ["a"]


def test_feature_suggest_listed_in_mutation_strategies():
    from hedwig.evolution.meta import MUTATION_STRATEGIES
    assert "feature_suggest_from_papers" in MUTATION_STRATEGIES


# --- R6: transcription disabled flag keeps audio untouched ------------------

def test_transcribe_no_flag_returns_none(tmp_env, monkeypatch):
    monkeypatch.delenv("HEDWIG_PODCAST_TRANSCRIBE", raising=False)
    from hedwig.sources._transcribe import transcribe_url
    result = asyncio.run(transcribe_url("https://example.com/audio.mp3"))
    assert result is None


def test_enrich_podcast_noop_when_no_audio(tmp_env):
    from hedwig.sources._transcribe import enrich_podcast_post
    from hedwig.models import Platform, RawPost
    post = RawPost(
        platform=Platform.PODCAST,
        external_id="p", title="t", url="", content="x",
        extra={"medium": "podcast"},
    )
    result = asyncio.run(enrich_podcast_post(post))
    assert result is post
    assert result.content == "x"


# --- R7: dashboard widget routes render ------------------------------------

def test_dashboard_widget_routes(tmp_env):
    from hedwig.dashboard.app import create_app
    client = TestClient(create_app())
    for path in ("/evolution", "/sandbox", "/meta"):
        resp = client.get(path)
        assert resp.status_code == 200
        assert "<html" in resp.text.lower() or "<!doctype" in resp.text.lower()


# --- R8: critical-loop + meta-cycle CLI flags wire up ----------------------

def test_cli_recognizes_new_flags():
    import subprocess
    result = subprocess.run(
        [".venv/bin/python", "-m", "hedwig", "--help"],
        capture_output=True, text=True, cwd=str(Path(__file__).resolve().parents[1]),
        timeout=15,
    )
    assert result.returncode == 0
    assert "--critical-loop" in result.stdout
    assert "--meta-cycle" in result.stdout
    assert "--critical-interval" in result.stdout
