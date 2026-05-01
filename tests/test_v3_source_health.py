"""Coverage for the wrap-up reinforcements."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def tmp_env(monkeypatch, tmp_path):
    monkeypatch.setenv("HEDWIG_STORAGE", "sqlite")
    monkeypatch.setenv("HEDWIG_DB_PATH", str(tmp_path / "hedwig.db"))
    yield tmp_path


# --- papers_with_code switched to HF Daily Papers --------------------

def test_papers_with_code_uses_hf_endpoint():
    from hedwig.sources.papers_with_code import HF_DAILY_PAPERS
    assert "huggingface.co/api/daily_papers" in HF_DAILY_PAPERS


# --- bluesky switched to RSS-based ----------------------------------

def test_bluesky_uses_rss_handles():
    from hedwig.sources.bluesky import BlueskySource, DEFAULT_HANDLES
    assert BlueskySource.fetch_method.value == "rss"
    assert "karpathy.bsky.social" in DEFAULT_HANDLES


def test_bluesky_env_handles_override(monkeypatch):
    monkeypatch.setenv("HEDWIG_BSKY_HANDLES", "alice.bsky.social,@bob.bsky.social")
    from hedwig.sources.bluesky import BlueskySource
    src = BlueskySource()
    assert "alice.bsky.social" in src.handles
    assert "bob.bsky.social" in src.handles  # @ stripped


# --- /status source-health panel ----------------------------------

def test_compute_source_health_returns_per_plugin(tmp_env):
    from hedwig.qa.exit_conditions import compute_source_health
    rows = compute_source_health(days=1)
    assert isinstance(rows, list)
    plugin_ids = {r["plugin_id"] for r in rows}
    # All registered sources must show up
    for required in ("hackernews", "ai_labs", "bluesky", "papers_with_code"):
        assert required in plugin_ids


def test_source_health_flags_missing_env(tmp_env, monkeypatch):
    """instagram/tiktok/podcast/web_search should report their missing env."""
    monkeypatch.delenv("SCRAPECREATORS_API_KEY", raising=False)
    monkeypatch.delenv("EXA_API_KEY", raising=False)
    monkeypatch.delenv("HEDWIG_PODCAST_FEEDS", raising=False)
    from hedwig.qa.exit_conditions import compute_source_health
    rows = compute_source_health()
    by_plugin = {r["plugin_id"]: r for r in rows}
    assert by_plugin["instagram"]["missing_env"] == "SCRAPECREATORS_API_KEY"
    assert by_plugin["tiktok"]["missing_env"] == "SCRAPECREATORS_API_KEY"
    assert by_plugin["podcast"]["missing_env"] == "HEDWIG_PODCAST_FEEDS"
    assert by_plugin["web_search"]["missing_env"] == "EXA_API_KEY"


def test_source_health_clears_when_env_set(tmp_env, monkeypatch):
    monkeypatch.setenv("EXA_API_KEY", "exa-fake")
    from hedwig.qa.exit_conditions import compute_source_health
    rows = compute_source_health()
    by_plugin = {r["plugin_id"]: r for r in rows}
    # web_search no longer flagged once EXA_API_KEY is present
    assert by_plugin["web_search"]["missing_env"] is None


def test_status_page_renders_source_health(tmp_env):
    from hedwig.dashboard.app import create_app
    client = TestClient(create_app())
    resp = client.get("/status")
    assert resp.status_code == 200
    assert "Source Health" in resp.text
    assert "src-health" in resp.text


# --- Setup page exposes new env vars -----------------------------

def test_env_manager_lists_new_optional_keys():
    from hedwig.dashboard.env_manager import EnvManager
    keys = EnvManager.OPTIONAL_KEYS
    for required in ("JINA_API_KEY", "EXA_API_KEY", "SCRAPECREATORS_API_KEY",
                     "HEDWIG_PODCAST_FEEDS", "HEDWIG_BSKY_HANDLES",
                     "HEDWIG_PIPELINE"):
        assert required in keys


def test_setup_page_includes_jina_key(tmp_env):
    from hedwig.dashboard.app import create_app
    client = TestClient(create_app())
    resp = client.get("/setup")
    assert resp.status_code == 200
    assert "JINA_API_KEY" in resp.text or "Jina" in resp.text
