"""Phase 0 smoke tests for v3 scaffolding.

Validates that all v3 modules import cleanly, algorithm.yaml loads, and the
/ask endpoint behaves as designed (RAG over empty DB falls back gracefully).

This runs without network, without OpenAI keys, without external services.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


def test_algorithm_yaml_loads(tmp_path, monkeypatch):
    monkeypatch.setenv("HEDWIG_STORAGE", "sqlite")
    from hedwig.config import load_algorithm_config, ALGORITHM_PATH

    assert ALGORITHM_PATH.exists(), "algorithm.yaml must exist in repo root"
    cfg = load_algorithm_config()
    assert cfg.get("version") == 1
    assert "retrieval" in cfg
    assert "ranking" in cfg
    assert "fitness" in cfg
    assert "meta_evolution" in cfg


def test_ensemble_reads_weights(monkeypatch):
    monkeypatch.setenv("HEDWIG_STORAGE", "sqlite")
    from hedwig.engine.ensemble import get_enabled_components, get_ensemble_weights

    ranking = get_enabled_components("ranking")
    assert "llm_judge" in ranking
    weights = get_ensemble_weights("ranking")
    # normalized
    assert abs(sum(weights.values()) - 1.0) < 1e-6


def test_qa_module_imports(monkeypatch):
    monkeypatch.setenv("HEDWIG_STORAGE", "sqlite")
    from hedwig.qa import router, retrieval  # noqa: F401

    assert hasattr(router, "answer")
    assert hasattr(retrieval, "retrieve_from_db")
    assert hasattr(retrieval, "format_context")


def test_ask_endpoint_empty_db(monkeypatch):
    monkeypatch.setenv("HEDWIG_STORAGE", "sqlite")
    # Steer the sqlite file to a tmp location so the test doesn't pollute state.
    import tempfile
    from pathlib import Path
    tmp = Path(tempfile.mkdtemp()) / "hedwig.db"
    monkeypatch.setenv("HEDWIG_DB_PATH", str(tmp))

    from hedwig.dashboard.app import create_app

    client = TestClient(create_app())
    resp = client.post("/ask", json={"question": "test question"})
    assert resp.status_code == 200
    data = resp.json()
    assert "answer" in data
    assert "sources" in data
    assert "fallback_suggested" in data


def test_check_required_keys_minimal(monkeypatch):
    """Quickstart mode must only require OPENAI_API_KEY."""
    monkeypatch.setattr("hedwig.config.OPENAI_API_KEY", "sk-test")
    from hedwig.config import check_required_keys, check_optional_keys

    # Only OPENAI needed; Supabase/delivery moved to optional
    assert check_required_keys("daily") == []
    assert check_required_keys("full") == []
    # Optional gaps surfaced as warnings
    gaps = check_optional_keys("daily")
    assert any("delivery" in g.lower() for g in gaps)


def test_dashboard_all_routes_render(monkeypatch):
    """All renderable dashboard routes must return non-500 after v2→v3 changes."""
    monkeypatch.setenv("HEDWIG_STORAGE", "sqlite")
    import tempfile
    from pathlib import Path
    tmp = Path(tempfile.mkdtemp()) / "hedwig.db"
    monkeypatch.setenv("HEDWIG_DB_PATH", str(tmp))
    monkeypatch.setattr("hedwig.config.OPENAI_API_KEY", "sk-test")

    from hedwig.dashboard.app import create_app

    client = TestClient(create_app())
    # These are the single-user mode routes; all must at minimum not 500
    for path in [
        "/",
        "/onboarding",
        "/signals",
        "/sources",
        "/settings",
        "/criteria",
    ]:
        resp = client.get(path, follow_redirects=False)
        # 200 or 303 (redirect to /setup) are acceptable
        assert resp.status_code in (200, 303), f"{path} returned {resp.status_code}"
