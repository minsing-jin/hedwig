"""
AC-4: /dashboard/stats returns aggregated dashboard metrics.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


@pytest.fixture
def saas_app():
    from hedwig.dashboard.app import create_app

    return create_app(saas_mode=True)


@pytest.fixture
def single_user_app():
    from hedwig.dashboard.app import create_app

    return create_app(saas_mode=False)


@pytest.mark.asyncio
async def test_dashboard_stats_returns_json_snapshot(monkeypatch, single_user_app):
    """GET /dashboard/stats returns the five requested stats fields."""
    from hedwig.dashboard import app as dashboard_app
    from httpx import ASGITransport, AsyncClient

    expected = {
        "total_signals": 42,
        "upvote_ratio": 0.75,
        "evolution_cycles": 3,
        "top_5_sources": [
            {"source": "github", "count": 12},
            {"source": "arxiv", "count": 9},
            {"source": "youtube", "count": 8},
            {"source": "reddit", "count": 6},
            {"source": "hackernews", "count": 4},
        ],
        "days_active": 9,
    }

    monkeypatch.setattr(dashboard_app, "_load_dashboard_stats", lambda: expected)

    transport = ASGITransport(app=single_user_app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        resp = await client.get("/dashboard/stats")

    assert resp.status_code == 200
    assert resp.json() == expected


@pytest.mark.asyncio
async def test_dashboard_stats_response_contains_expected_json_keys(
    monkeypatch, single_user_app
):
    """GET /dashboard/stats returns the stable dashboard stats response shape."""
    from hedwig.dashboard import app as dashboard_app
    from httpx import ASGITransport, AsyncClient

    monkeypatch.setattr(
        dashboard_app,
        "_load_dashboard_stats",
        lambda: {
            "total_signals": 1,
            "upvote_ratio": 1.0,
            "evolution_cycles": 0,
            "top_5_sources": [],
            "days_active": 1,
        },
    )

    transport = ASGITransport(app=single_user_app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        resp = await client.get("/dashboard/stats")

    assert resp.status_code == 200
    assert set(resp.json()) == {
        "total_signals",
        "upvote_ratio",
        "evolution_cycles",
        "top_5_sources",
        "days_active",
    }


@pytest.mark.asyncio
async def test_dashboard_stats_requires_auth_in_saas_mode(saas_app):
    """GET /dashboard/stats must reject anonymous SaaS requests."""
    from httpx import ASGITransport, AsyncClient

    transport = ASGITransport(app=saas_app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        resp = await client.get("/dashboard/stats")

    assert resp.status_code == 401
    assert resp.json() == {"detail": "Authentication required"}


@pytest.mark.asyncio
async def test_dashboard_stats_scopes_to_authenticated_saas_user(monkeypatch, saas_app):
    """Authenticated SaaS users receive tenant-scoped stats."""
    from hedwig.dashboard import app as dashboard_app
    from hedwig.saas import auth as auth_mod
    from httpx import ASGITransport, AsyncClient

    seen: dict[str, str | None] = {"user_id": None}

    async def fake_require_auth(request):
        return {"id": "user-123", "email": "user@example.com"}

    def fake_load_dashboard_stats(user_id: str | None = None):
        seen["user_id"] = user_id
        return {
            "total_signals": 6,
            "upvote_ratio": 2 / 3,
            "evolution_cycles": 4,
            "top_5_sources": [{"source": "github", "count": 6}],
            "days_active": 3,
        }

    monkeypatch.setattr(auth_mod, "require_auth", fake_require_auth)
    monkeypatch.setattr(dashboard_app, "_load_dashboard_stats", fake_load_dashboard_stats)

    transport = ASGITransport(app=saas_app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        resp = await client.get("/dashboard/stats")

    assert resp.status_code == 200
    assert seen["user_id"] == "user-123"
    assert resp.json() == {
        "total_signals": 6,
        "upvote_ratio": 2 / 3,
        "evolution_cycles": 4,
        "top_5_sources": [{"source": "github", "count": 6}],
        "days_active": 3,
    }


@pytest.mark.asyncio
async def test_dashboard_stats_rejects_authenticated_payloads_without_user_id(
    monkeypatch, saas_app
):
    """Malformed auth payloads must fail closed instead of leaking global stats."""
    from hedwig.dashboard import app as dashboard_app
    from hedwig.saas import auth as auth_mod
    from httpx import ASGITransport, AsyncClient

    async def fake_require_auth(request):
        return {"email": "user@example.com"}

    def fail_if_called(*args, **kwargs):
        raise AssertionError("stats loader should not run without a valid user id")

    monkeypatch.setattr(auth_mod, "require_auth", fake_require_auth)
    monkeypatch.setattr(dashboard_app, "_load_dashboard_stats", fail_if_called)

    transport = ASGITransport(app=saas_app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        resp = await client.get("/dashboard/stats")

    assert resp.status_code == 401
    assert resp.json() == {"detail": "Authenticated user missing id"}


def test_get_dashboard_activity_stats_aggregates_signal_and_feedback_rows(monkeypatch):
    """Storage stats helper aggregates counts, top sources, and active days."""
    from hedwig.storage import supabase as supabase_mod

    calls: list[tuple[str, str]] = []
    signal_rows = [
        {"platform": "github", "collected_at": "2026-04-10T06:00:00+00:00"},
        {"platform": "github", "collected_at": "2026-04-10T07:00:00+00:00"},
        {"platform": "github", "collected_at": "2026-04-11T06:00:00+00:00"},
        {"platform": "arxiv", "collected_at": "2026-04-11T08:00:00+00:00"},
        {"platform": "youtube", "collected_at": "2026-04-11T09:00:00+00:00"},
        {"platform": "youtube", "collected_at": "2026-04-12T06:00:00+00:00"},
        {"platform": "reddit", "collected_at": "2026-04-12T07:00:00+00:00"},
        {"platform": "newsletter", "collected_at": "2026-04-12T08:00:00+00:00"},
        {"platform": "bluesky", "collected_at": "2026-04-12T09:00:00+00:00"},
        {"platform": "threads", "collected_at": "2026-04-12T10:00:00+00:00"},
    ]
    feedback_rows = [
        {"vote": "up"},
        {"vote": "up"},
        {"vote": "up"},
        {"vote": "down"},
    ]

    class FakeQuery:
        def __init__(self, table_name: str, rows: list[dict]):
            self._table_name = table_name
            self._rows = rows

        def select(self, fields: str):
            calls.append((self._table_name, fields))
            return self

        def execute(self):
            class Result:
                data = self._rows

            return Result()

    class FakeClient:
        def table(self, table_name: str):
            if table_name == "signals":
                return FakeQuery(table_name, signal_rows)
            if table_name == "feedback":
                return FakeQuery(table_name, feedback_rows)
            raise AssertionError(f"Unexpected table: {table_name}")

    monkeypatch.setattr(supabase_mod, "_get_client", lambda: FakeClient())

    result = supabase_mod.get_dashboard_activity_stats()

    assert result == {
        "total_signals": 10,
        "upvote_ratio": 0.75,
        "top_5_sources": [
            {"source": "github", "count": 3},
            {"source": "youtube", "count": 2},
            {"source": "arxiv", "count": 1},
            {"source": "bluesky", "count": 1},
            {"source": "newsletter", "count": 1},
        ],
        "days_active": 3,
    }
    assert calls == [
        ("signals", "platform,collected_at"),
        ("feedback", "vote"),
    ]


def test_get_dashboard_activity_stats_filters_by_user_id_when_provided(monkeypatch):
    """Storage stats helper scopes both signals and feedback queries in SaaS mode."""
    from hedwig.storage import supabase as supabase_mod

    calls: list[tuple[str, str, str]] = []

    class FakeQuery:
        def __init__(self, table_name: str, rows: list[dict]):
            self._table_name = table_name
            self._rows = rows

        def select(self, fields: str):
            calls.append((self._table_name, "select", fields))
            return self

        def eq(self, field: str, value: str):
            calls.append((self._table_name, field, value))
            return self

        def execute(self):
            class Result:
                data = self._rows

            return Result()

    class FakeClient:
        def table(self, table_name: str):
            if table_name == "signals":
                return FakeQuery(
                    table_name,
                    [{"platform": "github", "collected_at": "2026-04-10T06:00:00+00:00"}],
                )
            if table_name == "feedback":
                return FakeQuery(table_name, [{"vote": "up"}])
            raise AssertionError(f"Unexpected table: {table_name}")

    monkeypatch.setattr(supabase_mod, "_get_client", lambda: FakeClient())

    result = supabase_mod.get_dashboard_activity_stats(user_id="user-123")

    assert result == {
        "total_signals": 1,
        "upvote_ratio": 1.0,
        "top_5_sources": [{"source": "github", "count": 1}],
        "days_active": 1,
    }
    assert calls == [
        ("signals", "select", "platform,collected_at"),
        ("signals", "user_id", "user-123"),
        ("feedback", "select", "vote"),
        ("feedback", "user_id", "user-123"),
    ]


def test_dashboard_activity_stats_round_trip_uses_tenant_owned_rows(monkeypatch):
    """Signals with the same external id must remain isolated per tenant."""
    from datetime import datetime, timezone

    from hedwig.models import Feedback, Platform, RawPost, ScoredSignal, UrgencyLevel, VoteType
    from hedwig.storage import supabase as supabase_mod

    state = {"signals": [], "feedback": []}

    class Result:
        def __init__(self, data):
            self.data = data

    class FakeTable:
        def __init__(self, table_name: str):
            self._table_name = table_name
            self._select_fields: str | None = None
            self._eq_filters: list[tuple[str, object]] = []
            self._in_filters: list[tuple[str, set[object]]] = []
            self._insert_rows: list[dict] | None = None
            self._upsert_rows: list[dict] | None = None
            self._on_conflict = ""

        def select(self, fields: str):
            self._select_fields = fields
            return self

        def eq(self, field: str, value: object):
            self._eq_filters.append((field, value))
            return self

        def in_(self, field: str, values):
            self._in_filters.append((field, set(values)))
            return self

        def insert(self, rows):
            if isinstance(rows, dict):
                self._insert_rows = [rows]
            else:
                self._insert_rows = list(rows)
            return self

        def upsert(self, rows, on_conflict: str):
            self._upsert_rows = list(rows)
            self._on_conflict = on_conflict
            return self

        def execute(self):
            if self._upsert_rows is not None:
                keys = tuple(part.strip() for part in self._on_conflict.split(",") if part.strip())
                for row in self._upsert_rows:
                    replaced = False
                    for idx, existing in enumerate(state[self._table_name]):
                        if all(existing.get(key) == row.get(key) for key in keys):
                            state[self._table_name][idx] = dict(row)
                            replaced = True
                            break
                    if not replaced:
                        state[self._table_name].append(dict(row))
                return Result([dict(row) for row in self._upsert_rows])

            if self._insert_rows is not None:
                for row in self._insert_rows:
                    state[self._table_name].append(dict(row))
                return Result([dict(row) for row in self._insert_rows])

            rows = [dict(row) for row in state[self._table_name]]
            for field, value in self._eq_filters:
                rows = [row for row in rows if row.get(field) == value]
            for field, values in self._in_filters:
                rows = [row for row in rows if row.get(field) in values]

            if self._select_fields and self._select_fields != "*":
                columns = [field.strip() for field in self._select_fields.split(",")]
                rows = [{field: row.get(field) for field in columns} for row in rows]
            return Result(rows)

    class FakeClient:
        def table(self, table_name: str):
            return FakeTable(table_name)

    monkeypatch.setattr(supabase_mod, "_get_client", lambda: FakeClient())

    def build_signal(title: str) -> ScoredSignal:
        return ScoredSignal(
            raw=RawPost(
                platform=Platform.REDDIT,
                external_id="shared-id",
                title=title,
                url="https://example.com/shared-id",
                content="tenant-owned signal",
                author="hedwig",
                published_at=datetime(2026, 4, 14, 6, 0, tzinfo=timezone.utc),
            ),
            relevance_score=0.9,
            urgency=UrgencyLevel.DIGEST,
            why_relevant="Round-trip tenant stats coverage.",
        )

    assert supabase_mod.save_signals([build_signal("User 123")], user_id="user-123") == 1
    assert supabase_mod.save_signals([build_signal("User 999")], user_id="user-999") == 1

    assert supabase_mod.save_feedback(
        Feedback(signal_id="shared-id", vote=VoteType.UP),
        user_id="user-123",
    )
    assert supabase_mod.save_feedback(
        Feedback(signal_id="shared-id", vote=VoteType.DOWN),
        user_id="user-999",
    )

    assert len(state["signals"]) == 2
    assert {row["user_id"] for row in state["signals"]} == {"user-123", "user-999"}
    assert {row["title"] for row in state["signals"]} == {"User 123", "User 999"}
    assert state["feedback"][0]["user_id"] == "user-123"

    assert supabase_mod.get_dashboard_activity_stats(user_id="user-123") == {
        "total_signals": 1,
        "upvote_ratio": 1.0,
        "top_5_sources": [{"source": "reddit", "count": 1}],
        "days_active": 1,
    }
    assert supabase_mod.get_dashboard_activity_stats(user_id="user-999") == {
        "total_signals": 1,
        "upvote_ratio": 0.0,
        "top_5_sources": [{"source": "reddit", "count": 1}],
        "days_active": 1,
    }


def test_load_dashboard_stats_adds_evolution_cycles_from_valid_log_rows(
    monkeypatch, tmp_path
):
    """App-level stats helper merges storage metrics with valid evolution log entries."""
    from hedwig import config as config_mod
    from hedwig.dashboard import app as dashboard_app

    evolution_log_path = tmp_path / "evolution_log.jsonl"
    evolution_log_path.write_text(
        '{"cycle_number": 0}\n'
        '\n'
        'not-json\n'
        '{"cycle_number": 1}\n',
        encoding="utf-8",
    )

    monkeypatch.setattr(
        dashboard_app,
        "_load_dashboard_activity_stats",
        lambda: {
            "total_signals": 7,
            "upvote_ratio": 0.5,
            "top_5_sources": [{"source": "github", "count": 7}],
            "days_active": 2,
        },
    )
    monkeypatch.setattr(config_mod, "EVOLUTION_LOG_PATH", evolution_log_path)

    assert dashboard_app._load_dashboard_stats() == {
        "total_signals": 7,
        "upvote_ratio": 0.5,
        "evolution_cycles": 2,
        "top_5_sources": [{"source": "github", "count": 7}],
        "days_active": 2,
    }
