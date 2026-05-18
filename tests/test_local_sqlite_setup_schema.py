from __future__ import annotations

import sqlite3

from fastapi.testclient import TestClient


class _FakeProcess:
    pid = 3232


def test_ensure_local_sqlite_schema_creates_first_run_app_state_tables(
    tmp_path,
    monkeypatch,
):
    db_path = tmp_path / "state" / "hedwig.db"
    monkeypatch.setenv("HEDWIG_DB_PATH", str(db_path))

    from hedwig.dashboard.db_setup import (
        LOCAL_SQLITE_REQUIRED_SCHEMA,
        ensure_local_sqlite_schema,
    )

    assert not db_path.exists()

    state = ensure_local_sqlite_schema()

    assert state["db_path"] == str(db_path)
    assert state["db_exists"] is True
    assert state["schema_ready"] is True
    assert state["missing_tables"] == []
    assert state["missing_columns"] == {}
    assert set(state["required_tables"]) == set(LOCAL_SQLITE_REQUIRED_SCHEMA)

    with sqlite3.connect(db_path) as conn:
        for table_name, required_columns in LOCAL_SQLITE_REQUIRED_SCHEMA.items():
            columns = {
                row[1]
                for row in conn.execute(f"PRAGMA table_info({table_name})").fetchall()
            }
            assert required_columns <= columns


def test_one_shot_setup_bootstraps_local_sqlite_schema_before_first_run(
    tmp_path,
    monkeypatch,
):
    monkeypatch.chdir(tmp_path)
    db_path = tmp_path / "hedwig.db"
    criteria_path = tmp_path / "criteria.yaml"
    user_memory_path = tmp_path / "user_memory.jsonl"
    source_settings_path = tmp_path / "source_settings.json"
    monkeypatch.setenv("HEDWIG_DB_PATH", str(db_path))

    from hedwig import config as hedwig_config
    from hedwig.dashboard import app as dashboard_app
    from hedwig.dashboard.db_setup import LOCAL_SQLITE_REQUIRED_SCHEMA
    from hedwig.sources import settings as source_settings

    launched = {}

    def fake_popen(args, cwd, env):
        launched["db_exists_before_run"] = db_path.exists()
        with sqlite3.connect(db_path) as conn:
            launched["tables_before_run"] = {
                row[0]
                for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table'"
                ).fetchall()
            }
        return _FakeProcess()

    monkeypatch.setattr(hedwig_config, "CRITERIA_PATH", criteria_path)
    monkeypatch.setattr(hedwig_config, "USER_MEMORY_PATH", user_memory_path)
    monkeypatch.setattr(source_settings, "SOURCE_SETTINGS_PATH", source_settings_path)
    monkeypatch.setattr(dashboard_app.subprocess, "Popen", fake_popen)

    assert not db_path.exists()

    resp = TestClient(dashboard_app.create_app()).post(
        "/setup/one-shot",
        data={"OPENAI_API_KEY": "sk-local-schema"},
    )

    assert resp.status_code == 200
    payload = resp.json()
    assert payload["ok"] is True
    assert payload["local_schema_state"]["schema_ready"] is True
    assert payload["local_schema_state"]["missing_tables"] == []
    assert payload["local_schema_state"]["missing_columns"] == {}
    assert launched["db_exists_before_run"] is True
    assert set(LOCAL_SQLITE_REQUIRED_SCHEMA) <= launched["tables_before_run"]

    with sqlite3.connect(db_path) as conn:
        assert (
            conn.execute("SELECT COUNT(*) FROM criteria_versions").fetchone()[0] == 1
        )
        assert conn.execute("SELECT COUNT(*) FROM user_memory").fetchone()[0] == 1
