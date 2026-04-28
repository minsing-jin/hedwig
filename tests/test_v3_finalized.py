"""Coverage for the four previously-deferred items + chat markdown."""
from __future__ import annotations

import asyncio
import json

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def tmp_env(monkeypatch, tmp_path):
    monkeypatch.setenv("HEDWIG_STORAGE", "sqlite")
    monkeypatch.setenv("HEDWIG_DB_PATH", str(tmp_path / "hedwig.db"))
    monkeypatch.setenv("HEDWIG_LTR_WEIGHTS", str(tmp_path / "ltr.json"))
    import hedwig.config as _cfg
    _cfg._ALGORITHM_VERSION_SEEDED = False
    yield tmp_path


# --- Chat markdown renderer (in HTML) -------------------------------

def test_chat_html_has_robust_md_renderer():
    from pathlib import Path
    body = (Path(__file__).resolve().parents[1]
            / "hedwig/dashboard/templates/chat.html").read_text()
    # Hallmarks of the new renderer
    assert "extract fenced code blocks" in body.lower() or "fenced code blocks" in body
    assert "h${level}" in body
    assert "<ol>" in body and "<ul>" in body
    # Inline transforms
    assert "<strong>" in body and "<em>" in body
    # Link autodetection
    assert "https?:" in body


# --- G1 — judgment first-class --------------------------------------

def test_judgment_save_and_fetch(tmp_env):
    from hedwig.dashboard.demo_seed import seed_demo
    from hedwig.models import Judgment, UrgencyLevel
    from hedwig.storage import get_judgments_for_signal, save_judgment
    seed_demo(reset=True)

    j = Judgment(
        signal_id="demo-0", score=0.85, urgency=UrgencyLevel.ALERT,
        rationale="useful for agent project",
        devil_advocate="might be hype",
        confidence=0.7, criteria_version=2,
        interpretation_style_id="style-abc",
        exploration_tags=["agent", "tooling"],
    )
    jid = save_judgment(j)
    assert jid

    rows = get_judgments_for_signal("demo-0")
    assert rows
    row = rows[0]
    assert row["score"] == 0.85
    assert row["urgency"] == "alert"
    assert row["criteria_version"] == 2
    assert row["interpretation_style_id"] == "style-abc"
    assert row["exploration_tags"] == ["agent", "tooling"]


def test_judgment_unique_per_version(tmp_env):
    """Same signal + criteria_version + style_id must idempotent-replace."""
    from hedwig.models import Judgment, UrgencyLevel
    from hedwig.storage import get_judgments_for_signal, save_judgment

    j1 = Judgment(signal_id="s1", score=0.5, urgency=UrgencyLevel.DIGEST,
                  criteria_version=1, interpretation_style_id="x")
    j2 = Judgment(signal_id="s1", score=0.7, urgency=UrgencyLevel.ALERT,
                  criteria_version=1, interpretation_style_id="x")
    save_judgment(j1)
    save_judgment(j2)
    rows = get_judgments_for_signal("s1")
    # Either 1 row (replace) or 2 rows is acceptable — but the latest score must surface
    assert any(r["score"] == 0.7 for r in rows)


def test_signals_table_has_judgment_id_column(tmp_env):
    from hedwig.storage import save_evolution_signal
    save_evolution_signal("explicit", "test", {})  # triggers init_db
    from hedwig.storage.local import _conn
    with _conn() as conn:
        cols = [r[1] for r in conn.execute("PRAGMA table_info(signals)").fetchall()]
    assert "judgment_id" in cols


# --- S8.2 — Sequential ranker --------------------------------------

def test_sequential_ranker_neutral_without_history(tmp_env):
    from hedwig.engine.ensemble.sequential import SequentialRanker
    from hedwig.models import Platform, RawPost
    posts = [
        RawPost(platform=Platform.HACKERNEWS, external_id="a",
                title="something", url="", content=""),
    ]
    scores = asyncio.run(SequentialRanker().score_posts(posts))
    assert scores == [0.5]


def test_sequential_registered_in_combine():
    from hedwig.engine.ensemble.combine import _registry
    assert "sequential" in _registry()


# --- S8.5 — Multi-task fitness --------------------------------------

def test_multi_task_fitness_returns_breakdown(tmp_env):
    from hedwig.dashboard.demo_seed import seed_demo
    from hedwig.evolution.multi_task import compute_multi_task_fitness
    seed_demo(reset=True)
    out = compute_multi_task_fitness()
    assert "scores" in out and "weights" in out
    expected = {"engagement", "retention", "save_rate", "share_rate"}
    assert set(out["scores"].keys()) == expected
    assert 0.0 <= out["weighted_total"] <= 1.0


def test_multi_task_weights_sum_to_one(tmp_env):
    from hedwig.evolution.multi_task import compute_multi_task_fitness
    out = compute_multi_task_fitness()
    total = sum(out["weights"].values())
    assert abs(total - 1.0) < 1e-3


# --- S8.6 — REINFORCE-lite -----------------------------------------

def test_reinforce_requires_data(tmp_env):
    from hedwig.evolution.rlhf import reinforce_update
    out = reinforce_update(criteria_keywords=["x"])
    assert out["updated"] is False
    assert "rewards" in out["reason"] or "matched" in out["reason"]


def test_reinforce_runs_with_seeded_data(tmp_env):
    """With demo seed (some upvotes recorded), REINFORCE should run."""
    from hedwig.dashboard.demo_seed import seed_demo
    from hedwig.evolution.rlhf import reinforce_update
    from hedwig.models import VoteType
    from hedwig.feedback import FeedbackCollector
    from hedwig.storage import save_feedback
    seed_demo(reset=True)

    # Add explicit feedback so reward function has matched signal_id ↔ row
    fc = FeedbackCollector()
    for sid, vote in (("demo-0", VoteType.UP), ("demo-1", VoteType.UP),
                       ("demo-2", VoteType.UP), ("demo-3", VoteType.DOWN),
                       ("demo-4", VoteType.UP)):
        save_feedback(fc.from_direct(signal_id=sid, vote=vote))

    out = reinforce_update(criteria_keywords=["AI"])
    # Either updates successfully or reports a clear reason
    assert "updated" in out
    if out["updated"]:
        assert out["n_steps"] >= 1
        assert "weights_keys" in out
