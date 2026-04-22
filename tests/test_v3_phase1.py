"""Phase 1 tests for Triple-Input + absorption infra.

Covers:
  - evolution_signal CRUD
  - algorithm_versions CRUD
  - nl_editor apply_changes / yaml_diff / confirm_edit
  - /criteria/propose 400 on empty intent
  - /criteria/apply applies a trivial change
  - /qa/feedback persists semi event
  - MCP/Skill adapter scaffolds importable
  - last30days enrich_score invariants
"""
from __future__ import annotations

import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient


@pytest.fixture
def tmp_env(monkeypatch, tmp_path):
    monkeypatch.setenv("HEDWIG_STORAGE", "sqlite")
    db = tmp_path / "hedwig.db"
    monkeypatch.setenv("HEDWIG_DB_PATH", str(db))
    yield tmp_path


def test_evolution_signal_crud(tmp_env):
    from hedwig.storage import save_evolution_signal, get_evolution_signals

    assert save_evolution_signal("semi", "qa_accept", {"q": "test"}, weight=2.0)
    rows = get_evolution_signals()
    assert len(rows) == 1
    assert rows[0]["channel"] == "semi"
    assert rows[0]["kind"] == "qa_accept"
    assert rows[0]["payload"] == {"q": "test"}
    assert rows[0]["weight"] == 2.0


def test_evolution_signal_invalid_channel(tmp_env):
    from hedwig.storage import save_evolution_signal
    assert not save_evolution_signal("garbage", "kind", {})


def test_algorithm_versions(tmp_env):
    from hedwig.storage import save_algorithm_version, get_algorithm_history

    assert save_algorithm_version(1, {"ranking": {"top_k": 30}}, origin="manual")
    hist = get_algorithm_history()
    assert len(hist) == 1
    assert hist[0]["version"] == 1


def test_nl_editor_apply_changes_list_ops():
    from hedwig.onboarding.nl_editor import apply_changes

    base = {"signal_preferences": {"care_about": ["X"], "ignore": []}}
    changes = [
        {"op": "add", "path": "signal_preferences.care_about", "value": "Y"},
        {"op": "remove", "path": "signal_preferences.care_about", "value": "X"},
        {"op": "add", "path": "signal_preferences.ignore", "value": "Z"},
    ]
    after = apply_changes(base, changes)
    assert after["signal_preferences"]["care_about"] == ["Y"]
    assert after["signal_preferences"]["ignore"] == ["Z"]


def test_nl_editor_set_op_creates_paths():
    from hedwig.onboarding.nl_editor import apply_changes

    after = apply_changes({}, [{"op": "set", "path": "identity.role", "value": "builder"}])
    assert after == {"identity": {"role": "builder"}}


def test_nl_editor_yaml_diff_nonempty():
    from hedwig.onboarding.nl_editor import yaml_diff
    diff = yaml_diff({"a": 1}, {"a": 1, "b": 2})
    assert "b: 2" in diff or "+b" in diff or diff  # at minimum non-empty


def test_nl_editor_confirm_writes_and_logs(tmp_env, monkeypatch):
    # Point CRITERIA_PATH to a tmp file so we don't clobber the repo's yaml
    tmp_criteria = tmp_env / "criteria.yaml"
    tmp_criteria.write_text(yaml.safe_dump({"signal_preferences": {"care_about": ["old"]}}))
    monkeypatch.setattr("hedwig.onboarding.nl_editor.CRITERIA_PATH", tmp_criteria)
    monkeypatch.setattr("hedwig.config.CRITERIA_PATH", tmp_criteria)

    from hedwig.onboarding.nl_editor import confirm_edit
    from hedwig.storage import get_evolution_signals

    result = confirm_edit(
        [{"op": "add", "path": "signal_preferences.care_about", "value": "new"}],
        intent="test",
    )
    assert result["ok"]
    data = yaml.safe_load(tmp_criteria.read_text())
    assert "new" in data["signal_preferences"]["care_about"]

    # Evolution signal logged
    events = get_evolution_signals(channel="explicit")
    assert any(e["kind"] == "criteria_edit" for e in events)


def test_dashboard_qa_feedback_endpoint(tmp_env):
    from hedwig.dashboard.app import create_app
    from hedwig.storage import get_evolution_signals

    client = TestClient(create_app())
    resp = client.post("/qa/feedback", json={"kind": "qa_accept", "question": "test"})
    assert resp.status_code == 200
    assert resp.json()["ok"]

    events = get_evolution_signals(channel="semi")
    assert any(e["kind"] == "qa_accept" for e in events)


def test_dashboard_qa_feedback_invalid_kind(tmp_env):
    from hedwig.dashboard.app import create_app
    client = TestClient(create_app())
    resp = client.post("/qa/feedback", json={"kind": "not_a_kind"})
    assert resp.status_code == 400


def test_dashboard_criteria_propose_requires_intent(tmp_env):
    from hedwig.dashboard.app import create_app
    client = TestClient(create_app())
    resp = client.post("/criteria/propose", json={"intent": ""})
    assert resp.status_code == 400


def test_dashboard_criteria_apply_writes(tmp_env, monkeypatch):
    tmp_criteria = tmp_env / "criteria.yaml"
    tmp_criteria.write_text(yaml.safe_dump({"signal_preferences": {"care_about": []}}))
    monkeypatch.setattr("hedwig.onboarding.nl_editor.CRITERIA_PATH", tmp_criteria)

    from hedwig.dashboard.app import create_app
    client = TestClient(create_app())
    resp = client.post(
        "/criteria/apply",
        json={
            "changes": [
                {"op": "add", "path": "signal_preferences.care_about", "value": "agent"},
            ],
            "intent": "add agent interest",
        },
    )
    assert resp.status_code == 200
    assert resp.json()["ok"]
    data = yaml.safe_load(tmp_criteria.read_text())
    assert "agent" in data["signal_preferences"]["care_about"]


def test_mcp_skill_adapters_import():
    from hedwig.sources._mcp_adapter import MCPSourceAdapter
    from hedwig.sources._skill_adapter import SkillSourceAdapter

    assert MCPSourceAdapter.metadata()["absorption_level"] == 1
    assert SkillSourceAdapter.metadata()["absorption_level"] == 2


def _make_post(title: str, platform: str = "hackernews", days_ago: int = 0):
    from hedwig.models import Platform, RawPost
    return RawPost(
        platform=Platform(platform),
        external_id=f"ext-{title}",
        title=title,
        url=f"https://example.com/{title}",
        content=title,
        author="alice",
        score=100,
        comments_count=10,
        published_at=datetime.now(tz=timezone.utc) - timedelta(days=days_ago),
    )


def test_last30days_saturation_penalty_drops_duplicates():
    from hedwig.engine.absorbed.last30days import saturation_penalty

    base = _make_post("LLM reasoning breakthrough")
    dups = [_make_post("LLM reasoning breakthrough") for _ in range(3)]
    penalty = saturation_penalty(base, dups)
    assert 0.2 <= penalty < 1.0, f"expected dampening, got {penalty}"


def test_last30days_persistence_rewards_repeated_topics():
    from hedwig.engine.absorbed.last30days import topic_persistence_score

    post = _make_post("AI agent frameworks compared")
    history = [
        _make_post("AI agent frameworks survey", days_ago=d)
        for d in (1, 3, 5, 7, 9)
    ]
    score = topic_persistence_score(post, history)
    assert score > 0.3


def test_last30days_enrich_bounds():
    from hedwig.engine.absorbed.last30days import enrich_score

    post = _make_post("novel single post")
    result = enrich_score(post, base_score=0.5, same_cycle_posts=[post], historical_posts=[])
    assert 0.0 <= result <= 1.0
