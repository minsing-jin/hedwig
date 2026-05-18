from __future__ import annotations

import importlib
import sqlite3

import pytest
import yaml


def test_config_loads_criteria_from_one_shot_env_override(tmp_path, monkeypatch):
    from hedwig import config as config_mod

    criteria_path = tmp_path / "criteria.yaml"
    criteria_path.write_text(
        yaml.safe_dump({"context": {"interests": ["first feed criteria"]}}),
        encoding="utf-8",
    )

    monkeypatch.setenv("HEDWIG_CRITERIA_PATH", str(criteria_path))
    reloaded = importlib.reload(config_mod)

    try:
        assert reloaded.CRITERIA_PATH == criteria_path
        assert reloaded.load_criteria()["context"]["interests"] == [
            "first feed criteria"
        ]
    finally:
        monkeypatch.delenv("HEDWIG_CRITERIA_PATH", raising=False)
        importlib.reload(config_mod)


@pytest.mark.asyncio
async def test_initial_feed_run_applies_generated_criteria_when_strategy_has_no_keywords(
    tmp_path,
    monkeypatch,
):
    """First feed execution must apply setup-generated criteria.yaml keywords."""
    from hedwig import config as config_mod
    from hedwig import main as main_mod
    from hedwig.engine.ensemble import combine as combine_mod
    from hedwig.models import Platform, RawPost, ScoredSignal, UrgencyLevel
    import hedwig.storage as storage_mod

    interest = "robot policy research"
    criteria_path = tmp_path / "criteria.yaml"
    criteria_path.write_text(
        yaml.safe_dump(
            {
                "identity": {"role": "AI builder", "focus": [interest]},
                "signal_preferences": {
                    "care_about": [interest, "implementation details"],
                    "ignore": ["press releases"],
                },
                "urgency_rules": {
                    "alert": ["major policy shift"],
                    "digest": ["new research"],
                    "skip": ["generic hype"],
                },
                "context": {"interests": [interest]},
                "metadata": {"generated_by": "quickstart"},
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    post = RawPost(
        platform=Platform.HACKERNEWS,
        external_id="first-feed-post",
        title="Robotics policy paper",
        url="https://example.test/robot-policy",
    )
    captured: dict[str, object] = {}

    async def fake_agent_collect(llm_client=None):
        captured["agent_llm_present"] = llm_client is not None
        return [post], {"priority_sources": ["hackernews"], "focus_keywords": []}

    async def fail_collect_all(enabled_only: bool = True):
        raise AssertionError("agent first-run path should not fall back to baseline")

    async def fake_normalize_and_prescore(posts, criteria_keywords):
        captured["retrieval_keywords"] = list(criteria_keywords)
        return posts

    async def fake_rank_and_build_signals(posts, criteria_keywords):
        captured["ranking_keywords"] = list(criteria_keywords)
        return [
            ScoredSignal(
                raw=posts[0],
                relevance_score=0.3,
                urgency=UrgencyLevel.SKIP,
            )
        ], {
            "retrieval_kept": 1,
            "ranking_kept": 1,
            "top_k": 1,
            "components_used": [],
        }

    async def fake_run_evolution_daily():
        return None

    monkeypatch.setenv("HEDWIG_PIPELINE", "ensemble")
    monkeypatch.setattr(config_mod, "OPENAI_API_KEY", "sk-test")
    monkeypatch.setattr(config_mod, "CRITERIA_PATH", criteria_path)
    monkeypatch.setattr(config_mod, "check_optional_keys", lambda mode="full": [])
    monkeypatch.setattr(main_mod, "agent_collect", fake_agent_collect)
    monkeypatch.setattr(main_mod, "collect_all", fail_collect_all)
    monkeypatch.setattr(main_mod, "normalize_and_prescore", fake_normalize_and_prescore)
    monkeypatch.setattr(combine_mod, "rank_and_build_signals", fake_rank_and_build_signals)
    monkeypatch.setattr(main_mod, "run_evolution_daily", fake_run_evolution_daily)
    monkeypatch.setattr(
        storage_mod,
        "save_signals",
        lambda signals: captured.setdefault("saved_count", len(signals)) or len(signals),
        raising=False,
    )
    monkeypatch.setattr(storage_mod, "get_backend_name", lambda: "local", raising=False)

    await main_mod.run_daily()

    assert captured["agent_llm_present"] is True
    assert captured["retrieval_keywords"] == [
        interest,
        "implementation details",
        interest,
    ]
    assert captured["ranking_keywords"] == captured["retrieval_keywords"]
    assert captured["saved_count"] == 1


@pytest.mark.asyncio
async def test_initial_feed_run_writes_results_to_existing_local_sqlite_store(
    tmp_path,
    monkeypatch,
):
    """One-shot first-run completion must populate the local feed database."""
    from hedwig import config as config_mod
    from hedwig import main as main_mod
    from hedwig.engine.ensemble import combine as combine_mod
    from hedwig.models import Platform, RawPost, ScoredSignal, UrgencyLevel
    from hedwig.storage import local as local_storage

    db_path = tmp_path / "hedwig.db"
    criteria_path = tmp_path / "criteria.yaml"
    criteria_path.write_text(
        yaml.safe_dump(
            {
                "signal_preferences": {"care_about": ["local sqlite first feed"]},
                "context": {"interests": ["local sqlite first feed"]},
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setenv("HEDWIG_STORAGE", "sqlite")
    monkeypatch.setenv("HEDWIG_DB_PATH", str(db_path))
    monkeypatch.setenv("HEDWIG_PIPELINE", "ensemble")
    monkeypatch.setattr(config_mod, "OPENAI_API_KEY", "sk-local-feed")
    monkeypatch.setattr(config_mod, "CRITERIA_PATH", criteria_path)
    monkeypatch.setattr(config_mod, "check_optional_keys", lambda mode="full": [])
    local_storage.init_db()

    post = RawPost(
        platform=Platform.HACKERNEWS,
        external_id="sqlite-first-feed-post",
        title="SQLite first feed result",
        url="https://example.test/sqlite-first-feed",
        content="A result created by the one-shot first collection.",
    )

    async def fake_agent_collect(llm_client=None):
        return [post], {"priority_sources": ["hackernews"], "focus_keywords": []}

    async def fake_normalize_and_prescore(posts, criteria_keywords):
        return posts

    async def fake_rank_and_build_signals(posts, criteria_keywords):
        return [
            ScoredSignal(
                raw=posts[0],
                relevance_score=0.72,
                urgency=UrgencyLevel.SKIP,
                why_relevant="Matches local SQLite first-feed setup.",
            )
        ], {
            "retrieval_kept": 1,
            "ranking_kept": 1,
            "top_k": 1,
            "components_used": [],
        }

    async def fake_run_evolution_daily():
        return None

    monkeypatch.setattr(main_mod, "agent_collect", fake_agent_collect)
    monkeypatch.setattr(main_mod, "normalize_and_prescore", fake_normalize_and_prescore)
    monkeypatch.setattr(combine_mod, "rank_and_build_signals", fake_rank_and_build_signals)
    monkeypatch.setattr(main_mod, "run_evolution_daily", fake_run_evolution_daily)

    await main_mod.run_daily()

    with sqlite3.connect(db_path) as conn:
        row = conn.execute(
            """
            SELECT platform, external_id, title, url, relevance_score, urgency
            FROM signals
            WHERE external_id = ?
            """,
            ("sqlite-first-feed-post",),
        ).fetchone()
        progress_row = conn.execute(
            """
            SELECT status, posts_collected, posts_filtered, signals_scored,
                   signals_saved, errors, started_at, last_updated_at, completed_at
            FROM collection_runs
            ORDER BY last_updated_at DESC
            LIMIT 1
            """
        ).fetchone()

    assert row == (
        "hackernews",
        "sqlite-first-feed-post",
        "SQLite first feed result",
        "https://example.test/sqlite-first-feed",
        0.72,
        "skip",
    )
    assert progress_row[0] == "completed"
    assert progress_row[1:5] == (1, 1, 1, 1)
    assert progress_row[5] == "[]"
    assert progress_row[6]
    assert progress_row[7]
    assert progress_row[8]


@pytest.mark.asyncio
async def test_initial_feed_run_records_collection_errors_and_timestamps(
    tmp_path,
    monkeypatch,
):
    """Backend progress must preserve failed first-collection status and errors."""
    from hedwig import config as config_mod
    from hedwig import main as main_mod
    from hedwig.models import Platform, RawPost
    from hedwig.storage import local as local_storage

    db_path = tmp_path / "hedwig.db"
    criteria_path = tmp_path / "criteria.yaml"
    criteria_path.write_text(
        yaml.safe_dump(
            {
                "signal_preferences": {"care_about": ["progress errors"]},
                "context": {"interests": ["progress errors"]},
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setenv("HEDWIG_STORAGE", "sqlite")
    monkeypatch.setenv("HEDWIG_DB_PATH", str(db_path))
    monkeypatch.setattr(config_mod, "OPENAI_API_KEY", "")
    monkeypatch.setattr(config_mod, "CRITERIA_PATH", criteria_path)
    monkeypatch.setattr(config_mod, "check_required_keys", lambda mode="full": ["OPENAI_API_KEY"])
    local_storage.init_db()

    post = RawPost(
        platform=Platform.HACKERNEWS,
        external_id="progress-error-post",
        title="Progress error post",
        url="https://example.test/progress-error",
    )

    async def fake_collect_all(enabled_only: bool = True):
        return [post]

    async def fake_normalize_and_prescore(posts, criteria_keywords):
        return posts

    monkeypatch.setattr(main_mod, "collect_all", fake_collect_all)
    monkeypatch.setattr(main_mod, "normalize_and_prescore", fake_normalize_and_prescore)

    await main_mod.run_daily()

    progress = local_storage.get_latest_collection_progress("daily")
    assert progress["status"] == "failed"
    assert progress["posts_collected"] == 1
    assert progress["posts_filtered"] == 1
    assert progress["signals_saved"] == 0
    assert progress["errors"][0]["message"] == "Missing env vars: OPENAI_API_KEY"
    assert progress["started_at"]
    assert progress["last_updated_at"]
    assert progress["completed_at"]


def test_feed_api_exposes_latest_collection_progress(tmp_path, monkeypatch):
    """Feed clients can read backend first-collection progress with feed items."""
    from fastapi.testclient import TestClient

    from hedwig.dashboard.app import create_app
    from hedwig.models import Platform, RawPost, ScoredSignal, UrgencyLevel
    from hedwig.storage import local as local_storage

    db_path = tmp_path / "hedwig.db"
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HEDWIG_STORAGE", "sqlite")
    monkeypatch.setenv("HEDWIG_DB_PATH", str(db_path))
    local_storage.init_db()

    run_id = local_storage.start_collection_run(
        "daily",
        status="running",
        metadata={"source": "setup_one_shot"},
    )
    local_storage.update_collection_run(
        run_id,
        status="scored",
        counts={
            "posts_collected": 2,
            "posts_filtered": 1,
            "signals_scored": 1,
        },
    )
    signal = ScoredSignal(
        raw=RawPost(
            platform=Platform.HACKERNEWS,
            external_id="feed-progress-item",
            title="Feed progress item",
            url="https://example.test/feed-progress",
        ),
        relevance_score=0.8,
        urgency=UrgencyLevel.DIGEST,
    )
    local_storage.save_signals([signal])

    client = TestClient(create_app())
    payload = client.get("/feed/api?limit=5").json()

    assert payload["items"][0]["title"] == "Feed progress item"
    assert payload["collection_progress"]["status"] == "scored"
    assert payload["collection_progress"]["posts_collected"] == 2
    assert payload["collection_progress"]["posts_filtered"] == 1
    assert payload["collection_progress"]["signals_scored"] == 1
    assert payload["collection_progress"]["last_updated_at"]


def test_feed_api_exposes_feed_rows_before_setup_completion(tmp_path, monkeypatch):
    """Readable SQLite feed rows are not gated on setup_complete."""
    from fastapi.testclient import TestClient

    from hedwig.dashboard.app import create_app
    from hedwig.models import Platform, RawPost, ScoredSignal, UrgencyLevel
    from hedwig.storage import local as local_storage

    db_path = tmp_path / "hedwig.db"
    state_path = tmp_path / ".hedwig" / "setup_state.json"
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("HEDWIG_STORAGE", "sqlite")
    monkeypatch.setenv("HEDWIG_DB_PATH", str(db_path))
    monkeypatch.setenv("HEDWIG_SETUP_STATE_PATH", str(state_path))
    local_storage.init_db()
    local_storage.save_signals(
        [
            ScoredSignal(
                raw=RawPost(
                    platform=Platform.HACKERNEWS,
                    external_id="partial-readiness-feed-item",
                    title="Partial readiness feed item",
                    url="https://example.test/partial-readiness",
                ),
                relevance_score=0.86,
                urgency=UrgencyLevel.DIGEST,
            )
        ]
    )

    client = TestClient(create_app())
    payload = client.get("/feed/api?limit=5").json()
    setup_readiness = payload["setup_readiness"]

    assert payload["items"][0]["title"] == "Partial readiness feed item"
    assert setup_readiness["setup_complete"] is False
    assert setup_readiness["setup_status"] == "blocked"
    assert setup_readiness["requires_setup_complete"] is False
    assert setup_readiness["can_read_feed_data"] is True
    assert setup_readiness["feed_items_available"] is True
    assert setup_readiness["readable_feed_items"] == 1
    assert setup_readiness["partial_readiness"]["first_feed_ready"] is True
    assert setup_readiness["partial_readiness"]["can_open_feed"] is True
    assert "openai_api_key" in setup_readiness["blocking_requirement_ids"]
    assert not state_path.exists()
