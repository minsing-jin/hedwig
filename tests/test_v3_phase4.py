"""Phase 4 tests — Meta-Evolution (mutate → shadow → adopt)."""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient


@pytest.fixture
def tmp_env(monkeypatch, tmp_path):
    monkeypatch.setenv("HEDWIG_STORAGE", "sqlite")
    monkeypatch.setenv("HEDWIG_DB_PATH", str(tmp_path / "hedwig.db"))
    # Relocate algorithm.yaml + log to tmp to avoid clobbering repo copy
    tmp_algo = tmp_path / "algorithm.yaml"
    tmp_algo.write_text(yaml.safe_dump({
        "version": 1,
        "retrieval": {"top_n": 200, "components": {}},
        "ranking": {
            "top_k": 30,
            "components": {
                "llm_judge": {"enabled": True, "weight": 0.5},
                "popularity_prior": {"enabled": True, "weight": 0.5},
            },
        },
        "fitness": {"adoption_threshold": 0.05},
        "meta_evolution": {"enabled": True},
    }))
    monkeypatch.setattr("hedwig.evolution.meta.ALGORITHM_PATH", tmp_algo)
    monkeypatch.setattr("hedwig.config.ALGORITHM_PATH", tmp_algo)
    log_path = tmp_path / "algorithm_log.jsonl"
    monkeypatch.setattr("hedwig.evolution.meta.ALGORITHM_LOG_PATH", log_path)
    yield tmp_path


def test_generate_candidate_weight_perturbation(tmp_env):
    from hedwig.evolution.meta import generate_candidate
    from hedwig.config import load_algorithm_config
    baseline = load_algorithm_config()
    cand, strat = generate_candidate(baseline, strategy="weight_perturbation")
    assert strat == "weight_perturbation"
    orig_weights = {
        n: c["weight"] for n, c in baseline["ranking"]["components"].items()
    }
    new_weights = {
        n: c["weight"] for n, c in cand["ranking"]["components"].items()
    }
    # At least one weight should differ (not guaranteed under tiny jitter, but very likely)
    assert orig_weights != new_weights or any(
        abs(orig_weights[n] - new_weights[n]) > 1e-6 for n in orig_weights
    )


def test_generate_candidate_feature_toggle(tmp_env):
    from hedwig.evolution.meta import generate_candidate
    from hedwig.config import load_algorithm_config
    baseline = load_algorithm_config()
    cand, strat = generate_candidate(baseline, strategy="feature_toggle")
    assert strat == "feature_toggle"


def test_generate_candidate_structural_change(tmp_env):
    from hedwig.evolution.meta import generate_candidate
    from hedwig.config import load_algorithm_config
    baseline = load_algorithm_config()
    cand, strat = generate_candidate(baseline, strategy="structural_change")
    assert strat == "structural_change"
    assert cand["retrieval"]["top_n"] != baseline["retrieval"]["top_n"] \
        or cand["ranking"]["top_k"] != baseline["ranking"]["top_k"]


def test_run_meta_cycle_respects_enabled_flag(tmp_env, monkeypatch):
    # Override the loaded config to disable meta_evolution
    tmp_algo = tmp_env / "algorithm.yaml"
    cfg = yaml.safe_load(tmp_algo.read_text())
    cfg["meta_evolution"]["enabled"] = False
    tmp_algo.write_text(yaml.safe_dump(cfg))

    from hedwig.evolution.meta import run_meta_cycle
    result = run_meta_cycle()
    assert result["adopted"] is False
    assert result.get("reason") == "disabled"


def test_run_meta_cycle_with_force(tmp_env):
    from hedwig.evolution.meta import run_meta_cycle

    result = run_meta_cycle(n_candidates=3, force=True)
    assert "candidates" in result
    assert len(result["candidates"]) == 3
    # Each candidate gets a delta and a recommend verdict
    for c in result["candidates"]:
        assert "strategy" in c
        assert "fitness_delta" in c
        assert c["recommend"] in ("adopt", "reject", "inconclusive")


def test_adopt_bumps_version_and_writes(tmp_env):
    from hedwig.evolution.meta import adopt
    from hedwig.config import load_algorithm_config

    baseline = load_algorithm_config()
    new_cfg = dict(baseline)
    new_cfg["ranking"]["components"]["popularity_prior"]["weight"] = 0.9
    adopted = adopt(new_cfg, reason="test", fitness_delta=0.1)
    assert adopted["version"] == baseline["version"] + 1

    # algorithm.yaml on disk was updated
    tmp_algo = tmp_env / "algorithm.yaml"
    written = yaml.safe_load(tmp_algo.read_text())
    assert written["version"] == adopted["version"]


def test_audit_log_written(tmp_env):
    from hedwig.evolution.meta import run_meta_cycle
    run_meta_cycle(force=True)
    log = tmp_env / "algorithm_log.jsonl"
    assert log.exists()
    lines = [l for l in log.read_text().splitlines() if l.strip()]
    # At least one candidate entry + one decision entry
    assert any('"event": "candidate"' in l for l in lines)
    assert any('"event": "no_adoption"' in l or '"event": "adopt"' in l for l in lines)


def test_meta_endpoint(tmp_env):
    from hedwig.dashboard.app import create_app
    client = TestClient(create_app())
    resp = client.post("/meta/cycle", json={"force": True, "n_candidates": 2})
    assert resp.status_code == 200
    data = resp.json()
    assert "candidates" in data
    assert len(data["candidates"]) == 2
