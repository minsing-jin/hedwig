"""/brief page + briefings CRUD."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def tmp_env(monkeypatch, tmp_path):
    monkeypatch.setenv("HEDWIG_STORAGE", "sqlite")
    monkeypatch.setenv("HEDWIG_DB_PATH", str(tmp_path / "hedwig.db"))
    yield tmp_path


def test_save_and_list_briefings(tmp_env):
    from hedwig.storage import get_briefings, save_briefing
    assert save_briefing("daily", "# Daily\nAlert: foo", signal_count=3)
    assert save_briefing("weekly", "# Weekly\nTrend X", signal_count=12)
    rows = get_briefings()
    assert len(rows) == 2
    # newest first
    assert rows[0]["cycle_type"] == "weekly"


def test_get_briefings_by_cycle(tmp_env):
    from hedwig.storage import get_briefings, save_briefing
    save_briefing("daily", "A")
    save_briefing("daily", "B")
    save_briefing("weekly", "C")
    assert len(get_briefings(cycle_type="daily")) == 2
    assert len(get_briefings(cycle_type="weekly")) == 1


def test_save_briefing_rejects_invalid_cycle(tmp_env):
    from hedwig.storage import save_briefing
    assert save_briefing("nonsense", "x") is None


def test_brief_page_empty_state(tmp_env):
    from hedwig.dashboard.app import create_app
    client = TestClient(create_app())
    resp = client.get("/brief")
    assert resp.status_code == 200
    assert "Briefings" in resp.text
    assert "아직 브리핑이 없습니다" in resp.text


def test_brief_page_renders_saved_brief(tmp_env):
    from hedwig.dashboard.app import create_app
    from hedwig.storage import save_briefing
    save_briefing(
        "daily",
        "### 🔴 즉시 주목\n- Big thing happened\n\n### 💡 오늘의 인사이트\nSomething",
        signal_count=5,
    )
    client = TestClient(create_app())
    resp = client.get("/brief")
    assert resp.status_code == 200
    assert "daily" in resp.text
    assert "Big thing happened" in resp.text
    assert "5 signals" in resp.text


def test_brief_page_cycle_filter(tmp_env):
    from hedwig.dashboard.app import create_app
    from hedwig.storage import save_briefing
    save_briefing("daily", "DAILY_CONTENT_MARKER")
    save_briefing("weekly", "WEEKLY_CONTENT_MARKER")
    client = TestClient(create_app())
    resp = client.get("/brief?cycle=daily")
    assert "DAILY_CONTENT_MARKER" in resp.text
    assert "WEEKLY_CONTENT_MARKER" not in resp.text


def test_nav_has_brief_link(tmp_env):
    from hedwig.dashboard.app import create_app
    client = TestClient(create_app())
    resp = client.get("/")
    assert 'href="/brief"' in resp.text
