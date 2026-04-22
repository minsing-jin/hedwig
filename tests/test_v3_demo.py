"""Demo page + seed data coverage."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def tmp_env(monkeypatch, tmp_path):
    monkeypatch.setenv("HEDWIG_STORAGE", "sqlite")
    monkeypatch.setenv("HEDWIG_DB_PATH", str(tmp_path / "hedwig.db"))
    import hedwig.config as _cfg
    _cfg._ALGORITHM_VERSION_SEEDED = False
    yield tmp_path


def test_demo_page_renders(tmp_env):
    from hedwig.dashboard.app import create_app
    client = TestClient(create_app())
    resp = client.get("/demo")
    assert resp.status_code == 200
    body = resp.text.lower()
    assert "concept demo" in body
    assert "5 differentiators" in body
    assert "/demo/seed" in body


def test_demo_seed_populates_store(tmp_env):
    from hedwig.dashboard.app import create_app
    from hedwig.storage import (
        get_algorithm_history,
        get_criteria_versions,
        get_evolution_signals,
        get_recent_signals,
    )

    client = TestClient(create_app())
    resp = client.post("/demo/seed")
    assert resp.status_code == 200
    result = resp.json()
    assert result["signals_seeded"] >= 10
    assert result["criteria_versions_seeded"] == 2
    assert result["algorithm_versions_seeded"] == 2

    # Signals inserted
    signals = get_recent_signals(days=7)
    assert any(s.get("external_id", "").startswith("demo-") for s in signals)

    # Triple-input events visible
    explicit = get_evolution_signals(channel="explicit")
    assert any(e["kind"] == "criteria_edit" for e in explicit)
    semi = get_evolution_signals(channel="semi")
    assert any(e["kind"] == "qa_accept" for e in semi)

    # Versioning
    crits = get_criteria_versions()
    assert any(c["created_by"] == "demo" for c in crits)
    algos = get_algorithm_history()
    assert any(a["created_by"] == "demo" for a in algos)


def test_demo_reset_removes_rows(tmp_env):
    from hedwig.dashboard.app import create_app
    from hedwig.storage import get_recent_signals

    client = TestClient(create_app())
    client.post("/demo/seed")
    assert any(s.get("external_id", "").startswith("demo-")
               for s in get_recent_signals(days=7))

    resp = client.post("/demo/reset")
    assert resp.status_code == 200
    assert resp.json()["reset"] is True

    remaining = [s for s in get_recent_signals(days=7)
                 if s.get("external_id", "").startswith("demo-")]
    assert remaining == []


def test_demo_nav_link_in_base_template(tmp_env):
    from hedwig.dashboard.app import create_app
    client = TestClient(create_app())
    resp = client.get("/")
    # nav renders the demo link on every page via base.html
    assert "href=\"/demo\"" in resp.text
