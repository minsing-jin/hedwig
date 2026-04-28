"""Reset endpoint + CLI + readability v2."""
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


def test_reset_signals_wipes_signals_only(tmp_env):
    from hedwig.dashboard.demo_seed import seed_demo
    from hedwig.admin import reset_data
    from hedwig.storage import (
        get_recent_signals, get_evolution_signals, get_criteria_versions,
    )
    seed_demo(reset=True)

    assert len(get_recent_signals(days=7)) > 0
    assert len(get_evolution_signals()) > 0
    assert len(get_criteria_versions()) > 0

    out = reset_data(scope="signals")
    assert out["scope"] == "signals"
    # Signals gone, evolution preserved
    assert len(get_recent_signals(days=7)) == 0
    assert len(get_evolution_signals()) > 0


def test_reset_all_wipes_everything(tmp_env):
    from hedwig.dashboard.demo_seed import seed_demo
    from hedwig.admin import reset_data
    from hedwig.storage import (
        get_recent_signals, get_evolution_signals,
        get_criteria_versions, get_algorithm_history,
    )
    seed_demo(reset=True)
    out = reset_data(scope="all")
    assert out["scope"] == "all"
    assert len(get_recent_signals(days=7)) == 0
    assert len(get_evolution_signals()) == 0
    assert len(get_criteria_versions()) == 0


def test_reset_endpoint(tmp_env):
    from hedwig.dashboard.app import create_app
    from hedwig.dashboard.demo_seed import seed_demo
    from hedwig.storage import get_recent_signals
    seed_demo(reset=True)
    client = TestClient(create_app())
    resp = client.post("/admin/reset", json={"scope": "signals"})
    assert resp.status_code == 200
    assert resp.json()["scope"] == "signals"
    assert len(get_recent_signals(days=7)) == 0


def test_admin_page_renders(tmp_env):
    from hedwig.dashboard.app import create_app
    client = TestClient(create_app())
    resp = client.get("/admin")
    assert resp.status_code == 200
    assert "초기화" in resp.text
    assert "/admin/reset" in resp.text


def test_reset_preserves_yaml_configs(tmp_env):
    """criteria.yaml / algorithm.yaml MUST not be touched by reset."""
    from hedwig.config import ALGORITHM_PATH, CRITERIA_PATH
    from hedwig.admin import reset_data

    crit_before = CRITERIA_PATH.read_text() if CRITERIA_PATH.exists() else ""
    algo_before = ALGORITHM_PATH.read_text() if ALGORITHM_PATH.exists() else ""

    reset_data(scope="all")

    crit_after = CRITERIA_PATH.read_text() if CRITERIA_PATH.exists() else ""
    algo_after = ALGORITHM_PATH.read_text() if ALGORITHM_PATH.exists() else ""
    assert crit_before == crit_after
    assert algo_before == algo_after


def test_v3_css_has_aggressive_muted_override():
    from pathlib import Path
    css = (Path(__file__).resolve().parents[1]
           / "hedwig/dashboard/static/v3.css").read_text()
    # Now we set body color globally and force .muted to mid-gray !important
    assert "body { background:" in css
    assert "color: #4b5563 !important" in css


def test_cli_recognizes_reset_flag():
    import subprocess
    from pathlib import Path
    result = subprocess.run(
        [".venv/bin/python", "-m", "hedwig", "--help"],
        capture_output=True, text=True,
        cwd=str(Path(__file__).resolve().parents[1]),
        timeout=15,
    )
    assert "--reset" in result.stdout
