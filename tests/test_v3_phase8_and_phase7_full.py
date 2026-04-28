"""S8 (LightGBM/LLM-rec/IPS) + Phase 7 S4-S9 coverage."""
from __future__ import annotations

import asyncio
import io
import json
import zipfile

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def tmp_env(monkeypatch, tmp_path):
    monkeypatch.setenv("HEDWIG_STORAGE", "sqlite")
    monkeypatch.setenv("HEDWIG_DB_PATH", str(tmp_path / "hedwig.db"))
    monkeypatch.setenv("HEDWIG_LTR_WEIGHTS", str(tmp_path / "ltr.json"))
    monkeypatch.setenv("HEDWIG_LTR_LGBM", str(tmp_path / "ltr.txt"))
    import hedwig.config as _cfg
    _cfg._ALGORITHM_VERSION_SEEDED = False
    yield tmp_path


# --- S8.1 LightGBM ----------------------------------------------------

def test_lightgbm_path_either_works_or_falls_back():
    """LightGBM availability is system-dependent (libomp on macOS).
    Either it imports cleanly OR we fall back without crashing — both OK."""
    from hedwig.engine.ensemble.ltr import _has_lightgbm
    # Just must not raise. Both True and False are acceptable.
    assert isinstance(_has_lightgbm(), bool)


def test_ltr_logistic_fallback_when_no_model(tmp_env):
    """No model file → LTR uses logistic prior, returns 0..1 scores."""
    from hedwig.engine.ensemble.ltr import LTRRanker
    from hedwig.models import Platform, RawPost
    posts = [RawPost(platform=Platform.HACKERNEWS, external_id="a",
                     title="agent benchmark", url="", content="x", score=10)]
    scores = asyncio.run(LTRRanker(criteria_keywords=["agent"]).score_posts(posts))
    assert all(0 <= s <= 1 for s in scores)


def test_lgbm_fit_requires_data(tmp_env):
    from hedwig.engine.ensemble.ltr import fit_lgbm_from_history
    out = fit_lgbm_from_history(criteria_keywords=["agent"])
    assert out["trained"] is False


# --- S8.3 LLM-rec ----------------------------------------------------

def test_llmrec_no_key_returns_neutral(tmp_env, monkeypatch):
    monkeypatch.setattr("hedwig.engine.ensemble.llm_rec.OPENAI_API_KEY", "")
    from hedwig.engine.ensemble.llm_rec import LLMRecRanker
    from hedwig.models import Platform, RawPost
    posts = [RawPost(platform=Platform.HACKERNEWS, external_id=f"e{i}",
                     title=f"t{i}", url="", content="") for i in range(3)]
    out = asyncio.run(LLMRecRanker().score_posts(posts))
    assert out == [0.5, 0.5, 0.5]


def test_llmrec_registered_in_combine(tmp_env):
    from hedwig.engine.ensemble.combine import _registry
    assert "llm_rec" in _registry()


# --- S8.4 IPS debias -------------------------------------------------

def test_ips_propensity_from_seeded_signals(tmp_env):
    from hedwig.dashboard.demo_seed import seed_demo
    from hedwig.engine.ensemble.debias import compute_platform_propensity
    seed_demo(reset=True)
    p = compute_platform_propensity(lookback_days=30)
    assert p
    assert all(0 < v <= 1 for v in p.values())


def test_ips_apply_correction_keeps_range(tmp_env):
    from hedwig.engine.ensemble.debias import apply_ips_correction
    from hedwig.models import Platform, RawPost
    posts = [
        RawPost(platform=Platform.HACKERNEWS, external_id="a", title="x", url=""),
        RawPost(platform=Platform.REDDIT, external_id="b", title="y", url=""),
    ]
    out = apply_ips_correction(
        [0.5, 0.5], posts,
        propensity={"hackernews": 0.8, "reddit": 0.2},
    )
    # The lower-propensity platform should now score higher
    assert out[1] > out[0]
    assert all(0 <= s <= 1 for s in out)


# --- Phase 7 S4 — Feeds/Deck ----------------------------------------

def test_load_feeds_yaml_present():
    from hedwig.feeds import list_feeds
    feeds = list_feeds()
    assert any(f["id"] == "default" for f in feeds)
    assert any(f["id"] == "morning_deep" for f in feeds)


def test_get_feed_config_applies_overrides():
    from hedwig.feeds import get_feed_config
    cfg = get_feed_config("morning_deep")
    top_k = cfg["algorithm"].get("ranking", {}).get("top_k")
    assert top_k == 12  # override applied


def test_feed_page_renders_tabs(tmp_env):
    from hedwig.dashboard.app import create_app
    client = TestClient(create_app())
    resp = client.get("/feed")
    assert resp.status_code == 200
    assert 'class="feed-tabs"' in resp.text
    assert "morning_deep" in resp.text or "아침" in resp.text


def test_feed_list_endpoint(tmp_env):
    from hedwig.dashboard.app import create_app
    client = TestClient(create_app())
    resp = client.get("/feed/list")
    assert resp.status_code == 200
    feeds = resp.json()["feeds"]
    assert any(f["id"] == "default" for f in feeds)


# --- Phase 7 S5 — /profile ------------------------------------------

def test_profile_page_renders(tmp_env):
    from hedwig.dashboard.app import create_app
    from hedwig.dashboard.demo_seed import seed_demo
    seed_demo(reset=True)
    client = TestClient(create_app())
    resp = client.get("/profile")
    assert resp.status_code == 200
    assert "Algorithm Profile" in resp.text
    assert "Feed Personality" in resp.text


# --- Phase 7 S6 — Algorithm export/import bundle --------------------

def test_export_bundle_returns_zip(tmp_env):
    from hedwig.dashboard.app import create_app
    client = TestClient(create_app())
    resp = client.get("/algorithm/export")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/zip"
    blob = resp.content
    with zipfile.ZipFile(io.BytesIO(blob)) as zf:
        names = zf.namelist()
    assert "manifest.json" in names
    assert "algorithm.yaml" in names
    assert "criteria.yaml" in names


def test_import_dry_run_filters_via_sovereignty(tmp_env):
    from hedwig.dashboard.app import create_app
    from hedwig.onboarding.bundle import export_bundle
    blob, _ = export_bundle()
    client = TestClient(create_app())
    resp = client.post("/algorithm/import/dry-run", content=blob,
                        headers={"Content-Type": "application/zip"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert "criteria_allowed" in data
    assert "algorithm_allowed" in data


def test_import_rejects_bad_zip(tmp_env):
    from hedwig.dashboard.app import create_app
    client = TestClient(create_app())
    resp = client.post("/algorithm/import", content=b"not a zip",
                        headers={"Content-Type": "application/zip"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is False
    assert "errors" in data


# --- Phase 7 S7 — PWA ----------------------------------------------

def test_manifest_served(tmp_env):
    from hedwig.dashboard.app import create_app
    client = TestClient(create_app())
    resp = client.get("/static/manifest.json")
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "Hedwig — Personal SNS Platform"
    assert "icons" in data


def test_sw_served(tmp_env):
    from hedwig.dashboard.app import create_app
    client = TestClient(create_app())
    resp = client.get("/static/sw.js")
    assert resp.status_code == 200
    body = resp.text
    assert "addEventListener" in body
    assert "SHELL_CACHE" in body


def test_base_html_registers_sw(tmp_env):
    from hedwig.dashboard.app import create_app
    client = TestClient(create_app())
    resp = client.get("/")
    assert "/static/manifest.json" in resp.text
    assert "navigator.serviceWorker.register" in resp.text


# --- Phase 7 S9 — Feed personality ----------------------------------

def test_feed_personality_aggregates(tmp_env):
    from hedwig.dashboard.demo_seed import seed_demo
    from hedwig.qa.personality import compute_feed_personality
    seed_demo(reset=True)
    out = compute_feed_personality(days=7)
    assert "upvote_ratio" in out
    assert "feedback_count" in out
    assert "top_platforms" in out
    assert isinstance(out["top_platforms"], list)


def test_profile_nav_link(tmp_env):
    from hedwig.dashboard.app import create_app
    client = TestClient(create_app())
    resp = client.get("/")
    assert 'href="/profile"' in resp.text
