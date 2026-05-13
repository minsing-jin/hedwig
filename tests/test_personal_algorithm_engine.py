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


def test_raw_events_and_rewards_are_separate(tmp_env):
    from hedwig.dashboard.app import create_app
    from hedwig.storage import get_behavior_events, get_behavior_rewards

    client = TestClient(create_app())
    resp = client.post("/events/beacon", json={"events": [
        {"signal_id": "1", "event_type": "save", "feed_mode": "grid"},
        {"signal_id": "1", "event_type": "dwell", "dwell_ms": 3000, "feed_mode": "detail_swipe"},
        {"signal_id": "1", "event_type": "not_interested", "feed_mode": "dense_reader"},
    ]})
    assert resp.status_code == 200
    assert resp.json()["saved"] == 3
    assert resp.json()["rewards"] == 3
    assert {row["event_type"] for row in get_behavior_events(signal_id="1")} == {"save", "dwell", "not_interested"}
    rewards = get_behavior_rewards(signal_id="1")
    assert {row["signal_strength"] for row in rewards} >= {"strong_positive", "weak_positive", "strong_negative"}


def test_swipe_defaults_and_policy_parser(tmp_env):
    from hedwig.onboarding.nl_algo_editor import propose_local_policy_edit
    from hedwig.personal_algorithm import get_personal_algorithm_policy, interpret_behavior_event

    policy = get_personal_algorithm_policy()
    assert policy["swipe_policy"]["left"]["action"] == "save_later"
    assert policy["swipe_policy"]["left"]["reward"] > 0
    assert policy["swipe_policy"]["right"]["action"] == "skip"
    assert policy["swipe_policy"]["right"]["reward"] <= 0
    assert interpret_behavior_event({"signal_id": "x", "event_type": "swipe_left"})["reward_value"] > 0
    assert interpret_behavior_event({"signal_id": "x", "event_type": "swipe_right"})["signal_strength"].startswith("weak")
    proposed = propose_local_policy_edit("make right skip neutral and show more agent papers")
    paths = {change["path"] for change in proposed["changes"]}
    assert "personal_algorithm.swipe_policy.right.reward" in paths
    assert any("preferences" in path for path in paths)


def test_feed_modes_exploration_delivery_and_metrics(tmp_env):
    from hedwig.dashboard.app import create_app
    from hedwig.dashboard.demo_seed import seed_demo
    from hedwig.storage import get_usage_metrics_by_mode, save_behavior_events_batch

    seed_demo(reset=True)
    client = TestClient(create_app())
    html = client.get("/feed").text
    assert 'data-mode="grid"' in html
    assert "Detail Swipe" in html
    assert "Dense Reader" in html
    assert "card_impression" in html
    assert "swipe_left" in html

    data = client.get("/feed/api?limit=20").json()
    assert data["items"]
    assert all("ensemble_score" in item for item in data["items"])
    assert all("delivery_policy" in item for item in data["items"])
    assert all("media_profile" in item for item in data["items"])
    explored = [item for item in data["items"] if item.get("is_exploration")]
    assert explored
    assert all(item.get("anomaly_label", {}).get("reason") for item in explored)

    save_behavior_events_batch([
        {"signal_id": "1", "event_type": "card_impression", "feed_mode": "grid"},
        {"signal_id": "2", "event_type": "viewed_card", "feed_mode": "detail_swipe"},
        {"signal_id": "3", "event_type": "open", "feed_mode": "dense_reader"},
    ])
    metrics = get_usage_metrics_by_mode()
    assert metrics["grid"]["card_impression"] == 1
    assert metrics["detail_swipe"]["viewed_card"] == 1
    assert metrics["dense_reader"]["open"] == 1
    assert client.get("/feed/metrics").json()["modes"]["grid"]["events"] >= 1


def test_shadow_fitness_media_and_rollback(tmp_env, monkeypatch):
    import shutil

    import hedwig.config as cfg
    import hedwig.onboarding.nl_algo_editor as nl_algo
    from hedwig.onboarding.nl_algo_editor import confirm_edit, restore_algorithm_version
    from hedwig.personal_algorithm import (
        composite_fitness,
        get_personal_algorithm_policy,
        media_profile_for_item,
        shadow_test_policy_edit,
    )

    fitness = composite_fitness(
        events=[
            {"event_type": "open", "feed_id": "a"},
            {"event_type": "save", "feed_id": "b"},
            {"event_type": "skip", "feed_id": "a"},
            {"event_type": "dwell", "dwell_ms": 5000, "feed_id": "a"},
        ],
        rewards=[{"reward_value": 1.0}],
    )
    assert set(fitness["signals"]) == {"upvote", "save", "open", "dwell", "skip", "diversity"}
    shadow = shadow_test_policy_edit([{"op": "set", "path": "reward_weights.skip", "value": -0.5}], "make skips stronger")
    assert shadow["shadow_test"] is True
    assert "composite_fitness" in shadow

    assert media_profile_for_item({"title": "x"})["strategy"] == "text_thumbnail_transcript"
    monkeypatch.setenv("HEDWIG_FULL_MEDIA_UNDERSTANDING", "1")
    assert get_personal_algorithm_policy()["media"]["full_understanding_enabled"] is True

    temp_algorithm = tmp_env / "algorithm.yaml"
    shutil.copy2(cfg.ALGORITHM_PATH, temp_algorithm)
    monkeypatch.setattr(cfg, "ALGORITHM_PATH", temp_algorithm)
    monkeypatch.setattr(nl_algo, "ALGORITHM_PATH", temp_algorithm)
    cfg._ALGORITHM_VERSION_SEEDED = False

    applied = confirm_edit([{"op": "set", "path": "personal_algorithm.feed.default_mode", "value": "dense_reader"}], intent="dense")
    assert applied["ok"]
    restored = restore_algorithm_version(1)
    assert restored["ok"]
