"""Regression test for the tz-naive vs tz-aware TypeError in enrich_score.

Originally raised by a live daily run: `_rows_to_posts` created RawPosts
without `published_at`, so the default `datetime.utcnow()` produced a naive
datetime that `topic_persistence_score` then compared against a tz-aware
cutoff → TypeError.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone


def test_rawpost_default_published_at_is_tz_aware():
    from hedwig.models import Platform, RawPost
    post = RawPost(platform=Platform.HACKERNEWS, external_id="x", title="t", url="")
    assert post.published_at.tzinfo is not None


def test_topic_persistence_tolerates_naive_history():
    """Even if some caller passes naive datetimes, the function must not crash."""
    from hedwig.engine.absorbed.last30days import topic_persistence_score
    from hedwig.models import Platform, RawPost

    now_aware = datetime.now(tz=timezone.utc)
    post = RawPost(
        platform=Platform.HACKERNEWS, external_id="p", title="agents",
        url="", content="", published_at=now_aware,
    )
    # Build a historical post with naive datetime (legacy path)
    naive_post = RawPost.model_construct(
        platform=Platform.HACKERNEWS, external_id="h", title="agents",
        url="", content="",
        published_at=datetime.utcnow() - timedelta(days=3),  # naive!
    )
    score = topic_persistence_score(post, [naive_post])
    assert 0.0 <= score <= 1.0


def test_rows_to_posts_parses_iso_timestamps():
    from hedwig.main import _rows_to_posts
    rows = [{
        "platform": "hackernews",
        "external_id": "a",
        "title": "x",
        "published_at": "2026-04-20T12:00:00+00:00",
    }]
    posts = _rows_to_posts(rows)
    assert len(posts) == 1
    assert posts[0].published_at.tzinfo is not None
    assert posts[0].published_at.year == 2026


def test_rows_to_posts_handles_missing_timestamp():
    from hedwig.main import _rows_to_posts
    rows = [{"platform": "hackernews", "external_id": "a", "title": "x"}]
    posts = _rows_to_posts(rows)
    assert len(posts) == 1
    # Default still tz-aware
    assert posts[0].published_at.tzinfo is not None


def test_normalize_and_prescore_does_not_raise_tz_error(monkeypatch, tmp_path):
    """End-to-end: even with historical rows in the DB, the enrichment pass
    completes without the offset-naive TypeError from the original stack."""
    import asyncio
    monkeypatch.setenv("HEDWIG_STORAGE", "sqlite")
    monkeypatch.setenv("HEDWIG_DB_PATH", str(tmp_path / "hedwig.db"))

    from hedwig.main import normalize_and_prescore
    from hedwig.models import Platform, RawPost
    # Bypass the real jina call to keep the test hermetic
    async def _noop(posts, max_concurrent=3):
        return posts
    monkeypatch.setattr("hedwig.engine.normalizer.normalize_batch", _noop)

    # Seed a historical row via storage layer
    from hedwig.dashboard.demo_seed import seed_demo
    seed_demo(reset=True)

    # Fresh post set
    now = datetime.now(tz=timezone.utc)
    posts = [
        RawPost(platform=Platform.HACKERNEWS, external_id=f"live-{i}",
                title=f"AI agents benchmark {i}", url="", content="body",
                score=50, comments_count=5, published_at=now)
        for i in range(5)
    ]
    result = asyncio.run(normalize_and_prescore(posts, ["agents"]))
    # Just needs to return a list without the TypeError
    assert isinstance(result, list)
