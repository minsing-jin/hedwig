from __future__ import annotations

import json

import yaml
from fastapi.testclient import TestClient


def _write_algorithm(path):
    path.write_text(yaml.safe_dump({
        "version": 1,
        "origin": "test",
        "ranking": {
            "components": {
                "llm_judge": {"enabled": True, "weight": 0.35},
                "ltr": {
                    "enabled": True,
                    "weight": 0.25,
                    "features": ["text_relevance", "source_authority"],
                },
                "content_based": {"enabled": True, "weight": 0.20},
                "bandit": {"enabled": False, "weight": 0.10},
                "sequential": {"enabled": False, "weight": 0.10},
                "llm_rec": {"enabled": False, "weight": 0.15},
            },
            "ips_debias": {"enabled": False},
        },
        "meta_evolution": {"enabled": False, "cadence_days": 28},
    }))


def test_ltr_training_status_reports_cold_start(monkeypatch, tmp_path):
    import hedwig.engine.ensemble.ltr as ltr

    monkeypatch.setattr(ltr, "WEIGHTS_PATH", tmp_path / "missing_weights.json")
    monkeypatch.setattr(ltr, "LGBM_MODEL_PATH", tmp_path / "missing_lgbm.txt")
    monkeypatch.setattr(ltr, "_call_feedback_since", lambda days: [])
    monkeypatch.setattr(ltr, "_call_recent_signals", lambda days: [])
    monkeypatch.setattr(ltr, "_call_behavior_events", lambda limit=2000: [])

    status = ltr.training_status()

    assert status["active_backend"] == "default_priors"
    assert status["cold_start"] is True
    assert status["lightgbm"]["model_exists"] is False
    assert status["logistic"]["trained"] is False


def test_ltr_training_status_reports_logistic_weights(monkeypatch, tmp_path):
    import hedwig.engine.ensemble.ltr as ltr

    weights = tmp_path / "ltr_weights.json"
    weights.write_text(json.dumps({"weights": {"text_relevance": 1.2}, "bias": -0.1}))

    monkeypatch.setattr(ltr, "WEIGHTS_PATH", weights)
    monkeypatch.setattr(ltr, "LGBM_MODEL_PATH", tmp_path / "missing_lgbm.txt")
    monkeypatch.setattr(ltr, "_call_feedback_since", lambda days: [{"signal_id": str(i), "vote": "up"} for i in range(5)])
    monkeypatch.setattr(ltr, "_call_recent_signals", lambda days: [])
    monkeypatch.setattr(ltr, "_call_behavior_events", lambda limit=2000: [])

    status = ltr.training_status()

    assert status["active_backend"] == "logistic_sgd"
    assert status["cold_start"] is False
    assert status["logistic"]["weights_exist"] is True
    assert status["logistic"]["enough_feedback"] is True


def test_compute_algorithm_training_status_is_truthful(monkeypatch, tmp_path):
    algo = tmp_path / "algorithm.yaml"
    _write_algorithm(algo)
    monkeypatch.setattr("hedwig.config.ALGORITHM_PATH", algo)
    import hedwig.config as cfg
    cfg._ALGORITHM_VERSION_SEEDED = False

    monkeypatch.setattr(
        "hedwig.engine.ensemble.ltr.training_status",
        lambda lookback_days=28: {
            "active_backend": "default_priors",
            "feedback_events": 0,
            "features": ["text_relevance"],
            "lightgbm": {"ready": False},
            "logistic": {"trained": False},
        },
    )

    from hedwig.qa.exit_conditions import compute_algorithm_training_status
    status = compute_algorithm_training_status()

    assert "Cold start" in status["summary"]
    assert status["optional_sota"]["bandit"] is False
    assert status["optional_sota"]["meta_evolution"] is False
    assert "ltr" in status["enabled_components"]


def test_status_page_renders_algorithm_training_status(monkeypatch, tmp_path):
    algo = tmp_path / "algorithm.yaml"
    _write_algorithm(algo)
    monkeypatch.setenv("HEDWIG_STORAGE", "sqlite")
    monkeypatch.setenv("HEDWIG_DB_PATH", str(tmp_path / "hedwig.db"))
    monkeypatch.setattr("hedwig.config.ALGORITHM_PATH", algo)
    import hedwig.config as cfg
    cfg._ALGORITHM_VERSION_SEEDED = False
    import hedwig.engine.ensemble.ltr as ltr
    monkeypatch.setattr(ltr, "WEIGHTS_PATH", tmp_path / "missing_weights.json")
    monkeypatch.setattr(ltr, "LGBM_MODEL_PATH", tmp_path / "missing_lgbm.txt")

    from hedwig.dashboard.app import create_app
    client = TestClient(create_app())
    resp = client.get("/status")

    assert resp.status_code == 200
    assert "Owned Algorithm Training Status" in resp.text
    assert "default_priors" in resp.text
