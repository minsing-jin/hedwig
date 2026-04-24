"""Coverage for G2/G11, G3, G4 — the three high-priority interview gaps
identified in docs/phase_reports/interview_gap_audit.md."""
from __future__ import annotations

import asyncio

import pytest
import yaml
from fastapi.testclient import TestClient


@pytest.fixture
def tmp_env(monkeypatch, tmp_path):
    monkeypatch.setenv("HEDWIG_STORAGE", "sqlite")
    monkeypatch.setenv("HEDWIG_DB_PATH", str(tmp_path / "hedwig.db"))
    import hedwig.config as _cfg
    _cfg._ALGORITHM_VERSION_SEEDED = False
    yield tmp_path


# --- G2/G11 — interpretation_style ---------------------------------------

def test_interpretation_style_seeded_on_first_call(tmp_env):
    from hedwig.evolution.interpretation import ensure_default_style
    from hedwig.storage import get_active_interpretation_style
    active = ensure_default_style()
    assert active["version"] == 1
    assert active["prompt_template"]
    again = get_active_interpretation_style()
    assert again["id"] == active["id"]


def test_interpretation_style_evolves_on_low_upvote(tmp_env):
    from hedwig.evolution.interpretation import (
        ensure_default_style,
        evolve_style_from_signals,
    )
    ensure_default_style()
    out = evolve_style_from_signals(recent_feedback_ratio=0.3, natural_language_hints=[])
    assert out["evolved"]
    assert out["jargon_level"] == "low"
    assert out["depth"] == "surface"
    assert out["to_version"] == 2


def test_interpretation_style_no_churn_when_high_upvote(tmp_env):
    from hedwig.evolution.interpretation import (
        ensure_default_style,
        evolve_style_from_signals,
    )
    ensure_default_style()
    out = evolve_style_from_signals(recent_feedback_ratio=0.8)
    assert out["evolved"] is False


def test_scorer_prompt_uses_active_style(tmp_env):
    from hedwig.evolution.interpretation import evolve_style_from_signals
    from hedwig.engine.scorer import _build_scoring_prompt
    evolve_style_from_signals(recent_feedback_ratio=0.2, force=True)
    prompt = _build_scoring_prompt({"identity": {"role": "builder"}})
    assert "Style (auto-tuned weekly)" in prompt


# --- G3 — user_memory weekly snapshot -----------------------------------

def test_weekly_snapshot_produces_row(tmp_env):
    from hedwig.dashboard.demo_seed import seed_demo
    from hedwig.memory.snapshot import create_weekly_snapshot
    from hedwig.storage import get_recent_signals  # init_db ensures schema
    get_recent_signals(days=1)   # trigger schema init
    seed_demo(reset=True)
    res = create_weekly_snapshot(week="2026-W17")
    assert res["week"] == "2026-W17"
    assert res["n_feedback"] >= 0
    assert res["persisted_db"] is True


# --- G4 — sovereignty boundary -----------------------------------------

def test_sovereignty_allows_user_editable_criteria_path(tmp_env):
    from hedwig.sovereignty import can_edit
    assert can_edit("criteria", "signal_preferences.care_about", actor="user")
    assert can_edit("criteria", "context.current_projects", actor="user")


def test_sovereignty_blocks_readonly_history(tmp_env):
    from hedwig.sovereignty import can_edit
    assert can_edit("algorithm", "version", actor="user") is False
    assert can_edit("algorithm", "version", actor="system") is False


def test_sovereignty_blocks_unlisted_user_path(tmp_env):
    from hedwig.sovereignty import can_edit
    # some random unlisted path
    assert can_edit("criteria", "totally.made.up.path", actor="user") is False


def test_sovereignty_enforce_raises(tmp_env):
    from hedwig.sovereignty import SovereigntyError, enforce
    with pytest.raises(SovereigntyError):
        enforce("algorithm", "version", actor="user")


def test_nl_criteria_rejects_unlisted_path(tmp_env, monkeypatch):
    tmp_criteria = tmp_env / "criteria.yaml"
    tmp_criteria.write_text(yaml.safe_dump({"signal_preferences": {"care_about": []}}))
    monkeypatch.setattr("hedwig.onboarding.nl_editor.CRITERIA_PATH", tmp_criteria)
    from hedwig.onboarding.nl_editor import confirm_edit

    r = confirm_edit(
        [
            {"op": "add", "path": "signal_preferences.care_about", "value": "agent"},  # allowed
            {"op": "set", "path": "_schema_version", "value": "evil"},                  # blocked
        ],
        intent="mixed",
    )
    assert r["ok"] is True
    assert len(r["applied_changes"]) == 1
    assert len(r["rejected_changes"]) == 1
    assert r["rejected_changes"][0]["reason"].startswith("sovereignty")


def test_sovereignty_page_renders(tmp_env):
    from hedwig.dashboard.app import create_app
    client = TestClient(create_app())
    resp = client.get("/sovereignty")
    assert resp.status_code == 200
    assert "User editable" in resp.text
    assert "System mutable" in resp.text
    assert "Readonly history" in resp.text


def test_sovereignty_nav_link(tmp_env):
    from hedwig.dashboard.app import create_app
    client = TestClient(create_app())
    resp = client.get("/")
    assert 'href="/sovereignty"' in resp.text
