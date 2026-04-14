"""
AC-2: /signals/search returns matching signals from title/content search.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


SAFE_EXPORT_FIELDS = (
    "id",
    "platform",
    "title",
    "url",
    "content",
    "author",
    "relevance_score",
    "urgency",
    "published_at",
    "collected_at",
)


def _raw_signal_row(
    *,
    signal_id: str,
    title: str,
    content: str,
) -> dict:
    return {
        "id": signal_id,
        "platform": "github",
        "title": title,
        "url": f"https://example.com/{signal_id}",
        "content": content,
        "author": "hedwig",
        "relevance_score": 0.91,
        "urgency": "digest",
        "published_at": "2026-04-14T06:00:00+00:00",
        "collected_at": "2026-04-14T06:05:00+00:00",
        "why_relevant": "Internal reasoning",
        "devils_advocate": "Internal objection",
        "opportunity_note": "Internal note",
        "exploration_tags": ["secret"],
        "extra": {"debug": True},
    }


@pytest.fixture
def saas_app():
    from hedwig.dashboard.app import create_app

    return create_app(saas_mode=True)


@pytest.fixture
def single_user_app():
    from hedwig.dashboard.app import create_app

    return create_app(saas_mode=False)


@pytest.mark.asyncio
async def test_signals_search_returns_safe_json_matches(monkeypatch, single_user_app):
    """GET /signals/search returns matched rows using the safe public schema."""
    from hedwig.dashboard import app as dashboard_app
    from httpx import ASGITransport, AsyncClient

    calls: dict[str, object] = {}
    raw_matches = [
        _raw_signal_row(
            signal_id="sig-title",
            title="AI agents keep shipping",
            content="Weekly roundup",
        ),
        _raw_signal_row(
            signal_id="sig-content",
            title="Shipping notes",
            content="This content mentions AI agents directly",
        ),
    ]

    def fake_search_signals(query: str, limit: int = 100) -> list[dict]:
        calls["query"] = query
        calls["limit"] = limit
        return raw_matches

    monkeypatch.setattr(dashboard_app, "_search_signals", fake_search_signals)

    transport = ASGITransport(app=single_user_app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        resp = await client.get("/signals/search", params={"q": "  AI agents  "})

    results = resp.json()
    assert resp.status_code == 200
    assert calls == {"query": "AI agents", "limit": 100}
    assert results == [
        {field: raw_signal[field] for field in SAFE_EXPORT_FIELDS}
        for raw_signal in raw_matches
    ]
    for result in results:
        assert set(result) == set(SAFE_EXPORT_FIELDS)
        for private_field in (
            "why_relevant",
            "devils_advocate",
            "opportunity_note",
            "exploration_tags",
            "extra",
        ):
            assert private_field not in result


@pytest.mark.asyncio
async def test_signals_search_requires_auth_in_saas_mode(saas_app):
    """GET /signals/search must reject anonymous SaaS requests."""
    from httpx import ASGITransport, AsyncClient

    transport = ASGITransport(app=saas_app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        resp = await client.get("/signals/search", params={"q": "ai"})

    assert resp.status_code == 401
    assert resp.json() == {"detail": "Authentication required"}


def test_search_signals_queries_title_and_content_fields(monkeypatch):
    """Supabase search must query both fields, dedupe overlaps, and keep newest first."""
    from hedwig.storage import supabase as supabase_mod

    title_match = _raw_signal_row(
        signal_id="sig-title",
        title="AI agents keep shipping",
        content="Title-only match",
    )
    title_match["collected_at"] = "2026-04-14T06:03:00+00:00"

    overlap_match = _raw_signal_row(
        signal_id="sig-overlap",
        title="AI agents and workflows",
        content="This content also mentions AI agents",
    )
    overlap_match["collected_at"] = "2026-04-14T06:08:00+00:00"

    content_match = _raw_signal_row(
        signal_id="sig-content",
        title="Shipping notes",
        content="This content mentions AI agents directly",
    )
    content_match["collected_at"] = "2026-04-14T06:05:00+00:00"

    table_calls: list[str] = []
    query_calls: list[dict[str, object]] = []

    class FakeQuery:
        def __init__(self, rows: list[dict]):
            self._rows = rows
            self._call: dict[str, object] = {}
            query_calls.append(self._call)

        def select(self, fields: str):
            self._call["select"] = fields
            return self

        def ilike(self, field: str, pattern: str):
            self._call["ilike"] = (field, pattern)
            return self

        def order(self, field: str, desc: bool = False):
            self._call["order"] = (field, desc)
            return self

        def limit(self, value: int):
            self._call["limit"] = value
            return self

        def execute(self):
            class Result:
                data = self._rows

            return Result()

    class FakeClient:
        def __init__(self):
            self._results = [
                [title_match, overlap_match],
                [overlap_match, content_match],
            ]
            self._next_result = 0

        def table(self, table_name: str):
            table_calls.append(table_name)
            rows = self._results[self._next_result]
            self._next_result += 1
            return FakeQuery(rows)

    monkeypatch.setattr(supabase_mod, "_get_client", lambda: FakeClient())

    result = supabase_mod.search_signals("  AI agents  ", limit=100)

    assert result == [overlap_match, content_match, title_match]
    assert table_calls == ["signals", "signals"]
    assert query_calls == [
        {
            "select": ",".join(SAFE_EXPORT_FIELDS),
            "ilike": ("title", "%AI agents%"),
            "order": ("collected_at", True),
            "limit": 100,
        },
        {
            "select": ",".join(SAFE_EXPORT_FIELDS),
            "ilike": ("content", "%AI agents%"),
            "order": ("collected_at", True),
            "limit": 100,
        },
    ]


def test_search_signals_treats_reserved_characters_and_wildcards_as_literal_text(monkeypatch):
    """Supabase search must escape wildcard characters while preserving literal punctuation."""
    from hedwig.storage import supabase as supabase_mod

    query_calls: list[dict[str, object]] = []

    class FakeQuery:
        def __init__(self):
            self._call: dict[str, object] = {}
            query_calls.append(self._call)

        def select(self, fields: str):
            self._call["select"] = fields
            return self

        def ilike(self, field: str, pattern: str):
            self._call["ilike"] = (field, pattern)
            return self

        def order(self, field: str, desc: bool = False):
            self._call["order"] = (field, desc)
            return self

        def limit(self, value: int):
            self._call["limit"] = value
            return self

        def execute(self):
            class Result:
                data = []

            return Result()

    class FakeClient:
        def table(self, table_name: str):
            assert table_name == "signals"
            return FakeQuery()

    monkeypatch.setattr(supabase_mod, "_get_client", lambda: FakeClient())

    result = supabase_mod.search_signals("  roadmap, (AI) 100%_ready\\beta  ", limit=25)

    assert result == []
    assert query_calls == [
        {
            "select": ",".join(SAFE_EXPORT_FIELDS),
            "ilike": ("title", r"%roadmap, (AI) 100\%\_ready\\beta%"),
            "order": ("collected_at", True),
            "limit": 25,
        },
        {
            "select": ",".join(SAFE_EXPORT_FIELDS),
            "ilike": ("content", r"%roadmap, (AI) 100\%\_ready\\beta%"),
            "order": ("collected_at", True),
            "limit": 25,
        },
    ]
