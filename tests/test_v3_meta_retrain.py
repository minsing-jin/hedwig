"""Coverage for monthly meta-cycle SOTA model retraining."""
from __future__ import annotations

import pytest
import yaml
from fastapi.testclient import TestClient


@pytest.fixture
def tmp_env(monkeypatch, tmp_path):
    monkeypatch.setenv("HEDWIG_STORAGE", "sqlite")
    monkeypatch.setenv("HEDWIG_DB_PATH", str(tmp_path / "hedwig.db"))
    monkeypatch.setenv("HEDWIG_LTR_WEIGHTS", str(tmp_path / "ltr.json"))
    monkeypatch.setenv("HEDWIG_LTR_LGBM", str(tmp_path / "ltr.txt"))

    tmp_algo = tmp_path / "algorithm.yaml"
    tmp_algo.write_text(yaml.safe_dump({
        "version": 1,
        "retrieval": {"top_n": 200, "threshold": 0.10},
        "ranking": {
            "top_k": 30,
            "components": {
                "llm_judge": {"enabled": True, "weight": 0.4},
                "popularity_prior": {"enabled": True, "weight": 0.1},
                "ltr": {"enabled": True, "weight": 0.25,
                        "features": ["text_relevance", "source_authority"]},
            },
        },
        "fitness": {"adoption_threshold": 0.05},
        "meta_evolution": {"enabled": True},
    }))
    monkeypatch.setattr("hedwig.evolution.meta.ALGORITHM_PATH", tmp_algo)
    monkeypatch.setattr("hedwig.config.ALGORITHM_PATH", tmp_algo)
    monkeypatch.setattr("hedwig.evolution.meta.ALGORITHM_LOG_PATH", tmp_path / "algorithm_log.jsonl")
    import hedwig.config as _cfg
    _cfg._ALGORITHM_VERSION_SEEDED = False
    yield tmp_path


def test_retrain_sota_models_returns_three_blocks(tmp_env):
    """Helper returns lightgbm + reinforce + interpretation, all three keys."""
    from hedwig.evolution.meta import _retrain_sota_models
    out = _retrain_sota_models(lookback_days=28)
    assert "lightgbm" in out
    assert "reinforce" in out
    assert "interpretation" in out
    assert out["lookback_days"] == 28


def test_meta_cycle_includes_models_retrained_block(tmp_env):
    from hedwig.evolution.meta import run_meta_cycle
    result = run_meta_cycle(force=True, n_candidates=2)
    assert "models_retrained" in result
    block = result["models_retrained"]
    assert isinstance(block, dict)
    assert "lightgbm" in block
    assert "reinforce" in block
    assert "interpretation" in block


def test_meta_cycle_can_skip_retrain(tmp_env):
    from hedwig.evolution.meta import run_meta_cycle
    result = run_meta_cycle(force=True, n_candidates=2, retrain_models=False)
    assert result.get("models_retrained") is None


def test_meta_cycle_audit_log_records_retrain(tmp_env):
    from pathlib import Path
    from hedwig.evolution.meta import run_meta_cycle
    run_meta_cycle(force=True, n_candidates=2)
    log_path = tmp_env / "algorithm_log.jsonl"
    assert log_path.exists()
    content = log_path.read_text()
    # The retrain step must be visible in the audit log
    assert "retrain_sota_models" in content


def test_meta_endpoint_includes_retrain_in_response(tmp_env):
    from hedwig.dashboard.app import create_app
    client = TestClient(create_app())
    resp = client.post("/meta/cycle", json={"force": True, "n_candidates": 2})
    assert resp.status_code == 200
    data = resp.json()
    # JSON serializability check
    assert "models_retrained" in data


def test_hybrid_ensemble_doc_present():
    """The doc the user asked us to save must exist."""
    from pathlib import Path
    p = Path(__file__).resolve().parents[1] / "docs/HYBRID_ENSEMBLE.md"
    assert p.exists()
    body = p.read_text()
    # Must contain the four hybrid axes + 6 components + evolution layers
    for keyword in ("Hybrid", "llm_judge", "ltr", "content_based",
                    "popularity_prior", "bandit", "sequential",
                    "Daily", "Weekly", "Monthly"):
        assert keyword in body
