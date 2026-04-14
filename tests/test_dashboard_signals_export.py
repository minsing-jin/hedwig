"""
AC-1: /signals/export returns a safe JSON download and is protected in SaaS mode.
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


def _raw_signal_row() -> dict:
    return {
        "id": "sig-1",
        "platform": "github",
        "title": "Newest signal",
        "url": "https://example.com/signal",
        "content": "Important update",
        "author": "hedwig",
        "relevance_score": 0.98,
        "urgency": "alert",
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
async def test_signals_export_returns_json_attachment_with_safe_schema(monkeypatch, single_user_app):
    """GET /signals/export exports only the public allowlist and requests 100 rows."""
    from hedwig.dashboard import app as dashboard_app
    from httpx import ASGITransport, AsyncClient

    calls: dict[str, int] = {}
    raw_signal = _raw_signal_row()

    def fake_load_latest_signals(limit: int = 20) -> list[dict]:
        calls["limit"] = limit
        return [raw_signal]

    monkeypatch.setattr(dashboard_app, "_load_latest_signals", fake_load_latest_signals)

    transport = ASGITransport(app=single_user_app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        resp = await client.get("/signals/export")

    exported = resp.json()
    assert resp.status_code == 200
    assert calls == {"limit": 100}
    assert "application/json" in resp.headers.get("content-type", "")
    assert resp.headers.get("content-disposition") == (
        'attachment; filename="signals-export.json"'
    )
    assert exported == [
        {field: raw_signal[field] for field in SAFE_EXPORT_FIELDS}
    ]
    assert set(exported[0]) == set(SAFE_EXPORT_FIELDS)
    for private_field in (
        "why_relevant",
        "devils_advocate",
        "opportunity_note",
        "exploration_tags",
        "extra",
    ):
        assert private_field not in exported[0]


@pytest.mark.asyncio
async def test_signals_export_requires_auth_in_saas_mode(saas_app):
    """GET /signals/export must reject anonymous SaaS requests."""
    from httpx import ASGITransport, AsyncClient

    transport = ASGITransport(app=saas_app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        resp = await client.get("/signals/export")

    assert resp.status_code == 401
    assert resp.json() == {"detail": "Authentication required"}


def test_get_latest_signals_queries_safe_export_fields(monkeypatch):
    """Supabase export query must use the safe-field allowlist, not select(*)."""
    from hedwig.storage import supabase as supabase_mod

    raw_signal = _raw_signal_row()
    calls: dict[str, object] = {}

    class FakeQuery:
        def select(self, fields: str):
            calls["select"] = fields
            return self

        def order(self, field: str, desc: bool = False):
            calls["order"] = (field, desc)
            return self

        def limit(self, value: int):
            calls["limit"] = value
            return self

        def execute(self):
            class Result:
                data = [raw_signal]

            return Result()

    class FakeClient:
        def table(self, table_name: str):
            calls["table"] = table_name
            return FakeQuery()

    monkeypatch.setattr(supabase_mod, "_get_client", lambda: FakeClient())

    result = supabase_mod.get_latest_signals(limit=100)

    assert result == [raw_signal]
    assert calls == {
        "table": "signals",
        "select": ",".join(SAFE_EXPORT_FIELDS),
        "order": ("collected_at", True),
        "limit": 100,
    }
