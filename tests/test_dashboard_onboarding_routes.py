from __future__ import annotations

import sqlite3

from fastapi.testclient import TestClient


def _fail_on_setup_dependency(*args, **kwargs):
    raise AssertionError("onboarding routes must not depend on /setup readiness")


def test_onboarding_entry_links_remain_available_outside_setup(
    tmp_path,
    monkeypatch,
):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HEDWIG_DB_PATH", str(tmp_path / "hedwig.db"))

    from hedwig.dashboard.app import create_app

    client = TestClient(create_app(saas_mode=True))
    resp = client.get("/feed")

    assert resp.status_code == 200
    assert "One-shot local onboarding" not in resp.text
    assert 'href="/onboarding"' in resp.text
    assert 'href="/onboarding/auto"' in resp.text
    assert "Onboarding" in resp.text
    assert "Auto Onboarding" in resp.text


def test_socratic_onboarding_renders_directly_without_setup_dependency(
    tmp_path,
    monkeypatch,
):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HEDWIG_DB_PATH", str(tmp_path / "hedwig.db"))

    from hedwig.dashboard.env_manager import EnvManager
    from hedwig.dashboard.app import create_app

    monkeypatch.setattr(EnvManager, "get_status", _fail_on_setup_dependency)
    monkeypatch.setattr(EnvManager, "load", _fail_on_setup_dependency)

    client = TestClient(create_app())
    resp = client.get("/onboarding", follow_redirects=False)

    assert resp.status_code == 200
    assert resp.headers.get("location") is None
    assert "Socratic Onboarding" in resp.text
    assert "One-shot local onboarding" not in resp.text


def test_socratic_onboarding_start_works_without_setup_dependency(
    tmp_path,
    monkeypatch,
):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HEDWIG_DB_PATH", str(tmp_path / "hedwig.db"))

    from hedwig import config
    from hedwig.dashboard.env_manager import EnvManager
    from hedwig.dashboard.app import create_app

    monkeypatch.setattr(config, "OPENAI_API_KEY", "")
    monkeypatch.setattr(EnvManager, "get_status", _fail_on_setup_dependency)
    monkeypatch.setattr(EnvManager, "load", _fail_on_setup_dependency)

    client = TestClient(create_app())
    resp = client.post("/onboarding/start")

    assert resp.status_code == 200
    payload = resp.json()
    assert payload["complete"] is False
    assert isinstance(payload["message"], str)
    assert payload["message"].strip()


def test_auto_onboarding_renders_directly_without_setup_dependency(
    tmp_path,
    monkeypatch,
):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HEDWIG_DB_PATH", str(tmp_path / "hedwig.db"))

    from hedwig.dashboard.env_manager import EnvManager
    from hedwig.dashboard.app import create_app

    monkeypatch.setattr(EnvManager, "get_status", _fail_on_setup_dependency)
    monkeypatch.setattr(EnvManager, "load", _fail_on_setup_dependency)

    client = TestClient(create_app(saas_mode=True))
    resp = client.get("/onboarding/auto", follow_redirects=False)

    assert resp.status_code == 200
    assert resp.headers.get("location") is None
    assert "Tell Hedwig who you are" in resp.text
    assert "One-shot local onboarding" not in resp.text


def test_completed_setup_state_does_not_replace_onboarding_routes(
    tmp_path,
    monkeypatch,
):
    monkeypatch.chdir(tmp_path)
    db_path = tmp_path / "hedwig.db"
    monkeypatch.setenv("HEDWIG_DB_PATH", str(db_path))
    (tmp_path / ".env").write_text(
        "OPENAI_API_KEY=sk-ready\nHEDWIG_STORAGE=sqlite\n",
        encoding="utf-8",
    )
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE signals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                platform TEXT NOT NULL,
                external_id TEXT NOT NULL,
                title TEXT NOT NULL
            )
            """
        )
        conn.execute(
            "INSERT INTO signals (platform, external_id, title) VALUES (?, ?, ?)",
            ("hackernews", "item-1", "First item"),
        )

    from hedwig.dashboard.app import create_app

    client = TestClient(create_app(saas_mode=True))

    setup_resp = client.get("/setup")
    assert setup_resp.status_code == 200
    assert 'data-feed-ready="true"' in setup_resp.text

    onboarding_resp = client.get("/onboarding", follow_redirects=False)
    assert onboarding_resp.status_code == 200
    assert onboarding_resp.headers.get("location") is None
    assert "Socratic Onboarding" in onboarding_resp.text
    assert "One-shot local onboarding" not in onboarding_resp.text

    auto_resp = client.get("/onboarding/auto", follow_redirects=False)
    assert auto_resp.status_code == 200
    assert auto_resp.headers.get("location") is None
    assert "Tell Hedwig who you are" in auto_resp.text
    assert "One-shot local onboarding" not in auto_resp.text
