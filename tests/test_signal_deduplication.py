"""
AC-9: save_signals skips duplicate URLs across platforms before persisting.
"""
from __future__ import annotations

from datetime import datetime, timezone

from hedwig.models import Platform, RawPost, ScoredSignal, UrgencyLevel


def _build_signal(
    *,
    platform: Platform,
    external_id: str,
    url: str,
    title: str | None = None,
    content: str = "Important AI update",
    comments_count: int = 0,
    relevance_score: float = 0.91,
) -> ScoredSignal:
    raw = RawPost(
        platform=platform,
        external_id=external_id,
        title=title or f"Signal for {external_id}",
        url=url,
        content=content,
        author="hedwig",
        comments_count=comments_count,
        published_at=datetime(2026, 4, 14, 6, 0, tzinfo=timezone.utc),
    )
    return ScoredSignal(
        raw=raw,
        relevance_score=relevance_score,
        urgency=UrgencyLevel.DIGEST,
        why_relevant="Useful context for product decisions.",
    )


def test_save_signals_skips_existing_and_in_batch_duplicate_urls(monkeypatch):
    """Storage dedup should skip URLs already saved under another platform and within a batch."""
    from hedwig.storage import supabase as supabase_mod

    already_saved = "https://example.com/already-saved"
    fresh_url = "https://example.com/fresh"
    signals = [
        _build_signal(
            platform=Platform.REDDIT,
            external_id="reddit-existing",
            url=already_saved,
        ),
        _build_signal(
            platform=Platform.YOUTUBE,
            external_id="youtube-existing",
            url=already_saved,
        ),
        _build_signal(
            platform=Platform.ARXIV,
            external_id="arxiv-fresh",
            url=fresh_url,
        ),
        _build_signal(
            platform=Platform.BLUESKY,
            external_id="bluesky-fresh",
            url=fresh_url,
        ),
    ]

    calls: dict[str, object] = {}

    class LookupQuery:
        def select(self, fields: str):
            calls["select"] = fields
            return self

        def eq(self, field: str, value: object):
            calls.setdefault("eq", []).append((field, value))
            return self

        def in_(self, field: str, values):
            calls["in_"] = (field, list(values))
            return self

        def execute(self):
            class Result:
                data = [
                    {
                        "url": already_saved,
                        "platform": Platform.HACKERNEWS.value,
                        "external_id": "hn-existing",
                    }
                ]

            return Result()

    class UpsertQuery:
        def upsert(self, rows: list[dict], on_conflict: str):
            calls["upsert"] = (rows, on_conflict)
            return self

        def execute(self):
            rows, _ = calls["upsert"]

            class Result:
                data = rows

            return Result()

    class FakeClient:
        def __init__(self):
            self._table_calls = 0

        def table(self, table_name: str):
            assert table_name == "signals"
            self._table_calls += 1
            calls.setdefault("table_calls", []).append(table_name)
            if self._table_calls == 1:
                return LookupQuery()
            if self._table_calls == 2:
                return UpsertQuery()
            raise AssertionError("Unexpected extra signals table call")

    monkeypatch.setattr(supabase_mod, "_get_client", lambda: FakeClient())

    saved = supabase_mod.save_signals(signals)

    assert saved == 1
    assert calls["table_calls"] == ["signals", "signals"]
    assert calls["select"] == "url,platform,external_id"
    assert calls["eq"] == [("user_id", "")]
    assert set(calls["in_"][1]) == {already_saved, fresh_url}

    rows, on_conflict = calls["upsert"]
    assert on_conflict == "user_id,platform,external_id"
    assert len(rows) == 1
    assert rows[0]["user_id"] == ""
    assert rows[0]["platform"] == Platform.ARXIV.value
    assert rows[0]["external_id"] == "arxiv-fresh"
    assert rows[0]["url"] == fresh_url


def test_save_signals_allows_same_row_url_refresh(monkeypatch):
    """A refresh of the same signal row should still upsert the latest fields."""
    from hedwig.storage import supabase as supabase_mod

    stable_url = "https://example.com/stable"
    signal = _build_signal(
        platform=Platform.REDDIT,
        external_id="reddit-existing",
        url=stable_url,
        title="Updated title",
        content="Updated content body",
        comments_count=37,
        relevance_score=0.98,
    )

    calls: dict[str, object] = {}

    class LookupQuery:
        def select(self, fields: str):
            calls["select"] = fields
            return self

        def eq(self, field: str, value: object):
            calls.setdefault("eq", []).append((field, value))
            return self

        def in_(self, field: str, values):
            calls["in_"] = (field, list(values))
            return self

        def execute(self):
            class Result:
                data = [
                    {
                        "url": stable_url,
                        "platform": Platform.REDDIT.value,
                        "external_id": "reddit-existing",
                    }
                ]

            return Result()

    class UpsertQuery:
        def upsert(self, rows: list[dict], on_conflict: str):
            calls["upsert"] = (rows, on_conflict)
            return self

        def execute(self):
            rows, _ = calls["upsert"]

            class Result:
                data = rows

            return Result()

    class FakeClient:
        def __init__(self):
            self._table_calls = 0

        def table(self, table_name: str):
            assert table_name == "signals"
            self._table_calls += 1
            calls.setdefault("table_calls", []).append(table_name)
            if self._table_calls == 1:
                return LookupQuery()
            if self._table_calls == 2:
                return UpsertQuery()
            raise AssertionError("Unexpected extra signals table call")

    monkeypatch.setattr(supabase_mod, "_get_client", lambda: FakeClient())

    saved = supabase_mod.save_signals([signal])

    assert saved == 1
    assert calls["table_calls"] == ["signals", "signals"]
    assert calls["select"] == "url,platform,external_id"
    assert calls["eq"] == [("user_id", "")]
    assert calls["in_"] == ("url", [stable_url])

    rows, on_conflict = calls["upsert"]
    assert on_conflict == "user_id,platform,external_id"
    assert len(rows) == 1

    row = rows[0]
    assert row["user_id"] == ""
    assert row["platform"] == Platform.REDDIT.value
    assert row["external_id"] == "reddit-existing"
    assert row["title"] == "Updated title"
    assert row["content"] == "Updated content body"
    assert row["comments_count"] == 37
    assert row["relevance_score"] == 0.98
    assert row["collected_at"].endswith("+00:00")


def test_save_signals_aborts_when_url_lookup_fails(monkeypatch):
    """URL dedup preflight failures should stop writes instead of failing open."""
    from hedwig.storage import supabase as supabase_mod

    signal = _build_signal(
        platform=Platform.BLUESKY,
        external_id="bluesky-1",
        url="https://example.com/failing-lookup",
    )

    calls: dict[str, object] = {}

    class LookupQuery:
        def select(self, fields: str):
            calls["select"] = fields
            return self

        def eq(self, field: str, value: object):
            calls.setdefault("eq", []).append((field, value))
            return self

        def in_(self, field: str, values):
            calls["in_"] = (field, list(values))
            return self

        def execute(self):
            raise RuntimeError("forced lookup failure")

    class FakeClient:
        def __init__(self):
            self._table_calls = 0

        def table(self, table_name: str):
            assert table_name == "signals"
            self._table_calls += 1
            calls.setdefault("table_calls", []).append(table_name)
            if self._table_calls == 1:
                return LookupQuery()
            raise AssertionError("save_signals should not attempt upsert after lookup failure")

    monkeypatch.setattr(supabase_mod, "_get_client", lambda: FakeClient())

    saved = supabase_mod.save_signals([signal])

    assert saved == 0
    assert calls["table_calls"] == ["signals"]
    assert calls["select"] == "url,platform,external_id"
    assert calls["eq"] == [("user_id", "")]
    assert calls["in_"] == ("url", ["https://example.com/failing-lookup"])
