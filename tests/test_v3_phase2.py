"""Phase 2 tests — instrumentation (trace, timeline, sandbox)."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def tmp_env(monkeypatch, tmp_path):
    monkeypatch.setenv("HEDWIG_STORAGE", "sqlite")
    monkeypatch.setenv("HEDWIG_DB_PATH", str(tmp_path / "hedwig.db"))
    yield tmp_path


def test_trace_signal_identifies_matches(tmp_env, monkeypatch):
    # Craft a fake criteria + row
    monkeypatch.setattr(
        "hedwig.engine.trace.load_criteria",
        lambda: {"signal_preferences": {"care_about": ["agent frameworks"], "ignore": ["crypto"]}},
    )
    from hedwig.engine.trace import trace_signal

    row = {
        "id": "42",
        "platform": "hackernews",
        "title": "New agent frameworks survey",
        "content": "overview of agent frameworks in 2026",
        "url": "https://x.com/a",
        "relevance_score": 0.82,
        "platform_score": 150,
        "comments_count": 40,
        "published_at": "2026-04-20T00:00:00+00:00",
        "exploration_tags": '["llm-tooling"]',
    }
    tr = trace_signal(row)
    assert tr["signal_id"] == "42"
    assert tr["relevance_score"] == 0.82
    # care_about matching
    assert "agent frameworks" in tr["matched_care_about"]
    assert tr["matched_ignore"] == []
    assert tr["exploration_tags"] == ["llm-tooling"]


def test_timeline_merges_events(tmp_env):
    from hedwig.storage import save_evolution_signal, save_algorithm_version
    from hedwig.evolution.timeline import build_timeline

    save_evolution_signal("explicit", "criteria_edit", {"intent": "x"})
    save_algorithm_version(1, {"ranking": {"top_k": 30}})
    tl = build_timeline(days=30)
    assert len(tl) >= 2
    kinds = {e["type"] for e in tl}
    assert "criteria_edit" in kinds
    assert "algorithm_version" in kinds


def test_sandbox_synthesize_fitness_empty():
    from hedwig.evolution.sandbox import synthesize_fitness

    result = synthesize_fitness({"ranking": {"components": {}}})
    # no events, no components enabled → predicted 0
    assert result["predicted_fitness"] == 0.0
    assert result["n_events"] == 0


def test_sandbox_diversity_bonus_penalizes_monoculture():
    from hedwig.evolution.sandbox import synthesize_fitness

    monoculture = {
        "ranking": {
            "components": {
                "a": {"enabled": True, "weight": 0.95},
                "b": {"enabled": True, "weight": 0.05},
            }
        }
    }
    # 5 up, 1 down with injected events
    events = [{"kind": "upvote"} for _ in range(5)] + [{"kind": "downvote"}]
    result = synthesize_fitness(monoculture, recent_events=events)
    assert result["diversity_bonus"] < 0  # penalized


def test_sandbox_diversity_bonus_rewards_mix():
    from hedwig.evolution.sandbox import synthesize_fitness

    mixed = {
        "ranking": {
            "components": {
                "a": {"enabled": True, "weight": 0.4},
                "b": {"enabled": True, "weight": 0.3},
                "c": {"enabled": True, "weight": 0.3},
            }
        }
    }
    events = [{"kind": "upvote"} for _ in range(5)]
    result = synthesize_fitness(mixed, recent_events=events)
    assert result["diversity_bonus"] > 0


def test_sandbox_make_candidate_perturbs_weights():
    from hedwig.evolution.sandbox import make_candidate

    baseline = {"ranking": {"components": {"llm_judge": {"enabled": True, "weight": 0.4}}}}
    cand = make_candidate(baseline, {"llm_judge": 0.6, "bandit": 0.2})
    assert cand["ranking"]["components"]["llm_judge"]["weight"] == 0.6
    assert cand["ranking"]["components"]["bandit"]["weight"] == 0.2
    assert cand["ranking"]["components"]["bandit"]["enabled"]


def test_endpoint_evolution_timeline(tmp_env):
    from hedwig.storage import save_evolution_signal
    from hedwig.dashboard.app import create_app

    save_evolution_signal("semi", "qa_accept", {"q": "test"})
    client = TestClient(create_app())
    resp = client.get("/evolution/timeline?days=7&limit=50")
    assert resp.status_code == 200
    data = resp.json()
    assert "events" in data
    assert any(e["type"] == "qa_accept" for e in data["events"])


def test_endpoint_sandbox_simulate(tmp_env):
    from hedwig.dashboard.app import create_app

    client = TestClient(create_app())
    resp = client.post(
        "/sandbox/simulate",
        json={"perturbations": {"bandit": 0.3, "llm_judge": 0.3}},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "baseline" in data
    assert "candidate" in data
    assert "delta" in data
    assert "candidate_config" in data
    # The candidate must have the perturbed weights
    comps = data["candidate_config"]["ranking"]["components"]
    assert comps["bandit"]["weight"] == 0.3


def test_endpoint_signal_trace_not_found(tmp_env):
    from hedwig.dashboard.app import create_app

    client = TestClient(create_app())
    resp = client.get("/signals/999999/trace")
    assert resp.status_code == 404
