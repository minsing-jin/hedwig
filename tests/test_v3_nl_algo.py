"""NL editor for algorithm.yaml."""
from __future__ import annotations

import pytest
import yaml
from fastapi.testclient import TestClient


@pytest.fixture
def tmp_env(monkeypatch, tmp_path):
    monkeypatch.setenv("HEDWIG_STORAGE", "sqlite")
    monkeypatch.setenv("HEDWIG_DB_PATH", str(tmp_path / "hedwig.db"))
    # Redirect ALGORITHM_PATH so the test doesn't clobber the repo yaml
    tmp_algo = tmp_path / "algorithm.yaml"
    tmp_algo.write_text(yaml.safe_dump({
        "version": 1,
        "retrieval": {"top_n": 200, "threshold": 0.10},
        "ranking": {
            "top_k": 30,
            "components": {
                "llm_judge": {"enabled": True, "weight": 0.4},
                "bandit": {"enabled": False, "weight": 0.1, "exploration_rate": 0.1},
            },
        },
        "fitness": {"adoption_threshold": 0.05},
        "meta_evolution": {"enabled": False},
    }))
    monkeypatch.setattr("hedwig.config.ALGORITHM_PATH", tmp_algo)
    monkeypatch.setattr("hedwig.onboarding.nl_algo_editor.ALGORITHM_PATH", tmp_algo)
    monkeypatch.setattr("hedwig.evolution.meta.ALGORITHM_PATH", tmp_algo)
    import hedwig.config as _cfg
    _cfg._ALGORITHM_VERSION_SEEDED = False
    yield tmp_path


def test_apply_changes_set_weight(tmp_env):
    from hedwig.onboarding.nl_algo_editor import apply_changes
    before = {"ranking": {"components": {"bandit": {"enabled": False, "weight": 0.1}}}}
    after = apply_changes(before, [
        {"op": "set", "path": "ranking.components.bandit.weight", "value": 0.25},
        {"op": "set", "path": "ranking.components.bandit.enabled", "value": True},
    ])
    assert after["ranking"]["components"]["bandit"]["weight"] == 0.25
    assert after["ranking"]["components"]["bandit"]["enabled"] is True


def test_apply_changes_creates_missing_paths():
    from hedwig.onboarding.nl_algo_editor import apply_changes
    after = apply_changes({}, [{"op": "set", "path": "ranking.top_k", "value": 50}])
    assert after == {"ranking": {"top_k": 50}}


def test_confirm_edit_writes_yaml_and_versions(tmp_env):
    from hedwig.onboarding.nl_algo_editor import confirm_edit
    from hedwig.storage import get_algorithm_history, get_evolution_signals

    r = confirm_edit(
        [{"op": "set", "path": "ranking.components.bandit.weight", "value": 0.3},
         {"op": "set", "path": "ranking.components.bandit.enabled", "value": True}],
        intent="bandit 비중 0.3으로 올려",
    )
    assert r["ok"]
    assert r["version"] == 2

    tmp_algo = tmp_env / "algorithm.yaml"
    reloaded = yaml.safe_load(tmp_algo.read_text())
    assert reloaded["ranking"]["components"]["bandit"]["weight"] == 0.3
    assert reloaded["ranking"]["components"]["bandit"]["enabled"] is True
    assert reloaded["version"] == 2
    assert reloaded["origin"] == "user_nl_editor"

    history = get_algorithm_history()
    assert any(a["version"] == 2 and a["created_by"] == "user_nl_editor" for a in history)

    events = get_evolution_signals(channel="explicit")
    assert any(e["kind"] == "algorithm_edit" for e in events)


def test_endpoint_propose_requires_intent(tmp_env):
    from hedwig.dashboard.app import create_app
    client = TestClient(create_app())
    resp = client.post("/algorithm/propose", json={"intent": ""})
    assert resp.status_code == 400


def test_endpoint_apply_versioning(tmp_env):
    from hedwig.dashboard.app import create_app
    from hedwig.storage import get_algorithm_history
    client = TestClient(create_app())

    resp = client.post("/algorithm/apply", json={
        "changes": [{"op": "set", "path": "ranking.top_k", "value": 25}],
        "intent": "smaller top_k",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"]
    assert data["version"] == 2

    history = get_algorithm_history()
    assert any(a["version"] == 2 for a in history)


def test_meta_page_shows_algorithm_editor(tmp_env):
    from hedwig.dashboard.app import create_app
    client = TestClient(create_app())
    resp = client.get("/meta")
    assert resp.status_code == 200
    assert "algorithm.yaml" in resp.text
    assert "algoPropose" in resp.text
