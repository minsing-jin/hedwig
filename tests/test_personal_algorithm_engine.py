from __future__ import annotations

import copy

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
    assert all(row["derivation_rule_version"] == "personal_algorithm_reward_v1" for row in rewards)
    assert any(row["source_event_ids"] for row in rewards)
    assert {row["polarity"] for row in rewards} >= {"positive", "negative"}


def test_delivery_events_use_separate_reward_derivation_path(tmp_env):
    from hedwig.dashboard.app import create_app
    from hedwig.delivery.ambient import (
        AMBIENT_DELIVERY_REWARD_RULE_VERSION,
        ambient_delivery_reward_mapping,
        interpret_ambient_delivery_event,
    )
    from hedwig.personal_algorithm import interpret_behavior_event
    from hedwig.storage import get_behavior_events, get_behavior_rewards

    client = TestClient(create_app())
    resp = client.post("/events/beacon", json={"events": [
        {"signal_id": "feed-1", "event_type": "open", "feed_mode": "grid"},
        {
            "signal_id": "ambient-1",
            "event_type": "delivered",
            "feed_id": "ambient:daily",
            "feed_mode": "ambient_daily",
            "ambient_surface": "daily",
            "raw_delivery_event": True,
        },
        {
            "signal_id": "ambient-1",
            "event_type": "opened",
            "feed_id": "ambient:daily",
            "feed_mode": "ambient_daily",
            "ambient_surface": "daily",
            "raw_delivery_event": True,
        },
        {
            "signal_id": "ambient-2",
            "event_type": "dismissed",
            "feed_id": "ambient:tray",
            "feed_mode": "ambient_tray",
            "delivery_surface": "tray",
            "raw_delivery_event": True,
        },
    ]})

    assert resp.status_code == 200
    assert resp.json()["saved"] == 4
    assert resp.json()["feed_rewards"] == 1
    assert resp.json()["delivery_rewards"] == 2
    assert resp.json()["rewards"] == 3

    ambient_events = get_behavior_events(event_types=["delivered", "opened", "dismissed"])
    assert {row["event_type"] for row in ambient_events} == {"delivered", "opened", "dismissed"}
    assert all(row["feed_mode"].startswith("ambient_") for row in ambient_events)

    rewards = get_behavior_rewards(limit=10)
    feed_rewards = [row for row in rewards if row["source"] == "personal_algorithm"]
    delivery_rewards = [row for row in rewards if row["source"] == "ambient_delivery"]
    assert [row["event_type"] for row in feed_rewards] == ["open"]
    assert {row["event_type"] for row in delivery_rewards} == {"opened", "dismissed"}
    assert all(row["derivation_rule_version"] == AMBIENT_DELIVERY_REWARD_RULE_VERSION for row in delivery_rewards)
    assert all(row["feed_mode"].startswith("ambient_") for row in delivery_rewards)
    assert all(row["source_event_ids"] for row in delivery_rewards)
    assert {row["polarity"] for row in delivery_rewards} == {"positive", "negative"}

    raw_delivery_event = {
        "signal_id": "ambient-direct",
        "event_type": "opened",
        "feed_id": "ambient:pwa",
        "feed_mode": "ambient_pwa",
        "raw_delivery_event": True,
    }
    assert interpret_behavior_event(raw_delivery_event) is None
    assert interpret_ambient_delivery_event(raw_delivery_event)["source"] == "ambient_delivery"
    assert interpret_ambient_delivery_event({
        "signal_id": "ambient-direct",
        "event_type": "delivered",
        "feed_id": "ambient:pwa",
        "feed_mode": "ambient_pwa",
        "raw_delivery_event": True,
    }) is None

    mapping = ambient_delivery_reward_mapping()
    assert set(mapping) == {"delivered", "opened", "dismissed", "snoozed", "saved", "clicked"}
    assert mapping["delivered"] is None

    expected_polarities = {
        "opened": "positive",
        "clicked": "positive",
        "saved": "positive",
        "dismissed": "negative",
        "snoozed": "negative",
    }
    for event_type, polarity in expected_polarities.items():
        reward = interpret_ambient_delivery_event({
            "id": 900 + len(event_type),
            "signal_id": f"ambient-{event_type}",
            "event_type": event_type,
            "feed_id": "ambient:daily",
            "feed_mode": "ambient_daily",
            "raw_delivery_event": True,
            "ensemble_score": 0.99,
            "final_score": 0.98,
            "pre_layer_ranking": {"input_rank": 1},
        })
        assert reward is not None
        assert reward["reward_value"] == mapping[event_type]["reward_value"]
        assert reward["signal_strength"] == mapping[event_type]["signal_strength"]
        assert reward["polarity"] == polarity
        assert reward["source"] == "ambient_delivery"
        assert reward["derivation_rule_version"] == AMBIENT_DELIVERY_REWARD_RULE_VERSION
        assert {
            "ensemble_score",
            "final_score",
            "pre_layer_ranking",
            "ranking_snapshot",
        }.isdisjoint(reward)


def test_delivery_events_and_rewards_persist_as_distinct_records(tmp_env):
    from hedwig.dashboard.app import create_app
    from hedwig.delivery.ambient import AMBIENT_DELIVERY_REWARD_RULE_VERSION
    from hedwig.storage import get_behavior_events, get_behavior_rewards

    client = TestClient(create_app())
    resp = client.post("/events/beacon", json={"events": [
        {
            "signal_id": "ambient-record-boundary",
            "event_type": "delivered",
            "feed_id": "ambient:critical",
            "feed_mode": "ambient_critical",
            "delivery_surface": "critical",
            "raw_delivery_event": True,
        },
        {
            "signal_id": "ambient-record-boundary",
            "event_type": "opened",
            "feed_id": "ambient:critical",
            "feed_mode": "ambient_critical",
            "delivery_surface": "critical",
            "raw_delivery_event": True,
        },
        {
            "signal_id": "ambient-record-boundary",
            "event_type": "saved",
            "feed_id": "ambient:critical",
            "feed_mode": "ambient_critical",
            "delivery_surface": "critical",
            "raw_delivery_event": True,
        },
    ]})

    assert resp.status_code == 200
    assert resp.json()["saved"] == 3
    assert resp.json()["delivery_rewards"] == 2
    assert resp.json()["feed_rewards"] == 0

    raw_events = get_behavior_events(signal_id="ambient-record-boundary")
    raw_events_by_type = {row["event_type"]: row for row in raw_events}
    assert set(raw_events_by_type) == {"delivered", "opened", "saved"}
    assert all(isinstance(row["id"], int) for row in raw_events)
    assert all("reward_value" not in row for row in raw_events)

    rewards = get_behavior_rewards(signal_id="ambient-record-boundary")
    rewards_by_type = {row["event_type"]: row for row in rewards}
    assert set(rewards_by_type) == {"opened", "saved"}
    assert all(row["source"] == "ambient_delivery" for row in rewards)
    assert all(row["derivation_rule_version"] == AMBIENT_DELIVERY_REWARD_RULE_VERSION for row in rewards)

    for event_type, reward in rewards_by_type.items():
        raw_event_id = raw_events_by_type[event_type]["id"]
        assert reward["raw_event_id"] == raw_event_id
        assert reward["source_event_ids"] == [raw_event_id]
        assert reward["id"] != raw_event_id


def test_ambient_delivery_events_do_not_create_feedback_records(tmp_env):
    from hedwig.dashboard.app import create_app
    from hedwig.delivery.ambient import AMBIENT_DELIVERY_REWARD_RULE_VERSION
    from hedwig.storage import get_behavior_events, get_behavior_rewards
    from hedwig.storage.local import _conn

    client = TestClient(create_app())
    resp = client.post("/events/beacon", json={"events": [
        {
            "signal_id": "ambient-feedback-boundary",
            "event_type": "delivered",
            "feed_id": "ambient:daily",
            "feed_mode": "ambient_daily",
            "delivery_surface": "daily",
            "raw_delivery_event": True,
        },
        {
            "signal_id": "ambient-feedback-boundary",
            "event_type": "opened",
            "feed_id": "ambient:daily",
            "feed_mode": "ambient_daily",
            "delivery_surface": "daily",
            "raw_delivery_event": True,
        },
    ]})

    assert resp.status_code == 200
    assert resp.json()["saved"] == 2
    assert resp.json()["delivery_rewards"] == 1
    assert resp.json()["feed_rewards"] == 0

    with _conn() as conn:
        feedback_rows = conn.execute(
            "SELECT * FROM feedback WHERE signal_id = ?",
            ("ambient-feedback-boundary",),
        ).fetchall()
    assert feedback_rows == []

    raw_events = get_behavior_events(signal_id="ambient-feedback-boundary")
    rewards = get_behavior_rewards(signal_id="ambient-feedback-boundary")
    assert {row["event_type"] for row in raw_events} == {"delivered", "opened"}
    assert [row["event_type"] for row in rewards] == ["opened"]
    assert rewards[0]["source"] == "ambient_delivery"
    assert rewards[0]["derivation_rule_version"] == AMBIENT_DELIVERY_REWARD_RULE_VERSION

    feedback_resp = client.post("/feedback/ambient-feedback-boundary/up")
    assert feedback_resp.status_code == 200

    with _conn() as conn:
        feedback_rows = conn.execute(
            "SELECT signal_id, vote FROM feedback WHERE signal_id = ?",
            ("ambient-feedback-boundary",),
        ).fetchall()
    assert [dict(row) for row in feedback_rows] == [
        {"signal_id": "ambient-feedback-boundary", "vote": "up"}
    ]

    rewards_after_feedback = get_behavior_rewards(signal_id="ambient-feedback-boundary")
    assert rewards_after_feedback == rewards


def test_derived_delivery_rewards_reference_originating_delivery_events(tmp_env):
    from hedwig.dashboard.app import create_app
    from hedwig.delivery.ambient import AMBIENT_DELIVERY_REWARD_RULE_VERSION
    from hedwig.storage import get_behavior_events, get_behavior_rewards

    client = TestClient(create_app())
    resp = client.post("/events/beacon", json={"events": [
        {
            "signal_id": "ambient-reward-lineage",
            "event_type": "delivered",
            "feed_id": "ambient:daily",
            "feed_mode": "ambient_daily",
            "ambient_surface": "daily",
            "raw_delivery_event": True,
        },
        {
            "signal_id": "ambient-reward-lineage",
            "event_type": "opened",
            "feed_id": "ambient:daily",
            "feed_mode": "ambient_daily",
            "ambient_surface": "daily",
            "raw_delivery_event": True,
        },
        {
            "signal_id": "ambient-reward-lineage",
            "event_type": "clicked",
            "feed_id": "ambient:daily",
            "feed_mode": "ambient_daily",
            "ambient_surface": "daily",
            "raw_delivery_event": True,
        },
        {
            "signal_id": "ambient-reward-lineage",
            "event_type": "dismissed",
            "feed_id": "ambient:daily",
            "feed_mode": "ambient_daily",
            "ambient_surface": "daily",
            "raw_delivery_event": True,
        },
    ]})

    assert resp.status_code == 200
    assert resp.json()["saved"] == 4
    assert resp.json()["delivery_rewards"] == 3
    assert resp.json()["feed_rewards"] == 0

    raw_events = get_behavior_events(signal_id="ambient-reward-lineage")
    raw_events_by_id = {row["id"]: row for row in raw_events}
    delivered_event_id = next(row["id"] for row in raw_events if row["event_type"] == "delivered")

    rewards = get_behavior_rewards(signal_id="ambient-reward-lineage")
    assert {row["event_type"] for row in rewards} == {"opened", "clicked", "dismissed"}
    assert {row["raw_event_id"] for row in rewards}.isdisjoint({delivered_event_id})
    assert {row["raw_event_id"] for row in rewards}.issubset(raw_events_by_id)

    for reward in rewards:
        origin = raw_events_by_id[reward["raw_event_id"]]
        assert reward["source"] == "ambient_delivery"
        assert reward["derivation_rule_version"] == AMBIENT_DELIVERY_REWARD_RULE_VERSION
        assert reward["source_event_ids"] == [origin["id"]]
        assert reward["event_type"] == origin["event_type"]
        assert reward["signal_id"] == origin["signal_id"]
        assert reward["feed_mode"] == origin["feed_mode"]
        assert reward["id"] != origin["id"]


def test_supported_delivery_behavior_events_are_rewarded_only_by_ambient_path(tmp_env):
    from hedwig.dashboard.app import create_app
    from hedwig.delivery.ambient import AMBIENT_DELIVERY_REWARD_RULE_VERSION
    from hedwig.storage import get_behavior_events, get_behavior_rewards

    supported_events = ["delivered", "opened", "clicked", "saved", "dismissed", "snoozed"]
    client = TestClient(create_app())
    resp = client.post("/events/beacon", json={"events": [
        {
            "signal_id": f"ambient-supported-{event_type}",
            "event_type": event_type,
            "feed_id": "ambient:daily",
            "feed_mode": "ambient_daily",
            "ambient_surface": "daily",
            "raw_delivery_event": True,
        }
        for event_type in supported_events
    ]})

    assert resp.status_code == 200
    assert resp.json()["saved"] == len(supported_events)
    assert resp.json()["feed_rewards"] == 0
    assert resp.json()["delivery_rewards"] == 5
    assert resp.json()["rewards"] == 5

    stored_events = get_behavior_events(event_types=supported_events)
    assert {row["event_type"] for row in stored_events} == set(supported_events)
    assert all(row["feed_id"] == "ambient:daily" for row in stored_events)
    assert all(row["feed_mode"] == "ambient_daily" for row in stored_events)

    rewards = get_behavior_rewards(limit=10)
    assert {row["event_type"] for row in rewards} == {
        "opened",
        "clicked",
        "saved",
        "dismissed",
        "snoozed",
    }
    assert all(row["source"] == "ambient_delivery" for row in rewards)
    assert all(row["derivation_rule_version"] == AMBIENT_DELIVERY_REWARD_RULE_VERSION for row in rewards)
    assert all(row["raw_event_id"] in row["source_event_ids"] for row in rewards)
    assert all(row["feed_mode"] == "ambient_daily" for row in rewards)


def test_ambient_marked_ignored_events_do_not_enter_existing_reward_paths(tmp_env):
    from hedwig.dashboard.app import create_app
    from hedwig.delivery.ambient import interpret_ambient_delivery_event, is_ambient_delivery_event
    from hedwig.storage import get_behavior_events, get_behavior_rewards, get_evolution_signals

    feed_save = {"signal_id": "feed-save", "event_type": "save", "feed_mode": "grid"}
    ambient_legacy_save = {
        "signal_id": "ambient-legacy-save",
        "event_type": "save",
        "feed_id": "ambient:pwa",
        "feed_mode": "ambient_pwa",
        "raw_delivery_event": True,
    }
    ambient_view_start = {
        "signal_id": "ambient-view-start",
        "event_type": "view_start",
        "feed_id": "ambient:tray",
        "feed_mode": "ambient_tray",
        "delivery_surface": "tray",
    }
    ambient_delivered = {
        "signal_id": "ambient-delivered-only",
        "event_type": "delivered",
        "feed_id": "ambient:critical",
        "feed_mode": "ambient_critical",
        "raw_delivery_event": True,
    }
    stray_opened = {"signal_id": "stray-opened", "event_type": "opened", "feed_mode": "grid"}

    assert is_ambient_delivery_event(ambient_legacy_save) is True
    assert interpret_ambient_delivery_event(ambient_legacy_save) is None
    assert interpret_ambient_delivery_event(ambient_view_start) is None
    assert interpret_ambient_delivery_event(ambient_delivered) is None

    client = TestClient(create_app())
    resp = client.post("/events/beacon", json={"events": [
        feed_save,
        ambient_legacy_save,
        ambient_view_start,
        ambient_delivered,
        stray_opened,
    ]})

    assert resp.status_code == 200
    assert resp.json()["saved"] == 5
    assert resp.json()["feed_rewards"] == 1
    assert resp.json()["delivery_rewards"] == 0
    assert resp.json()["rewards"] == 1

    for signal_id in (
        "ambient-legacy-save",
        "ambient-view-start",
        "ambient-delivered-only",
        "stray-opened",
    ):
        assert get_behavior_events(signal_id=signal_id)
        assert get_behavior_rewards(signal_id=signal_id) == []

    feed_rewards = get_behavior_rewards(signal_id="feed-save")
    assert len(feed_rewards) == 1
    assert feed_rewards[0]["event_type"] == "save"
    assert feed_rewards[0]["source"] == "personal_algorithm"

    evolution_signals = get_evolution_signals(channel="implicit")
    assert [row["kind"] for row in evolution_signals] == ["behavior_save"]
    assert evolution_signals[0]["payload"]["signal_id"] == "feed-save"


def test_delivery_reward_events_cannot_smuggle_ranking_boundary_fields(tmp_env):
    from hedwig.dashboard.app import create_app
    from hedwig.delivery.ambient import (
        AMBIENT_DELIVERY_REWARD_RULE_VERSION,
        ambient_delivery_events,
        interpret_ambient_delivery_event,
    )
    from hedwig.personal_algorithm import interpret_behavior_event
    from hedwig.storage import get_behavior_events, get_behavior_rewards, get_evolution_signals

    ranked_item = {
        "id": "ambient-boundary-ranked",
        "title": "Already ranked ambient item",
        "ensemble_score": 0.91,
        "final_score": 0.90,
        "ensemble_rank": 1,
        "pre_layer_ranking": {
            "ensemble_score": 0.91,
            "final_score": 0.90,
            "input_rank": 1,
            "input_order": 0,
            "rank_identifiers": {"ranking_run_id": "pr18-gen9", "rank_slot": "slot-1"},
            "immutable": True,
        },
        "delivery_decision": {
            "surface": "critical",
            "ranking_snapshot": {
                "input_ensemble_score": 0.91,
                "input_final_score": 0.90,
                "input_ensemble_rank": 1,
                "input_order": 0,
                "rank_identifiers": {"ranking_run_id": "pr18-gen9", "rank_slot": "slot-1"},
                "immutable": True,
            },
            "explanation": {
                "text": "Display-only context.",
                "display_only": True,
                "ranking_input": False,
                "score_like_authority": False,
            },
        },
    }

    server_events = ambient_delivery_events(
        {"surface": "critical", "items": [ranked_item]},
        event_type="opened",
    )
    assert server_events == [{
        "signal_id": "ambient-boundary-ranked",
        "event_type": "opened",
        "position_in_feed": 0,
        "feed_id": "ambient:critical",
        "feed_mode": "ambient_critical",
        "device": "server_api",
    }]
    assert {
        "ensemble_score",
        "final_score",
        "pre_layer_ranking",
        "ranking_snapshot",
        "delivery_decision",
    }.isdisjoint(server_events[0])

    spoofed_ambient_events = [
        {
            "signal_id": "ambient-spoof-open",
            "event_type": "open",
            "feed_id": "ambient:critical",
            "feed_mode": "ambient_critical",
            "raw_delivery_event": True,
            "ensemble_score": 1.0,
            "final_score": 1.0,
            "pre_layer_ranking": {"input_rank": 1, "input_order": 0},
        },
        {
            "signal_id": "ambient-spoof-saved",
            "event_type": "saved",
            "feed_id": "ambient:critical",
            "feed_mode": "ambient_critical",
            "raw_delivery_event": True,
            "ensemble_score": 999.0,
            "final_score": 999.0,
            "ranking_snapshot": {"input_ensemble_score": 999.0, "input_final_score": 999.0},
            "pre_layer_ranking": {"input_rank": -1, "input_order": -1},
        },
    ]

    assert interpret_behavior_event(spoofed_ambient_events[0])["source"] == "personal_algorithm"
    assert interpret_ambient_delivery_event(spoofed_ambient_events[0]) is None
    delivery_reward = interpret_ambient_delivery_event(spoofed_ambient_events[1])
    assert delivery_reward["source"] == "ambient_delivery"
    assert {
        "ensemble_score",
        "final_score",
        "pre_layer_ranking",
        "ranking_snapshot",
        "delivery_decision",
        "input_ensemble_score",
        "input_final_score",
    }.isdisjoint(delivery_reward)

    client = TestClient(create_app())
    resp = client.post("/events/beacon", json={"events": spoofed_ambient_events + server_events})

    assert resp.status_code == 200
    assert resp.json()["saved"] == 3
    assert resp.json()["feed_rewards"] == 0
    assert resp.json()["delivery_rewards"] == 2
    assert resp.json()["rewards"] == 2

    for signal_id in ("ambient-spoof-open", "ambient-spoof-saved", "ambient-boundary-ranked"):
        stored_events = get_behavior_events(signal_id=signal_id)
        assert len(stored_events) == 1
        assert {
            "ensemble_score",
            "final_score",
            "pre_layer_ranking",
            "ranking_snapshot",
            "delivery_decision",
        }.isdisjoint(stored_events[0])

    assert get_behavior_rewards(signal_id="ambient-spoof-open") == []

    stored_rewards = (
        get_behavior_rewards(signal_id="ambient-spoof-saved")
        + get_behavior_rewards(signal_id="ambient-boundary-ranked")
    )
    assert {row["event_type"] for row in stored_rewards} == {"saved", "opened"}
    assert all(row["source"] == "ambient_delivery" for row in stored_rewards)
    assert all(row["derivation_rule_version"] == AMBIENT_DELIVERY_REWARD_RULE_VERSION for row in stored_rewards)
    for reward in stored_rewards:
        assert reward["raw_event_id"] in reward["source_event_ids"]
        assert {
            "ensemble_score",
            "final_score",
            "pre_layer_ranking",
            "ranking_snapshot",
            "delivery_decision",
            "input_ensemble_score",
            "input_final_score",
        }.isdisjoint(reward)

    assert get_evolution_signals(channel="implicit") == []


def test_swipe_defaults_and_policy_parser(tmp_env):
    from hedwig.onboarding.nl_algo_editor import propose_local_policy_edit
    from hedwig.personal_algorithm import classify_policy_edit, get_personal_algorithm_policy, interpret_behavior_event

    policy = get_personal_algorithm_policy()
    assert policy["swipe_policy"]["immutable_defaults"]["left"]["action"] == "save_later"
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
    assert proposed["risk_class"] == "risky_post_ranking"
    safe = classify_policy_edit([{"op": "set", "path": "personal_algorithm.feed.default_mode", "value": "grid"}], "use grid")
    assert safe["risk_class"] == "safe"
    future = propose_local_policy_edit("use composite fitness optimization to replace ranking")
    assert future["risk_class"] == "future_ranking_experimental"


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
    assert all("final_score" in item for item in data["items"])
    assert all(item["pre_layer_ranking"]["immutable"] for item in data["items"])
    assert all("delivery_policy" in item for item in data["items"])
    assert all(item["delivery_policy"]["does_not_mutate_ensemble"] for item in data["items"])
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
    assert metrics["grid"]["normalized_rates"]["card_impression"]["per_impression_rate"] == 1.0
    assert client.get("/feed/metrics").json()["modes"]["grid"]["events"] >= 1


def test_delivery_decision_metadata_is_post_ranking_schema(tmp_env):
    from hedwig.models import DeliveryDecisionMetadata, Judgment, Platform, RawPost, ScoredSignal, UrgencyLevel
    from hedwig.personal_algorithm import route_items_after_ranking

    forbidden_delivery_fields = {
        "delivery",
        "delivery_channel",
        "delivery_decision",
        "delivery_policy",
        "delivery_surface",
        "delivery_timing",
        "post_ranking_decisions",
        "surface",
    }
    ranking_input_fields = set(RawPost.model_fields)
    ranking_output_fields = set(ScoredSignal.model_fields) | set(Judgment.model_fields)
    assert forbidden_delivery_fields.isdisjoint(ranking_input_fields)
    assert forbidden_delivery_fields.isdisjoint(ranking_output_fields)
    assert forbidden_delivery_fields.isdisjoint(RawPost.model_json_schema()["properties"])
    assert forbidden_delivery_fields.isdisjoint(ScoredSignal.model_json_schema()["properties"])
    assert forbidden_delivery_fields.isdisjoint(Judgment.model_json_schema()["properties"])

    raw_with_delivery_extra = RawPost.model_validate({
        "platform": Platform.CUSTOM,
        "external_id": "raw-extra",
        "title": "Raw ranking candidate",
        "url": "https://example.test/raw",
        "delivery_decision": {"surface": "critical"},
    })
    signal_with_delivery_extra = ScoredSignal.model_validate({
        "raw": raw_with_delivery_extra,
        "relevance_score": 0.8,
        "urgency": UrgencyLevel.ALERT,
        "delivery_policy": {"surface": "daily"},
        "post_ranking_decisions": {"delivery": {"surface": "daily"}},
    })
    assert forbidden_delivery_fields.isdisjoint(raw_with_delivery_extra.model_dump())
    assert forbidden_delivery_fields.isdisjoint(signal_with_delivery_extra.model_dump())

    ranked = [{
        "id": "sig-1",
        "title": "Important item",
        "ensemble_score": 0.91,
        "final_score": 0.88,
        "ensemble_rank": 3,
        "urgency": "alert",
    }]
    routed = route_items_after_ranking(ranked)
    item = routed[0]
    decision = item["delivery_decision"]

    DeliveryDecisionMetadata.model_validate(decision)
    assert item["ensemble_score"] == 0.91
    assert item["final_score"] == 0.88
    assert item["pre_layer_ranking"]["input_rank"] == 3
    assert forbidden_delivery_fields.isdisjoint(item["pre_layer_ranking"])
    assert decision["decision_layer"] == "post_ranking_delivery"
    assert decision["post_ranking"] is True
    assert decision["ranking_input"] is False
    assert decision["ranking_output"] is False
    assert decision["does_not_mutate_ensemble"] is True
    assert decision["ranking_snapshot"] == {
        "input_ensemble_rank": 3,
        "input_order": 0,
        "rank_identifiers": {"id": "sig-1", "ensemble_rank": 3},
        "input_ensemble_score": 0.91,
        "input_final_score": 0.88,
        "immutable": True,
    }
    assert decision["explanation"]["display_only"] is True
    assert decision["explanation"]["ranking_input"] is False
    assert decision["explanation"]["score_like_authority"] is False


def test_delivery_decision_fields_only_populated_after_ranking_completion(tmp_env):
    from hedwig.personal_algorithm import apply_exploration_layer, choose_delivery, route_items_after_ranking

    raw_like_item = [{
        "id": "raw-1",
        "title": "Raw item has no completed-ranking output",
        "score": 120,
        "urgency": "alert",
    }]
    with pytest.raises(ValueError, match="completed ranking output"):
        route_items_after_ranking(raw_like_item)
    with pytest.raises(ValueError, match="completed ranking output"):
        choose_delivery(raw_like_item[0])

    explored = apply_exploration_layer([{
        "id": "ranked-1",
        "title": "Ranked item",
        "ensemble_score": 0.72,
        "final_score": 0.70,
        "ensemble_rank": 1,
    }])
    assert "delivery_policy" not in explored[0]
    assert "delivery_decision" not in explored[0]
    assert "delivery" not in explored[0].get("post_ranking_decisions", {})

    routed = route_items_after_ranking([{
        "id": "ranked-1",
        "title": "Ranked item",
        "ensemble_score": 0.72,
        "final_score": 0.70,
        "ensemble_rank": 1,
    }])
    assert "delivery_policy" in routed[0]
    assert "delivery_decision" in routed[0]
    assert "delivery" in routed[0]["post_ranking_decisions"]


def test_delivery_processing_copies_read_only_score_fields(tmp_env):
    from hedwig.personal_algorithm import route_items_after_ranking

    ranked = [{
        "id": "score-boundary",
        "title": "Canonical scores must win",
        "score": 999,
        "relevance_score": 999,
        "ensemble_score": 0.0,
        "final_score": 0.0,
        "ensemble_rank": 7,
        "urgency": "digest",
    }]

    routed = route_items_after_ranking(ranked)

    assert ranked[0]["ensemble_score"] == 0.0
    assert ranked[0]["final_score"] == 0.0
    assert routed[0]["ensemble_score"] == ranked[0]["ensemble_score"]
    assert routed[0]["final_score"] == ranked[0]["final_score"]
    assert routed[0]["pre_layer_ranking"]["ensemble_score"] == ranked[0]["ensemble_score"]
    assert routed[0]["pre_layer_ranking"]["final_score"] == ranked[0]["final_score"]
    assert routed[0]["delivery_decision"]["ranking_snapshot"]["input_ensemble_score"] == ranked[0]["ensemble_score"]
    assert routed[0]["delivery_decision"]["ranking_snapshot"]["input_final_score"] == ranked[0]["final_score"]


def test_delivery_decision_logic_preserves_existing_ranking_scores_exactly(tmp_env):
    from hedwig.personal_algorithm import (
        assert_delivery_scores_unchanged,
        choose_delivery,
        route_items_after_ranking,
    )

    ranked = [{
        "id": "exact-score-boundary",
        "title": "Delivery routing must not reinterpret scores",
        "score": 10_000,
        "relevance_score": 10_000,
        "ensemble_score": 0.654321987654,
        "final_score": 0.654321987653,
        "ensemble_rank": 4,
        "urgency": "digest",
    }]
    before = [dict(ranked[0])]

    decision = choose_delivery(ranked[0])
    routed = route_items_after_ranking(ranked)

    assert ranked == before
    assert routed[0]["ensemble_score"] == before[0]["ensemble_score"]
    assert routed[0]["final_score"] == before[0]["final_score"]
    assert routed[0]["delivery_decision"]["ranking_snapshot"]["input_ensemble_score"] == before[0]["ensemble_score"]
    assert routed[0]["delivery_decision"]["ranking_snapshot"]["input_final_score"] == before[0]["final_score"]
    assert decision["ranking_snapshot"]["input_ensemble_score"] == before[0]["ensemble_score"]
    assert decision["ranking_snapshot"]["input_final_score"] == before[0]["final_score"]

    mutated = [dict(routed[0], ensemble_score=round(routed[0]["ensemble_score"], 2))]
    with pytest.raises(ValueError, match="score mutation detected"):
        assert_delivery_scores_unchanged(before, mutated)

    mutated = [dict(routed[0], final_score=round(routed[0]["final_score"], 2))]
    with pytest.raises(ValueError, match="score mutation detected"):
        assert_delivery_scores_unchanged(before, mutated)


def test_delivery_processing_preserves_pre_layer_rank_identity(tmp_env):
    from hedwig.personal_algorithm import choose_delivery, route_items_after_ranking

    ranked = [
        {
            "id": "ranked-b",
            "title": "Second in pre-layer ordering",
            "ensemble_score": 0.70,
            "final_score": 0.70,
            "ensemble_rank": 20,
            "feed_position": 1,
            "urgency": "digest",
            "pre_layer_ranking": {
                "input_rank": 20,
                "input_order": 1,
                "rank_identifiers": {"ranking_run_id": "run-42", "rank_slot": "slot-b"},
                "immutable": True,
            },
        },
        {
            "id": "ranked-a",
            "title": "First in pre-layer ordering",
            "ensemble_score": 0.90,
            "final_score": 0.90,
            "ensemble_rank": 10,
            "feed_position": 0,
            "urgency": "alert",
            "pre_layer_ranking": {
                "input_rank": 10,
                "input_order": 0,
                "rank_identifiers": {"ranking_run_id": "run-42", "rank_slot": "slot-a"},
                "immutable": True,
            },
        },
    ]

    routed = route_items_after_ranking(ranked)
    direct_decision = choose_delivery({
        "id": "direct-ranked",
        "title": "Direct delivery decision",
        "ensemble_score": 0.80,
        "final_score": 0.79,
        "ensemble_rank": 9,
        "feed_position": 8,
        "urgency": "digest",
    })

    assert [item["id"] for item in routed] == ["ranked-b", "ranked-a"]
    assert direct_decision["ranking_snapshot"]["input_ensemble_rank"] == 9
    assert direct_decision["ranking_snapshot"]["input_order"] == 0
    assert direct_decision["ranking_snapshot"]["rank_identifiers"]["feed_position"] == 8
    for original, processed in zip(ranked, routed):
        assert processed["ensemble_rank"] == original["ensemble_rank"]
        assert processed["feed_position"] == original["feed_position"]
        assert processed["pre_layer_ranking"]["input_rank"] == original["pre_layer_ranking"]["input_rank"]
        assert processed["pre_layer_ranking"]["input_order"] == original["pre_layer_ranking"]["input_order"]
        assert processed["pre_layer_ranking"]["rank_identifiers"]["ranking_run_id"] == "run-42"
        assert processed["pre_layer_ranking"]["rank_identifiers"]["rank_slot"] == original["pre_layer_ranking"]["rank_identifiers"]["rank_slot"]
        assert processed["delivery_decision"]["ranking_snapshot"]["input_ensemble_rank"] == original["pre_layer_ranking"]["input_rank"]
        assert processed["delivery_decision"]["ranking_snapshot"]["input_order"] == original["pre_layer_ranking"]["input_order"]
        assert processed["delivery_decision"]["ranking_snapshot"]["rank_identifiers"]["rank_slot"] == original["pre_layer_ranking"]["rank_identifiers"]["rank_slot"]


def test_ambient_routing_does_not_resort_ties_or_reinterpret_score_semantics(tmp_env):
    from hedwig.personal_algorithm import (
        assert_delivery_rank_identity_unchanged,
        assert_delivery_scores_unchanged,
        route_items_after_ranking,
    )

    ranked = [
        {
            "id": "tie-daily-first",
            "title": "First tied daily item",
            "score": -999,
            "relevance_score": 0.01,
            "ensemble_score": 0.70,
            "final_score": 0.111111111111,
            "ensemble_rank": 10,
            "feed_position": 0,
            "urgency": "digest",
            "pre_layer_ranking": {
                "input_rank": 10,
                "input_order": 0,
                "rank_identifiers": {"ranking_run_id": "gen9-boundary", "rank_slot": "slot-a"},
                "immutable": True,
            },
        },
        {
            "id": "critical-second-with-higher-score",
            "title": "Critical item stays second",
            "score": 100_000,
            "relevance_score": 999.9,
            "ensemble_score": 0.96,
            "final_score": 0.222222222222,
            "ensemble_rank": 1,
            "feed_position": 1,
            "urgency": "alert",
            "pre_layer_ranking": {
                "input_rank": 1,
                "input_order": 1,
                "rank_identifiers": {"ranking_run_id": "gen9-boundary", "rank_slot": "slot-b"},
                "immutable": True,
            },
        },
        {
            "id": "tie-daily-third",
            "title": "Second tied daily item",
            "score": 50_000,
            "relevance_score": 500.0,
            "ensemble_score": 0.70,
            "final_score": 0.999999999999,
            "ensemble_rank": 30,
            "feed_position": 2,
            "urgency": "digest",
            "pre_layer_ranking": {
                "input_rank": 30,
                "input_order": 2,
                "rank_identifiers": {"ranking_run_id": "gen9-boundary", "rank_slot": "slot-c"},
                "immutable": True,
            },
        },
    ]
    before = copy.deepcopy(ranked)

    routed = route_items_after_ranking(ranked)

    assert ranked == before
    assert [item["id"] for item in routed] == [
        "tie-daily-first",
        "critical-second-with-higher-score",
        "tie-daily-third",
    ]
    assert [item["delivery_decision"]["surface"] for item in routed] == ["daily", "critical", "daily"]
    assert_delivery_scores_unchanged(before, routed)
    assert_delivery_rank_identity_unchanged(before, routed)
    for original, processed in zip(before, routed):
        assert processed["ensemble_score"] == original["ensemble_score"]
        assert processed["final_score"] == original["final_score"]
        assert processed["score"] == original["score"]
        assert processed["relevance_score"] == original["relevance_score"]
        assert processed["pre_layer_ranking"]["input_order"] == original["pre_layer_ranking"]["input_order"]
        assert processed["delivery_decision"]["ranking_snapshot"]["input_ensemble_score"] == original["ensemble_score"]
        assert processed["delivery_decision"]["ranking_snapshot"]["input_final_score"] == original["final_score"]
        assert processed["delivery_decision"]["ranking_snapshot"]["rank_identifiers"] == original["pre_layer_ranking"]["rank_identifiers"]
        assert "score" not in processed["delivery_decision"]["explanation"]["text"].lower()


def test_delivery_rank_identity_guard_rejects_per_item_identity_mutations(tmp_env):
    from hedwig.personal_algorithm import assert_delivery_rank_identity_unchanged, route_items_after_ranking

    ranked = [
        {
            "id": "identity-a",
            "title": "First immutable ranked item",
            "ensemble_score": 0.90,
            "final_score": 0.89,
            "ensemble_rank": 1,
            "feed_position": 0,
            "urgency": "alert",
            "pre_layer_ranking": {
                "input_rank": 1,
                "input_order": 0,
                "rank_identifiers": {
                    "ranking_run_id": "run-identity-regression",
                    "rank_slot": "slot-a",
                },
                "immutable": True,
            },
        },
        {
            "id": "identity-b",
            "title": "Second immutable ranked item",
            "ensemble_score": 0.72,
            "final_score": 0.71,
            "ensemble_rank": 2,
            "feed_position": 1,
            "urgency": "digest",
            "pre_layer_ranking": {
                "input_rank": 2,
                "input_order": 1,
                "rank_identifiers": {
                    "ranking_run_id": "run-identity-regression",
                    "rank_slot": "slot-b",
                },
                "immutable": True,
            },
        },
    ]

    routed = route_items_after_ranking(ranked)
    assert_delivery_rank_identity_unchanged(ranked, routed)

    reordered = [routed[1], routed[0]]
    with pytest.raises(ValueError, match="rank identity mutation detected"):
        assert_delivery_rank_identity_unchanged(ranked, reordered)

    mutated_rank = [dict(routed[0]), dict(routed[1])]
    mutated_rank[0]["pre_layer_ranking"] = dict(mutated_rank[0]["pre_layer_ranking"], input_rank=99)
    with pytest.raises(ValueError, match="rank identity mutation detected for identity-a"):
        assert_delivery_rank_identity_unchanged(ranked, mutated_rank)

    mutated_identifier = [dict(routed[0]), dict(routed[1])]
    mutated_identifier[1]["pre_layer_ranking"] = dict(mutated_identifier[1]["pre_layer_ranking"])
    mutated_identifier[1]["pre_layer_ranking"]["rank_identifiers"] = {
        **mutated_identifier[1]["pre_layer_ranking"]["rank_identifiers"],
        "rank_slot": "slot-c",
    }
    with pytest.raises(ValueError, match="rank identity mutation detected for identity-b"):
        assert_delivery_rank_identity_unchanged(ranked, mutated_identifier)

    with pytest.raises(ValueError, match="must not add or remove ranked items"):
        assert_delivery_rank_identity_unchanged(ranked, routed[:1])


def test_weekly_ambient_routing_batches_lower_priority_items_and_preserves_ranking_boundary(tmp_env):
    from hedwig.delivery.ambient import select_ambient_items

    policy = {
        "delivery": {
            "default_channel": "dashboard",
            "repeat": {"enabled": True, "max_count": 2},
        },
        "exploration": {"enabled": False},
    }
    ranked = [
        {
            "id": "urgent-1",
            "title": "Immediate item",
            "url": "https://example.test/urgent",
            "ensemble_score": 0.94,
            "final_score": 0.93,
            "ensemble_rank": 1,
            "feed_position": 0,
            "urgency": "alert",
        },
        {
            "id": "daily-1",
            "title": "Daily item",
            "url": "https://example.test/daily",
            "ensemble_score": 0.74,
            "final_score": 0.73,
            "ensemble_rank": 2,
            "feed_position": 1,
            "urgency": "digest",
        },
        {
            "id": "weekly-1",
            "title": "Weekly catch-up one",
            "url": "https://example.test/weekly-1",
            "ensemble_score": 0.64,
            "final_score": 0.63,
            "ensemble_rank": 3,
            "feed_position": 2,
            "urgency": "digest",
            "why_relevant": "Useful background context for later review.",
        },
        {
            "id": "weekly-2",
            "title": "Weekly catch-up two",
            "url": "https://example.test/weekly-2",
            "ensemble_score": 0.31,
            "final_score": 0.30,
            "ensemble_rank": 4,
            "feed_position": 3,
            "urgency": "skip",
            "why_relevant": "Non-urgent learning material for a weekly pass.",
        },
        {
            "id": "weekly-3",
            "title": "Weekly catch-up three",
            "url": "https://example.test/weekly-3",
            "ensemble_score": 0.20,
            "final_score": 0.19,
            "ensemble_rank": 5,
            "feed_position": 4,
            "urgency": "skip",
            "why_relevant": "Reference item that should batch behind stronger items.",
        },
    ]
    before = [dict(item) for item in ranked]

    payload = select_ambient_items(ranked, "weekly", policy=policy, limit=2)

    assert ranked == before
    assert payload["surface"] == "weekly"
    assert payload["count"] == 2
    assert payload["limit"] == 2
    assert payload["entry_point"]["aggregation_behavior"].startswith("group already-ranked lower-urgency")
    assert [item["id"] for item in payload["items"]] == ["weekly-1", "weekly-2"]
    assert "urgent-1" not in {item["id"] for item in payload["items"]}
    assert "daily-1" not in {item["id"] for item in payload["items"]}

    for original, item in zip(ranked[2:4], payload["items"]):
        assert item["surface"] == "weekly"
        assert item["delivery_timing"] == "weekly_digest"
        assert item["delivery_decision"]["decision_layer"] == "post_ranking_delivery"
        assert item["delivery_decision"]["post_ranking"] is True
        assert item["delivery_decision"]["ranking_input"] is False
        assert item["delivery_decision"]["ranking_output"] is False
        assert item["delivery_decision"]["does_not_mutate_ensemble"] is True
        assert item["ensemble_score"] == original["ensemble_score"]
        assert item["final_score"] == original["final_score"]
        assert item["pre_layer_ranking"]["ensemble_score"] == original["ensemble_score"]
        assert item["pre_layer_ranking"]["final_score"] == original["final_score"]
        assert item["pre_layer_ranking"]["input_rank"] == original["ensemble_rank"]
        assert item["pre_layer_ranking"]["input_order"] == original["feed_position"]
        assert item["pre_layer_ranking"]["rank_identifiers"]["id"] == original["id"]
        assert item["delivery_decision"]["ranking_snapshot"]["input_ensemble_score"] == original["ensemble_score"]
        assert item["delivery_decision"]["ranking_snapshot"]["input_final_score"] == original["final_score"]
        assert item["delivery_decision"]["ranking_snapshot"]["input_ensemble_rank"] == original["ensemble_rank"]
        assert item["delivery_decision"]["ranking_snapshot"]["input_order"] == original["feed_position"]
        assert item["explanation"]["display_only"] is True
        assert item["explanation"]["ranking_input"] is False
        assert item["explanation"]["score_like_authority"] is False
        assert "score" not in item["reason"].lower()
        assert "rank" not in item["reason"].lower()


def test_shadow_fitness_media_and_rollback(tmp_env, monkeypatch):
    import shutil

    import hedwig.config as cfg
    import hedwig.onboarding.nl_algo_editor as nl_algo
    from hedwig.onboarding.nl_algo_editor import confirm_edit, propose_local_policy_edit, restore_algorithm_version
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
    assert get_personal_algorithm_policy()["media"]["full_understanding_enabled"] is False
    assert media_profile_for_item({"title": "x"})["default_media_mode"]["active_mode"] == "Text+Thumbnail+Transcript"

    temp_algorithm = tmp_env / "algorithm.yaml"
    shutil.copy2(cfg.ALGORITHM_PATH, temp_algorithm)
    monkeypatch.setattr(cfg, "ALGORITHM_PATH", temp_algorithm)
    monkeypatch.setattr(nl_algo, "ALGORITHM_PATH", temp_algorithm)
    cfg._ALGORITHM_VERSION_SEEDED = False

    applied = confirm_edit([{"op": "set", "path": "personal_algorithm.feed.default_mode", "value": "dense_reader"}], intent="dense")
    assert applied["ok"]
    risky = confirm_edit([{"op": "set", "path": "personal_algorithm.exploration.rate", "value": 0.15}], intent="more exploration")
    assert risky["requires_shadow_test"]
    future = confirm_edit(propose_local_policy_edit("replace ranking with composite fitness optimization")["changes"], intent="replace ranking")
    assert future["ok"]
    assert "future_ranking_experiments" in future["diff"]
    restored = restore_algorithm_version(1)
    assert restored["ok"]
