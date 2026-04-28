"""Coverage for Phase 7 (S1+S2+S3) + interview gaps G5–G10."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def tmp_env(monkeypatch, tmp_path):
    monkeypatch.setenv("HEDWIG_STORAGE", "sqlite")
    monkeypatch.setenv("HEDWIG_DB_PATH", str(tmp_path / "hedwig.db"))
    import hedwig.config as _cfg
    _cfg._ALGORITHM_VERSION_SEEDED = False
    yield tmp_path


# --- Phase 7 S3 — behavior_events ---------------------------------------

def test_behavior_event_save_and_fetch(tmp_env):
    from hedwig.storage import get_behavior_events, save_behavior_event
    assert save_behavior_event("sig-1", "view_start", position_in_feed=0)
    assert save_behavior_event("sig-1", "dwell", dwell_ms=4500)
    rows = get_behavior_events(signal_id="sig-1")
    kinds = {r["event_type"] for r in rows}
    assert kinds == {"view_start", "dwell"}


def test_behavior_event_invalid_type_rejected(tmp_env):
    from hedwig.storage import save_behavior_events_batch
    saved = save_behavior_events_batch([
        {"signal_id": "x", "event_type": "view_start"},
        {"signal_id": "x", "event_type": "totally-not-a-type"},
        {"signal_id": "y", "event_type": "dwell", "dwell_ms": 1000},
    ])
    assert saved == 2


# --- Phase 7 S1 — /feed cursor pagination -------------------------------

def test_feed_api_returns_items(tmp_env):
    from hedwig.dashboard.app import create_app
    from hedwig.dashboard.demo_seed import seed_demo
    seed_demo(reset=True)
    client = TestClient(create_app())
    resp = client.get("/feed/api?limit=5")
    assert resp.status_code == 200
    data = resp.json()
    assert "items" in data
    assert len(data["items"]) <= 5
    assert "has_more" in data


def test_feed_api_cursor_advances(tmp_env):
    from hedwig.dashboard.app import create_app
    from hedwig.dashboard.demo_seed import seed_demo
    seed_demo(reset=True)
    client = TestClient(create_app())
    page1 = client.get("/feed/api?limit=3").json()
    if not page1.get("next_cursor"):
        pytest.skip("not enough demo signals to paginate")
    page2 = client.get(f"/feed/api?limit=3&cursor={page1['next_cursor']}").json()
    ids1 = {it["id"] for it in page1["items"]}
    ids2 = {it["id"] for it in page2["items"]}
    assert ids1.isdisjoint(ids2)


def test_feed_html_renders(tmp_env):
    from hedwig.dashboard.app import create_app
    client = TestClient(create_app())
    resp = client.get("/feed")
    assert resp.status_code == 200
    body = resp.text
    assert "feed-shell" in body
    assert "/events/beacon" in body
    assert "IntersectionObserver" in body


def test_events_beacon_endpoint(tmp_env):
    from hedwig.dashboard.app import create_app
    from hedwig.storage import get_behavior_events, get_evolution_signals
    client = TestClient(create_app())
    resp = client.post("/events/beacon", json={"events": [
        {"signal_id": "1", "event_type": "view_start", "position_in_feed": 0},
        {"signal_id": "1", "event_type": "dwell", "dwell_ms": 3000},
        {"signal_id": "2", "event_type": "skip", "dwell_ms": 500},
    ]})
    assert resp.status_code == 200
    assert resp.json()["saved"] == 3
    assert len(get_behavior_events()) >= 3
    # dwell + skip should have surfaced as evolution_signal rows
    impl = get_evolution_signals(channel="implicit")
    kinds = {e["kind"] for e in impl}
    assert "behavior_dwell" in kinds
    assert "behavior_skip" in kinds


def test_events_beacon_rejects_bad_payload(tmp_env):
    from hedwig.dashboard.app import create_app
    client = TestClient(create_app())
    resp = client.post("/events/beacon", json={"events": "not-a-list"})
    assert resp.status_code == 400


# --- G5 — feedback.attribution -----------------------------------------

def test_save_feedback_writes_attribution(tmp_env, monkeypatch):
    from hedwig.dashboard.demo_seed import seed_demo
    seed_demo(reset=True)
    monkeypatch.setattr(
        "hedwig.config.load_criteria",
        lambda: {"signal_preferences": {"care_about": ["agent", "MoE"]}},
    )
    from hedwig.feedback import FeedbackCollector
    from hedwig.models import VoteType
    from hedwig.storage import save_feedback
    fb = FeedbackCollector().from_direct(signal_id="demo-0", vote=VoteType.UP)
    assert save_feedback(fb)

    # Verify attribution column populated
    from hedwig.storage.local import _conn
    with _conn() as conn:
        row = conn.execute(
            "SELECT attribution FROM feedback WHERE signal_id = ? LIMIT 1",
            ("demo-0",),
        ).fetchone()
    assert row is not None
    import json as _json
    attr = _json.loads(row["attribution"] or "{}")
    assert "criterion_keywords" in attr
    assert "platform" in attr


# --- G6 — delivered_signals --------------------------------------------

def test_delivered_signals_crud(tmp_env):
    from hedwig.storage import get_delivered_signals, save_delivered_signal
    new_id = save_delivered_signal("sig-1", "feed", message_ref="card-42")
    assert new_id
    rows = get_delivered_signals(signal_id="sig-1")
    assert any(r["channel"] == "feed" for r in rows)


def test_delivered_signals_invalid_channel(tmp_env):
    from hedwig.storage import save_delivered_signal
    assert save_delivered_signal("x", "telegram") is None


# --- G7 — cycle structured fields --------------------------------------

def test_save_cycle_log_with_scope(tmp_env):
    from hedwig.storage import get_cycle_logs, save_cycle_log
    save_cycle_log(
        cycle_type="weekly", cycle_number=4,
        scope="macro", axis="interpretation",
        inputs={"feedback_ids": [1, 2]},
        outputs={"new_style_id": "abc"},
        mutations_applied=["tone:technical"],
        fitness_before=0.5, fitness_after=0.6,
        analysis_summary="Switched tone",
        evaluator_verdict="adopt",
    )
    rows = get_cycle_logs(scope="macro")
    assert rows
    assert rows[0]["axis"] == "interpretation"
    assert rows[0]["inputs"] == {"feedback_ids": [1, 2]}
    assert rows[0]["mutations_applied"] == ["tone:technical"]


# --- G8 — exit_conditions ----------------------------------------------

def test_exit_conditions_returns_four(tmp_env):
    from hedwig.qa.exit_conditions import compute_exit_progress
    out = compute_exit_progress()
    names = [c["name"] for c in out]
    assert names == [
        "mvp_operational",
        "evolution_active",
        "weekly_loop_active",
        "user_satisfaction",
    ]
    for c in out:
        assert 0.0 <= c["progress"] <= 1.0


def test_status_page_renders(tmp_env):
    from hedwig.dashboard.app import create_app
    client = TestClient(create_app())
    resp = client.get("/status")
    assert resp.status_code == 200
    assert "exit conditions" in resp.text.lower()
    assert "mvp_operational" in resp.text


# --- G9 — principled fitness -------------------------------------------

def test_principled_fitness_returns_breakdown(tmp_env):
    from hedwig.dashboard.demo_seed import seed_demo
    seed_demo(reset=True)
    from hedwig.evolution.principled_fitness import compute_principled_fitness
    out = compute_principled_fitness()
    assert "weighted_total" in out
    names = {b["name"] for b in out["breakdown"]}
    assert {
        "signal_quality", "self_improvement", "interpretation_depth",
        "source_coverage", "opportunity_insight", "noise_reduction",
    } == names
    weights = sum(b["weight"] for b in out["breakdown"])
    assert abs(weights - 1.0) < 1e-3


def test_sandbox_includes_principled_block(tmp_env):
    from hedwig.dashboard.demo_seed import seed_demo
    seed_demo(reset=True)
    from hedwig.evolution.sandbox import run_sandbox
    out = run_sandbox(
        candidate_config={"ranking": {"components": {"a": {"enabled": True, "weight": 1.0}}}},
        baseline_config={"ranking": {"components": {"a": {"enabled": True, "weight": 1.0}}}},
    )
    assert "principled_fitness" in out
    assert out["principled_fitness"] is None or "weighted_total" in out["principled_fitness"]


# --- G10 — briefing structured fields ----------------------------------

def test_briefing_parser_extracts_sections():
    from hedwig.engine.briefing_parser import parse_briefing
    md = """# Daily Brief

### 🔴 즉시 주목
- Big alert one
- Big alert two

### 🟡 오늘의 주요 흐름
- Trend A appearing across HN + Reddit
- Trend B in academic

### 🎯 기회 포착 (Opportunity Notes)
- Build a wrapper
- Try the new API

### 💡 오늘의 인사이트
- Pattern: enterprise wants verticalized agents
"""
    out = parse_briefing(md)
    assert out["alerts"] == ["Big alert one", "Big alert two"]
    assert len(out["trend_patterns"]) == 2
    assert "Build a wrapper" in out["opportunity_hypotheses"]
    assert any("verticalized" in s for s in out["exploration_suggestions"])


def test_save_briefing_persists_structured(tmp_env):
    from hedwig.storage import get_briefings, save_briefing
    save_briefing(
        "daily",
        "### 🔴 Alerts\n- launch X\n\n### 🎯 Opportunity\n- ride trend Y",
        signal_count=3,
    )
    rows = get_briefings(cycle_type="daily")
    assert rows
    structured = rows[0].get("structured") or {}
    assert "launch X" in (structured.get("alerts") or [])
    assert "ride trend Y" in (structured.get("opportunity_hypotheses") or [])


def test_brief_page_renders_structured_section(tmp_env):
    from hedwig.dashboard.app import create_app
    from hedwig.storage import save_briefing
    save_briefing(
        "weekly",
        "### 🎯 기회 포착\n- WIN_OPPORTUNITY_MARKER\n\n### 🟡 흐름\n- WIN_TREND_MARKER",
        signal_count=10,
    )
    client = TestClient(create_app())
    resp = client.get("/brief?cycle=weekly")
    assert resp.status_code == 200
    assert "WIN_OPPORTUNITY_MARKER" in resp.text
    # New GeekNews-style headline+toggle layout
    assert "headline-card" in resp.text
    assert "기회 포착" in resp.text


# --- Misc — nav + status link ------------------------------------------

def test_nav_has_feed_and_status(tmp_env):
    from hedwig.dashboard.app import create_app
    client = TestClient(create_app())
    resp = client.get("/")
    assert 'href="/feed"' in resp.text
    assert 'href="/status"' in resp.text
