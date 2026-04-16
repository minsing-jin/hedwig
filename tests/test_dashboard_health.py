"""
AC-8: /health returns runtime and evolution metadata.
"""
from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


@pytest.fixture
def saas_app():
    from hedwig.dashboard.app import create_app

    return create_app(saas_mode=True)


@pytest.mark.asyncio
async def test_health_returns_public_json_snapshot(monkeypatch, saas_app):
    """GET /health is public and returns the requested JSON shape."""
    from hedwig.dashboard import app as dashboard_app
    from httpx import ASGITransport, AsyncClient

    expected = {
        "consecutive_daily_runs": 3,
        "total_daily_cycles": 5,
        "total_weekly_cycles": 2,
        "last_daily_at": "2026-04-13T09:15:00+00:00",
        "last_weekly_at": "2026-04-12T07:30:00+00:00",
        "last_daily_run": "2026-04-13T09:15:00+00:00",
        "last_weekly_run": "2026-04-12T07:30:00+00:00",
        "evolution_cycle_count": 7,
        "source_count": 17,
        "uptime_seconds": 123,
    }

    monkeypatch.setattr(
        dashboard_app,
        "_load_health_status",
        lambda started_at=None: expected,
    )

    transport = ASGITransport(app=saas_app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        resp = await client.get("/health")

    assert resp.status_code == 200
    assert resp.json() == expected


def test_load_health_status_reads_run_stats_from_storage(monkeypatch):
    """Health helper exposes run-history stats from the storage backend."""
    from hedwig.dashboard import app as dashboard_app

    monkeypatch.setattr(dashboard_app, "_count_sources", lambda: 17)
    monkeypatch.setattr(
        dashboard_app,
        "_load_run_stats",
        lambda: {
            "consecutive_daily_runs": 3,
            "total_daily_cycles": 5,
            "total_weekly_cycles": 2,
            "last_daily_at": "2026-04-13T09:15:00+00:00",
            "last_weekly_at": "2026-04-12T07:30:00+00:00",
        },
    )
    monkeypatch.setattr(
        dashboard_app,
        "_utcnow",
        lambda: datetime(2026, 4, 14, 7, 1, 2, tzinfo=timezone.utc),
    )

    result = dashboard_app._load_health_status(
        started_at=datetime(2026, 4, 14, 6, 0, 0, tzinfo=timezone.utc)
    )

    assert result == {
        "consecutive_daily_runs": 3,
        "total_daily_cycles": 5,
        "total_weekly_cycles": 2,
        "last_daily_at": "2026-04-13T09:15:00+00:00",
        "last_weekly_at": "2026-04-12T07:30:00+00:00",
        "last_daily_run": "2026-04-13T09:15:00+00:00",
        "last_weekly_run": "2026-04-12T07:30:00+00:00",
        "evolution_cycle_count": 7,
        "source_count": 17,
        "uptime_seconds": 3662,
    }
