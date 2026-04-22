"""Phase 5 tests — multimodal sources + critical polling."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest


@pytest.fixture
def tmp_env(monkeypatch, tmp_path):
    monkeypatch.setenv("HEDWIG_STORAGE", "sqlite")
    monkeypatch.setenv("HEDWIG_DB_PATH", str(tmp_path / "hedwig.db"))
    yield tmp_path


def test_arxiv_recsys_query_shape(tmp_env):
    from hedwig.sources.arxiv_recsys import ArxivRecSysSource
    src = ArxivRecSysSource()
    q = src._build_query()
    assert "cs.IR" in q
    assert "cs.LG" in q
    assert "recommender" in q
    assert "contextual bandit" in q


def test_arxiv_recsys_registered():
    from hedwig.sources import get_registered_sources
    registry = get_registered_sources()
    assert "arxiv_recsys" in registry


def test_podcast_registered():
    from hedwig.sources import get_registered_sources
    registry = get_registered_sources()
    assert "podcast" in registry


def test_podcast_env_feed_parsing(monkeypatch):
    monkeypatch.setenv(
        "HEDWIG_PODCAST_FEEDS",
        "https://example.com/rss|Latent Space, https://another.com/feed|Decoder",
    )
    from hedwig.sources.podcast import _parse_feeds_env
    feeds = _parse_feeds_env()
    assert len(feeds) == 2
    assert feeds[0][1] == "Latent Space"


def test_podcast_no_feeds_returns_empty(monkeypatch):
    import asyncio
    monkeypatch.delenv("HEDWIG_PODCAST_FEEDS", raising=False)
    from hedwig.sources.podcast import PodcastSource
    src = PodcastSource(feeds=[])
    result = asyncio.run(src.fetch())
    assert result == []


def _make_post(title, platform="hackernews", hours_ago=1, score=100, uid=""):
    from hedwig.models import Platform, RawPost
    return RawPost(
        platform=Platform(platform),
        external_id=f"ext-{platform}-{uid or title}",
        title=title,
        url="https://example.com/" + title,
        content=title,
        author="alice",
        score=score,
        comments_count=10,
        published_at=datetime.now(tz=timezone.utc) - timedelta(hours=hours_ago),
    )


def test_critical_score_factors():
    from hedwig.engine.critical import critical_score
    post = _make_post("AGI breakthrough", hours_ago=1, score=500)
    score, factors = critical_score(post, [post])
    assert 0 <= score <= 1
    assert "engagement" in factors
    assert "recency_6h_halflife" in factors


def test_critical_filter_requires_convergence():
    from hedwig.engine.critical import filter_critical
    # Single platform, high engagement — should NOT qualify (convergence = 0)
    posts = [_make_post("Agent X launches", hours_ago=1, score=1000)]
    qualified = filter_critical(posts, threshold=0.5)
    assert qualified == []


def test_critical_filter_accepts_cross_platform():
    from hedwig.engine.critical import filter_critical
    # Same headline on 3 different platforms, all recent + highly-engaged
    title = "GPT release shipping"
    posts = [
        _make_post(title, platform="hackernews", hours_ago=1, score=500),
        _make_post(title, platform="reddit", hours_ago=1, score=800),
        _make_post(title, platform="twitter", hours_ago=1, score=300),
    ]
    qualified = filter_critical(posts, threshold=0.5, min_convergence_platforms=2)
    assert len(qualified) >= 1
    for post, score, factors in qualified:
        assert factors["convergence"] > 0


def test_critical_endpoint(tmp_env, monkeypatch):
    """Critical endpoint must not crash when all sources error out."""
    from fastapi.testclient import TestClient
    from hedwig.dashboard.app import create_app

    # Stub the registry so we don't hit network in CI/tests
    def empty_registry():
        return {}
    monkeypatch.setattr(
        "hedwig.sources.get_registered_sources", empty_registry
    )

    client = TestClient(create_app())
    resp = client.post("/run/critical")
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert data["scanned"] == 0
    assert data["qualified"] == 0
