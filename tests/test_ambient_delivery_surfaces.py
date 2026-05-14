from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

PROJECT_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def tmp_env(monkeypatch, tmp_path):
    monkeypatch.setenv("HEDWIG_STORAGE", "sqlite")
    monkeypatch.setenv("HEDWIG_DB_PATH", str(tmp_path / "hedwig.db"))
    import hedwig.config as _cfg
    _cfg._ALGORITHM_VERSION_SEEDED = False
    yield tmp_path


def _ranked_items() -> list[dict]:
    return [
        {"id": "critical-1", "title": "Critical", "ensemble_score": 0.91, "final_score": 0.91, "ensemble_rank": 1, "urgency": "alert"},
        {"id": "daily-1", "title": "Daily", "ensemble_score": 0.72, "final_score": 0.72, "ensemble_rank": 2, "urgency": "digest"},
        {"id": "weekly-1", "title": "Weekly", "ensemble_score": 0.40, "final_score": 0.40, "ensemble_rank": 3, "urgency": "digest"},
        {"id": "pwa-1", "title": "PWA", "ensemble_score": 0.30, "final_score": 0.30, "ensemble_rank": 4, "urgency": "skip"},
    ]


def test_ambient_surface_entry_points_have_request_or_receive_semantics():
    from hedwig.delivery.ambient import ambient_surface_entry_points

    surfaces = {entry["surface"]: entry for entry in ambient_surface_entry_points()}
    assert set(surfaces) == {"critical", "daily", "weekly", "pwa", "tray"}
    assert surfaces["critical"]["entry_kind"] == "receiver"
    assert surfaces["daily"]["entry_kind"] == "receiver"
    assert surfaces["weekly"]["entry_kind"] == "receiver"
    assert surfaces["pwa"]["entry_kind"] == "requester"
    assert surfaces["tray"]["entry_kind"] == "requester"
    assert all(entry["manual_feed_entry_required"] is False for entry in surfaces.values())
    assert all(entry["post_ranking_boundary"]["mutates_scores"] is False for entry in surfaces.values())
    assert all(entry["contract_schema"] == "ambient_delivery_item_set.v1" for entry in surfaces.values())
    assert all(entry["contract_model"] == "AmbientDeliveryItemSet" for entry in surfaces.values())
    assert all(entry["page_path"] == f"/ambient/{entry['surface']}" for entry in surfaces.values())
    assert all(entry["request_path"] == f"/ambient/{entry['surface']}/api" for entry in surfaces.values())
    assert surfaces["pwa"]["installed_display_modes"] == [
        "standalone",
        "fullscreen",
        "minimal-ui",
        "window-controls-overlay",
    ]
    assert surfaces["pwa"]["unsupported_browser_fallback_surface"] == "daily"
    assert surfaces["pwa"]["unsupported_browser_fallback_path"] == "/ambient/daily"


def test_delivery_policy_config_schema_covers_steerable_ambient_policy_fields():
    from pydantic import ValidationError

    from hedwig.delivery.ambient import delivery_policy_config, delivery_policy_config_schema
    from hedwig.models import DeliveryPolicyConfig
    from hedwig.personal_algorithm import get_delivery_policy_config

    schema = delivery_policy_config_schema()
    assert schema["title"] == "DeliveryPolicyConfig"
    assert schema["properties"]["schema_version"]["default"] == "delivery_policy_config.v1"
    for field in ("timing", "repeat", "quiet_hours", "urgency", "preferred_surfaces"):
        assert field in schema["properties"]

    config = get_delivery_policy_config({
        "delivery": {
            "surfaces": ["critical", "daily", "weekly", "pwa", "native"],
            "preferred_surfaces": ["daily", "native"],
            "channels": ["dashboard", "pwa", "tray"],
            "default_channel": "dashboard",
            "timing": {
                "critical_timing": "now",
                "daily_digest_time": "8:05",
                "weekly_digest_day": "friday",
                "weekly_digest_time": "17:30",
                "timezone": "Asia/Seoul",
                "defer_to_quiet_hours": True,
            },
            "repeat": {"enabled": True, "max_count": 3, "min_interval_minutes": 90},
            "quiet_hours": {
                "enabled": True,
                "start": "23:15",
                "end": "07:00",
                "timezone": "Asia/Seoul",
                "allow_critical_override": False,
            },
            "urgency": {
                "critical_urgencies": ["alert"],
                "critical_score_threshold": 0.9,
                "daily_score_threshold": 0.7,
                "exploration_surface": "pwa",
            },
        }
    })

    assert config.schema_version == "delivery_policy_config.v1"
    assert config.timing.daily_digest_time == "08:05"
    assert config.repeat.max_count == 3
    assert config.quiet_hours.enabled is True
    assert config.quiet_hours.allow_critical_override is False
    assert config.urgency.critical_score_threshold == 0.9
    assert config.preferred_surfaces == ["daily", "tray"]
    assert config.post_ranking_only is True
    assert config.ranking_input is False
    assert config.mutates_scores is False
    assert config.mutates_rank_identity is False

    normalized = delivery_policy_config({"delivery": config.model_dump(mode="json")})
    assert normalized["timing"]["weekly_digest_time"] == "17:30"
    assert normalized["quiet_hours"]["start"] == "23:15"
    assert normalized["urgency"]["daily_score_threshold"] == 0.7
    assert normalized["preferred_surfaces"] == ["daily", "tray"]

    with pytest.raises(ValidationError):
        DeliveryPolicyConfig.model_validate({
            "preferred_surfaces": ["tray"],
            "surfaces": ["daily"],
        })
    with pytest.raises(ValidationError):
        DeliveryPolicyConfig.model_validate({"timing": {"daily_digest_time": "25:00"}})
    with pytest.raises(ValidationError):
        DeliveryPolicyConfig.model_validate({"ranking_input": True})
    with pytest.raises(ValidationError):
        DeliveryPolicyConfig.model_validate({
            "urgency": {"critical_score_threshold": 0.4, "daily_score_threshold": 0.7}
        })


def test_delivery_policy_steering_interface_maps_supported_nl_intents_without_ranking_inputs():
    from hedwig.delivery.ambient import (
        delivery_policy_steering_interface,
        propose_delivery_policy_steering,
    )

    interface = delivery_policy_steering_interface()
    assert interface["target_schema"] == "delivery_policy_config.v1"
    assert interface["allowed_path_prefix"] == "personal_algorithm.delivery"
    assert interface["ranking_boundary"]["ranking_input"] is False
    assert interface["ranking_boundary"]["mutates_scores"] is False
    assert interface["ranking_boundary"]["mutates_rank_identity"] is False

    proposal = propose_delivery_policy_steering(
        "Quiet hours from 22:30 to 07:15, daily digest at 8:05, "
        "weekly review Friday at 17:30, prefer native and PWA, "
        "repeat max 3, snooze 45 minutes, critical alerts above 90%."
    )

    assert proposal["ok"] is True
    assert proposal["risk_class"] == "risky_post_ranking"
    assert proposal["ranking_boundary"]["new_ranking_inputs"] == []
    assert set(proposal["matched_intents"]) == {
        "set_daily_digest_time",
        "set_post_ranking_urgency_thresholds",
        "set_preferred_surfaces",
        "set_quiet_hours",
        "set_repeat_policy",
        "set_weekly_digest_schedule",
    }
    assert all(change["path"].startswith("personal_algorithm.delivery.") for change in proposal["changes"])
    assert {
        "ranking",
        "retrieval",
        "fitness",
        "personal_algorithm.delivery.ranking_input",
        "personal_algorithm.delivery.mutates_scores",
        "personal_algorithm.delivery.mutates_rank_identity",
    }.isdisjoint({change["path"] for change in proposal["changes"]})

    changes = {change["path"]: change["value"] for change in proposal["changes"]}
    assert changes["personal_algorithm.delivery.timing.daily_digest_time"] == "08:05"
    assert changes["personal_algorithm.delivery.timing.weekly_digest_day"] == "friday"
    assert changes["personal_algorithm.delivery.timing.weekly_digest_time"] == "17:30"
    assert changes["personal_algorithm.delivery.quiet_hours.enabled"] is True
    assert changes["personal_algorithm.delivery.quiet_hours.start"] == "22:30"
    assert changes["personal_algorithm.delivery.quiet_hours.end"] == "07:15"
    assert changes["personal_algorithm.delivery.preferred_surfaces"] == ["pwa", "tray"]
    assert changes["personal_algorithm.delivery.repeat.max_count"] == 3
    assert changes["personal_algorithm.delivery.repeat.snooze_minutes"] == 45
    assert changes["personal_algorithm.delivery.urgency.critical_score_threshold"] == 0.9

    normalized = proposal["normalized_delivery_policy"]
    assert normalized["post_ranking_only"] is True
    assert normalized["ranking_input"] is False
    assert normalized["mutates_scores"] is False
    assert normalized["mutates_rank_identity"] is False
    assert normalized["preferred_surfaces"] == ["pwa", "tray"]


def test_delivery_policy_parser_validates_updates_without_time_as_threshold_confusion():
    from hedwig.delivery.ambient import parse_delivery_policy_updates

    proposal = parse_delivery_policy_updates(
        "Daily digest at 8:05, weekly review Monday at 9:30, "
        "critical alerts above 90%, daily threshold 70%, no critical quiet-hours override."
    )

    assert proposal["ok"] is True
    changes = {change["path"]: change["value"] for change in proposal["changes"]}
    assert changes["personal_algorithm.delivery.timing.daily_digest_time"] == "08:05"
    assert changes["personal_algorithm.delivery.timing.weekly_digest_time"] == "09:30"
    assert changes["personal_algorithm.delivery.urgency.critical_score_threshold"] == 0.9
    assert changes["personal_algorithm.delivery.urgency.daily_score_threshold"] == 0.7
    assert changes["personal_algorithm.delivery.quiet_hours.allow_critical_override"] is False
    assert proposal["normalized_delivery_policy"]["urgency"]["daily_score_threshold"] == 0.7


def test_delivery_policy_changes_are_classified_by_exposure_impact():
    from hedwig.delivery.ambient import propose_delivery_policy_steering
    from hedwig.personal_algorithm import classify_policy_edit

    safe = propose_delivery_policy_steering(
        "Daily digest at 8:05, weekly review Monday at 9:30."
    )
    assert safe["ok"] is True
    assert safe["risk_class"] == "safe"
    assert safe["classification"]["scopes"] == ["delivery_policy_timing"]
    assert safe["ranking_boundary"]["ranking_input"] is False
    assert all(
        change["path"] in {
            "personal_algorithm.delivery.timing.daily_digest_time",
            "personal_algorithm.delivery.timing.weekly_digest_day",
            "personal_algorithm.delivery.timing.weekly_digest_time",
        }
        for change in safe["changes"]
    )

    risky = classify_policy_edit(
        [
            {"op": "set", "path": "personal_algorithm.delivery.preferred_surfaces", "value": ["tray"]},
            {"op": "set", "path": "personal_algorithm.delivery.repeat.max_count", "value": 3},
            {"op": "set", "path": "personal_algorithm.delivery.urgency.daily_score_threshold", "value": 0.7},
        ],
        "Prefer tray, repeat max 3, daily threshold 70%",
    )
    assert risky["risk_class"] == "risky_post_ranking"
    assert risky["scopes"] == ["delivery_policy"]
    assert "post-ranking exposure" in risky["reason"]

    future = classify_policy_edit(
        [
            {"op": "set", "path": "personal_algorithm.delivery.repeat.max_count", "value": 3},
            {"op": "set", "path": "personal_algorithm.delivery.ranking_input", "value": True},
        ],
        "Make delivery a ranking input and repeat max 3",
    )
    assert future["risk_class"] == "future_ranking_experimental"
    assert "delivery_policy_boundary" in future["scopes"]
    assert "ranking input" in future["reason"]


def test_delivery_policy_parser_returns_validation_errors_for_schema_invalid_updates():
    from hedwig.delivery.ambient import parse_delivery_policy_updates

    proposal = parse_delivery_policy_updates(
        "Critical alerts above 40%, daily threshold 70%, repeat max 99."
    )

    assert proposal["ok"] is False
    assert proposal["error"] == "invalid delivery policy update"
    assert proposal["ranking_boundary"]["ranking_input"] is False
    assert proposal["ranking_boundary"]["new_ranking_inputs"] == []
    assert "validation_error" in proposal
    assert all(change["path"].startswith("personal_algorithm.delivery.") for change in proposal["changes"])


def test_delivery_policy_steering_rejects_ranking_like_requests_as_unsupported():
    from hedwig.delivery.ambient import propose_delivery_policy_steering

    proposal = propose_delivery_policy_steering(
        "Use tray notifications, but also change ranking and final_score for these items."
    )

    assert proposal["ok"] is True
    assert proposal["changes"] == [
        {
            "op": "set",
            "path": "personal_algorithm.delivery.preferred_surfaces",
            "value": ["tray"],
        }
    ]
    assert proposal["unsupported_intents"] == [{
        "intent": "ranking_or_score_mutation",
        "reason": "Delivery steering cannot add ranking inputs, mutate score fields, or change rank identity.",
    }]
    assert proposal["ranking_boundary"]["new_ranking_inputs"] == []
    assert proposal["normalized_delivery_policy"]["ranking_input"] is False


def test_policy_steering_only_changes_delivery_metadata_not_ranking_boundaries():
    from hedwig.delivery.ambient import propose_delivery_policy_steering
    from hedwig.personal_algorithm import (
        assert_delivery_rank_identity_unchanged,
        assert_delivery_scores_unchanged,
        route_items_after_ranking,
    )

    ranked = [
        {
            "id": "steered-critical",
            "title": "Critical item remains in its ranked slot",
            "ensemble_score": 0.87,
            "final_score": 0.861,
            "ensemble_rank": 1,
            "feed_position": 0,
            "urgency": "digest",
            "pre_layer_ranking": {
                "input_rank": 1,
                "input_order": 0,
                "rank_identifiers": {"ranking_run_id": "pr18-gen9", "rank_slot": "slot-1"},
                "immutable": True,
            },
        },
        {
            "id": "steered-daily",
            "title": "Daily item remains in its ranked slot",
            "ensemble_score": 0.72,
            "final_score": 0.719,
            "ensemble_rank": 2,
            "feed_position": 1,
            "urgency": "digest",
            "pre_layer_ranking": {
                "input_rank": 2,
                "input_order": 1,
                "rank_identifiers": {"ranking_run_id": "pr18-gen9", "rank_slot": "slot-2"},
                "immutable": True,
            },
        },
        {
            "id": "steered-weekly",
            "title": "Weekly item remains in its ranked slot",
            "ensemble_score": 0.52,
            "final_score": 0.519,
            "ensemble_rank": 3,
            "feed_position": 2,
            "urgency": "digest",
            "pre_layer_ranking": {
                "input_rank": 3,
                "input_order": 2,
                "rank_identifiers": {"ranking_run_id": "pr18-gen9", "rank_slot": "slot-3"},
                "immutable": True,
            },
        },
    ]
    before = copy.deepcopy(ranked)

    proposal = propose_delivery_policy_steering(
        "Prefer tray and PWA, daily threshold 70%, critical alerts above 90%, "
        "daily digest at 08:15, and do not repeat notifications. "
        "Do not change ranking, final_score, ensemble_score, or rank identity."
    )

    assert proposal["ok"] is True
    assert proposal["risk_class"] == "risky_post_ranking"
    assert proposal["classification"]["scopes"] == ["delivery_policy"]
    assert proposal["unsupported_intents"] == [{
        "intent": "ranking_or_score_mutation",
        "reason": "Delivery steering cannot add ranking inputs, mutate score fields, or change rank identity.",
    }]
    assert proposal["ranking_boundary"] == {
        "post_ranking_only": True,
        "ranking_input": False,
        "mutates_scores": False,
        "mutates_rank_identity": False,
        "new_ranking_inputs": [],
    }
    assert all(change["path"].startswith("personal_algorithm.delivery.") for change in proposal["changes"])
    assert {
        "ensemble_score",
        "final_score",
        "pre_layer_ranking",
        "ranking",
        "retrieval",
        "fitness",
        "meta_evolution",
    }.isdisjoint({change["path"] for change in proposal["changes"]})

    steered_policy = {"delivery": proposal["normalized_delivery_policy"]}
    baseline = route_items_after_ranking(before)
    steered = route_items_after_ranking(ranked, policy=steered_policy)

    assert ranked == before
    assert [item["id"] for item in steered] == [item["id"] for item in before]
    assert_delivery_scores_unchanged(before, steered)
    assert_delivery_rank_identity_unchanged(before, steered)

    assert [item["delivery_decision"]["surface"] for item in baseline] == ["critical", "daily", "pwa"]
    assert [item["delivery_decision"]["surface"] for item in steered] == ["pwa", "pwa", "pwa"]
    assert all(item["delivery_decision"]["repeat"] is False for item in steered)
    for original, routed in zip(before, steered):
        assert routed["ensemble_score"] == original["ensemble_score"]
        assert routed["final_score"] == original["final_score"]
        assert routed["pre_layer_ranking"]["ensemble_score"] == original["ensemble_score"]
        assert routed["pre_layer_ranking"]["final_score"] == original["final_score"]
        assert routed["pre_layer_ranking"]["input_rank"] == original["pre_layer_ranking"]["input_rank"]
        assert routed["pre_layer_ranking"]["input_order"] == original["pre_layer_ranking"]["input_order"]
        assert routed["pre_layer_ranking"]["rank_identifiers"] == original["pre_layer_ranking"]["rank_identifiers"]
        assert routed["pre_layer_ranking"]["immutable"] is True
        assert routed["delivery_decision"]["ranking_snapshot"]["input_ensemble_score"] == original["ensemble_score"]
        assert routed["delivery_decision"]["ranking_snapshot"]["input_final_score"] == original["final_score"]
        assert routed["delivery_decision"]["ranking_snapshot"]["rank_identifiers"] == original["pre_layer_ranking"]["rank_identifiers"]
        assert routed["delivery_decision"]["ranking_input"] is False
        assert routed["delivery_decision"]["ranking_output"] is False
        assert routed["delivery_decision"]["preferred_surfaces"] == ["pwa", "tray"]
        assert routed["delivery_decision"]["surface_preference"]["post_ranking_only"] is True
        assert routed["delivery_decision"]["surface_preference"]["mutates_scores"] is False


def test_timing_only_policy_steering_is_safe_and_preserves_ranking_boundary():
    from hedwig.delivery.ambient import propose_delivery_policy_steering, select_ambient_items
    from hedwig.personal_algorithm import (
        assert_delivery_rank_identity_unchanged,
        assert_delivery_scores_unchanged,
        route_items_after_ranking,
    )

    ranked = [
        {
            "id": "timing-safe-daily",
            "title": "Timing steering should not alter the ranked item",
            "ensemble_score": 0.75,
            "final_score": 0.749,
            "ensemble_rank": 4,
            "feed_position": 0,
            "urgency": "digest",
            "pre_layer_ranking": {
                "input_rank": 4,
                "input_order": 0,
                "rank_identifiers": {"ranking_run_id": "pr18-gen9", "rank_slot": "slot-4"},
                "immutable": True,
            },
        },
    ]
    before = copy.deepcopy(ranked)

    proposal = propose_delivery_policy_steering("Daily digest at 08:45.")

    assert proposal["ok"] is True
    assert proposal["risk_class"] == "safe"
    assert proposal["changes"] == [{
        "op": "set",
        "path": "personal_algorithm.delivery.timing.daily_digest_time",
        "value": "08:45",
    }]
    assert proposal["classification"]["scopes"] == ["delivery_policy_timing"]
    assert proposal["ranking_boundary"] == {
        "post_ranking_only": True,
        "ranking_input": False,
        "mutates_scores": False,
        "mutates_rank_identity": False,
        "new_ranking_inputs": [],
    }

    policy = {"delivery": proposal["normalized_delivery_policy"]}
    baseline = route_items_after_ranking(ranked)
    steered = route_items_after_ranking(ranked, policy=policy)
    selected = select_ambient_items(
        ranked,
        "daily",
        policy=policy,
        client_context={"enforce_delivery_schedule": True, "current_time": "08:30", "weekday": "thursday"},
    )

    assert ranked == before
    assert [item["id"] for item in steered] == [item["id"] for item in baseline] == ["timing-safe-daily"]
    assert [item["delivery_decision"]["surface"] for item in steered] == [item["delivery_decision"]["surface"] for item in baseline]
    assert_delivery_scores_unchanged(before, steered)
    assert_delivery_rank_identity_unchanged(before, steered)
    assert selected["items"] == []
    assert selected["post_ranking_boundary"]["mutates_scores"] is False
    assert selected["post_ranking_boundary"]["mutates_rank_identity"] is False


def test_delivery_policy_steering_risk_classes_are_exposure_bounded():
    from hedwig.delivery.ambient import propose_delivery_policy_steering
    from hedwig.personal_algorithm import classify_policy_edit

    safe = classify_policy_edit(
        [{"op": "set", "path": "personal_algorithm.delivery.timing.daily_digest_time", "value": "08:45"}],
        "Daily digest at 08:45.",
    )
    risky = classify_policy_edit(
        [{"op": "set", "path": "personal_algorithm.delivery.preferred_surfaces", "value": ["tray"]}],
        "Prefer tray for ambient delivery.",
    )
    future = classify_policy_edit(
        [{"op": "set", "path": "personal_algorithm.delivery.ranking_input", "value": True}],
        "Use delivery as a ranking input.",
    )

    assert safe["risk_class"] == "safe"
    assert safe["scopes"] == ["delivery_policy_timing"]
    assert "does not change item eligibility or exposure distribution" in safe["reason"]
    assert risky["risk_class"] == "risky_post_ranking"
    assert risky["scopes"] == ["delivery_policy"]
    assert "post-ranking exposure" in risky["reason"]
    assert future["risk_class"] == "future_ranking_experimental"
    assert future["scopes"] == ["delivery_policy_boundary"]
    assert "ranking input" in future["reason"]

    proposal = propose_delivery_policy_steering(
        "Prefer native notifications, but do not mutate ensemble_score, final_score, or pre_layer_ranking."
    )

    assert proposal["ok"] is True
    assert proposal["risk_class"] == "risky_post_ranking"
    assert proposal["changes"] == [{
        "op": "set",
        "path": "personal_algorithm.delivery.preferred_surfaces",
        "value": ["tray"],
    }]
    assert proposal["unsupported_intents"] == [{
        "intent": "ranking_or_score_mutation",
        "reason": "Delivery steering cannot add ranking inputs, mutate score fields, or change rank identity.",
    }]
    assert all(change["path"].startswith("personal_algorithm.delivery.") for change in proposal["changes"])
    assert {
        "ensemble_score",
        "final_score",
        "pre_layer_ranking",
        "ranking",
        "retrieval",
        "fitness",
    }.isdisjoint({change["path"] for change in proposal["changes"]})
    assert proposal["ranking_boundary"]["new_ranking_inputs"] == []
    assert proposal["normalized_delivery_policy"]["ranking_input"] is False
    assert proposal["normalized_delivery_policy"]["mutates_scores"] is False
    assert proposal["normalized_delivery_policy"]["mutates_rank_identity"] is False


def test_local_policy_editor_routes_delivery_language_to_delivery_policy_schema(tmp_env):
    from hedwig.onboarding.nl_algo_editor import propose_local_policy_edit

    proposed = propose_local_policy_edit(
        "Do not repeat notifications and set quiet hours from 10pm to 6am."
    )

    assert proposed["ok"] is True
    assert proposed["summary"] == "ambient delivery policy steering"
    assert proposed["risk_class"] == "risky_post_ranking"
    assert proposed["ranking_boundary"]["ranking_input"] is False
    assert proposed["ranking_boundary"]["new_ranking_inputs"] == []
    paths = {change["path"] for change in proposed["changes"]}
    assert paths == {
        "personal_algorithm.delivery.quiet_hours.enabled",
        "personal_algorithm.delivery.quiet_hours.start",
        "personal_algorithm.delivery.quiet_hours.end",
        "personal_algorithm.delivery.repeat.enabled",
        "personal_algorithm.delivery.repeat.max_count",
    }
    values = {change["path"]: change["value"] for change in proposed["changes"]}
    assert values["personal_algorithm.delivery.quiet_hours.start"] == "22:00"
    assert values["personal_algorithm.delivery.quiet_hours.end"] == "06:00"
    assert values["personal_algorithm.delivery.repeat.enabled"] is False
    assert values["personal_algorithm.delivery.repeat.max_count"] == 0
    assert all(path.startswith("personal_algorithm.delivery.") for path in paths)


def test_local_policy_editor_persists_natural_language_delivery_policy_updates(tmp_env, monkeypatch):
    import yaml

    import hedwig.config as hedwig_config
    import hedwig.onboarding.nl_algo_editor as nl_algo
    from hedwig.onboarding.nl_algo_editor import confirm_edit, propose_local_policy_edit
    from hedwig.storage import get_algorithm_history, get_evolution_signals

    algorithm_path = tmp_env / "algorithm.yaml"
    algorithm_path.write_text(
        yaml.safe_dump({
            "version": 7,
            "ranking": {
                "top_k": 30,
                "components": {
                    "llm_judge": {"enabled": True, "weight": 0.4},
                    "bandit": {"enabled": False, "weight": 0.1},
                },
            },
            "personal_algorithm": {
                "delivery": {
                    "schema_version": "delivery_policy_config.v1",
                    "preferred_surfaces": ["daily"],
                    "policy_layer": "post_ranking_delivery",
                    "post_ranking_only": True,
                    "ranking_input": False,
                    "mutates_scores": False,
                    "mutates_rank_identity": False,
                },
            },
        }),
        encoding="utf-8",
    )
    monkeypatch.setattr(hedwig_config, "ALGORITHM_PATH", algorithm_path)
    monkeypatch.setattr(nl_algo, "ALGORITHM_PATH", algorithm_path)
    hedwig_config._ALGORITHM_VERSION_SEEDED = False

    proposed = propose_local_policy_edit(
        "Use PWA and native notifications, daily digest at 8:05am, "
        "weekly Friday at 5:30pm, quiet hours from 10:30pm to 7:15am, "
        "repeat max 3, snooze 45 minutes, critical alerts above 90%."
    )
    assert proposed["ok"] is True
    assert proposed["summary"] == "ambient delivery policy steering"
    assert proposed["risk_class"] == "risky_post_ranking"
    assert proposed["ranking_boundary"] == {
        "post_ranking_only": True,
        "ranking_input": False,
        "mutates_scores": False,
        "mutates_rank_identity": False,
        "new_ranking_inputs": [],
    }

    applied = confirm_edit(proposed["changes"], intent="ambient policy update", shadow_approved=True)

    assert applied["ok"] is True
    assert applied["version"] == 8
    assert applied["classification"]["risk_class"] == "risky_post_ranking"
    assert applied["rejected_changes"] == []
    assert all(
        change["path"].startswith("personal_algorithm.delivery.")
        for change in applied["applied_changes"]
    )

    reloaded = yaml.safe_load(algorithm_path.read_text(encoding="utf-8"))
    delivery = reloaded["personal_algorithm"]["delivery"]
    assert reloaded["version"] == 8
    assert reloaded["origin"] == "user_nl_editor"
    assert reloaded["ranking"]["components"]["llm_judge"]["weight"] == 0.4
    assert reloaded["ranking"]["components"]["bandit"]["enabled"] is False
    assert delivery["timing"]["daily_digest_time"] == "08:05"
    assert delivery["timing"]["weekly_digest_day"] == "friday"
    assert delivery["timing"]["weekly_digest_time"] == "17:30"
    assert delivery["quiet_hours"]["enabled"] is True
    assert delivery["quiet_hours"]["start"] == "22:30"
    assert delivery["quiet_hours"]["end"] == "07:15"
    assert delivery["preferred_surfaces"] == ["pwa", "tray"]
    assert delivery["repeat"]["enabled"] is True
    assert delivery["repeat"]["max_count"] == 3
    assert delivery["repeat"]["snooze_minutes"] == 45
    assert delivery["urgency"]["critical_score_threshold"] == 0.9
    assert delivery["ranking_input"] is False
    assert delivery["mutates_scores"] is False
    assert delivery["mutates_rank_identity"] is False

    history = get_algorithm_history()
    assert any(row["version"] == 8 and row["origin"] == "user_nl_editor" for row in history)
    events = get_evolution_signals(channel="explicit")
    assert any(
        event["kind"] == "algorithm_edit"
        and event["payload"]["classification"]["risk_class"] == "risky_post_ranking"
        for event in events
    )


@pytest.mark.parametrize(
    "overlay",
    [
        {"delivery": {"timing": {"critical_timing": "later"}}},
        {"delivery": {"timing": {"daily_digest_time": "24:00"}}},
        {"delivery": {"timing": {"weekly_digest_day": "funday"}}},
        {"delivery": {"timing": {"weekly_digest_time": "12:99"}}},
        {"delivery": {"repeat": {"max_count": -1}}},
        {"delivery": {"repeat": {"min_interval_minutes": 10081}}},
        {"delivery": {"quiet_hours": {"start": "nope"}}},
        {"delivery": {"quiet_hours": {"enabled": True, "start": "22:00", "end": "22:00"}}},
        {"delivery": {"urgency": {"critical_urgencies": ["panic"]}}},
        {"delivery": {"urgency": {"exploration_surface": "manual_feed"}}},
        {"delivery": {"surfaces": ["daily", "manual_feed"]}},
        {"delivery": {"preferred_surfaces": ["weekly"], "surfaces": ["daily"]}},
    ],
)
def test_delivery_policy_config_rejects_invalid_policy_fields(overlay):
    from pydantic import ValidationError

    from hedwig.personal_algorithm import get_delivery_policy_config

    with pytest.raises(ValidationError):
        get_delivery_policy_config(overlay)


def test_delivery_policy_config_defaults_are_complete_and_post_ranking_only():
    from hedwig.delivery.ambient import delivery_policy_config
    from hedwig.personal_algorithm import get_delivery_policy_config

    typed = get_delivery_policy_config({"delivery": {}})
    normalized = delivery_policy_config({"delivery": {}})

    assert typed.schema_version == "delivery_policy_config.v1"
    assert typed.enabled is True
    assert typed.surfaces == ["critical", "daily", "weekly", "pwa", "tray"]
    assert typed.preferred_surfaces == ["daily"]
    assert typed.channels == ["dashboard", "email", "slack", "discord", "pwa", "tray"]
    assert typed.default_channel == "dashboard"
    assert typed.timing.model_dump(mode="json") == {
        "critical_timing": "now",
        "daily_digest_time": "09:00",
        "weekly_digest_day": "monday",
        "weekly_digest_time": "09:00",
        "timezone": "local",
        "defer_to_quiet_hours": True,
    }
    assert typed.repeat.model_dump(mode="json") == {
        "enabled": True,
        "max_count": 2,
        "min_interval_minutes": 240,
        "snooze_minutes": 60,
    }
    assert typed.quiet_hours.model_dump(mode="json") == {
        "enabled": False,
        "start": "22:00",
        "end": "07:00",
        "timezone": "local",
        "allow_critical_override": True,
    }
    assert typed.urgency.model_dump(mode="json") == {
        "critical_urgencies": ["alert"],
        "critical_score_threshold": 0.85,
        "daily_score_threshold": 0.65,
        "exploration_surface": "pwa",
    }
    assert normalized == typed.model_dump(mode="json")
    assert normalized["policy_layer"] == "post_ranking_delivery"
    assert normalized["post_ranking_only"] is True
    assert normalized["ranking_input"] is False
    assert normalized["mutates_scores"] is False
    assert normalized["mutates_rank_identity"] is False


def test_delivery_policy_config_loads_from_algorithm_yaml_and_validates_boundaries(monkeypatch, tmp_path):
    from pydantic import ValidationError

    import hedwig.config as hedwig_config
    from hedwig.personal_algorithm import get_delivery_policy_config

    algorithm_path = tmp_path / "algorithm.yaml"
    monkeypatch.setattr(hedwig_config, "ALGORITHM_PATH", algorithm_path)
    monkeypatch.setattr(hedwig_config, "_ALGORITHM_VERSION_SEEDED", True)

    algorithm_path.write_text(
        """
version: 20
personal_algorithm:
  delivery:
    schema_version: delivery_policy_config.v1
    surfaces: [critical, daily, weekly, pwa, native]
    preferred_surfaces: [native, pwa]
    channels: [dashboard, pwa, tray]
    default_channel: pwa
    timing:
      daily_digest_time: "07:30"
      weekly_digest_day: thursday
      weekly_digest_time: "18:15"
      timezone: Asia/Seoul
    repeat:
      max_count: 3
      min_interval_minutes: 120
      snooze_minutes: 45
    quiet_hours:
      enabled: true
      start: "22:30"
      end: "06:30"
      allow_critical_override: false
    urgency:
      critical_score_threshold: 0.9
      daily_score_threshold: 0.7
      exploration_surface: pwa
    policy_layer: post_ranking_delivery
    post_ranking_only: true
    ranking_input: false
    mutates_scores: false
    mutates_rank_identity: false
""",
        encoding="utf-8",
    )

    loaded = get_delivery_policy_config()

    assert loaded.schema_version == "delivery_policy_config.v1"
    assert loaded.surfaces == ["critical", "daily", "weekly", "pwa", "tray"]
    assert loaded.preferred_surfaces == ["tray", "pwa"]
    assert loaded.default_channel == "pwa"
    assert loaded.timing.daily_digest_time == "07:30"
    assert loaded.timing.weekly_digest_day == "thursday"
    assert loaded.timing.weekly_digest_time == "18:15"
    assert loaded.repeat.max_count == 3
    assert loaded.repeat.min_interval_minutes == 120
    assert loaded.repeat.snooze_minutes == 45
    assert loaded.quiet_hours.enabled is True
    assert loaded.quiet_hours.allow_critical_override is False
    assert loaded.urgency.critical_score_threshold == 0.9
    assert loaded.urgency.daily_score_threshold == 0.7
    assert loaded.post_ranking_only is True
    assert loaded.ranking_input is False
    assert loaded.mutates_scores is False
    assert loaded.mutates_rank_identity is False

    algorithm_path.write_text(
        """
personal_algorithm:
  delivery:
    surfaces: [daily]
    preferred_surfaces: [tray]
    ranking_input: true
""",
        encoding="utf-8",
    )

    with pytest.raises(ValidationError, match="post-ranking|preferred_surfaces"):
        get_delivery_policy_config()


def test_loaded_preferred_surface_policy_routes_after_ranking_without_score_mutation(monkeypatch, tmp_path):
    import hedwig.config as hedwig_config
    from hedwig.personal_algorithm import (
        assert_delivery_rank_identity_unchanged,
        assert_delivery_scores_unchanged,
        route_items_after_ranking,
    )

    algorithm_path = tmp_path / "algorithm.yaml"
    monkeypatch.setattr(hedwig_config, "ALGORITHM_PATH", algorithm_path)
    monkeypatch.setattr(hedwig_config, "_ALGORITHM_VERSION_SEEDED", True)
    algorithm_path.write_text(
        """
personal_algorithm:
  exploration:
    enabled: false
  delivery:
    surfaces: [critical, daily, weekly, pwa, native]
    preferred_surfaces: [native, pwa]
    channels: [dashboard, tray]
    default_channel: tray
    urgency:
      critical_score_threshold: 0.9
      daily_score_threshold: 0.7
    post_ranking_only: true
    ranking_input: false
    mutates_scores: false
    mutates_rank_identity: false
""",
        encoding="utf-8",
    )
    ranked = [
        {
            "id": "loaded-critical",
            "title": "Loaded critical",
            "ensemble_score": 0.94,
            "final_score": 0.93,
            "ensemble_rank": 1,
            "feed_position": 0,
            "urgency": "alert",
        },
        {
            "id": "loaded-daily",
            "title": "Loaded daily",
            "ensemble_score": 0.74,
            "final_score": 0.73,
            "ensemble_rank": 2,
            "feed_position": 1,
            "urgency": "digest",
        },
        {
            "id": "loaded-weekly",
            "title": "Loaded weekly",
            "ensemble_score": 0.42,
            "final_score": 0.41,
            "ensemble_rank": 3,
            "feed_position": 2,
            "urgency": "digest",
        },
    ]
    before = copy.deepcopy(ranked)

    routed = route_items_after_ranking(ranked)

    assert ranked == before
    assert_delivery_scores_unchanged(before, routed)
    assert_delivery_rank_identity_unchanged(before, routed)
    assert [item["id"] for item in routed] == ["loaded-critical", "loaded-daily", "loaded-weekly"]
    assert [item["delivery_decision"]["surface"] for item in routed] == ["tray", "tray", "weekly"]
    assert [item["delivery_decision"]["canonical_surface"] for item in routed] == ["critical", "daily", "weekly"]

    for original, routed_item in zip(before, routed):
        decision = routed_item["delivery_decision"]
        assert routed_item["ensemble_score"] == original["ensemble_score"]
        assert routed_item["final_score"] == original["final_score"]
        assert decision["preferred_surfaces"] == ["tray", "pwa"]
        assert decision["surface_preference"]["post_ranking_only"] is True
        assert decision["surface_preference"]["ranking_input"] is False
        assert decision["surface_preference"]["mutates_scores"] is False
        assert decision["surface_preference"]["mutates_rank_identity"] is False
        assert decision["ranking_snapshot"]["input_ensemble_score"] == original["ensemble_score"]
        assert decision["ranking_snapshot"]["input_final_score"] == original["final_score"]

    assert routed[0]["delivery_decision"]["surface_preference"]["selection_reason"] == "matched_user_surface_preference"
    assert routed[1]["delivery_decision"]["surface_preference"]["selection_reason"] == "matched_user_surface_preference"
    assert routed[2]["delivery_decision"]["surface_preference"]["selection_reason"] == "canonical_surface_enabled"


def test_delivery_policy_config_accepts_valid_complete_configuration():
    from hedwig.delivery.ambient import delivery_policy_config
    from hedwig.personal_algorithm import get_delivery_policy_config

    policy = {
        "delivery": {
            "schema_version": "delivery_policy_config.v1",
            "enabled": True,
            "surfaces": ["critical", "daily", "weekly", "pwa", "native", "notification", "daily"],
            "preferred_surfaces": ["native", "notification"],
            "channels": ["pwa", "tray"],
            "default_channel": "pwa",
            "timing": {
                "critical_timing": "now",
                "daily_digest_time": "7:05",
                "weekly_digest_day": "saturday",
                "weekly_digest_time": "18:45",
                "timezone": "Asia/Seoul",
                "defer_to_quiet_hours": False,
            },
            "repeat": {
                "enabled": True,
                "max_count": 5,
                "min_interval_minutes": 30,
                "snooze_minutes": 15,
            },
            "quiet_hours": {
                "enabled": True,
                "start": "21:30",
                "end": "06:45",
                "timezone": "Asia/Seoul",
                "allow_critical_override": True,
            },
            "urgency": {
                "critical_urgencies": ["alert", "digest"],
                "critical_score_threshold": 0.92,
                "daily_score_threshold": 0.51,
                "exploration_surface": "tray",
            },
            "policy_layer": "post_ranking_delivery",
            "post_ranking_only": True,
            "ranking_input": False,
            "mutates_scores": False,
            "mutates_rank_identity": False,
        }
    }

    typed = get_delivery_policy_config(policy)
    normalized = delivery_policy_config(policy)

    assert typed.surfaces == ["critical", "daily", "weekly", "pwa", "tray"]
    assert typed.preferred_surfaces == ["tray", "critical"]
    assert typed.channels == ["pwa", "tray"]
    assert typed.default_channel == "pwa"
    assert typed.timing.daily_digest_time == "07:05"
    assert typed.timing.weekly_digest_day == "saturday"
    assert typed.timing.weekly_digest_time == "18:45"
    assert typed.timing.defer_to_quiet_hours is False
    assert typed.repeat.max_count == 5
    assert typed.repeat.min_interval_minutes == 30
    assert typed.repeat.snooze_minutes == 15
    assert typed.quiet_hours.enabled is True
    assert typed.quiet_hours.start == "21:30"
    assert typed.quiet_hours.end == "06:45"
    assert typed.urgency.critical_urgencies == ["alert", "digest"]
    assert typed.urgency.critical_score_threshold == 0.92
    assert typed.urgency.daily_score_threshold == 0.51
    assert typed.urgency.exploration_surface == "tray"
    assert normalized == typed.model_dump(mode="json")


@pytest.mark.parametrize(
    "overlay, error",
    [
        ({"delivery": {"default_channel": "email", "channels": ["pwa"]}}, "default_channel"),
        ({"delivery": {"preferred_surfaces": ["weekly"], "surfaces": ["daily"]}}, "preferred_surfaces"),
        ({"delivery": {"post_ranking_only": False}}, "post-ranking"),
        ({"delivery": {"ranking_input": True}}, "post-ranking"),
        ({"delivery": {"mutates_scores": True}}, "mutate"),
        ({"delivery": {"mutates_rank_identity": True}}, "mutate"),
        ({"delivery": {"timing": {"daily_digest_time": "9am"}}}, "HH:MM"),
        ({"delivery": {"timing": {"weekly_digest_day": "someday"}}}, "weekday"),
        ({"delivery": {"repeat": {"max_count": 11}}}, "less than or equal"),
        ({"delivery": {"quiet_hours": {"enabled": True, "start": "08:00", "end": "08:00"}}}, "non-empty"),
        ({"delivery": {"urgency": {"critical_score_threshold": 0.4, "daily_score_threshold": 0.6}}}, "greater"),
        ({"delivery": {"urgency": {"exploration_surface": "manual_feed"}}}, "exploration_surface"),
        ({"delivery": {"unexpected": True}}, "Extra inputs"),
    ],
)
def test_delivery_policy_config_validation_failures_are_explicit(overlay, error):
    from pydantic import ValidationError

    from hedwig.personal_algorithm import get_delivery_policy_config

    with pytest.raises(ValidationError, match=error):
        get_delivery_policy_config(overlay)


def test_delivery_policy_config_merges_defaults_when_fields_are_omitted():
    from hedwig.delivery.ambient import delivery_policy_config
    from hedwig.personal_algorithm import get_delivery_policy_config

    partial = get_delivery_policy_config({
        "delivery": {
            "timing": {"daily_digest_time": "6:30"},
            "repeat": {"max_count": 4},
            "quiet_hours": {"enabled": True},
            "urgency": {"daily_score_threshold": 0.7},
        }
    })

    assert partial.timing.daily_digest_time == "06:30"
    assert partial.timing.weekly_digest_day == "monday"
    assert partial.timing.weekly_digest_time == "09:00"
    assert partial.repeat.enabled is True
    assert partial.repeat.max_count == 4
    assert partial.repeat.min_interval_minutes == 240
    assert partial.quiet_hours.enabled is True
    assert partial.quiet_hours.start == "22:00"
    assert partial.quiet_hours.end == "07:00"
    assert partial.urgency.critical_score_threshold == 0.85
    assert partial.urgency.daily_score_threshold == 0.7
    assert partial.surfaces == ["critical", "daily", "weekly", "pwa", "tray"]
    assert partial.preferred_surfaces == ["daily"]
    assert partial.default_channel == "dashboard"
    assert partial.post_ranking_only is True
    assert partial.ranking_input is False

    constrained = delivery_policy_config({
        "delivery": {
            "surfaces": ["critical"],
            "channels": ["pwa"],
            "timing": {"weekly_digest_day": "sunday"},
        }
    })

    assert constrained["surfaces"] == ["critical"]
    assert constrained["preferred_surfaces"] == ["critical"]
    assert constrained["channels"] == ["pwa"]
    assert constrained["default_channel"] == "pwa"
    assert constrained["timing"]["daily_digest_time"] == "09:00"
    assert constrained["timing"]["weekly_digest_day"] == "sunday"
    assert constrained["repeat"]["snooze_minutes"] == 60
    assert constrained["quiet_hours"]["allow_critical_override"] is True
    assert constrained["policy_layer"] == "post_ranking_delivery"
    assert constrained["mutates_scores"] is False


def test_delivery_policy_thresholds_drive_post_ranking_metadata_without_score_mutation():
    from hedwig.delivery.ambient import select_ambient_items

    items = [
        {
            "id": "policy-daily",
            "title": "Policy daily threshold",
            "ensemble_score": 0.72,
            "final_score": 0.71,
            "ensemble_rank": 1,
            "urgency": "digest",
        },
        {
            "id": "policy-weekly",
            "title": "Policy weekly threshold",
            "ensemble_score": 0.68,
            "final_score": 0.67,
            "ensemble_rank": 2,
            "urgency": "digest",
        },
    ]
    before = copy.deepcopy(items)
    policy = {
        "delivery": {
            "default_channel": "dashboard",
            "surfaces": ["critical", "daily", "weekly", "pwa", "tray"],
            "preferred_surfaces": ["daily"],
            "urgency": {"critical_score_threshold": 0.95, "daily_score_threshold": 0.70},
            "repeat": {"enabled": True, "max_count": 1, "min_interval_minutes": 120},
        },
        "exploration": {"enabled": False},
    }

    daily = select_ambient_items(items, "daily", policy=policy, limit=5)
    weekly = select_ambient_items(items, "weekly", policy=policy, limit=5)

    assert [item["id"] for item in daily["items"]] == ["policy-daily"]
    assert [item["id"] for item in weekly["items"]] == ["policy-weekly"]
    assert daily["items"][0]["delivery_decision"]["repeat_rule"]["max_count"] == 1
    assert daily["items"][0]["delivery_decision"]["repeat_rule"]["min_interval_minutes"] == 120
    assert items == before
    for payload in (daily, weekly):
        for delivered in payload["items"]:
            original = next(item for item in before if item["id"] == delivered["id"])
            assert delivered["ensemble_score"] == original["ensemble_score"]
            assert delivered["final_score"] == original["final_score"]
            assert delivered["delivery_decision"]["ranking_input"] is False
            assert delivered["delivery_decision"]["ranking_output"] is False


def test_preferred_surfaces_choose_eligible_ambient_routes_without_reranking():
    from hedwig.delivery.ambient import select_ambient_items
    from hedwig.personal_algorithm import (
        assert_delivery_rank_identity_unchanged,
        assert_delivery_scores_unchanged,
        route_items_after_ranking,
    )

    items = [
        {
            "id": "prefer-critical-tray",
            "title": "Critical item can use tray preference",
            "ensemble_score": 0.91,
            "final_score": 0.90,
            "ensemble_rank": 1,
            "feed_position": 0,
            "urgency": "alert",
        },
        {
            "id": "prefer-daily-tray",
            "title": "Daily item can use tray preference",
            "ensemble_score": 0.74,
            "final_score": 0.73,
            "ensemble_rank": 2,
            "feed_position": 1,
            "urgency": "digest",
        },
        {
            "id": "prefer-weekly-stays-weekly",
            "title": "Weekly item is not promoted by tray preference",
            "ensemble_score": 0.40,
            "final_score": 0.39,
            "ensemble_rank": 3,
            "feed_position": 2,
            "urgency": "digest",
        },
    ]
    policy = {
        "exploration": {"enabled": False},
        "delivery": {
            "surfaces": ["critical", "daily", "weekly", "pwa", "tray"],
            "preferred_surfaces": ["tray", "pwa"],
        },
    }
    before = copy.deepcopy(items)

    routed = route_items_after_ranking(items, policy=policy)
    tray = select_ambient_items(items, "tray", policy=policy, limit=10)
    daily = select_ambient_items(items, "daily", policy=policy, limit=10)
    weekly = select_ambient_items(items, "weekly", policy=policy, limit=10)

    assert items == before
    assert_delivery_scores_unchanged(before, routed)
    assert_delivery_rank_identity_unchanged(before, routed)
    assert [item["delivery_decision"]["surface"] for item in routed] == ["tray", "tray", "weekly"]
    assert [item["id"] for item in tray["items"]] == ["prefer-critical-tray", "prefer-daily-tray"]
    assert daily["items"] == []
    assert [item["id"] for item in weekly["items"]] == ["prefer-weekly-stays-weekly"]

    for item in tray["items"]:
        decision = item["delivery_decision"]
        assert decision["surface"] == "tray"
        assert decision["surface_preference"]["canonical_surface"] in {"critical", "daily"}
        assert decision["surface_preference"]["eligible_surfaces"] in (
            ["critical", "tray", "pwa"],
            ["daily", "tray", "pwa"],
        )
        assert decision["surface_preference"]["preferred_surfaces"] == ["tray", "pwa"]
        assert decision["surface_preference"]["preference_matched"] is True
        assert decision["surface_preference"]["ranking_input"] is False
        assert decision["surface_preference"]["mutates_scores"] is False
        original = next(row for row in before if row["id"] == item["id"])
        assert item["ensemble_score"] == original["ensemble_score"]
        assert item["final_score"] == original["final_score"]
        assert item["pre_layer_ranking"]["input_order"] == original["feed_position"]


def test_disabled_canonical_surface_falls_back_to_enabled_preference_post_ranking():
    from hedwig.delivery.ambient import select_ambient_items

    items = [
        {
            "id": "critical-daily-fallback",
            "title": "Critical item respects enabled preferred daily fallback",
            "ensemble_score": 0.95,
            "final_score": 0.94,
            "ensemble_rank": 1,
            "feed_position": 0,
            "urgency": "alert",
        },
    ]
    policy = {
        "exploration": {"enabled": False},
        "delivery": {
            "surfaces": ["daily"],
            "preferred_surfaces": ["daily"],
        },
    }
    before = copy.deepcopy(items)

    daily = select_ambient_items(items, "daily", policy=policy, limit=5)
    critical = select_ambient_items(items, "critical", policy=policy, limit=5)

    assert items == before
    assert [item["id"] for item in daily["items"]] == ["critical-daily-fallback"]
    assert critical["items"] == []
    decision = daily["items"][0]["delivery_decision"]
    assert decision["surface"] == "daily"
    assert decision["canonical_surface"] == "critical"
    assert decision["eligible_surfaces"] == ["daily"]
    assert decision["preferred_surfaces"] == ["daily"]
    assert decision["surface_preference"]["selection_reason"] == "matched_user_surface_preference"
    assert decision["surface_preference"]["post_ranking_only"] is True
    assert decision["ranking_snapshot"]["input_ensemble_score"] == before[0]["ensemble_score"]
    assert daily["items"][0]["ensemble_score"] == before[0]["ensemble_score"]
    assert daily["items"][0]["final_score"] == before[0]["final_score"]
    assert daily["items"][0]["pre_layer_ranking"]["input_order"] == before[0]["feed_position"]


def test_disabled_or_globally_disabled_surfaces_are_suppressed_before_selection():
    from hedwig.delivery.ambient import select_ambient_items

    items = _ranked_items()
    before = copy.deepcopy(items)
    daily_only_policy = {
        "exploration": {"enabled": False},
        "delivery": {
            "enabled": True,
            "surfaces": ["daily"],
            "preferred_surfaces": ["daily"],
        },
    }
    disabled_policy = {
        "exploration": {"enabled": False},
        "delivery": {
            "enabled": False,
            "surfaces": ["critical", "daily", "weekly", "pwa", "tray"],
            "preferred_surfaces": ["daily"],
        },
    }

    disabled_pwa = select_ambient_items(items, "pwa", policy=daily_only_policy, limit=5)
    disabled_tray = select_ambient_items(items, "native", policy=daily_only_policy, limit=5)
    globally_disabled = select_ambient_items(items, "daily", policy=disabled_policy, limit=5)

    assert items == before
    assert disabled_pwa["surface"] == "pwa"
    assert disabled_pwa["entry_point"]["enabled"] is False
    assert disabled_pwa["items"] == []
    assert disabled_pwa["selection_suppression"] == {
        "schema_version": "ambient_surface_selection_suppression.v1",
        "reason": "surface_disabled",
        "surface": "pwa",
        "post_ranking_only": True,
        "ranking_input": False,
        "mutates_scores": False,
        "mutates_rank_identity": False,
    }

    assert disabled_tray["surface"] == "tray"
    assert disabled_tray["requested_surface"] == "tray"
    assert disabled_tray["entry_point"]["enabled"] is False
    assert disabled_tray["items"] == []
    assert disabled_tray["selection_suppression"]["reason"] == "surface_disabled"
    assert disabled_tray["selection_suppression"]["ranking_input"] is False

    assert globally_disabled["surface"] == "daily"
    assert globally_disabled["entry_point"]["enabled"] is False
    assert globally_disabled["items"] == []
    assert globally_disabled["selection_suppression"]["reason"] == "delivery_policy_disabled"
    assert globally_disabled["selection_suppression"]["mutates_scores"] is False


def test_unsupported_ambient_surface_is_rejected_before_item_selection():
    from hedwig.delivery.ambient import select_ambient_items

    items = _ranked_items()
    before = copy.deepcopy(items)

    with pytest.raises(ValueError, match="unknown ambient surface: sms"):
        select_ambient_items(items, "sms")

    assert items == before


def test_quiet_hours_defer_scheduled_candidates_without_score_or_rank_mutation():
    from hedwig.delivery.ambient import select_ambient_items

    items = [
        {
            "id": "quiet-critical",
            "title": "Critical during quiet hours",
            "ensemble_score": 0.93,
            "final_score": 0.92,
            "ensemble_rank": 1,
            "feed_position": 0,
            "urgency": "alert",
        },
        {
            "id": "quiet-daily",
            "title": "Daily during quiet hours",
            "ensemble_score": 0.72,
            "final_score": 0.71,
            "ensemble_rank": 2,
            "feed_position": 1,
            "urgency": "digest",
        },
    ]
    policy = {
        "exploration": {"enabled": False},
        "delivery": {
            "timing": {"daily_digest_time": "21:00", "defer_to_quiet_hours": True},
            "quiet_hours": {
                "enabled": True,
                "start": "22:00",
                "end": "07:00",
                "allow_critical_override": True,
            },
        },
    }
    before = copy.deepcopy(items)
    scheduler_context = {"current_time": "23:30", "weekday": "monday"}

    daily = select_ambient_items(items, "daily", policy=policy, client_context=scheduler_context)
    critical = select_ambient_items(items, "critical", policy=policy, client_context=scheduler_context)
    blocked_critical = select_ambient_items(
        items,
        "critical",
        policy={
            "exploration": {"enabled": False},
            "delivery": {
                "timing": {"defer_to_quiet_hours": True},
                "quiet_hours": {
                    "enabled": True,
                    "start": "22:00",
                    "end": "07:00",
                    "allow_critical_override": False,
                },
            },
        },
        client_context=scheduler_context,
    )

    assert items == before
    assert daily["items"] == []
    assert critical["items"][0]["id"] == "quiet-critical"
    decision = critical["items"][0]["delivery_decision"]
    assert decision["delivery_schedule"]["quiet_hours_active"] is True
    assert decision["delivery_schedule"]["quiet_hours_deferred"] is False
    assert decision["delivery_schedule"]["defer_reason"] == "critical_quiet_hours_override"
    assert decision["eligible_now"] is True
    assert critical["items"][0]["ensemble_score"] == before[0]["ensemble_score"]
    assert critical["items"][0]["final_score"] == before[0]["final_score"]
    assert critical["items"][0]["pre_layer_ranking"]["input_order"] == before[0]["feed_position"]
    assert blocked_critical["items"] == []


def test_quiet_hours_suppression_allows_only_critical_urgency_override_delivery():
    from hedwig.delivery.ambient import delivery_schedule_for_decision, select_ambient_items
    from hedwig.personal_algorithm import get_delivery_policy_config, route_items_after_ranking

    items = [
        {
            "id": "quiet-digest",
            "title": "Digest item suppressed during quiet hours",
            "ensemble_score": 0.74,
            "final_score": 0.73,
            "ensemble_rank": 1,
            "feed_position": 0,
            "urgency": "digest",
        },
        {
            "id": "quiet-alert",
            "title": "Alert item can override quiet hours",
            "ensemble_score": 0.86,
            "final_score": 0.85,
            "ensemble_rank": 2,
            "feed_position": 1,
            "urgency": "alert",
        },
    ]
    policy = {
        "exploration": {"enabled": False},
        "delivery": {
            "timing": {"daily_digest_time": "08:00", "defer_to_quiet_hours": True},
            "quiet_hours": {
                "enabled": True,
                "start": "22:00",
                "end": "07:00",
                "allow_critical_override": True,
            },
            "urgency": {"critical_score_threshold": 0.85, "daily_score_threshold": 0.65},
        },
    }
    client_context = {"current_time": "23:15", "weekday": "tuesday"}
    before = copy.deepcopy(items)

    routed = route_items_after_ranking(items, policy=policy)
    policy_config = get_delivery_policy_config(policy)
    schedules = {
        item["id"]: delivery_schedule_for_decision(
            item["delivery_decision"],
            policy_config,
            client_context=client_context,
        )
        for item in routed
    }
    daily = select_ambient_items(items, "daily", policy=policy, client_context=client_context, limit=5)
    critical = select_ambient_items(items, "critical", policy=policy, client_context=client_context, limit=5)

    assert items == before
    assert daily["items"] == []
    assert [item["id"] for item in critical["items"]] == ["quiet-alert"]

    digest_schedule = schedules["quiet-digest"]
    assert digest_schedule["quiet_hours_active"] is True
    assert digest_schedule["quiet_hours_deferred"] is True
    assert digest_schedule["eligible_now"] is False
    assert digest_schedule["defer_reason"] == "quiet_hours"

    alert_schedule = critical["items"][0]["delivery_decision"]["delivery_schedule"]
    assert alert_schedule["quiet_hours_active"] is True
    assert alert_schedule["quiet_hours_deferred"] is False
    assert alert_schedule["eligible_now"] is True
    assert alert_schedule["defer_reason"] == "critical_quiet_hours_override"
    assert alert_schedule["scheduling_priority"]["urgency"] == "alert"
    assert critical["items"][0]["ensemble_score"] == before[1]["ensemble_score"]
    assert critical["items"][0]["final_score"] == before[1]["final_score"]
    assert critical["items"][0]["pre_layer_ranking"]["input_order"] == before[1]["feed_position"]
    assert critical["items"][0]["delivery_decision"]["ranking_snapshot"]["input_ensemble_score"] == before[1]["ensemble_score"]
    assert critical["items"][0]["delivery_decision"]["ranking_input"] is False


def test_daily_and_weekly_timing_windows_gate_scheduler_candidates_post_ranking():
    from hedwig.delivery.ambient import select_ambient_items

    items = [
        {
            "id": "timed-daily",
            "title": "Daily window candidate",
            "ensemble_score": 0.70,
            "final_score": 0.69,
            "ensemble_rank": 10,
            "feed_position": 0,
            "urgency": "digest",
        },
        {
            "id": "timed-weekly",
            "title": "Weekly window candidate",
            "ensemble_score": 0.40,
            "final_score": 0.39,
            "ensemble_rank": 11,
            "feed_position": 1,
            "urgency": "digest",
        },
    ]
    policy = {
        "exploration": {"enabled": False},
        "delivery": {
            "timing": {
                "daily_digest_time": "09:00",
                "weekly_digest_day": "friday",
                "weekly_digest_time": "17:30",
            },
        },
    }
    before = copy.deepcopy(items)

    daily_before = select_ambient_items(
        items,
        "daily",
        policy=policy,
        client_context={"current_time": "08:59", "weekday": "friday"},
    )
    daily_at_window = select_ambient_items(
        items,
        "daily",
        policy=policy,
        client_context={"current_time": "09:00", "weekday": "friday"},
    )
    weekly_wrong_day = select_ambient_items(
        items,
        "weekly",
        policy=policy,
        client_context={"current_time": "18:00", "weekday": "thursday"},
    )
    weekly_before = select_ambient_items(
        items,
        "weekly",
        policy=policy,
        client_context={"current_time": "17:29", "weekday": "friday"},
    )
    weekly_at_window = select_ambient_items(
        items,
        "weekly",
        policy=policy,
        client_context={"current_time": "17:30", "weekday": "friday"},
    )

    assert items == before
    assert daily_before["items"] == []
    assert [item["id"] for item in daily_at_window["items"]] == ["timed-daily"]
    assert weekly_wrong_day["items"] == []
    assert weekly_before["items"] == []
    assert [item["id"] for item in weekly_at_window["items"]] == ["timed-weekly"]

    daily_decision = daily_at_window["items"][0]["delivery_decision"]
    weekly_decision = weekly_at_window["items"][0]["delivery_decision"]
    assert daily_decision["delivery_schedule"]["target_time"] == "09:00"
    assert daily_decision["delivery_schedule"]["eligible_now"] is True
    assert weekly_decision["delivery_schedule"]["target_day"] == "friday"
    assert weekly_decision["delivery_schedule"]["target_time"] == "17:30"
    assert weekly_decision["delivery_schedule"]["eligible_now"] is True
    assert daily_at_window["items"][0]["ensemble_score"] == before[0]["ensemble_score"]
    assert weekly_at_window["items"][0]["final_score"] == before[1]["final_score"]
    assert weekly_at_window["items"][0]["pre_layer_ranking"]["input_order"] == before[1]["feed_position"]


def test_urgency_drives_scheduler_priority_within_policy_limits_without_rank_mutation():
    from hedwig.delivery.ambient import delivery_schedule_for_decision, select_ambient_items
    from hedwig.personal_algorithm import get_delivery_policy_config, route_items_after_ranking

    items = [
        {
            "id": "digest-first",
            "title": "Higher ranked digest item waits for digest window",
            "ensemble_score": 0.84,
            "final_score": 0.84,
            "ensemble_rank": 1,
            "feed_position": 0,
            "urgency": "digest",
        },
        {
            "id": "urgent-second",
            "title": "Lower ranked urgent item can be scheduled sooner",
            "ensemble_score": 0.86,
            "final_score": 0.86,
            "ensemble_rank": 2,
            "feed_position": 1,
            "urgency": "alert",
        },
    ]
    policy = {
        "exploration": {"enabled": False},
        "delivery": {
            "timing": {"daily_digest_time": "09:00", "defer_to_quiet_hours": True},
            "quiet_hours": {
                "enabled": True,
                "start": "22:00",
                "end": "07:00",
                "allow_critical_override": False,
            },
            "urgency": {"critical_score_threshold": 0.85, "daily_score_threshold": 0.65},
        },
    }
    before = copy.deepcopy(items)

    routed = route_items_after_ranking(items, policy=policy)
    policy_config = get_delivery_policy_config(policy)
    digest_schedule = delivery_schedule_for_decision(
        routed[0]["delivery_decision"],
        policy_config,
        client_context={"current_time": "08:00", "weekday": "monday"},
    )
    daily_before_digest = select_ambient_items(
        items,
        "daily",
        policy=policy,
        client_context={"current_time": "08:00", "weekday": "monday"},
    )
    critical_before_digest = select_ambient_items(
        items,
        "critical",
        policy=policy,
        client_context={"current_time": "08:00", "weekday": "monday"},
    )
    critical_quiet_hours = select_ambient_items(
        items,
        "critical",
        policy=policy,
        client_context={"current_time": "23:00", "weekday": "monday"},
    )

    assert items == before
    assert [item["id"] for item in routed] == ["digest-first", "urgent-second"]
    assert daily_before_digest["items"] == []
    assert [item["id"] for item in critical_before_digest["items"]] == ["urgent-second"]
    assert critical_quiet_hours["items"] == []

    urgent_decision = critical_before_digest["items"][0]["delivery_decision"]
    urgent_schedule = urgent_decision["delivery_schedule"]
    assert urgent_schedule["priority_tier"] == "immediate"
    assert urgent_schedule["scheduling_priority"]["urgency"] == "alert"
    assert urgent_schedule["priority"] < digest_schedule["priority"]
    assert urgent_schedule["eligible_now"] is True
    assert urgent_decision["ranking_input"] is False
    assert urgent_decision["ranking_output"] is False
    assert urgent_decision["ranking_snapshot"]["input_order"] == before[1]["feed_position"]
    assert critical_before_digest["items"][0]["ensemble_score"] == before[1]["ensemble_score"]
    assert critical_before_digest["items"][0]["final_score"] == before[1]["final_score"]


def test_repeat_frequency_caps_suppress_or_delay_previous_deliveries_without_rank_mutation():
    from hedwig.delivery.ambient import delivery_schedule_for_decision, select_ambient_items
    from hedwig.personal_algorithm import get_delivery_policy_config, route_items_after_ranking

    items = [
        {
            "id": "repeat-maxed",
            "title": "Already delivered twice",
            "ensemble_score": 0.72,
            "final_score": 0.95,
            "ensemble_rank": 1,
            "feed_position": 0,
            "urgency": "digest",
        },
        {
            "id": "repeat-interval",
            "title": "Delivered too recently",
            "ensemble_score": 0.71,
            "final_score": 0.94,
            "ensemble_rank": 2,
            "feed_position": 1,
            "urgency": "digest",
        },
        {
            "id": "repeat-snoozed",
            "title": "User snoozed this item",
            "ensemble_score": 0.70,
            "final_score": 0.93,
            "ensemble_rank": 3,
            "feed_position": 2,
            "urgency": "digest",
        },
        {
            "id": "repeat-ok",
            "title": "Eligible daily item",
            "ensemble_score": 0.69,
            "final_score": 0.92,
            "ensemble_rank": 4,
            "feed_position": 3,
            "urgency": "digest",
        },
    ]
    before = copy.deepcopy(items)
    policy = {
        "exploration": {"enabled": False},
        "delivery": {
            "repeat": {
                "enabled": True,
                "max_count": 2,
                "min_interval_minutes": 240,
                "snooze_minutes": 60,
            },
            "urgency": {"critical_score_threshold": 0.90, "daily_score_threshold": 0.65},
        },
    }
    client_context = {
        "now": "2026-05-14T10:00:00",
        "ambient_delivery_events": [
            {"signal_id": "repeat-maxed", "event_type": "delivered", "captured_at": "2026-05-12T09:00:00"},
            {"signal_id": "repeat-maxed", "event_type": "delivered", "captured_at": "2026-05-13T09:00:00"},
            {"signal_id": "repeat-interval", "event_type": "delivered", "captured_at": "2026-05-14T08:30:00"},
            {"signal_id": "repeat-snoozed", "event_type": "snoozed", "captured_at": "2026-05-14T09:30:00"},
        ],
    }

    daily = select_ambient_items(items, "daily", policy=policy, limit=10, client_context=client_context)
    routed = route_items_after_ranking(items, policy=policy)
    policy_config = get_delivery_policy_config(policy)
    schedules = {
        item["id"]: delivery_schedule_for_decision(
            item["delivery_decision"],
            policy_config,
            client_context=client_context,
        )
        for item in routed
    }

    assert items == before
    assert [item["id"] for item in daily["items"]] == ["repeat-ok"]
    assert schedules["repeat-maxed"]["eligible_now"] is False
    assert schedules["repeat-maxed"]["defer_reason"] == "repeat_max_count"
    assert schedules["repeat-maxed"]["repeat_state"]["delivered_count"] == 2
    assert schedules["repeat-maxed"]["frequency_cap_suppressed"] is True
    assert schedules["repeat-interval"]["eligible_now"] is False
    assert schedules["repeat-interval"]["defer_reason"] == "repeat_min_interval"
    assert schedules["repeat-interval"]["repeat_state"]["minutes_since_last_delivery"] == 90
    assert schedules["repeat-interval"]["frequency_cap_deferred"] is True
    assert schedules["repeat-snoozed"]["eligible_now"] is False
    assert schedules["repeat-snoozed"]["defer_reason"] == "snoozed"
    assert schedules["repeat-snoozed"]["repeat_state"]["minutes_since_last_snooze"] == 30
    assert daily["items"][0]["ensemble_score"] == before[3]["ensemble_score"]
    assert daily["items"][0]["final_score"] == before[3]["final_score"]
    assert daily["items"][0]["pre_layer_ranking"]["input_order"] == before[3]["feed_position"]
    assert daily["items"][0]["delivery_decision"]["ranking_input"] is False


def test_repeat_history_deduplicates_same_delivery_event_before_redelivery_limit():
    from hedwig.delivery.ambient import delivery_schedule_for_decision, select_ambient_items
    from hedwig.personal_algorithm import get_delivery_policy_config, route_items_after_ranking

    items = [
        {
            "id": "deduped-repeat",
            "title": "Duplicate history should count once",
            "ensemble_score": 0.74,
            "final_score": 0.74,
            "ensemble_rank": 1,
            "feed_position": 0,
            "urgency": "digest",
        },
        {
            "id": "distinct-repeat",
            "title": "Distinct history should hit the limit",
            "ensemble_score": 0.73,
            "final_score": 0.73,
            "ensemble_rank": 2,
            "feed_position": 1,
            "urgency": "digest",
        },
    ]
    before = copy.deepcopy(items)
    policy = {
        "exploration": {"enabled": False},
        "delivery": {
            "repeat": {
                "enabled": True,
                "max_count": 2,
                "min_interval_minutes": 60,
                "snooze_minutes": 30,
            },
            "urgency": {"daily_score_threshold": 0.65},
        },
    }
    client_context = {
        "now": "2026-05-14T10:00:00",
        "ambient_delivery_events": [
            {"id": "delivery-1", "signal_id": "deduped-repeat", "event_type": "delivered", "captured_at": "2026-05-13T08:00:00"},
            {"id": "delivery-1", "signal_id": "deduped-repeat", "event_type": "delivered", "captured_at": "2026-05-13T08:00:00"},
            {"id": "delivery-2", "signal_id": "distinct-repeat", "event_type": "delivered", "captured_at": "2026-05-12T08:00:00"},
            {"id": "delivery-3", "signal_id": "distinct-repeat", "event_type": "delivered", "captured_at": "2026-05-13T08:00:00"},
        ],
    }

    daily = select_ambient_items(items, "daily", policy=policy, limit=5, client_context=client_context)
    routed = route_items_after_ranking(items, policy=policy)
    policy_config = get_delivery_policy_config(policy)
    schedules = {
        item["id"]: delivery_schedule_for_decision(
            item["delivery_decision"],
            policy_config,
            client_context=client_context,
        )
        for item in routed
    }

    assert items == before
    assert [item["id"] for item in daily["items"]] == ["deduped-repeat"]
    assert schedules["deduped-repeat"]["repeat_state"]["delivered_count"] == 1
    assert schedules["deduped-repeat"]["eligible_now"] is True
    assert schedules["deduped-repeat"]["frequency_cap_suppressed"] is False
    assert schedules["distinct-repeat"]["repeat_state"]["delivered_count"] == 2
    assert schedules["distinct-repeat"]["eligible_now"] is False
    assert schedules["distinct-repeat"]["defer_reason"] == "repeat_max_count"
    assert schedules["distinct-repeat"]["frequency_cap_suppressed"] is True
    assert daily["items"][0]["ensemble_score"] == before[0]["ensemble_score"]
    assert daily["items"][0]["final_score"] == before[0]["final_score"]
    assert daily["items"][0]["delivery_decision"]["delivery_schedule"]["post_ranking_only"] is True
    assert daily["items"][0]["delivery_decision"]["delivery_schedule"]["ranking_input"] is False


def test_ambient_api_uses_persisted_delivery_events_for_repeat_caps(tmp_env, monkeypatch):
    import hedwig.dashboard.app as dashboard_app

    ranked = [
        {
            "id": "persisted-repeat",
            "title": "Persisted repeat candidate",
            "ensemble_score": 0.72,
            "final_score": 0.72,
            "ensemble_rank": 1,
            "urgency": "digest",
        }
    ]
    monkeypatch.setattr(dashboard_app, "_load_ranked_feed_items", lambda days=14: copy.deepcopy(ranked))
    client = TestClient(dashboard_app.create_app())

    first = client.get("/ambient/daily/api?limit=1")
    second = client.get("/ambient/daily/api?limit=1")
    third = client.get("/ambient/daily/api?limit=1")

    assert first.status_code == 200
    assert second.status_code == 200
    assert third.status_code == 200
    assert [item["id"] for item in first.json()["items"]] == ["persisted-repeat"]
    assert [item["id"] for item in second.json()["items"]] == ["persisted-repeat"]
    assert third.json()["items"] == []


def test_pwa_installed_standalone_context_routes_to_pwa_shelf_without_score_mutation():
    from hedwig.delivery.ambient import select_ambient_items

    items = _ranked_items()
    before = copy.deepcopy(items)

    pwa = select_ambient_items(
        items,
        "pwa",
        client_context={
            "display_mode": "standalone",
            "installed": "true",
            "supports_service_worker": "true",
            "supports_manifest": "true",
        },
    )

    assert pwa["surface"] == "pwa"
    assert pwa["requested_surface"] == "pwa"
    assert pwa["client_route"]["resolved_surface"] == "pwa"
    assert pwa["client_route"]["fallback"] is False
    assert pwa["client_route"]["manual_feed_entry_required"] is False
    assert pwa["entry_point"]["page_path"] == "/ambient/pwa"
    assert pwa["entry_point"]["request_path"] == "/ambient/pwa/api"
    assert pwa["count"] == 1
    assert pwa["items"][0]["id"] == "pwa-1"
    assert pwa["items"][0]["delivery_decision"]["surface"] == "pwa"
    assert pwa["items"][0]["delivery_decision"]["decision_layer"] == "post_ranking_delivery"
    assert pwa["items"][0]["delivery_decision"]["ranking_input"] is False
    assert pwa["items"][0]["delivery_decision"]["ranking_output"] is False
    assert pwa["items"][0]["ensemble_score"] == before[3]["ensemble_score"]
    assert pwa["items"][0]["final_score"] == before[3]["final_score"]
    assert pwa["items"][0]["pre_layer_ranking"]["input_order"] == 3
    assert pwa["items"][0]["delivery_decision"]["ranking_snapshot"]["input_ensemble_score"] == before[3]["ensemble_score"]
    assert pwa["items"][0]["delivery_decision"]["ranking_snapshot"]["input_final_score"] == before[3]["final_score"]
    assert items == before


def test_pwa_unsupported_browser_falls_back_to_daily_ambient_route_not_manual_feed(tmp_env, monkeypatch):
    from hedwig.delivery.ambient import select_ambient_items
    import hedwig.dashboard.app as dashboard_app

    items = _ranked_items()
    before = copy.deepcopy(items)
    unsupported_context = {
        "display_mode": "browser",
        "supports_service_worker": "false",
        "supports_manifest": "false",
    }

    fallback = select_ambient_items(items, "pwa", client_context=unsupported_context, limit=1)

    assert fallback["surface"] == "daily"
    assert fallback["requested_surface"] == "pwa"
    assert fallback["client_route"]["resolved_surface"] == "daily"
    assert fallback["client_route"]["fallback"] is True
    assert fallback["client_route"]["manual_feed_entry_required"] is False
    assert fallback["entry_point"]["page_path"] == "/ambient/daily"
    assert fallback["entry_point"]["request_path"] == "/ambient/daily/api"
    assert fallback["items"][0]["id"] == "daily-1"
    assert fallback["items"][0]["delivery_decision"]["surface"] == "daily"
    assert fallback["items"][0]["ensemble_score"] == before[1]["ensemble_score"]
    assert fallback["items"][0]["final_score"] == before[1]["final_score"]
    assert items == before

    monkeypatch.setattr(dashboard_app, "_load_ranked_feed_items", lambda days=14: copy.deepcopy(before))
    client = TestClient(dashboard_app.create_app())
    query = "limit=1&display_mode=browser&supports_service_worker=false&supports_manifest=false"

    api = client.get(f"/ambient/pwa/api?{query}")
    assert api.status_code == 200
    body = api.json()
    assert body["surface"] == "daily"
    assert body["requested_surface"] == "pwa"
    assert body["client_route"]["fallback"] is True
    assert body["entry_point"]["manual_feed_entry_required"] is False
    assert body["items"][0]["id"] == "daily-1"

    page = client.get(f"/ambient/pwa?{query}")
    assert page.status_code == 200
    assert "Daily" in page.text
    assert 'data-surface="daily"' in page.text
    assert "/feed?stream=critical_only" not in page.text
    assert "feed-shell" not in page.text


def test_unavailable_preferred_pwa_falls_back_to_available_ambient_surface_without_reranking():
    from hedwig.delivery.ambient import select_ambient_items
    from hedwig.personal_algorithm import (
        assert_delivery_rank_identity_unchanged,
        assert_delivery_scores_unchanged,
        route_items_after_ranking,
    )

    items = [
        {
            "id": "preferred-pwa-daily-fallback",
            "title": "Daily item survives unavailable preferred PWA",
            "url": "https://example.test/preferred-pwa-daily-fallback",
            "ensemble_score": 0.74,
            "final_score": 0.73,
            "ensemble_rank": 12,
            "feed_position": 0,
            "urgency": "digest",
        },
    ]
    policy = {
        "exploration": {"enabled": False},
        "delivery": {
            "surfaces": ["daily", "pwa"],
            "preferred_surfaces": ["pwa", "daily"],
        },
    }
    unsupported_pwa_context = {
        "display_mode": "browser",
        "supports_service_worker": "false",
        "supports_manifest": "false",
    }
    before = copy.deepcopy(items)

    routed = route_items_after_ranking(items, policy=policy)
    fallback = select_ambient_items(
        items,
        "pwa",
        policy=policy,
        client_context=unsupported_pwa_context,
        limit=5,
    )

    assert items == before
    assert_delivery_scores_unchanged(before, routed)
    assert_delivery_rank_identity_unchanged(before, routed)
    assert routed[0]["delivery_decision"]["surface"] == "pwa"

    assert fallback["surface"] == "daily"
    assert fallback["requested_surface"] == "pwa"
    assert fallback["client_route"]["fallback"] is True
    assert fallback["client_route"]["resolved_surface"] == "daily"
    assert fallback["client_route"]["manual_feed_entry_required"] is False
    assert [item["id"] for item in fallback["items"]] == ["preferred-pwa-daily-fallback"]

    decision = fallback["items"][0]["delivery_decision"]
    assert decision["surface"] == "daily"
    assert decision["canonical_surface"] == "daily"
    assert decision["surface_preference"]["preferred_surfaces"] == ["daily"]
    assert decision["surface_preference"]["selection_reason"] == "matched_user_surface_preference"
    assert decision["ranking_input"] is False
    assert decision["ranking_output"] is False
    assert fallback["items"][0]["ensemble_score"] == before[0]["ensemble_score"]
    assert fallback["items"][0]["final_score"] == before[0]["final_score"]
    assert fallback["items"][0]["pre_layer_ranking"]["input_order"] == before[0]["feed_position"]
    assert (
        fallback["items"][0]["delivery_decision"]["ranking_snapshot"]["input_ensemble_score"]
        == before[0]["ensemble_score"]
    )


def test_tray_native_routing_handles_available_unavailable_and_permission_denied_paths(tmp_env, monkeypatch):
    import hedwig.dashboard.app as dashboard_app

    from hedwig.delivery.ambient import resolve_ambient_surface_for_client, select_ambient_items

    items = _ranked_items()
    before = copy.deepcopy(items)

    available = select_ambient_items(
        items,
        "native",
        client_context={"native_available": "true", "notification_permission": "granted"},
    )
    assert available["surface"] == "tray"
    assert available["requested_surface"] == "tray"
    assert available["client_route"]["fallback"] is False
    assert available["client_route"]["native_available"] is True
    assert available["client_route"]["native_notifications_enabled"] is True
    assert [item["id"] for item in available["items"]] == ["critical-1", "daily-1", "pwa-1"]

    unavailable = select_ambient_items(
        items,
        "native",
        client_context={
            "native_available": "false",
            "display_mode": "standalone",
            "supports_service_worker": "true",
            "supports_manifest": "true",
        },
    )
    assert unavailable["surface"] == "pwa"
    assert unavailable["requested_surface"] == "tray"
    assert unavailable["client_route"]["fallback"] is True
    assert unavailable["client_route"]["manual_feed_entry_required"] is False
    assert unavailable["client_route"]["native_available"] is False
    assert [item["id"] for item in unavailable["items"]] == ["pwa-1"]

    denied = select_ambient_items(
        items,
        "native_notification",
        client_context={"supports_native": "true", "native_notification_permission": "denied"},
    )
    assert denied["surface"] == "tray"
    assert denied["requested_surface"] == "tray"
    assert denied["client_route"]["fallback"] is False
    assert denied["client_route"]["native_available"] is True
    assert denied["client_route"]["native_notification_permission"] == "denied"
    assert denied["client_route"]["native_notifications_enabled"] is False
    assert "permission denied" in denied["client_route"]["reason"]
    assert [item["id"] for item in denied["items"]] == ["critical-1", "daily-1", "pwa-1"]

    for payload in (available, unavailable, denied):
        assert payload["client_route"]["manual_feed_entry_required"] is False
        for delivered in payload["items"]:
            original = next(item for item in before if item["id"] == delivered["id"])
            assert delivered["ensemble_score"] == original["ensemble_score"]
            assert delivered["final_score"] == original["final_score"]
            assert delivered["delivery_decision"]["ranking_input"] is False
            assert delivered["delivery_decision"]["ranking_output"] is False
    assert items == before

    assert resolve_ambient_surface_for_client(
        "native",
        client_context={
            "native_available": "false",
            "display_mode": "browser",
            "supports_service_worker": "false",
            "supports_manifest": "false",
        },
    )["resolved_surface"] == "daily"

    monkeypatch.setattr(dashboard_app, "_load_ranked_feed_items", lambda days=14: copy.deepcopy(before))
    client = TestClient(dashboard_app.create_app())

    api = client.get(
        "/ambient/native/api"
        "?limit=1&native_available=false&display_mode=browser"
        "&supports_service_worker=false&supports_manifest=false"
    )
    assert api.status_code == 200
    body = api.json()
    assert body["surface"] == "daily"
    assert body["requested_surface"] == "tray"
    assert body["client_route"]["fallback"] is True
    assert body["client_route"]["manual_feed_entry_required"] is False
    assert body["items"][0]["id"] == "daily-1"

    page = client.get(
        "/ambient/native_notification"
        "?limit=2&native_available=true&native_notification_permission=denied"
    )
    assert page.status_code == 200
    assert "<strong>tray</strong>" in page.text
    assert 'data-feed-id="ambient:tray"' in page.text
    assert 'data-surface="critical"' in page.text
    assert 'data-surface="daily"' in page.text
    assert "Critical" in page.text
    assert "Daily" in page.text
    assert "feed-shell" not in page.text


def test_ambient_surface_docs_define_critical_trigger_and_ranking_boundary():
    doc = (PROJECT_ROOT / "docs" / "ambient_delivery_surfaces.md").read_text()
    normalized_doc = " ".join(doc.split())

    for surface in ("critical", "daily", "weekly", "pwa", "tray"):
        assert f"`{surface}`" in doc
    assert "## Critical Surface Contract" in doc
    assert '`delivery_decision.surface == "critical"`' in doc
    assert '`urgency == "alert"`' in doc
    assert "`ensemble_score >= 0.85`" in doc
    assert "`/ambient/critical/api`" in doc
    assert "`ambient_delivery_item_set.v1`" in doc
    assert "must not mutate `ensemble_score`, `final_score`" in doc
    assert "`pre_layer_ranking.input_order`" in doc
    assert "Explanations can help a user understand why an item appeared" in normalized_doc
    assert "not ranking inputs, scores, weights, labels, or authority for reordering" in normalized_doc
    assert "## Ranking Boundary: Ranked Output In, Routing Metadata Out" in doc
    assert "completed ranked outputs" in normalized_doc
    assert "read-only input and appends routing metadata" in normalized_doc
    assert "Routing consumes existing ranked outputs only" in normalized_doc
    assert "must not alter PR #18 / Gen 9 ranking logic, score computation, score ordering" in normalized_doc
    assert "outside issue #20 and must be handled as separate ranking work" in normalized_doc
    assert "`delivery_decision`" in doc
    assert "`delivery_policy`" in doc
    assert "`post_ranking_decisions.delivery`" in doc
    assert "compute, normalize, round, overwrite, or backfill `ensemble_score`" in doc
    assert "compute, normalize, round, overwrite, or backfill `final_score`" in doc
    assert "reorder the ranked item list or rewrite pre-layer order" in normalized_doc
    assert "`pre_layer_ranking.rank_identifiers`" in doc
    assert "Raw delivery behavior events are stored separately from derived rewards" in normalized_doc


def test_daily_surface_docs_define_cadence_selection_inputs_and_ranking_boundary():
    from hedwig.delivery.ambient import ambient_surface_entry_points

    doc = (PROJECT_ROOT / "docs" / "ambient_delivery_surfaces.md").read_text()
    normalized_doc = " ".join(doc.split())
    daily = {
        entry["surface"]: entry
        for entry in ambient_surface_entry_points()
    }["daily"]

    assert "## Daily Surface Contract" in doc
    assert "next daily digest run after ranking has completed" in normalized_doc
    assert '`delivery_decision.surface == "daily"`' in doc
    assert "`ensemble_score >= 0.65`" in doc
    assert "`ensemble_score >= 0.85`" in doc
    assert "`urgency == \"alert\"`" in doc
    assert "`final_score`" in doc
    assert "`pre_layer_ranking`" in doc
    assert "`ambient_delivery_item_set.v1`" in doc
    assert "limit of 5 items" in normalized_doc
    assert "must not mutate `ensemble_score`, `final_score`, or `pre_layer_ranking`" in normalized_doc
    assert "must not become a score, ranking feature, authority label, or input to reorder" in normalized_doc

    assert daily["cadence"] == "next daily digest run"
    assert daily["selection_rule"] == "delivery_decision.surface == daily"
    assert daily["default_limit"] == 5
    assert daily["post_ranking_only"] is True
    assert daily["post_ranking_boundary"]["mutates_scores"] is False
    assert daily["post_ranking_boundary"]["mutates_rank_identity"] is False
    assert daily["item_selection_inputs"] == [
        "completed ensemble_score",
        "completed final_score",
        "urgency",
        "pre_layer_ranking rank identity",
        "delivery_decision.surface",
    ]


def test_weekly_surface_docs_define_routing_cadence_aggregation_and_ranking_boundary():
    from hedwig.delivery.ambient import ambient_surface_entry_points

    doc = (PROJECT_ROOT / "docs" / "ambient_delivery_surfaces.md").read_text()
    normalized_doc = " ".join(doc.split())
    weekly = {
        entry["surface"]: entry
        for entry in ambient_surface_entry_points()
    }["weekly"]

    assert "## Weekly Surface Contract" in doc
    assert "next weekly review run after ranking has completed" in normalized_doc
    assert "Weekly aggregation is a delivery packaging step, not a second ranking pass" in normalized_doc
    assert '`delivery_decision.surface == "weekly"`' in doc
    assert "`/ambient/weekly/api`" in doc
    assert "`ambient_delivery_item_set.v1`" in doc
    assert "limit of 8 items" in normalized_doc
    assert "must preserve pre-layer item order" in normalized_doc
    assert "must not deduplicate, promote, suppress, cluster, or summarize items" in normalized_doc
    assert "must not mutate `ensemble_score`, `final_score`, or `pre_layer_ranking`" in normalized_doc
    assert "must not become a score, ranking feature, authority label, or input to reorder" in normalized_doc

    assert weekly["cadence"] == "next weekly review run"
    assert weekly["selection_rule"] == "delivery_decision.surface == weekly"
    assert weekly["aggregation_behavior"] == (
        "group already-ranked lower-urgency catch-up items into a compact weekly review batch"
    )
    assert weekly["default_limit"] == 8
    assert weekly["post_ranking_only"] is True
    assert weekly["post_ranking_boundary"]["mutates_scores"] is False
    assert weekly["post_ranking_boundary"]["mutates_rank_identity"] is False
    assert weekly["item_selection_inputs"] == [
        "completed ensemble_score",
        "completed final_score",
        "urgency",
        "pre_layer_ranking rank identity",
        "delivery_decision.surface",
    ]


def test_tray_native_docs_define_eligibility_aliases_metadata_and_ranking_boundary():
    from hedwig.delivery.ambient import ambient_surface_entry_points, normalize_ambient_surface

    doc = (PROJECT_ROOT / "docs" / "ambient_delivery_surfaces.md").read_text()
    normalized_doc = " ".join(doc.split())
    tray = {
        entry["surface"]: entry
        for entry in ambient_surface_entry_points()
    }["tray"]

    assert "## Tray / Native Surface Contract" in doc
    assert "`native` and `native_notification` normalize to the same tray requester surface" in normalized_doc
    assert '`delivery_decision.surface in {"critical", "daily", "pwa"}`' in doc
    assert "`/ambient/tray/api`" in doc
    assert "`ambient_delivery_item_set.v1`" in doc
    assert "limit of 4 items" in normalized_doc
    assert "Weekly catch-up items are intentionally excluded" in normalized_doc
    assert "critical items must not jump ahead of earlier ranked daily or PWA items" in normalized_doc
    assert "must not mutate `ensemble_score`, `final_score`, or `pre_layer_ranking`" in normalized_doc
    assert "each item retains its original `delivery_decision.surface`" in normalized_doc
    assert 'entry_point.aliases == ["native", "native_notification"]' in doc
    assert 'entry_point.eligible_surfaces == ["critical", "daily", "pwa"]' in doc
    assert "Raw tray behavior events" in normalized_doc
    assert "remain separate from derived reward signals" in normalized_doc
    assert "must not become a ranking feature, score proxy, authority label, or input to tray ordering" in normalized_doc

    assert normalize_ambient_surface("native") == "tray"
    assert normalize_ambient_surface("native_notification") == "tray"
    assert tray["selection_rule"] == (
        "delivery_decision.surface in {critical, daily, pwa}, preserving pre-layer rank order"
    )
    assert tray["aliases"] == ["native", "native_notification"]
    assert tray["eligible_surfaces"] == ["critical", "daily", "pwa"]
    assert tray["default_limit"] == 4
    assert tray["post_ranking_only"] is True
    assert tray["post_ranking_boundary"]["mutates_scores"] is False
    assert tray["post_ranking_boundary"]["mutates_rank_identity"] is False
    assert tray["item_selection_inputs"] == [
        "completed ensemble_score",
        "completed final_score",
        "pre_layer_ranking rank identity",
        "delivery_decision.surface",
    ]


def test_ambient_item_selection_preserves_ranking_boundary():
    from hedwig.delivery.ambient import select_ambient_items
    from hedwig.models import AmbientDeliveryItemSet

    items = _ranked_items()
    items[1]["score"] = 999
    items[1]["relevance_score"] = 999
    before = copy.deepcopy(items)
    daily = select_ambient_items(items, "daily")
    tray = select_ambient_items(items, "native_notification")

    AmbientDeliveryItemSet.model_validate(daily)
    assert daily["schema_version"] == "ambient_delivery_item_set.v1"
    assert daily["limit"] == 5
    assert daily["count"] == 1
    assert items == before
    assert [item["id"] for item in daily["items"]] == ["daily-1"]
    assert daily["items"][0]["ensemble_score"] == before[1]["ensemble_score"]
    assert daily["items"][0]["final_score"] == before[1]["final_score"]
    assert daily["items"][0]["pre_layer_ranking"]["ensemble_score"] == before[1]["ensemble_score"]
    assert daily["items"][0]["pre_layer_ranking"]["final_score"] == before[1]["final_score"]
    assert daily["items"][0]["delivery_decision"]["ranking_snapshot"]["input_ensemble_score"] == before[1]["ensemble_score"]
    assert daily["items"][0]["delivery_decision"]["ranking_snapshot"]["input_final_score"] == before[1]["final_score"]
    assert daily["items"][0]["pre_layer_ranking"]["input_rank"] == before[1]["ensemble_rank"]
    assert daily["items"][0]["pre_layer_ranking"]["input_order"] == 1
    assert daily["items"][0]["pre_layer_ranking"]["rank_identifiers"]["id"] == before[1]["id"]
    assert daily["items"][0]["pre_layer_ranking"]["rank_identifiers"]["ensemble_rank"] == before[1]["ensemble_rank"]
    assert daily["items"][0]["delivery_decision"]["ranking_snapshot"]["input_order"] == 1
    assert daily["items"][0]["delivery_decision"]["ranking_snapshot"]["rank_identifiers"]["id"] == before[1]["id"]
    assert daily["post_ranking_boundary"]["mutates_rank_identity"] is False
    assert [item["id"] for item in tray["items"]] == ["critical-1", "daily-1", "pwa-1"]


@pytest.mark.parametrize(
    (
        "surface",
        "expected_ids",
        "expected_entry_kind",
        "expected_selection_rule",
        "expected_decision_surfaces",
    ),
    [
        (
            "critical",
            ["critical-1"],
            "receiver",
            "delivery_decision.surface == critical",
            ["critical"],
        ),
        (
            "daily",
            ["daily-1"],
            "receiver",
            "delivery_decision.surface == daily",
            ["daily"],
        ),
        (
            "weekly",
            ["weekly-1"],
            "receiver",
            "delivery_decision.surface == weekly",
            ["weekly"],
        ),
        (
            "pwa",
            ["pwa-1"],
            "requester",
            "delivery_decision.surface == pwa",
            ["pwa"],
        ),
        (
            "tray",
            ["critical-1", "daily-1", "pwa-1"],
            "requester",
            "delivery_decision.surface in {critical, daily, pwa}, preserving pre-layer rank order",
            ["critical", "daily", "pwa"],
        ),
    ],
)
def test_supported_ambient_surface_routing_matrix_selects_expected_items(
    surface,
    expected_ids,
    expected_entry_kind,
    expected_selection_rule,
    expected_decision_surfaces,
):
    from hedwig.delivery.ambient import ambient_surface_entry_points, select_ambient_items
    from hedwig.models import AmbientDeliveryItemSet

    supported_surfaces = {entry["surface"] for entry in ambient_surface_entry_points()}
    assert supported_surfaces == {"critical", "daily", "weekly", "pwa", "tray"}
    assert surface in supported_surfaces

    items = _ranked_items()
    before = {item["id"]: copy.deepcopy(item) for item in items}

    payload = select_ambient_items(items, surface, limit=10)

    AmbientDeliveryItemSet.model_validate(payload)
    assert payload["surface"] == surface
    assert payload["requested_surface"] == surface
    assert payload["client_route"]["resolved_surface"] == surface
    assert payload["client_route"]["manual_feed_entry_required"] is False
    assert payload["entry_point"]["entry_kind"] == expected_entry_kind
    assert payload["entry_point"]["selection_rule"] == expected_selection_rule
    assert payload["entry_point"]["post_ranking_boundary"]["mutates_scores"] is False
    assert payload["entry_point"]["post_ranking_boundary"]["mutates_rank_identity"] is False
    assert payload["post_ranking_boundary"]["mutates_scores"] is False
    assert payload["post_ranking_boundary"]["mutates_rank_identity"] is False
    assert [item["id"] for item in payload["items"]] == expected_ids
    assert [
        item["delivery_decision"]["surface"]
        for item in payload["items"]
    ] == expected_decision_surfaces

    for processed in payload["items"]:
        original = before[processed["id"]]
        assert processed["ensemble_score"] == original["ensemble_score"]
        assert processed["final_score"] == original["final_score"]
        assert processed["pre_layer_ranking"]["input_rank"] == original["ensemble_rank"]
        assert processed["pre_layer_ranking"]["input_order"] == list(before).index(processed["id"])
        assert processed["delivery_decision"]["decision_layer"] == "post_ranking_delivery"
        assert processed["delivery_decision"]["ranking_input"] is False
        assert processed["delivery_decision"]["ranking_output"] is False
        assert (
            processed["delivery_decision"]["ranking_snapshot"]["input_ensemble_score"]
            == original["ensemble_score"]
        )
        assert (
            processed["delivery_decision"]["ranking_snapshot"]["input_final_score"]
            == original["final_score"]
        )

    assert items == list(before.values())


def test_ambient_routing_preserves_gen9_order_thresholds_and_ties_without_reranking():
    from hedwig.delivery.ambient import select_ambient_items
    from hedwig.models import AmbientDeliveryItemSet

    ranked_items = [
        {
            "id": "daily-tie-first",
            "title": "First tied daily item",
            "url": "https://example.test/daily-tie-first",
            "ensemble_score": 0.70,
            "final_score": 0.10,
            "ensemble_rank": 40,
            "feed_position": 0,
            "urgency": "digest",
            "pre_layer_ranking": {
                "input_rank": 40,
                "input_order": 0,
                "rank_identifiers": {"ranking_run_id": "pr18-gen9-boundary", "rank_slot": "slot-a"},
                "immutable": True,
            },
        },
        {
            "id": "critical-threshold",
            "title": "Critical threshold item remains second",
            "url": "https://example.test/critical-threshold",
            "ensemble_score": 0.85,
            "final_score": 0.20,
            "ensemble_rank": 10,
            "feed_position": 1,
            "urgency": "digest",
            "pre_layer_ranking": {
                "input_rank": 10,
                "input_order": 1,
                "rank_identifiers": {"ranking_run_id": "pr18-gen9-boundary", "rank_slot": "slot-b"},
                "immutable": True,
            },
        },
        {
            "id": "daily-lower-threshold",
            "title": "Daily lower threshold item",
            "url": "https://example.test/daily-lower-threshold",
            "ensemble_score": 0.65,
            "final_score": 0.60,
            "ensemble_rank": 30,
            "feed_position": 2,
            "urgency": "digest",
            "pre_layer_ranking": {
                "input_rank": 30,
                "input_order": 2,
                "rank_identifiers": {"ranking_run_id": "pr18-gen9-boundary", "rank_slot": "slot-c"},
                "immutable": True,
            },
        },
        {
            "id": "daily-tie-second",
            "title": "Second tied daily item has higher final score",
            "url": "https://example.test/daily-tie-second",
            "ensemble_score": 0.70,
            "final_score": 0.99,
            "ensemble_rank": 20,
            "feed_position": 3,
            "urgency": "digest",
            "pre_layer_ranking": {
                "input_rank": 20,
                "input_order": 3,
                "rank_identifiers": {"ranking_run_id": "pr18-gen9-boundary", "rank_slot": "slot-d"},
                "immutable": True,
            },
        },
        {
            "id": "weekly-below-threshold",
            "title": "Below daily threshold item",
            "url": "https://example.test/weekly-below-threshold",
            "ensemble_score": 0.649999,
            "final_score": 0.95,
            "ensemble_rank": 50,
            "feed_position": 4,
            "urgency": "digest",
            "pre_layer_ranking": {
                "input_rank": 50,
                "input_order": 4,
                "rank_identifiers": {"ranking_run_id": "pr18-gen9-boundary", "rank_slot": "slot-e"},
                "immutable": True,
            },
        },
        {
            "id": "critical-alert-tail",
            "title": "Alert critical item stays in tail position",
            "url": "https://example.test/critical-alert-tail",
            "ensemble_score": 0.20,
            "final_score": 0.90,
            "ensemble_rank": 60,
            "feed_position": 5,
            "urgency": "alert",
            "pre_layer_ranking": {
                "input_rank": 60,
                "input_order": 5,
                "rank_identifiers": {"ranking_run_id": "pr18-gen9-boundary", "rank_slot": "slot-f"},
                "immutable": True,
            },
        },
    ]
    policy = {
        "exploration": {"enabled": False},
        "delivery": {"default_channel": "dashboard", "repeat": {"enabled": True, "max_count": 2}},
    }
    before = copy.deepcopy(ranked_items)

    daily = select_ambient_items(ranked_items, "daily", policy=policy, limit=10)
    critical = select_ambient_items(ranked_items, "critical", policy=policy, limit=10)
    weekly = select_ambient_items(ranked_items, "weekly", policy=policy, limit=10)
    tray = select_ambient_items(ranked_items, "tray", policy=policy, limit=10)

    for payload in (daily, critical, weekly, tray):
        AmbientDeliveryItemSet.model_validate(payload)
        assert payload["post_ranking_boundary"]["mutates_scores"] is False
        assert payload["post_ranking_boundary"]["mutates_rank_identity"] is False

    assert ranked_items == before
    assert [item["id"] for item in daily["items"]] == [
        "daily-tie-first",
        "daily-lower-threshold",
        "daily-tie-second",
    ]
    assert [item["id"] for item in critical["items"]] == [
        "critical-threshold",
        "critical-alert-tail",
    ]
    assert [item["id"] for item in weekly["items"]] == ["weekly-below-threshold"]
    assert [item["id"] for item in tray["items"]] == [
        "daily-tie-first",
        "critical-threshold",
        "daily-lower-threshold",
        "daily-tie-second",
        "critical-alert-tail",
    ]

    originals = {item["id"]: item for item in before}
    delivered_by_id = {
        item["id"]: item
        for payload in (daily, critical, weekly, tray)
        for item in payload["items"]
    }
    for signal_id, delivered in delivered_by_id.items():
        original = originals[signal_id]
        snapshot = delivered["delivery_decision"]["ranking_snapshot"]
        assert delivered["ensemble_score"] == original["ensemble_score"]
        assert delivered["final_score"] == original["final_score"]
        assert delivered["pre_layer_ranking"]["input_rank"] == original["pre_layer_ranking"]["input_rank"]
        assert delivered["pre_layer_ranking"]["input_order"] == original["pre_layer_ranking"]["input_order"]
        assert delivered["pre_layer_ranking"]["rank_identifiers"] == original["pre_layer_ranking"]["rank_identifiers"]
        assert snapshot["input_ensemble_score"] == original["ensemble_score"]
        assert snapshot["input_final_score"] == original["final_score"]
        assert snapshot["input_ensemble_rank"] == original["pre_layer_ranking"]["input_rank"]
        assert snapshot["input_order"] == original["pre_layer_ranking"]["input_order"]
        assert snapshot["rank_identifiers"] == original["pre_layer_ranking"]["rank_identifiers"]


def test_critical_surface_routes_immediately_without_mutating_ranking_boundary(tmp_env, monkeypatch):
    import hedwig.dashboard.app as dashboard_app

    from hedwig.delivery.ambient import ambient_delivery_events, select_ambient_items
    from hedwig.models import AmbientDeliveryItemSet
    from hedwig.storage import get_behavior_events, get_behavior_rewards

    ranked_items = [
        {
            "id": "critical-alert-low-score",
            "title": "Low-score item still urgent",
            "url": "https://example.test/critical-alert-low-score",
            "platform": "test",
            "ensemble_score": 0.42,
            "final_score": 0.41,
            "ensemble_rank": 9,
            "feed_position": 0,
            "urgency": "alert",
            "pre_layer_ranking": {
                "input_rank": 9,
                "input_order": 0,
                "rank_identifiers": {"ranking_run_id": "critical-routing", "rank_slot": "alert-low"},
                "immutable": True,
            },
        },
        {
            "id": "daily-before-high-score-critical",
            "title": "Daily item stays between critical routes",
            "url": "https://example.test/daily-between",
            "platform": "test",
            "ensemble_score": 0.72,
            "final_score": 0.71,
            "ensemble_rank": 2,
            "feed_position": 1,
            "urgency": "digest",
            "pre_layer_ranking": {
                "input_rank": 2,
                "input_order": 1,
                "rank_identifiers": {"ranking_run_id": "critical-routing", "rank_slot": "daily-between"},
                "immutable": True,
            },
        },
        {
            "id": "critical-score-threshold",
            "title": "High-score item routes immediately",
            "url": "https://example.test/critical-score-threshold",
            "platform": "test",
            "ensemble_score": 0.90,
            "final_score": 0.84,
            "ensemble_rank": 1,
            "feed_position": 2,
            "urgency": "digest",
            "pre_layer_ranking": {
                "input_rank": 1,
                "input_order": 2,
                "rank_identifiers": {"ranking_run_id": "critical-routing", "rank_slot": "score-threshold"},
                "immutable": True,
            },
        },
        {
            "id": "weekly-tail",
            "title": "Weekly tail keeps exploration off critical fixture",
            "url": "https://example.test/weekly-tail",
            "platform": "test",
            "ensemble_score": 0.20,
            "final_score": 0.20,
            "ensemble_rank": 10,
            "feed_position": 3,
            "urgency": "digest",
            "pre_layer_ranking": {
                "input_rank": 10,
                "input_order": 3,
                "rank_identifiers": {"ranking_run_id": "critical-routing", "rank_slot": "weekly-tail"},
                "immutable": True,
            },
        },
    ]
    before = copy.deepcopy(ranked_items)

    critical = select_ambient_items(ranked_items, "critical", limit=5)

    AmbientDeliveryItemSet.model_validate(critical)
    assert ranked_items == before
    assert critical["surface"] == "critical"
    assert critical["entry_point"]["entry_kind"] == "receiver"
    assert critical["entry_point"]["delivery_semantics"].startswith("Immediate high-urgency")
    assert critical["post_ranking_boundary"]["mutates_scores"] is False
    assert critical["post_ranking_boundary"]["mutates_rank_identity"] is False
    assert [item["id"] for item in critical["items"]] == [
        "critical-alert-low-score",
        "critical-score-threshold",
    ]

    originals = {item["id"]: item for item in before}
    for delivered in critical["items"]:
        original = originals[delivered["id"]]
        decision = delivered["delivery_decision"]
        snapshot = decision["ranking_snapshot"]

        assert decision["surface"] == "critical"
        assert decision["timing"] == "now"
        assert decision["decision_layer"] == "post_ranking_delivery"
        assert decision["post_ranking"] is True
        assert decision["ranking_input"] is False
        assert decision["ranking_output"] is False
        assert decision["does_not_mutate_ensemble"] is True
        assert delivered["delivery_timing"] == "now"
        assert delivered["ensemble_score"] == original["ensemble_score"]
        assert delivered["final_score"] == original["final_score"]
        assert delivered["pre_layer_ranking"]["ensemble_score"] == original["ensemble_score"]
        assert delivered["pre_layer_ranking"]["final_score"] == original["final_score"]
        assert delivered["pre_layer_ranking"]["input_rank"] == original["pre_layer_ranking"]["input_rank"]
        assert delivered["pre_layer_ranking"]["input_order"] == original["pre_layer_ranking"]["input_order"]
        for key, value in original["pre_layer_ranking"]["rank_identifiers"].items():
            assert delivered["pre_layer_ranking"]["rank_identifiers"][key] == value
        assert snapshot["input_ensemble_score"] == original["ensemble_score"]
        assert snapshot["input_final_score"] == original["final_score"]
        assert snapshot["input_ensemble_rank"] == original["pre_layer_ranking"]["input_rank"]
        assert snapshot["input_order"] == original["pre_layer_ranking"]["input_order"]
        assert snapshot["rank_identifiers"] == delivered["pre_layer_ranking"]["rank_identifiers"]
        assert delivered["explanation"]["display_only"] is True
        assert delivered["explanation"]["ranking_input"] is False
        assert delivered["explanation"]["score_like_authority"] is False

    events = ambient_delivery_events(critical, event_type="delivered", device="critical_receiver")
    assert [event["signal_id"] for event in events] == [
        "critical-alert-low-score",
        "critical-score-threshold",
    ]
    assert all(event["event_type"] == "delivered" for event in events)
    assert all(event["feed_id"] == "ambient:critical" for event in events)
    assert all(event["feed_mode"] == "ambient_critical" for event in events)
    assert [event["position_in_feed"] for event in events] == [0, 2]

    monkeypatch.setattr(dashboard_app, "_load_ranked_feed_items", lambda days=14: copy.deepcopy(ranked_items))
    client = TestClient(dashboard_app.create_app())
    response = client.get("/ambient/critical/api?limit=5")
    assert response.status_code == 200
    payload = response.json()
    assert [item["id"] for item in payload["items"]] == [
        "critical-alert-low-score",
        "critical-score-threshold",
    ]
    assert all(item["delivery_decision"]["timing"] == "now" for item in payload["items"])
    assert len(get_behavior_events(signal_id="critical-alert-low-score", feed_mode="ambient_critical")) == 1
    assert len(get_behavior_events(signal_id="critical-score-threshold", feed_mode="ambient_critical")) == 1
    assert get_behavior_rewards(signal_id="critical-alert-low-score") == []
    assert get_behavior_rewards(signal_id="critical-score-threshold") == []


def test_daily_surface_routes_digest_items_without_mutating_ranking_boundary(tmp_env, monkeypatch):
    import hedwig.dashboard.app as dashboard_app

    from hedwig.delivery.ambient import ambient_delivery_events, select_ambient_items
    from hedwig.models import AmbientDeliveryItemSet
    from hedwig.storage import get_behavior_events, get_behavior_rewards

    ranked_items = [
        {
            "id": "critical-alert-excluded",
            "title": "Alert is not daily digest eligible",
            "url": "https://example.test/critical-alert-excluded",
            "platform": "test",
            "ensemble_score": 0.73,
            "final_score": 0.72,
            "ensemble_rank": 1,
            "feed_position": 0,
            "urgency": "alert",
            "pre_layer_ranking": {
                "input_rank": 1,
                "input_order": 0,
                "rank_identifiers": {"ranking_run_id": "daily-routing", "rank_slot": "alert"},
                "immutable": True,
            },
        },
        {
            "id": "daily-digest-first",
            "title": "First digest eligible item",
            "url": "https://example.test/daily-digest-first",
            "platform": "test",
            "ensemble_score": 0.84,
            "final_score": 0.83,
            "ensemble_rank": 2,
            "feed_position": 1,
            "urgency": "digest",
            "pre_layer_ranking": {
                "input_rank": 2,
                "input_order": 1,
                "rank_identifiers": {"ranking_run_id": "daily-routing", "rank_slot": "daily-a"},
                "immutable": True,
            },
        },
        {
            "id": "critical-score-excluded",
            "title": "High score routes critical instead of daily",
            "url": "https://example.test/critical-score-excluded",
            "platform": "test",
            "ensemble_score": 0.85,
            "final_score": 0.80,
            "ensemble_rank": 3,
            "feed_position": 2,
            "urgency": "digest",
            "pre_layer_ranking": {
                "input_rank": 3,
                "input_order": 2,
                "rank_identifiers": {"ranking_run_id": "daily-routing", "rank_slot": "critical-score"},
                "immutable": True,
            },
        },
        {
            "id": "daily-digest-second",
            "title": "Second digest eligible item",
            "url": "https://example.test/daily-digest-second",
            "platform": "test",
            "ensemble_score": 0.65,
            "final_score": 0.60,
            "ensemble_rank": 4,
            "feed_position": 3,
            "urgency": "digest",
            "pre_layer_ranking": {
                "input_rank": 4,
                "input_order": 3,
                "rank_identifiers": {"ranking_run_id": "daily-routing", "rank_slot": "daily-b"},
                "immutable": True,
            },
        },
        {
            "id": "weekly-below-threshold",
            "title": "Below daily threshold routes weekly",
            "url": "https://example.test/weekly-below-threshold",
            "platform": "test",
            "ensemble_score": 0.64,
            "final_score": 0.64,
            "ensemble_rank": 5,
            "feed_position": 4,
            "urgency": "digest",
            "pre_layer_ranking": {
                "input_rank": 5,
                "input_order": 4,
                "rank_identifiers": {"ranking_run_id": "daily-routing", "rank_slot": "weekly"},
                "immutable": True,
            },
        },
    ]
    policy = {
        "exploration": {"enabled": False},
        "delivery": {"default_channel": "dashboard", "repeat": {"enabled": True, "max_count": 2}},
    }
    before = copy.deepcopy(ranked_items)

    daily = select_ambient_items(ranked_items, "daily", policy=policy, limit=5)

    AmbientDeliveryItemSet.model_validate(daily)
    assert ranked_items == before
    assert daily["surface"] == "daily"
    assert daily["entry_point"]["cadence"] == "next daily digest run"
    assert daily["entry_point"]["selection_rule"] == "delivery_decision.surface == daily"
    assert daily["post_ranking_boundary"]["mutates_scores"] is False
    assert daily["post_ranking_boundary"]["mutates_rank_identity"] is False
    assert [item["id"] for item in daily["items"]] == [
        "daily-digest-first",
        "daily-digest-second",
    ]

    originals = {item["id"]: item for item in before}
    for delivered in daily["items"]:
        original = originals[delivered["id"]]
        decision = delivered["delivery_decision"]
        snapshot = decision["ranking_snapshot"]

        assert original["urgency"] == "digest"
        assert original["ensemble_score"] >= 0.65
        assert original["ensemble_score"] < 0.85
        assert decision["surface"] == "daily"
        assert decision["timing"] == "next_digest"
        assert decision["decision_layer"] == "post_ranking_delivery"
        assert decision["post_ranking"] is True
        assert decision["ranking_input"] is False
        assert decision["ranking_output"] is False
        assert decision["does_not_mutate_ensemble"] is True
        assert delivered["delivery_timing"] == "next_digest"
        assert delivered["ensemble_score"] == original["ensemble_score"]
        assert delivered["final_score"] == original["final_score"]
        assert delivered["pre_layer_ranking"]["ensemble_score"] == original["ensemble_score"]
        assert delivered["pre_layer_ranking"]["final_score"] == original["final_score"]
        assert delivered["pre_layer_ranking"]["input_rank"] == original["pre_layer_ranking"]["input_rank"]
        assert delivered["pre_layer_ranking"]["input_order"] == original["pre_layer_ranking"]["input_order"]
        assert delivered["pre_layer_ranking"]["rank_identifiers"] == original["pre_layer_ranking"]["rank_identifiers"]
        assert snapshot["input_ensemble_score"] == original["ensemble_score"]
        assert snapshot["input_final_score"] == original["final_score"]
        assert snapshot["input_ensemble_rank"] == original["pre_layer_ranking"]["input_rank"]
        assert snapshot["input_order"] == original["pre_layer_ranking"]["input_order"]
        assert snapshot["rank_identifiers"] == original["pre_layer_ranking"]["rank_identifiers"]
        assert delivered["explanation"]["display_only"] is True
        assert delivered["explanation"]["ranking_input"] is False
        assert delivered["explanation"]["score_like_authority"] is False

    events = ambient_delivery_events(daily, event_type="delivered", device="daily_digest")
    assert [event["signal_id"] for event in events] == ["daily-digest-first", "daily-digest-second"]
    assert all(event["event_type"] == "delivered" for event in events)
    assert all(event["feed_id"] == "ambient:daily" for event in events)
    assert all(event["feed_mode"] == "ambient_daily" for event in events)
    assert [event["position_in_feed"] for event in events] == [1, 3]

    monkeypatch.setattr(dashboard_app, "_load_ranked_feed_items", lambda days=14: copy.deepcopy(ranked_items))
    client = TestClient(dashboard_app.create_app())
    response = client.get("/ambient/daily/api?limit=5")
    assert response.status_code == 200
    payload = response.json()
    assert [item["id"] for item in payload["items"]] == [
        "daily-digest-first",
        "daily-digest-second",
    ]
    assert all(item["delivery_decision"]["timing"] == "next_digest" for item in payload["items"])
    assert len(get_behavior_events(signal_id="daily-digest-first", feed_mode="ambient_daily")) == 1
    assert len(get_behavior_events(signal_id="daily-digest-second", feed_mode="ambient_daily")) == 1
    assert get_behavior_rewards(signal_id="daily-digest-first") == []
    assert get_behavior_rewards(signal_id="daily-digest-second") == []


def test_ambient_item_payload_includes_short_display_reason_from_relevance_or_context():
    from hedwig.delivery.ambient import select_ambient_items
    from hedwig.models import AmbientDeliveryItemSet

    long_relevance = " ".join(["Strong match to your current infrastructure migration plan."] * 8)
    items = [
        {
            "id": "critical-context",
            "title": "Critical fallback context",
            "url": "https://example.test/critical-context",
            "ensemble_score": 0.94,
            "final_score": 0.94,
            "ensemble_rank": 1,
            "urgency": "alert",
        },
        {
            "id": "daily-context",
            "title": "Daily with relevance context",
            "url": "https://example.test/daily-context",
            "ensemble_score": 0.74,
            "final_score": 0.74,
            "ensemble_rank": 2,
            "urgency": "digest",
            "why_relevant": long_relevance,
        },
        {
            "id": "weekly-tail",
            "title": "Weekly tail",
            "url": "https://example.test/weekly-tail",
            "ensemble_score": 0.34,
            "final_score": 0.34,
            "ensemble_rank": 3,
            "urgency": "digest",
        },
    ]

    daily = select_ambient_items(items, "daily", limit=1)
    critical = select_ambient_items(items, "critical", limit=1)

    AmbientDeliveryItemSet.model_validate(daily)
    AmbientDeliveryItemSet.model_validate(critical)
    daily_reason = daily["items"][0]["reason"]
    critical_reason = critical["items"][0]["reason"]
    assert daily_reason.startswith("Strong match to your current infrastructure migration plan.")
    assert len(daily_reason) <= 160
    assert critical_reason == "Critical context routed this item to immediate ambient delivery."
    assert daily["items"][0]["explanation"]["display_only"] is True
    assert daily["items"][0]["explanation"]["ranking_input"] is False
    assert daily["items"][0]["explanation"]["score_like_authority"] is False
    assert "reason" not in daily["items"][0]["pre_layer_ranking"]
    assert "reason" not in daily["items"][0]["delivery_decision"]["ranking_snapshot"]


def test_ambient_explanation_copy_avoids_scores_ranks_confidence_and_authority():
    from hedwig.delivery.ambient import explanation_copy_is_surface_safe, select_ambient_items
    from hedwig.models import AmbientDeliveryItemSet

    items = [
        {
            "id": "unsafe-copy-daily",
            "title": "Unsafe copy daily",
            "url": "https://example.test/unsafe-copy-daily",
            "ensemble_score": 0.74,
            "final_score": 0.74,
            "ensemble_rank": 2,
            "urgency": "digest",
            "why_relevant": (
                "Strong match to your migration plan. "
                "Score 0.74, rank #2, 95% confidence, top authoritative item."
            ),
        },
        {
            "id": "unsafe-copy-critical",
            "title": "Unsafe copy critical",
            "url": "https://example.test/unsafe-copy-critical",
            "ensemble_score": 0.96,
            "final_score": 0.96,
            "ensemble_rank": 1,
            "urgency": "alert",
            "reason": "Final score 0.96 makes this the best ranked alert.",
        },
        {
            "id": "unsafe-copy-tail",
            "title": "Unsafe copy tail",
            "url": "https://example.test/unsafe-copy-tail",
            "ensemble_score": 0.10,
            "final_score": 0.10,
            "ensemble_rank": 3,
            "urgency": "digest",
        },
    ]

    daily = select_ambient_items(copy.deepcopy(items), "daily", limit=1)
    critical = select_ambient_items(copy.deepcopy(items), "critical", limit=1)

    AmbientDeliveryItemSet.model_validate(daily)
    AmbientDeliveryItemSet.model_validate(critical)
    assert daily["items"][0]["reason"] == "Strong match to your migration plan"
    assert critical["items"][0]["reason"] == "Critical context routed this item to immediate ambient delivery."
    for payload in (daily, critical):
        reason = payload["items"][0]["reason"]
        explanation = payload["items"][0]["explanation"]["text"]
        assert explanation_copy_is_surface_safe(reason)
        assert explanation_copy_is_surface_safe(explanation)
        assert "score" not in reason.lower()
        assert "rank" not in reason.lower()
        assert "confidence" not in reason.lower()
        assert "%" not in reason
        assert "0." not in reason
        assert "top" not in reason.lower()
        assert "best" not in reason.lower()
        assert "authoritative" not in reason.lower()


def test_ambient_explanation_context_uses_approved_metadata_contract_only():
    from hedwig.delivery.ambient import (
        ambient_display_reason_from_context,
        ambient_explanation_context,
        ambient_explanation_metadata_contract,
        select_ambient_items,
    )
    from hedwig.models import AmbientDeliveryItemSet

    item = {
        "id": "contract-daily",
        "title": "Contract daily",
        "url": "https://example.test/contract-daily",
        "platform": "test",
        "author": "Analyst",
        "urgency": "digest",
        "reason": "Matches your migration planning context.",
        "why_relevant": "Component score 0.99 says this is top ranked.",
        "anomaly_label": {"reason": "Contrarian perspective for ambient discovery."},
        "is_exploration": False,
        "score": 999,
        "relevance_score": 999,
        "ensemble_score": 0.74,
        "final_score": 0.73,
        "ensemble_rank": 2,
        "feed_position": 1,
        "component_scores": {"llm_judge": 0.99, "bandit": 0.10},
        "ranking_features": {"freshness": 0.8},
        "ranking_trace": [{"component": "llm_judge", "weight": 0.4}],
        "weights": {"llm_judge": 0.4},
        "pre_layer_ranking": {
            "input_rank": 2,
            "input_order": 1,
            "rank_identifiers": {"ranking_run_id": "gen9-run"},
            "immutable": True,
        },
    }

    policy = {"exploration": {"enabled": False}, "delivery": {"default_channel": "dashboard"}}
    daily = select_ambient_items([copy.deepcopy(item)], "daily", policy=policy, limit=1)
    decision = daily["items"][0]["delivery_decision"]
    context = ambient_explanation_context(item, decision)
    contract = ambient_explanation_metadata_contract()
    context_text = json.dumps(context, sort_keys=True)

    AmbientDeliveryItemSet.model_validate(daily)
    assert daily["items"][0]["reason"] == "Matches your migration planning context."
    assert daily["items"][0]["why_relevant"] == ""
    assert context["schema_version"] == "ambient_explanation_metadata.v1"
    assert set(context["item"]) == set(contract["approved_item_fields"])
    assert set(context["delivery"]) == set(contract["approved_delivery_fields"])
    assert context["boundary"]["display_only"] is True
    assert context["boundary"]["ranking_input"] is False
    assert context["boundary"]["score_like_authority"] is False
    assert context["boundary"]["excludes_raw_pr18_gen9_internals"] is True

    for forbidden in contract["forbidden_ranking_fields"]:
        assert forbidden not in context["item"]
        assert forbidden not in context["delivery"]

    assert context["item"]["why_relevant"] == ""
    assert "ranking_snapshot" not in context_text
    assert "component_scores" not in context_text
    assert "llm_judge" not in context_text
    assert "gen9-run" not in context_text
    assert "0.99" not in context_text
    assert daily["items"][0]["explanation"]["display_only"] is True
    assert daily["items"][0]["explanation"]["ranking_input"] is False
    assert daily["items"][0]["explanation"]["score_like_authority"] is False

    assert ambient_display_reason_from_context(context) == "Matches your migration planning context."
    unsafe_context = copy.deepcopy(context)
    unsafe_context["item"]["ensemble_score"] = 0.74
    with pytest.raises(ValueError, match="unapproved fields"):
        ambient_display_reason_from_context(unsafe_context)


def test_ambient_explanation_payload_serialization_filters_raw_ranking_internals():
    from pydantic import ValidationError

    from hedwig.delivery.ambient import (
        _contract_item,
        explanation_payload_is_serialization_safe,
        sanitize_ambient_explanation_payload,
    )
    from hedwig.models import DeliveryExplanationMetadata

    unsafe_explanation = {
        "text": "Final score 0.91 makes this top ranked.",
        "display_only": False,
        "ranking_input": True,
        "score_like_authority": True,
        "ensemble_score": 0.91,
        "final_score": 0.90,
        "ranking_snapshot": {"input_ensemble_rank": 1},
        "component_scores": {"llm_judge": 0.99},
        "nested": {"rank_identifiers": {"ranking_run_id": "gen9-raw"}},
    }

    assert explanation_payload_is_serialization_safe(unsafe_explanation) is False
    sanitized = sanitize_ambient_explanation_payload(
        unsafe_explanation,
        fallback_text="Routed for ambient review.",
    )

    assert sanitized == {
        "text": "Routed for ambient review.",
        "display_only": True,
        "ranking_input": False,
        "score_like_authority": False,
    }
    assert explanation_payload_is_serialization_safe(sanitized) is True

    with pytest.raises(ValidationError):
        DeliveryExplanationMetadata.model_validate(unsafe_explanation)

    item = {
        "id": "serialized-explanation-boundary",
        "title": "Serialized explanation boundary",
        "url": "https://example.test/serialized-explanation-boundary",
        "ensemble_score": 0.91,
        "final_score": 0.90,
        "ensemble_rank": 1,
        "urgency": "alert",
        "reason": "Immediate operational context.",
        "pre_layer_ranking": {
            "ensemble_score": 0.91,
            "final_score": 0.90,
            "input_rank": 1,
            "input_order": 0,
            "rank_identifiers": {"ranking_run_id": "gen9-raw"},
            "immutable": True,
        },
        "delivery_decision": {
            "signal_id": "serialized-explanation-boundary",
            "surface": "critical",
            "channel": "dashboard",
            "timing": "now",
            "ranking_snapshot": {
                "input_ensemble_rank": 1,
                "input_order": 0,
                "rank_identifiers": {"ranking_run_id": "gen9-raw"},
                "input_ensemble_score": 0.91,
                "input_final_score": 0.90,
                "immutable": True,
            },
            "explanation": unsafe_explanation,
        },
    }

    serialized = _contract_item(item).model_dump(mode="json")
    explanation = serialized["explanation"]
    explanation_text = json.dumps(explanation, sort_keys=True)

    assert explanation == {
        "text": "Immediate operational context.",
        "display_only": True,
        "ranking_input": False,
        "score_like_authority": False,
    }
    assert explanation_payload_is_serialization_safe(explanation) is True
    assert "ensemble_score" not in explanation_text
    assert "final_score" not in explanation_text
    assert "ranking_snapshot" not in explanation_text
    assert "component_scores" not in explanation_text
    assert "rank_identifiers" not in explanation_text
    assert "gen9-raw" not in explanation_text


def test_ambient_explanations_allow_display_context_but_exclude_scores_weights_and_debug_fields():
    from hedwig.delivery.ambient import (
        ambient_explanation_context,
        ambient_explanation_metadata_contract,
        explanation_payload_is_serialization_safe,
        select_ambient_items,
    )
    from hedwig.models import AmbientDeliveryItemSet

    item = {
        "id": "allowed-context-with-internals",
        "title": "Allowed context title",
        "url": "https://example.test/allowed-context",
        "platform": "newsletter",
        "author": "Research Desk",
        "urgency": "digest",
        "reason": "",
        "why_relevant": "Connects to your current database reliability work.",
        "anomaly_label": {"reason": "Diverse source for a later review."},
        "is_exploration": False,
        "ensemble_score": 0.74,
        "final_score": 0.73,
        "ensemble_rank": 4,
        "feed_position": 3,
        "component_scores": {"llm_judge": 0.91, "bandit": 0.20},
        "weights": {"llm_judge": 0.45, "bandit": 0.15},
        "debug": {"prompt": "ranking internals must not serialize"},
        "debug_trace": [{"step": "score", "value": 0.91}],
        "ranking_debug": {"feature_vector": [0.1, 0.2]},
        "pre_layer_ranking": {
            "input_rank": 4,
            "input_order": 3,
            "rank_identifiers": {"ranking_run_id": "gen9-debug-run", "rank_slot": "slot-4"},
            "immutable": True,
        },
    }

    daily = select_ambient_items([copy.deepcopy(item)], "daily", limit=1)

    AmbientDeliveryItemSet.model_validate(daily)
    delivered = daily["items"][0]
    context = ambient_explanation_context(item, delivered["delivery_decision"])
    contract = ambient_explanation_metadata_contract()
    serialized_explanation = json.dumps(delivered["explanation"], sort_keys=True)
    serialized_context = json.dumps(context, sort_keys=True)

    assert delivered["reason"] == "Connects to your current database reliability work."
    assert delivered["why_relevant"] == "Connects to your current database reliability work."
    assert delivered["explanation"] == {
        "text": "Connects to your current database reliability work.",
        "display_only": True,
        "ranking_input": False,
        "score_like_authority": False,
    }
    assert context["item"] == {
        "id": "allowed-context-with-internals",
        "title": "Allowed context title",
        "url": "https://example.test/allowed-context",
        "platform": "newsletter",
        "author": "Research Desk",
        "urgency": "digest",
        "reason": "",
        "why_relevant": "Connects to your current database reliability work.",
        "anomaly_reason": "Diverse source for a later review.",
        "is_exploration": False,
    }
    assert context["delivery"] == {
        "surface": "daily",
        "timing": "next_digest",
        "channel": "dashboard",
    }
    assert context["boundary"]["display_only"] is True
    assert context["boundary"]["ranking_input"] is False
    assert context["boundary"]["score_like_authority"] is False

    for forbidden in contract["forbidden_ranking_fields"]:
        assert forbidden not in delivered["explanation"]
        assert forbidden not in context["item"]
        assert forbidden not in context["delivery"]

    for leaked_internal in (
        "ensemble_score",
        "final_score",
        "component_scores",
        "llm_judge",
        "weights",
        "debug_trace",
        "ranking_debug",
        "gen9-debug-run",
        "0.74",
        "0.73",
        "0.91",
        "0.45",
        "rank_slot",
    ):
        assert leaked_internal not in serialized_explanation
        assert leaked_internal not in serialized_context
    assert explanation_payload_is_serialization_safe(delivered["explanation"]) is True
    assert explanation_payload_is_serialization_safe({"text": "safe", "debug": {"score": 0.91}}) is False
    assert explanation_payload_is_serialization_safe({"text": "safe", "weights": {"llm_judge": 0.45}}) is False
    assert explanation_payload_is_serialization_safe({"text": "safe", "ranking_debug": {"rank": 4}}) is False


def test_ambient_surfaces_fallback_when_delivered_item_reason_is_missing(tmp_env, monkeypatch):
    import hedwig.dashboard.app as dashboard_app

    from hedwig.delivery.ambient import select_ambient_items
    from hedwig.models import AmbientDeliveryItemSet

    ranked_items = [
        {
            "id": "missing-reason-critical",
            "title": "Critical Missing Reason",
            "url": "https://example.test/missing-reason-critical",
            "platform": "test",
            "ensemble_score": 0.96,
            "final_score": 0.96,
            "ensemble_rank": 1,
            "urgency": "alert",
            "reason": None,
            "why_relevant": "",
        },
        {
            "id": "missing-reason-daily",
            "title": "Daily Missing Reason",
            "url": "https://example.test/missing-reason-daily",
            "platform": "test",
            "ensemble_score": 0.76,
            "final_score": 0.76,
            "ensemble_rank": 2,
            "urgency": "digest",
            "reason": "   ",
            "why_relevant": " \n ",
            "anomaly_label": {"reason": ""},
        },
        {
            "id": "missing-reason-weekly-tail",
            "title": "Weekly Missing Reason Tail",
            "url": "https://example.test/missing-reason-weekly-tail",
            "platform": "test",
            "ensemble_score": 0.42,
            "final_score": 0.42,
            "ensemble_rank": 3,
            "urgency": "digest",
            "reason": "",
            "why_relevant": "",
        },
    ]

    daily = select_ambient_items(copy.deepcopy(ranked_items), "daily", limit=1)
    critical = select_ambient_items(copy.deepcopy(ranked_items), "critical", limit=1)

    AmbientDeliveryItemSet.model_validate(daily)
    AmbientDeliveryItemSet.model_validate(critical)
    assert daily["items"][0]["reason"] == "Relevant digest item selected for today."
    assert critical["items"][0]["reason"] == "Critical context routed this item to immediate ambient delivery."
    assert daily["items"][0]["reason"].strip()
    assert critical["items"][0]["reason"].strip()
    assert daily["items"][0]["explanation"]["display_only"] is True
    assert critical["items"][0]["explanation"]["display_only"] is True
    assert "reason" not in daily["items"][0]["pre_layer_ranking"]
    assert "reason" not in daily["items"][0]["delivery_decision"]["ranking_snapshot"]

    monkeypatch.setattr(dashboard_app, "_load_ranked_feed_items", lambda days=14: copy.deepcopy(ranked_items))
    client = TestClient(dashboard_app.create_app())
    page = client.get("/ambient/daily?limit=1")

    assert page.status_code == 200
    assert "Daily Missing Reason" in page.text
    assert "Relevant digest item selected for today." in page.text
    assert 'data-reason="Relevant digest item selected for today."' in page.text
    assert 'aria-label="Display-only reason"' in page.text


def test_ambient_delivery_decisions_preserve_ranked_item_order():
    from hedwig.delivery.ambient import select_ambient_items
    from hedwig.personal_algorithm import route_items_after_ranking

    ranked = [
        {
            "id": "daily-first",
            "title": "Daily item that stays first",
            "ensemble_score": 0.70,
            "final_score": 0.70,
            "ensemble_rank": 10,
            "feed_position": 0,
            "urgency": "digest",
            "pre_layer_ranking": {
                "input_rank": 10,
                "input_order": 0,
                "rank_identifiers": {"ranking_run_id": "order-regression", "rank_slot": "slot-0"},
                "immutable": True,
            },
        },
        {
            "id": "critical-second",
            "title": "Critical item that must not jump ahead",
            "ensemble_score": 0.95,
            "final_score": 0.95,
            "ensemble_rank": 1,
            "feed_position": 1,
            "urgency": "alert",
            "pre_layer_ranking": {
                "input_rank": 1,
                "input_order": 1,
                "rank_identifiers": {"ranking_run_id": "order-regression", "rank_slot": "slot-1"},
                "immutable": True,
            },
        },
        {
            "id": "daily-third",
            "title": "Second daily item that stays third",
            "ensemble_score": 0.80,
            "final_score": 0.80,
            "ensemble_rank": 30,
            "feed_position": 2,
            "urgency": "digest",
            "pre_layer_ranking": {
                "input_rank": 30,
                "input_order": 2,
                "rank_identifiers": {"ranking_run_id": "order-regression", "rank_slot": "slot-2"},
                "immutable": True,
            },
        },
        {
            "id": "pwa-fourth",
            "title": "Exploration tail item that stays fourth",
            "ensemble_score": 0.20,
            "final_score": 0.20,
            "ensemble_rank": 5,
            "feed_position": 3,
            "urgency": "digest",
            "pre_layer_ranking": {
                "input_rank": 5,
                "input_order": 3,
                "rank_identifiers": {"ranking_run_id": "order-regression", "rank_slot": "slot-3"},
                "immutable": True,
            },
        },
    ]

    routed = route_items_after_ranking(ranked)
    daily = select_ambient_items(ranked, "daily")
    tray = select_ambient_items(ranked, "tray")

    assert [item["id"] for item in routed] == [
        "daily-first",
        "critical-second",
        "daily-third",
        "pwa-fourth",
    ]
    assert [item["delivery_decision"]["surface"] for item in routed] == [
        "daily",
        "critical",
        "daily",
        "pwa",
    ]
    assert [item["id"] for item in daily["items"]] == ["daily-first", "daily-third"]
    assert [item["id"] for item in tray["items"]] == [
        "daily-first",
        "critical-second",
        "daily-third",
        "pwa-fourth",
    ]
    assert [item["pre_layer_ranking"]["input_order"] for item in tray["items"]] == [0, 1, 2, 3]
    assert [
        item["delivery_decision"]["ranking_snapshot"]["rank_identifiers"]["rank_slot"]
        for item in tray["items"]
    ] == ["slot-0", "slot-1", "slot-2", "slot-3"]


def test_ambient_routing_preserves_pr18_gen9_ranking_inputs_and_identity():
    from hedwig.delivery.ambient import select_ambient_items
    from hedwig.personal_algorithm import route_items_after_ranking

    ranked = [
        {
            "id": "gen9-critical",
            "title": "Already-ranked critical item",
            "score": 42.5,
            "relevance_score": 0.875,
            "ensemble_score": 0.92,
            "final_score": 0.89,
            "ensemble_rank": 3,
            "feed_position": 0,
            "urgency": "alert",
            "component_scores": {"llm_judge": 0.91, "content": 0.73},
            "ranking_features": {"source_authority": 0.8, "recency_hours": 2},
            "pre_layer_ranking": {
                "ensemble_score": 0.92,
                "final_score": 0.89,
                "input_rank": 3,
                "input_order": 0,
                "rank_identifiers": {
                    "ranking_run_id": "pr18-gen9-run",
                    "rank_slot": "slot-3",
                    "source_rank": "critical-upstream",
                },
                "immutable": True,
            },
        },
        {
            "id": "gen9-daily",
            "title": "Already-ranked daily item",
            "score": 17.25,
            "relevance_score": 0.625,
            "ensemble_score": 0.74,
            "final_score": 0.70,
            "ensemble_rank": 6,
            "feed_position": 1,
            "urgency": "digest",
            "component_scores": {"llm_judge": 0.70, "content": 0.64},
            "ranking_features": {"source_authority": 0.6, "recency_hours": 8},
            "pre_layer_ranking": {
                "ensemble_score": 0.74,
                "final_score": 0.70,
                "input_rank": 6,
                "input_order": 1,
                "rank_identifiers": {
                    "ranking_run_id": "pr18-gen9-run",
                    "rank_slot": "slot-6",
                    "source_rank": "daily-upstream",
                },
                "immutable": True,
            },
        },
        {
            "id": "gen9-weekly",
            "title": "Already-ranked weekly item",
            "score": 9.5,
            "relevance_score": 0.35,
            "ensemble_score": 0.38,
            "final_score": 0.36,
            "ensemble_rank": 12,
            "feed_position": 2,
            "urgency": "digest",
            "component_scores": {"llm_judge": 0.37, "content": 0.33},
            "ranking_features": {"source_authority": 0.3, "recency_hours": 72},
            "pre_layer_ranking": {
                "ensemble_score": 0.38,
                "final_score": 0.36,
                "input_rank": 12,
                "input_order": 2,
                "rank_identifiers": {
                    "ranking_run_id": "pr18-gen9-run",
                    "rank_slot": "slot-12",
                    "source_rank": "weekly-upstream",
                },
                "immutable": True,
            },
        },
    ]
    before = copy.deepcopy(ranked)
    policy = {
        "exploration": {"enabled": False},
        "delivery": {
            "surfaces": ["critical", "daily", "weekly", "pwa", "tray"],
            "preferred_surfaces": ["tray", "pwa"],
            "urgency": {
                "critical_score_threshold": 0.90,
                "daily_score_threshold": 0.65,
            },
        },
    }
    ranking_input_fields = {
        "score",
        "relevance_score",
        "ensemble_score",
        "final_score",
        "ensemble_rank",
        "feed_position",
        "component_scores",
        "ranking_features",
        "pre_layer_ranking",
    }

    routed = route_items_after_ranking(ranked, policy=policy)

    assert ranked == before
    assert [item["id"] for item in routed] == [item["id"] for item in before]
    for original, delivered in zip(before, routed):
        for field in ranking_input_fields:
            assert delivered[field] == original[field]

        decision = delivered["delivery_decision"]
        snapshot = decision["ranking_snapshot"]
        assert decision["decision_layer"] == "post_ranking_delivery"
        assert decision["post_ranking"] is True
        assert decision["ranking_input"] is False
        assert decision["ranking_output"] is False
        assert decision["does_not_mutate_ensemble"] is True
        assert decision["surface_preference"]["post_ranking_only"] is True
        assert decision["surface_preference"]["mutates_scores"] is False
        assert decision["surface_preference"]["mutates_rank_identity"] is False
        assert snapshot["input_ensemble_score"] == original["ensemble_score"]
        assert snapshot["input_final_score"] == original["final_score"]
        assert snapshot["input_ensemble_rank"] == original["pre_layer_ranking"]["input_rank"]
        assert snapshot["input_order"] == original["pre_layer_ranking"]["input_order"]
        assert snapshot["rank_identifiers"] == original["pre_layer_ranking"]["rank_identifiers"]
        assert "component_scores" not in snapshot
        assert "ranking_features" not in snapshot

    tray = select_ambient_items(ranked, "tray", policy=policy, limit=10)
    weekly = select_ambient_items(ranked, "weekly", policy=policy, limit=10)

    assert ranked == before
    assert [item["id"] for item in tray["items"]] == ["gen9-critical", "gen9-daily"]
    assert [item["id"] for item in weekly["items"]] == ["gen9-weekly"]
    originals = {item["id"]: item for item in before}
    for item in tray["items"] + weekly["items"]:
        original = originals[item["id"]]
        assert item["ensemble_score"] == original["ensemble_score"]
        assert item["final_score"] == original["final_score"]
        assert item["pre_layer_ranking"]["ensemble_score"] == original["ensemble_score"]
        assert item["pre_layer_ranking"]["final_score"] == original["final_score"]
        assert item["pre_layer_ranking"]["input_rank"] == original["pre_layer_ranking"]["input_rank"]
        assert item["pre_layer_ranking"]["input_order"] == original["pre_layer_ranking"]["input_order"]
        assert item["pre_layer_ranking"]["rank_identifiers"] == original["pre_layer_ranking"]["rank_identifiers"]
        assert item["delivery_decision"]["ranking_snapshot"]["rank_identifiers"] == original["pre_layer_ranking"]["rank_identifiers"]
        assert item["delivery_decision"]["ranking_input"] is False
        assert item["delivery_decision"]["ranking_output"] is False
        assert item["explanation"]["display_only"] is True
        assert item["explanation"]["ranking_input"] is False
        assert item["explanation"]["score_like_authority"] is False


def test_surface_filtering_preserves_pre_layer_order_across_boundary_score_cases():
    from hedwig.delivery.ambient import select_ambient_items
    from hedwig.models import AmbientDeliveryItemSet

    ranked = [
        {
            "id": "daily-before-critical",
            "title": "Daily item before later critical item",
            "url": "https://example.test/daily-before-critical",
            "platform": "test",
            "score": -100,
            "relevance_score": 0.02,
            "ensemble_score": 0.65,
            "final_score": 0.999999999998,
            "ensemble_rank": 20,
            "feed_position": 0,
            "urgency": "digest",
            "pre_layer_ranking": {
                "input_rank": 20,
                "input_order": 0,
                "rank_identifiers": {"ranking_run_id": "ambient-boundary", "rank_slot": "slot-0"},
                "immutable": True,
            },
        },
        {
            "id": "critical-later",
            "title": "Critical item remains second in tray",
            "url": "https://example.test/critical-later",
            "platform": "test",
            "score": 1_000_000,
            "relevance_score": 999.0,
            "ensemble_score": 0.850000000001,
            "final_score": 0.10,
            "ensemble_rank": 1,
            "feed_position": 1,
            "urgency": "digest",
            "pre_layer_ranking": {
                "input_rank": 1,
                "input_order": 1,
                "rank_identifiers": {"ranking_run_id": "ambient-boundary", "rank_slot": "slot-1"},
                "immutable": True,
            },
        },
        {
            "id": "daily-tie-after-critical",
            "title": "Tied daily item remains after critical item",
            "url": "https://example.test/daily-tie-after-critical",
            "platform": "test",
            "score": 500_000,
            "relevance_score": 500.0,
            "ensemble_score": 0.65,
            "final_score": 0.999999999999,
            "ensemble_rank": 30,
            "feed_position": 2,
            "urgency": "digest",
            "pre_layer_ranking": {
                "input_rank": 30,
                "input_order": 2,
                "rank_identifiers": {"ranking_run_id": "ambient-boundary", "rank_slot": "slot-2"},
                "immutable": True,
            },
        },
        {
            "id": "weekly-zero-score-tail",
            "title": "Weekly zero-score item",
            "url": "https://example.test/weekly-zero-score-tail",
            "platform": "test",
            "score": 999_999,
            "relevance_score": 999.0,
            "ensemble_score": 0.0,
            "final_score": 0.0,
            "ensemble_rank": 40,
            "feed_position": 3,
            "urgency": "digest",
            "pre_layer_ranking": {
                "input_rank": 40,
                "input_order": 3,
                "rank_identifiers": {"ranking_run_id": "ambient-boundary", "rank_slot": "slot-3"},
                "immutable": True,
            },
        },
    ]
    before = copy.deepcopy(ranked)
    policy = {
        "exploration": {"enabled": False},
        "delivery": {"default_channel": "dashboard", "repeat": {"enabled": True, "max_count": 2}},
    }

    daily = select_ambient_items(ranked, "daily", policy=policy, limit=10)
    tray = select_ambient_items(ranked, "tray", policy=policy, limit=10)
    weekly = select_ambient_items(ranked, "weekly", policy=policy, limit=10)

    AmbientDeliveryItemSet.model_validate(daily)
    AmbientDeliveryItemSet.model_validate(tray)
    AmbientDeliveryItemSet.model_validate(weekly)
    assert ranked == before
    assert [item["id"] for item in daily["items"]] == [
        "daily-before-critical",
        "daily-tie-after-critical",
    ]
    assert [item["id"] for item in tray["items"]] == [
        "daily-before-critical",
        "critical-later",
        "daily-tie-after-critical",
    ]
    assert [item["id"] for item in weekly["items"]] == ["weekly-zero-score-tail"]

    originals = {item["id"]: item for item in before}
    for payload in (daily, tray, weekly):
        assert payload["post_ranking_boundary"]["mutates_scores"] is False
        assert payload["post_ranking_boundary"]["mutates_rank_identity"] is False
        for delivered in payload["items"]:
            original = originals[delivered["id"]]
            assert delivered["ensemble_score"] == original["ensemble_score"]
            assert delivered["final_score"] == original["final_score"]
            assert delivered["pre_layer_ranking"]["ensemble_score"] == original["ensemble_score"]
            assert delivered["pre_layer_ranking"]["final_score"] == original["final_score"]
            assert delivered["pre_layer_ranking"]["input_rank"] == original["pre_layer_ranking"]["input_rank"]
            assert delivered["pre_layer_ranking"]["input_order"] == original["pre_layer_ranking"]["input_order"]
            assert delivered["pre_layer_ranking"]["rank_identifiers"] == original["pre_layer_ranking"]["rank_identifiers"]
            assert delivered["delivery_decision"]["ranking_snapshot"]["input_ensemble_score"] == original["ensemble_score"]
            assert delivered["delivery_decision"]["ranking_snapshot"]["input_final_score"] == original["final_score"]
            assert delivered["delivery_decision"]["ranking_snapshot"]["rank_identifiers"] == original["pre_layer_ranking"]["rank_identifiers"]
            assert delivered["explanation"]["display_only"] is True
            assert delivered["explanation"]["ranking_input"] is False
            assert delivered["explanation"]["score_like_authority"] is False


@pytest.mark.parametrize("surface", ["critical", "daily", "weekly", "pwa", "tray"])
def test_each_ambient_surface_preserves_scores_after_processing(surface):
    from hedwig.delivery.ambient import select_ambient_items
    from hedwig.models import AmbientDeliveryItemSet

    items = _ranked_items()
    before = {item["id"]: copy.deepcopy(item) for item in items}

    payload = select_ambient_items(items, surface)

    AmbientDeliveryItemSet.model_validate(payload)
    assert payload["surface"] == surface
    assert payload["items"], f"{surface} should expose at least one regression item"
    for processed in payload["items"]:
        original = before[processed["id"]]
        assert processed["ensemble_score"] == original["ensemble_score"]
        assert processed["final_score"] == original["final_score"]
        assert processed["pre_layer_ranking"]["ensemble_score"] == original["ensemble_score"]
        assert processed["pre_layer_ranking"]["final_score"] == original["final_score"]
        assert (
            processed["delivery_decision"]["ranking_snapshot"]["input_ensemble_score"]
            == original["ensemble_score"]
        )
        assert (
            processed["delivery_decision"]["ranking_snapshot"]["input_final_score"]
            == original["final_score"]
        )
    assert items == list(before.values())


@pytest.mark.parametrize("surface", ["critical", "daily", "weekly", "pwa", "tray"])
def test_each_ambient_surface_preserves_existing_score_values_without_recomputing(surface):
    from hedwig.delivery.ambient import select_ambient_items
    from hedwig.models import AmbientDeliveryItemSet

    ranked = [
        {
            "id": "score-critical",
            "title": "Critical score must remain the ranking output",
            "score": 0.01,
            "relevance_score": 0.02,
            "ensemble_score": 0.930001,
            "final_score": 0.870003,
            "ensemble_rank": 4,
            "feed_position": 0,
            "urgency": "alert",
            "pre_layer_ranking": {
                "ensemble_score": 0.930001,
                "final_score": 0.870003,
                "input_rank": 4,
                "input_order": 0,
                "rank_identifiers": {"ranking_run_id": "score-preservation", "rank_slot": "critical"},
                "immutable": True,
            },
        },
        {
            "id": "score-daily",
            "title": "Daily score must not be recomputed from relevance",
            "score": 99.0,
            "relevance_score": 98.0,
            "ensemble_score": 0.740007,
            "final_score": 0.710009,
            "ensemble_rank": 5,
            "feed_position": 1,
            "urgency": "digest",
            "pre_layer_ranking": {
                "ensemble_score": 0.740007,
                "final_score": 0.710009,
                "input_rank": 5,
                "input_order": 1,
                "rank_identifiers": {"ranking_run_id": "score-preservation", "rank_slot": "daily"},
                "immutable": True,
            },
        },
        {
            "id": "score-weekly",
            "title": "Weekly score must remain low without normalization",
            "score": 88.0,
            "relevance_score": 87.0,
            "ensemble_score": 0.120011,
            "final_score": 0.080013,
            "ensemble_rank": 6,
            "feed_position": 2,
            "urgency": "digest",
            "pre_layer_ranking": {
                "ensemble_score": 0.120011,
                "final_score": 0.080013,
                "input_rank": 6,
                "input_order": 2,
                "rank_identifiers": {"ranking_run_id": "score-preservation", "rank_slot": "weekly"},
                "immutable": True,
            },
        },
        {
            "id": "score-pwa",
            "title": "PWA score must remain exploration input value",
            "score": 77.0,
            "relevance_score": 76.0,
            "ensemble_score": 0.210017,
            "final_score": 0.190019,
            "ensemble_rank": 7,
            "feed_position": 3,
            "urgency": "digest",
            "is_exploration": True,
            "pre_layer_ranking": {
                "ensemble_score": 0.210017,
                "final_score": 0.190019,
                "input_rank": 7,
                "input_order": 3,
                "rank_identifiers": {"ranking_run_id": "score-preservation", "rank_slot": "pwa"},
                "immutable": True,
            },
        },
    ]
    policy = {
        "exploration": {"enabled": True},
        "delivery": {"urgency": {"critical_score_threshold": 0.9, "daily_score_threshold": 0.65}},
    }
    expected_ids = {
        "critical": ["score-critical"],
        "daily": ["score-daily"],
        "weekly": ["score-weekly"],
        "pwa": ["score-pwa"],
        "tray": ["score-critical", "score-daily", "score-pwa"],
    }
    before = copy.deepcopy(ranked)
    originals = {item["id"]: item for item in before}

    payload = select_ambient_items(ranked, surface, policy=policy, limit=10)

    AmbientDeliveryItemSet.model_validate(payload)
    assert [item["id"] for item in payload["items"]] == expected_ids[surface]
    assert ranked == before
    assert payload["post_ranking_boundary"]["mutates_scores"] is False
    for delivered in payload["items"]:
        original = originals[delivered["id"]]
        snapshot = delivered["delivery_decision"]["ranking_snapshot"]
        assert delivered["ensemble_score"] == original["ensemble_score"]
        assert delivered["final_score"] == original["final_score"]
        assert delivered["ensemble_score"] != original["score"]
        assert delivered["final_score"] != original["relevance_score"]
        assert delivered["pre_layer_ranking"]["ensemble_score"] == original["ensemble_score"]
        assert delivered["pre_layer_ranking"]["final_score"] == original["final_score"]
        assert snapshot["input_ensemble_score"] == original["ensemble_score"]
        assert snapshot["input_final_score"] == original["final_score"]
        assert snapshot["rank_identifiers"] == original["pre_layer_ranking"]["rank_identifiers"]
        assert delivered["delivery_decision"]["does_not_mutate_ensemble"] is True
        assert delivered["delivery_decision"]["ranking_input"] is False
        assert delivered["delivery_decision"]["ranking_output"] is False


def test_ambient_delivery_routes_existing_pr18_gen9_ranking_inputs_without_new_ranking_signals():
    from hedwig.personal_algorithm import route_items_after_ranking

    ranked = [
        {
            "id": "pr18-critical",
            "title": "Critical PR18 item",
            "url": "https://example.test/pr18-critical",
            "platform": "test",
            "ensemble_score": 0.940001,
            "final_score": 0.910003,
            "ensemble_rank": 1,
            "feed_position": 0,
            "urgency": "alert",
            "component_scores": {"content": 0.88, "popularity": 0.42},
            "ranking_features": {"source_reliability": 0.7, "novelty": 0.3},
            "pre_layer_ranking": {
                "ensemble_score": 0.940001,
                "final_score": 0.910003,
                "input_rank": 1,
                "input_order": 0,
                "rank_identifiers": {
                    "ranking_run_id": "pr18-gen9-run",
                    "rank_slot": "slot-1",
                    "feed_position": 0,
                },
                "immutable": True,
            },
        },
        {
            "id": "pr18-daily",
            "title": "Daily PR18 item",
            "url": "https://example.test/pr18-daily",
            "platform": "test",
            "ensemble_score": 0.730007,
            "final_score": 0.700009,
            "ensemble_rank": 2,
            "feed_position": 1,
            "urgency": "digest",
            "component_scores": {"content": 0.67, "popularity": 0.51},
            "ranking_features": {"source_reliability": 0.6, "novelty": 0.5},
            "pre_layer_ranking": {
                "ensemble_score": 0.730007,
                "final_score": 0.700009,
                "input_rank": 2,
                "input_order": 1,
                "rank_identifiers": {
                    "ranking_run_id": "pr18-gen9-run",
                    "rank_slot": "slot-2",
                    "feed_position": 1,
                },
                "immutable": True,
            },
        },
    ]
    before = copy.deepcopy(ranked)
    policy = {
        "exploration": {"enabled": False},
        "delivery": {
            "default_channel": "dashboard",
            "urgency": {"critical_score_threshold": 0.9, "daily_score_threshold": 0.65},
        },
    }

    routed = route_items_after_ranking(ranked, policy=policy)

    assert ranked == before
    assert [item["id"] for item in routed] == ["pr18-critical", "pr18-daily"]
    allowed_added_fields = {
        "delivery_policy",
        "delivery_decision",
        "is_exploration",
        "media_profile",
        "post_ranking_decisions",
    }
    forbidden_added_ranking_signals = {
        "ambient_score",
        "delivery_score",
        "delivery_rank",
        "explanation_score",
        "ranking_signal",
        "ranking_signals",
        "composite_fitness",
        "manus_score",
        "litellm_score",
        "vlm_score",
        "media_understanding_score",
    }
    for original, delivered in zip(before, routed):
        assert set(delivered) - set(original) <= allowed_added_fields
        assert forbidden_added_ranking_signals.isdisjoint(set(delivered) - set(original))
        assert delivered["ensemble_score"] == original["ensemble_score"]
        assert delivered["final_score"] == original["final_score"]
        assert delivered["component_scores"] == original["component_scores"]
        assert delivered["ranking_features"] == original["ranking_features"]
        assert delivered["pre_layer_ranking"] == original["pre_layer_ranking"]

        decision = delivered["delivery_decision"]
        snapshot = decision["ranking_snapshot"]
        assert decision["decision_layer"] == "post_ranking_delivery"
        assert decision["post_ranking"] is True
        assert decision["does_not_mutate_ensemble"] is True
        assert decision["ranking_input"] is False
        assert decision["ranking_output"] is False
        assert snapshot["input_ensemble_score"] == original["ensemble_score"]
        assert snapshot["input_final_score"] == original["final_score"]
        assert snapshot["input_ensemble_rank"] == original["pre_layer_ranking"]["input_rank"]
        assert snapshot["input_order"] == original["pre_layer_ranking"]["input_order"]
        assert snapshot["rank_identifiers"] == original["pre_layer_ranking"]["rank_identifiers"]
        assert delivered["post_ranking_decisions"]["delivery"] == decision


def test_ambient_item_contract_keeps_delivery_and_explanation_metadata_out_of_ranking_inputs():
    from hedwig.delivery.ambient import select_ambient_items
    from hedwig.models import AmbientDeliveryItemSet

    ranked = [
        {
            "id": "boundary-critical",
            "title": "Boundary critical",
            "url": "https://example.test/boundary-critical",
            "platform": "test",
            "ensemble_score": 0.92,
            "final_score": 0.89,
            "ensemble_rank": 4,
            "feed_position": 0,
            "urgency": "alert",
            "why_relevant": "Operationally relevant without exposing score details.",
            "pre_layer_ranking": {
                "ensemble_score": 0.92,
                "final_score": 0.89,
                "input_rank": 4,
                "input_order": 0,
                "rank_identifiers": {"ranking_run_id": "boundary-run", "rank_slot": "critical"},
                "immutable": True,
            },
        }
    ]

    payload = select_ambient_items(ranked, "critical", limit=1)

    AmbientDeliveryItemSet.model_validate(payload)
    item = payload["items"][0]
    assert item["id"] == "boundary-critical"
    assert payload["post_ranking_boundary"]["delivery_decisions_are_metadata"] is True
    assert payload["post_ranking_boundary"]["mutates_scores"] is False
    assert payload["post_ranking_boundary"]["mutates_rank_identity"] is False
    assert payload["post_ranking_boundary"]["immutable_fields"] == [
        "ensemble_score",
        "final_score",
        "pre_layer_ranking",
    ]
    assert item["post_ranking_boundary"]["delivery_decisions_are_metadata"] is True
    assert item["post_ranking_boundary"]["mutates_scores"] is False
    assert item["post_ranking_boundary"]["mutates_rank_identity"] is False
    assert item["post_ranking_boundary"]["explanation_is_display_only"] is True

    decision = item["delivery_decision"]
    explanation = item["explanation"]
    assert decision["ranking_input"] is False
    assert decision["ranking_output"] is False
    assert decision["explanation"]["ranking_input"] is False
    assert decision["explanation"]["score_like_authority"] is False
    assert explanation["display_only"] is True
    assert explanation["ranking_input"] is False
    assert explanation["score_like_authority"] is False

    ranking_input_like_keys = {
        "component_scores",
        "ranking_features",
        "ranking_trace",
        "llm_judge",
        "bandit_state",
        "reward_value",
        "signal_strength",
        "composite_fitness",
    }
    assert ranking_input_like_keys.isdisjoint(item)
    assert ranking_input_like_keys.isdisjoint(decision)
    assert ranking_input_like_keys.isdisjoint(explanation)


def test_ambient_explanations_deny_score_like_authority_in_surface_payloads():
    from hedwig.delivery.ambient import (
        explanation_copy_is_surface_safe,
        explanation_payload_is_serialization_safe,
        select_ambient_items,
    )
    from hedwig.models import AmbientDeliveryItemSet

    ranked = [
        {
            "id": "explanation-authority-denied",
            "title": "Explanation authority denial",
            "url": "https://example.test/explanation-authority-denied",
            "platform": "test",
            "ensemble_score": 0.99,
            "final_score": 0.98,
            "ensemble_rank": 1,
            "feed_position": 0,
            "urgency": "alert",
            "reason": "Ranked #1 with final_score 0.98 and 99% confidence. Must read.",
            "why_relevant": "Highest score in the ranking trace.",
            "anomaly_label": {"reason": "Top ranked because component_scores were strongest."},
            "ranking_features": {"source_authority": 1.0},
            "component_scores": {"llm_judge": 0.99},
            "ranking_trace": {"final_score": 0.98},
            "pre_layer_ranking": {
                "ensemble_score": 0.99,
                "final_score": 0.98,
                "input_rank": 1,
                "input_order": 0,
                "rank_identifiers": {"ranking_run_id": "explanation-boundary", "rank_slot": "slot-1"},
                "immutable": True,
            },
        }
    ]

    payload = select_ambient_items(ranked, "critical", limit=1)

    AmbientDeliveryItemSet.model_validate(payload)
    item = payload["items"][0]
    assert item["explanation"]["text"] == item["reason"]
    assert item["explanation"]["display_only"] is True
    assert item["explanation"]["ranking_input"] is False
    assert item["explanation"]["score_like_authority"] is False
    assert item["delivery_decision"]["explanation"] == item["explanation"]
    assert explanation_copy_is_surface_safe(item["reason"]) is True
    assert explanation_payload_is_serialization_safe(item["explanation"]) is True

    serialized = json.dumps(item["explanation"])
    for forbidden_text in (
        "final_score",
        "99%",
        "confidence",
        "Ranked #1",
        "Must read",
        "Highest score",
        "component_scores",
        "ranking_trace",
    ):
        assert forbidden_text not in serialized


def test_ambient_explanation_context_rejects_unapproved_authority_fields():
    from hedwig.delivery.ambient import (
        ambient_display_reason_from_context,
        ambient_explanation_context,
        explanation_payload_is_serialization_safe,
        sanitize_ambient_explanation_payload,
    )

    item = {
        "id": "context-authority-denied",
        "title": "Context authority denial",
        "url": "https://example.test/context-authority-denied",
        "platform": "test",
        "author": "tester",
        "urgency": "digest",
        "reason": "Useful for the daily workflow.",
        "ensemble_score": 0.91,
        "final_score": 0.9,
        "ranking_features": {"source_authority": 0.8},
        "component_scores": {"content": 0.9},
    }
    decision = {
        "surface": "daily",
        "timing": "next_digest",
        "channel": "dashboard",
        "ranking_snapshot": {"input_final_score": 0.9},
    }

    context = ambient_explanation_context(item, decision)

    assert set(context["item"]) == {
        "id",
        "title",
        "url",
        "platform",
        "author",
        "urgency",
        "reason",
        "why_relevant",
        "anomaly_reason",
        "is_exploration",
    }
    assert set(context["delivery"]) == {"surface", "timing", "channel"}
    assert "ensemble_score" not in context["item"]
    assert "final_score" not in context["item"]
    assert "ranking_snapshot" not in context["delivery"]
    assert ambient_display_reason_from_context(context) == "Useful for the daily workflow."

    with pytest.raises(ValueError, match="unapproved fields"):
        ambient_display_reason_from_context({
            **context,
            "item": {**context["item"], "final_score": 0.9},
        })
    with pytest.raises(ValueError, match="unapproved fields"):
        ambient_display_reason_from_context({
            **context,
            "delivery": {**context["delivery"], "ranking_snapshot": {"input_final_score": 0.9}},
        })

    unsafe_payload = {"text": "Display copy", "ranking_snapshot": {"input_final_score": 0.9}}
    assert explanation_payload_is_serialization_safe(unsafe_payload) is False
    assert sanitize_ambient_explanation_payload(
        {"text": "Ranked #1 with final_score 0.90 and 90% confidence."},
        fallback_text="Relevant digest item selected for today.",
    ) == {
        "text": "Relevant digest item selected for today.",
        "display_only": True,
        "ranking_input": False,
        "score_like_authority": False,
    }


def test_shared_ambient_helpers_preserve_scores_through_filtering_and_formatting():
    from hedwig.delivery.ambient import select_ambient_items
    from hedwig.models import AmbientDeliveryItemSet

    items = _ranked_items()
    items[0]["final_score"] = 0.89
    items[1]["score"] = 999
    items[1]["relevance_score"] = 999
    items[2]["ensemble_score"] = 0.0
    items[2]["final_score"] = 0.0
    before = {item["id"]: copy.deepcopy(item) for item in items}

    weekly = select_ambient_items(items, "weekly", limit=1)
    tray = select_ambient_items(items, "native-notification", limit=2)

    assert [item["id"] for item in weekly["items"]] == ["weekly-1"]
    assert [item["id"] for item in tray["items"]] == ["critical-1", "daily-1"]
    assert items == list(before.values())

    formatted_weekly = json.loads(json.dumps(weekly))
    formatted_tray = json.loads(json.dumps(tray))
    AmbientDeliveryItemSet.model_validate(formatted_weekly)
    AmbientDeliveryItemSet.model_validate(formatted_tray)

    for payload in (formatted_weekly, formatted_tray):
        assert payload["post_ranking_boundary"]["mutates_scores"] is False
        assert payload["post_ranking_boundary"]["mutates_rank_identity"] is False
        for item in payload["items"]:
            original = before[item["id"]]
            assert item["ensemble_score"] == original["ensemble_score"]
            assert item["final_score"] == original["final_score"]
            assert item["pre_layer_ranking"]["ensemble_score"] == original["ensemble_score"]
            assert item["pre_layer_ranking"]["final_score"] == original["final_score"]
            assert item["delivery_decision"]["ranking_snapshot"]["input_ensemble_score"] == original["ensemble_score"]
            assert item["delivery_decision"]["ranking_snapshot"]["input_final_score"] == original["final_score"]
            assert item["pre_layer_ranking"]["input_rank"] == original["ensemble_rank"]
            expected_order = original.get("feed_position", original["ensemble_rank"] - 1)
            assert item["pre_layer_ranking"]["input_order"] == expected_order
            assert item["pre_layer_ranking"]["rank_identifiers"]["id"] == original["id"]
            assert item["pre_layer_ranking"]["rank_identifiers"]["ensemble_rank"] == original["ensemble_rank"]
            assert item["delivery_decision"]["ranking_snapshot"]["input_order"] == expected_order
            assert item["delivery_decision"]["ranking_snapshot"]["rank_identifiers"]["id"] == original["id"]
            assert item["delivery_decision"]["does_not_mutate_ensemble"] is True
            assert item["explanation"]["display_only"] is True
            assert item["explanation"]["ranking_input"] is False
            assert item["explanation"]["score_like_authority"] is False


def test_ambient_contract_preserves_existing_pre_layer_rank_identifiers():
    from hedwig.delivery.ambient import select_ambient_items
    from hedwig.models import AmbientDeliveryItemSet

    items = _ranked_items()
    items[1]["pre_layer_ranking"] = {
        "input_rank": 200,
        "input_order": 12,
        "rank_identifiers": {"ranking_run_id": "ambient-run", "rank_slot": "daily-slot"},
        "immutable": True,
    }

    daily = select_ambient_items(items, "daily", limit=1)

    AmbientDeliveryItemSet.model_validate(daily)
    assert daily["items"][0]["id"] == "daily-1"
    assert daily["items"][0]["pre_layer_ranking"]["input_rank"] == 200
    assert daily["items"][0]["pre_layer_ranking"]["input_order"] == 12
    assert daily["items"][0]["pre_layer_ranking"]["rank_identifiers"]["ranking_run_id"] == "ambient-run"
    assert daily["items"][0]["pre_layer_ranking"]["rank_identifiers"]["rank_slot"] == "daily-slot"
    assert daily["items"][0]["delivery_decision"]["ranking_snapshot"]["input_ensemble_rank"] == 200
    assert daily["items"][0]["delivery_decision"]["ranking_snapshot"]["input_order"] == 12
    assert daily["items"][0]["delivery_decision"]["ranking_snapshot"]["rank_identifiers"]["rank_slot"] == "daily-slot"


def test_ambient_item_set_contract_is_small_and_display_only():
    from pydantic import ValidationError

    from hedwig.delivery.ambient import ambient_item_set_schema, select_ambient_items
    from hedwig.models import AmbientDeliveryItemSet

    noisy_items = _ranked_items()
    noisy_items[0]["content"] = "large body should not be in ambient item contract"
    noisy_items[0]["devils_advocate"] = "not needed by ambient surfaces"
    noisy_items[0]["extra"] = {"thumbnail_url": "https://example.test/thumb.png"}

    critical = select_ambient_items(noisy_items, "critical", limit=1)

    schema = ambient_item_set_schema()
    assert schema["title"] == "AmbientDeliveryItemSet"
    assert "AmbientDeliveryItem" in schema["$defs"]
    assert critical["limit"] == 1
    assert critical["count"] == 1
    assert "content" not in critical["items"][0]
    assert "devils_advocate" not in critical["items"][0]
    assert critical["items"][0]["explanation"]["display_only"] is True
    assert critical["items"][0]["explanation"]["ranking_input"] is False
    assert critical["items"][0]["explanation"]["score_like_authority"] is False
    AmbientDeliveryItemSet.model_validate(critical)

    unsafe = copy.deepcopy(critical)
    unsafe["items"][0]["explanation"]["score_like_authority"] = True
    with pytest.raises(ValidationError):
        AmbientDeliveryItemSet.model_validate(unsafe)


def test_ambient_dashboard_endpoints_expose_surfaces_and_items(tmp_env):
    from hedwig.dashboard.app import create_app
    from hedwig.dashboard.demo_seed import seed_demo
    from hedwig.models import AmbientDeliveryItemSet

    seed_demo(reset=True)
    client = TestClient(create_app())

    surfaces = client.get("/ambient/surfaces").json()["surfaces"]
    assert {surface["surface"] for surface in surfaces} >= {"critical", "daily", "weekly", "pwa", "tray"}

    critical = client.get("/ambient/critical/api?limit=2").json()
    AmbientDeliveryItemSet.model_validate(critical)
    assert critical["surface"] == "critical"
    assert critical["entry_point"]["request_path"] == "/ambient/critical/api"
    assert critical["entry_point"]["contract_schema"] == "ambient_delivery_item_set.v1"
    assert critical["items"]
    assert len(critical["items"]) <= 2
    assert all(item["delivery_decision"]["surface"] == "critical" for item in critical["items"])
    assert all(item["delivery_decision"]["does_not_mutate_ensemble"] for item in critical["items"])

    tray = client.get("/ambient/tray/api?limit=3").json()
    AmbientDeliveryItemSet.model_validate(tray)
    assert tray["surface"] == "tray"
    assert tray["entry_point"]["entry_kind"] == "requester"
    assert tray["entry_point"]["request_path"] == "/ambient/tray/api"
    assert len(tray["items"]) <= 3
    assert client.get("/ambient/not-real/api").status_code == 404


def test_ambient_dashboard_uses_existing_ranked_output_adapter(tmp_env, monkeypatch):
    import hedwig.dashboard.app as dashboard_app

    ranked_rows = [
        {
            "id": "stored-critical",
            "title": "Stored Critical",
            "url": "https://example.test/stored-critical",
            "platform": "test",
            "relevance_score": 999,
            "ensemble_score": 0.93,
            "final_score": 0.87,
            "ensemble_rank": 7,
            "urgency": "alert",
            "why_relevant": "Already ranked upstream.",
        },
        {
            "id": "stored-daily",
            "title": "Stored Daily",
            "url": "https://example.test/stored-daily",
            "platform": "test",
            "relevance_score": 999,
            "ensemble_score": 0.71,
            "final_score": 0.69,
            "ensemble_rank": 8,
            "urgency": "digest",
        },
    ]

    monkeypatch.setattr(
        dashboard_app,
        "_load_ranked_feed_items",
        lambda days=14: [
            dashboard_app._ranked_feed_item_from_signal_row(row, input_order=offset)
            for offset, row in enumerate(ranked_rows)
        ],
    )

    client = TestClient(dashboard_app.create_app())
    critical = client.get("/ambient/critical/api?limit=1").json()

    assert critical["items"][0]["id"] == "stored-critical"
    assert critical["items"][0]["ensemble_score"] == 0.93
    assert critical["items"][0]["final_score"] == 0.87
    assert critical["items"][0]["pre_layer_ranking"]["ensemble_score"] == 0.93
    assert critical["items"][0]["pre_layer_ranking"]["final_score"] == 0.87
    assert critical["items"][0]["pre_layer_ranking"]["input_rank"] == 7
    assert critical["items"][0]["pre_layer_ranking"]["input_order"] == 0
    assert critical["items"][0]["delivery_decision"]["ranking_snapshot"]["input_ensemble_score"] == 0.93
    assert critical["items"][0]["delivery_decision"]["ranking_snapshot"]["input_final_score"] == 0.87
    assert critical["items"][0]["delivery_decision"]["ranking_snapshot"]["input_ensemble_rank"] == 7
    assert critical["items"][0]["delivery_decision"]["ranking_snapshot"]["rank_identifiers"]["feed_position"] == 0
    assert critical["items"][0]["explanation"]["display_only"] is True
    assert critical["items"][0]["explanation"]["ranking_input"] is False


def test_ambient_page_renders_selected_items_without_manual_feed_entry(tmp_env):
    from hedwig.dashboard.app import create_app
    from hedwig.dashboard.demo_seed import seed_demo

    seed_demo(reset=True)
    client = TestClient(create_app())

    page = client.get("/ambient/critical?limit=2")
    assert page.status_code == 200
    assert "Ambient delivery" in page.text
    assert "ambient_delivery_item_set.v1" in page.text
    assert "post-ranking" in page.text
    assert "/feed?stream=critical_only" not in page.text
    assert "Pre-layer scores" not in page.text
    assert 'class="ambient-card"' in page.text
    assert 'aria-label="Ambient item actions"' in page.text
    assert 'data-ambient-action="open"' in page.text
    assert 'data-ambient-action="save"' in page.text
    assert 'data-ambient-action="snooze"' in page.text
    assert 'data-ambient-action="dismiss"' in page.text
    assert 'data-event-type="opened"' in page.text
    assert 'data-event-type="saved"' in page.text
    assert 'data-event-type="snoozed"' in page.text
    assert 'data-event-type="dismissed"' in page.text
    assert 'data-reward-derived="false"' in page.text
    assert "raw_delivery_event: true" in page.text
    assert "navigator.sendBeacon('/events/beacon'" in page.text
    assert "Delivery rule" in page.text
    assert "Why this surfaced" in page.text
    assert 'aria-label="Display-only reason"' in page.text
    assert "reason display-only" in page.text

    missing = client.get("/ambient/not-real")
    assert missing.status_code == 404
    assert "Surface unavailable" in missing.text


def test_ambient_delivery_ui_events_reuse_pr18_raw_behavior_schema(tmp_env):
    from hedwig.dashboard.app import create_app
    from hedwig.storage import get_behavior_events, get_behavior_rewards

    client = TestClient(create_app())
    resp = client.post(
        "/events/beacon",
        json={
            "events": [
                {
                    "signal_id": "ambient-raw-1",
                    "event_type": "delivered",
                    "feed_id": "ambient:critical",
                    "feed_mode": "ambient_critical",
                    "position_in_feed": 0,
                    "device": "desktop",
                },
                {
                    "signal_id": "ambient-raw-1",
                    "event_type": "opened",
                    "feed_id": "ambient:critical",
                    "feed_mode": "ambient_critical",
                    "position_in_feed": 0,
                    "device": "desktop",
                },
                {
                    "signal_id": "ambient-raw-1",
                    "event_type": "clicked",
                    "feed_id": "ambient:critical",
                    "feed_mode": "ambient_critical",
                    "position_in_feed": 0,
                    "device": "desktop",
                },
                {
                    "signal_id": "ambient-raw-2",
                    "event_type": "saved",
                    "feed_id": "ambient:daily",
                    "feed_mode": "ambient_daily",
                    "position_in_feed": 1,
                    "device": "mobile_web",
                },
                {
                    "signal_id": "ambient-raw-2",
                    "event_type": "snoozed",
                    "feed_id": "ambient:daily",
                    "feed_mode": "ambient_daily",
                    "position_in_feed": 1,
                    "device": "mobile_web",
                },
                {
                    "signal_id": "ambient-raw-2",
                    "event_type": "dismissed",
                    "feed_id": "ambient:daily",
                    "feed_mode": "ambient_daily",
                    "position_in_feed": 1,
                    "device": "mobile_web",
                },
            ]
        },
    )

    assert resp.status_code == 200
    assert resp.json()["saved"] == 6
    assert resp.json()["feed_rewards"] == 0
    assert resp.json()["delivery_rewards"] == 5
    assert resp.json()["rewards"] == 5

    critical_events = get_behavior_events(signal_id="ambient-raw-1", feed_mode="ambient_critical")
    daily_events = get_behavior_events(signal_id="ambient-raw-2", feed_mode="ambient_daily")
    assert {row["event_type"] for row in critical_events} == {"delivered", "opened", "clicked"}
    assert {row["event_type"] for row in daily_events} == {"saved", "snoozed", "dismissed"}
    assert all(row["feed_id"].startswith("ambient:") for row in critical_events + daily_events)
    assert all(row["position_in_feed"] in {0, 1} for row in critical_events + daily_events)
    critical_rewards = get_behavior_rewards(signal_id="ambient-raw-1")
    daily_rewards = get_behavior_rewards(signal_id="ambient-raw-2")
    assert {row["event_type"] for row in critical_rewards} == {"opened", "clicked"}
    assert {row["event_type"] for row in daily_rewards} == {"saved", "snoozed", "dismissed"}
    assert all(row["source"] == "ambient_delivery" for row in critical_rewards + daily_rewards)
    assert all(row["derivation_rule_version"] == "ambient_delivery_reward_v1" for row in critical_rewards + daily_rewards)
    assert all(row["feed_mode"].startswith("ambient_") for row in critical_rewards + daily_rewards)
    assert all(row["source_event_ids"] for row in critical_rewards + daily_rewards)


def test_ambient_delivery_surface_events_do_not_call_reward_creation(tmp_env, monkeypatch):
    import hedwig.delivery.ambient as ambient_delivery
    import hedwig.personal_algorithm as personal_algorithm
    import hedwig.storage as storage

    from hedwig.dashboard.app import create_app
    from hedwig.storage import get_behavior_events, get_behavior_rewards

    def reward_interpreter_must_not_run(event):
        raise AssertionError(f"ambient delivery event reached reward interpreter: {event!r}")

    def evolution_writer_must_not_run(*args, **kwargs):
        raise AssertionError("ambient delivery event reached evolution signal writer")

    ambient_interpreter_calls = []
    original_ambient_interpreter = ambient_delivery.interpret_ambient_delivery_event

    def tracking_ambient_reward_interpreter(event):
        ambient_interpreter_calls.append(event["event_type"])
        return original_ambient_interpreter(event)

    monkeypatch.setattr(personal_algorithm, "interpret_behavior_event", reward_interpreter_must_not_run)
    monkeypatch.setattr(ambient_delivery, "interpret_ambient_delivery_event", tracking_ambient_reward_interpreter)
    monkeypatch.setattr(storage, "save_evolution_signal", evolution_writer_must_not_run)

    client = TestClient(create_app())
    resp = client.post(
        "/events/beacon",
        json={
            "events": [
                {
                    "signal_id": "ambient-boundary-1",
                    "event_type": "delivered",
                    "feed_id": "ambient:critical",
                    "feed_mode": "ambient_critical",
                    "raw_delivery_event": True,
                },
                {
                    "signal_id": "ambient-boundary-1",
                    "event_type": "opened",
                    "feed_id": "ambient:critical",
                    "feed_mode": "ambient_critical",
                    "delivery_surface": "critical",
                },
                {
                    "signal_id": "ambient-boundary-2",
                    "event_type": "saved",
                    "feed_id": "ambient:daily",
                    "feed_mode": "ambient_daily",
                    "ambient_surface": "daily",
                },
            ]
        },
    )

    assert resp.status_code == 200
    assert resp.json()["saved"] == 3
    assert resp.json()["feed_rewards"] == 0
    assert resp.json()["delivery_rewards"] == 2
    assert resp.json()["rewards"] == 2
    assert ambient_interpreter_calls == ["delivered", "opened", "saved"]
    assert {row["event_type"] for row in get_behavior_events(signal_id="ambient-boundary-1")} == {
        "delivered",
        "opened",
    }
    assert {row["event_type"] for row in get_behavior_events(signal_id="ambient-boundary-2")} == {"saved"}
    rewards = get_behavior_rewards(signal_id="ambient-boundary-1") + get_behavior_rewards(signal_id="ambient-boundary-2")
    assert {row["event_type"] for row in rewards} == {"opened", "saved"}
    assert all(row["source"] == "ambient_delivery" for row in rewards)


def test_ambient_delivery_api_and_background_paths_emit_same_raw_events_and_rewards_without_schema_extensions(
    tmp_env,
    monkeypatch,
):
    import hedwig.dashboard.app as dashboard_app
    from hedwig.delivery.ambient import ambient_delivery_events, record_ambient_delivery_events
    from hedwig.storage import get_behavior_events, get_behavior_rewards

    ranked_rows = [
        {
            "id": "ambient-api-1",
            "title": "API delivered item",
            "url": "https://example.test/api-delivered",
            "platform": "test",
            "ensemble_score": 0.94,
            "final_score": 0.90,
            "ensemble_rank": 1,
            "urgency": "alert",
        },
        {
            "id": "ambient-api-2",
            "title": "Daily API delivered item",
            "url": "https://example.test/api-daily",
            "platform": "test",
            "ensemble_score": 0.70,
            "final_score": 0.68,
            "ensemble_rank": 2,
            "urgency": "digest",
        },
    ]

    monkeypatch.setattr(
        dashboard_app,
        "_load_ranked_feed_items",
        lambda days=14: [
            dashboard_app._ranked_feed_item_from_signal_row(row, input_order=offset)
            for offset, row in enumerate(ranked_rows)
        ],
    )

    client = TestClient(dashboard_app.create_app())
    response = client.get("/ambient/critical/api?limit=1")

    assert response.status_code == 200
    payload = response.json()
    assert [item["id"] for item in payload["items"]] == ["ambient-api-1"]

    api_events = get_behavior_events(
        signal_id="ambient-api-1",
        event_types=["delivered"],
        feed_mode="ambient_critical",
    )
    assert len(api_events) == 1
    assert api_events[0]["feed_id"] == "ambient:critical"
    assert api_events[0]["device"] == "server_api"
    assert api_events[0]["position_in_feed"] == 0
    assert get_behavior_rewards(signal_id="ambient-api-1") == []

    background_events = ambient_delivery_events(
        payload,
        event_type="clicked",
        device="background_worker",
    )
    existing_behavior_event_columns = {
        "signal_id",
        "event_type",
        "dwell_ms",
        "position_in_feed",
        "feed_id",
        "feed_mode",
        "device",
    }
    assert len(background_events) == 1
    assert set(background_events[0]).issubset(existing_behavior_event_columns)
    assert "ambient_surface" not in background_events[0]
    assert "delivery_surface" not in background_events[0]
    assert background_events[0]["feed_id"] == api_events[0]["feed_id"]
    assert background_events[0]["feed_mode"] == api_events[0]["feed_mode"]
    assert background_events[0]["position_in_feed"] == api_events[0]["position_in_feed"]

    assert record_ambient_delivery_events(
        payload,
        event_type="clicked",
        device="background_worker",
    ) == 1
    stored_background_events = get_behavior_events(
        signal_id="ambient-api-1",
        event_types=["clicked"],
        feed_mode="ambient_critical",
    )
    assert len(stored_background_events) == 1
    assert stored_background_events[0]["feed_id"] == "ambient:critical"
    assert stored_background_events[0]["device"] == "background_worker"
    background_rewards = get_behavior_rewards(signal_id="ambient-api-1")
    assert len(background_rewards) == 1
    assert background_rewards[0]["event_type"] == "clicked"
    assert background_rewards[0]["source"] == "ambient_delivery"
    assert background_rewards[0]["derivation_rule_version"] == "ambient_delivery_reward_v1"
    assert background_rewards[0]["feed_mode"] == "ambient_critical"
    assert background_rewards[0]["source_event_ids"] == [stored_background_events[0]["id"]]


@pytest.mark.parametrize(
    ("surface", "expected_titles", "expected_reasons", "excluded_titles"),
    [
        (
            "critical",
            ["Ambient Critical Signal"],
            ["Critical reason rendered on the critical surface."],
            [
                "Ambient Daily Alpha",
                "Ambient Daily Beta",
                "Ambient Weekly Alpha",
                "Ambient Weekly Beta",
                "Ambient PWA Exploration",
            ],
        ),
        (
            "daily",
            ["Ambient Daily Alpha", "Ambient Daily Beta"],
            [
                "Daily alpha reason rendered on daily and tray surfaces.",
                "Daily beta reason rendered only when selected.",
            ],
            [
                "Ambient Critical Signal",
                "Ambient Weekly Alpha",
                "Ambient Weekly Beta",
                "Ambient PWA Exploration",
            ],
        ),
        (
            "weekly",
            ["Ambient Weekly Alpha", "Ambient Weekly Beta"],
            [
                "Weekly alpha reason rendered on the weekly surface.",
                "Weekly beta reason rendered only when selected.",
            ],
            [
                "Ambient Critical Signal",
                "Ambient Daily Alpha",
                "Ambient Daily Beta",
                "Ambient PWA Exploration",
            ],
        ),
        (
            "pwa",
            ["Ambient PWA Exploration"],
            ["PWA reason rendered on the installable ambient shelf."],
            [
                "Ambient Critical Signal",
                "Ambient Daily Alpha",
                "Ambient Daily Beta",
                "Ambient Weekly Alpha",
                "Ambient Weekly Beta",
            ],
        ),
        (
            "tray",
            ["Ambient Critical Signal", "Ambient Daily Alpha"],
            [
                "Critical reason rendered on the critical surface.",
                "Daily alpha reason rendered on daily and tray surfaces.",
            ],
            [
                "Ambient Daily Beta",
                "Ambient Weekly Alpha",
                "Ambient Weekly Beta",
                "Ambient PWA Exploration",
            ],
        ),
    ],
)
def test_each_ambient_surface_page_renders_only_selected_small_item_set(
    tmp_env,
    monkeypatch,
    surface,
    expected_titles,
    expected_reasons,
    excluded_titles,
):
    import hedwig.dashboard.app as dashboard_app

    ranked_items = [
        {
            "id": "ambient-critical",
            "title": "Ambient Critical Signal",
            "url": "https://example.test/critical",
            "platform": "test",
            "ensemble_score": 0.96,
            "final_score": 0.96,
            "ensemble_rank": 1,
            "urgency": "alert",
            "why_relevant": "Critical reason rendered on the critical surface.",
        },
        {
            "id": "ambient-daily-alpha",
            "title": "Ambient Daily Alpha",
            "url": "https://example.test/daily-alpha",
            "platform": "test",
            "ensemble_score": 0.74,
            "final_score": 0.74,
            "ensemble_rank": 2,
            "urgency": "digest",
            "why_relevant": "Daily alpha reason rendered on daily and tray surfaces.",
        },
        {
            "id": "ambient-daily-beta",
            "title": "Ambient Daily Beta",
            "url": "https://example.test/daily-beta",
            "platform": "test",
            "ensemble_score": 0.68,
            "final_score": 0.68,
            "ensemble_rank": 3,
            "urgency": "digest",
            "why_relevant": "Daily beta reason rendered only when selected.",
        },
        {
            "id": "ambient-weekly-alpha",
            "title": "Ambient Weekly Alpha",
            "url": "https://example.test/weekly-alpha",
            "platform": "test",
            "ensemble_score": 0.61,
            "final_score": 0.61,
            "ensemble_rank": 4,
            "urgency": "digest",
            "why_relevant": "Weekly alpha reason rendered on the weekly surface.",
        },
        {
            "id": "ambient-weekly-beta",
            "title": "Ambient Weekly Beta",
            "url": "https://example.test/weekly-beta",
            "platform": "test",
            "ensemble_score": 0.44,
            "final_score": 0.44,
            "ensemble_rank": 5,
            "urgency": "digest",
            "why_relevant": "Weekly beta reason rendered only when selected.",
        },
        {
            "id": "ambient-pwa",
            "title": "Ambient PWA Exploration",
            "url": "https://example.test/pwa",
            "platform": "test",
            "ensemble_score": 0.35,
            "final_score": 0.35,
            "ensemble_rank": 6,
            "is_exploration": True,
            "why_relevant": "PWA reason rendered on the installable ambient shelf.",
        },
    ]

    monkeypatch.setattr(dashboard_app, "_load_ranked_feed_items", lambda days=14: copy.deepcopy(ranked_items))

    client = TestClient(dashboard_app.create_app())
    page = client.get(f"/ambient/{surface}?limit=2")

    assert page.status_code == 200
    assert page.text.count('class="ambient-card"') == len(expected_titles)
    for title in expected_titles:
        assert title in page.text
    for reason in expected_reasons:
        assert reason in page.text
    for title in excluded_titles:
        assert title not in page.text
    assert "/feed?stream=critical_only" not in page.text
    assert 'aria-label="Ambient item actions"' in page.text
    assert 'aria-label="Display-only reason"' in page.text
    assert "Why this surfaced" in page.text
    assert "post-ranking metadata" in page.text


def test_ambient_page_renders_from_selected_items_when_manual_feed_is_unavailable(tmp_env, monkeypatch):
    import hedwig.dashboard.app as dashboard_app
    import hedwig.feeds as feeds

    ranked_items = [
        {
            "id": "ambient-only-1",
            "title": "Ambient Only Critical",
            "url": "https://example.test/ambient-only",
            "platform": "test",
            "ensemble_score": 0.99,
            "final_score": 0.99,
            "ensemble_rank": 1,
            "urgency": "alert",
            "why_relevant": "Selected for a receiver surface without opening the feed.",
        },
        {
            "id": "ambient-tail-exploration",
            "title": "Tail Exploration",
            "url": "https://example.test/tail",
            "platform": "test",
            "ensemble_score": 0.20,
            "final_score": 0.20,
            "ensemble_rank": 2,
        }
    ]

    def fail_manual_feed(*args, **kwargs):
        raise AssertionError("manual feed route/helper should not be required for ambient rendering")

    monkeypatch.setattr(dashboard_app, "_load_ranked_feed_items", lambda days=14: copy.deepcopy(ranked_items))
    monkeypatch.setattr(feeds, "list_feeds", fail_manual_feed)

    client = TestClient(dashboard_app.create_app())

    ambient = client.get("/ambient/critical?limit=1")
    assert ambient.status_code == 200
    assert "Ambient Only Critical" in ambient.text
    assert 'class="ambient-card"' in ambient.text
    assert 'data-signal-id="ambient-only-1"' in ambient.text
    assert 'data-surface="critical"' in ambient.text
    assert "Selected for a receiver surface without opening the feed." in ambient.text
    assert "feed-shell" not in ambient.text
    assert "feed-list" not in ambient.text

    with pytest.raises(AssertionError, match="manual feed route/helper"):
        client.get("/feed")


def test_all_ambient_surfaces_render_and_serve_api_without_opening_manual_feed(tmp_env, monkeypatch):
    import hedwig.dashboard.app as dashboard_app
    import hedwig.feeds as feeds

    ranked_items = [
        {
            "id": "ambient-reachable-critical",
            "title": "Reachable Critical Alert",
            "url": "https://example.test/reachable-critical",
            "platform": "test",
            "ensemble_score": 0.98,
            "final_score": 0.98,
            "ensemble_rank": 1,
            "urgency": "alert",
            "why_relevant": "Critical notification reason stays display-only.",
        },
        {
            "id": "ambient-reachable-daily",
            "title": "Reachable Daily Digest",
            "url": "https://example.test/reachable-daily",
            "platform": "test",
            "ensemble_score": 0.74,
            "final_score": 0.74,
            "ensemble_rank": 2,
            "urgency": "digest",
            "why_relevant": "Daily digest reason stays display-only.",
        },
        {
            "id": "ambient-reachable-weekly",
            "title": "Reachable Weekly Catchup",
            "url": "https://example.test/reachable-weekly",
            "platform": "test",
            "ensemble_score": 0.43,
            "final_score": 0.43,
            "ensemble_rank": 3,
            "urgency": "digest",
            "why_relevant": "Weekly catchup reason stays display-only.",
        },
        {
            "id": "ambient-reachable-pwa",
            "title": "Reachable PWA Shelf",
            "url": "https://example.test/reachable-pwa",
            "platform": "test",
            "ensemble_score": 0.28,
            "final_score": 0.28,
            "ensemble_rank": 4,
            "why_relevant": "PWA shelf reason stays display-only.",
        },
    ]

    def fail_manual_feed(*args, **kwargs):
        raise AssertionError("manual feed helper should not be used by ambient surfaces")

    monkeypatch.setattr(dashboard_app, "_load_ranked_feed_items", lambda days=14: copy.deepcopy(ranked_items))
    monkeypatch.setattr(feeds, "list_feeds", fail_manual_feed)

    client = TestClient(dashboard_app.create_app())
    expected_titles = {
        "critical": "Reachable Critical Alert",
        "daily": "Reachable Daily Digest",
        "weekly": "Reachable Weekly Catchup",
        "pwa": "Reachable PWA Shelf",
        "tray": "Reachable Critical Alert",
    }
    expected_reasons = {
        "critical": "Critical notification reason stays display-only.",
        "daily": "Daily digest reason stays display-only.",
        "weekly": "Weekly catchup reason stays display-only.",
        "pwa": "PWA shelf reason stays display-only.",
        "tray": "Critical notification reason stays display-only.",
    }

    surfaces = client.get("/ambient/surfaces")
    assert surfaces.status_code == 200
    entries = {entry["surface"]: entry for entry in surfaces.json()["surfaces"]}
    assert set(expected_titles).issubset(entries)
    assert all(entries[surface]["manual_feed_entry_required"] is False for surface in expected_titles)

    for surface, title in expected_titles.items():
        page = client.get(f"/ambient/{surface}?limit=1")
        assert page.status_code == 200
        assert title in page.text
        assert expected_reasons[surface] in page.text
        assert 'data-reason="' in page.text
        assert 'aria-label="Display-only reason"' in page.text
        assert 'class="ambient-card"' in page.text
        assert "feed-shell" not in page.text
        assert "feed-list" not in page.text
        assert "/feed?stream=critical_only" not in page.text

        payload = client.get(f"/ambient/{surface}/api?limit=1")
        assert payload.status_code == 200
        body = payload.json()
        assert body["surface"] == surface
        assert body["count"] == 1
        assert body["items"][0]["title"] == title
        assert body["items"][0]["reason"] == expected_reasons[surface]
        assert "reason" not in body["items"][0]["pre_layer_ranking"]
        assert "reason" not in body["items"][0]["delivery_decision"]["ranking_snapshot"]
        assert body["entry_point"]["manual_feed_entry_required"] is False


def test_app_shell_links_ambient_surface_without_replacing_feed_route(tmp_env):
    from hedwig.dashboard.app import create_app
    from hedwig.dashboard.demo_seed import seed_demo

    seed_demo(reset=True)
    client = TestClient(create_app())

    page = client.get("/")
    assert page.status_code == 200
    assert 'href="/ambient/pwa"' in page.text
    assert 'href="/feed"' in page.text
    assert "/feed?stream=critical_only" not in page.text

    feed = client.get("/feed")
    assert feed.status_code == 200
    assert 'data-stream="default"' in feed.text


def test_static_and_native_entry_points_use_ambient_contract_paths():
    from hedwig.delivery.ambient import ambient_surface_entry_points

    entry_points = {entry["surface"]: entry for entry in ambient_surface_entry_points()}
    manifest = json.loads(Path("hedwig/dashboard/static/manifest.json").read_text())
    sw = Path("hedwig/dashboard/static/sw.js").read_text()
    tray = Path("hedwig/native/tray.py").read_text()

    ambient_shortcut = next(shortcut for shortcut in manifest["shortcuts"] if shortcut["name"] == "Ambient")
    assert ambient_shortcut["url"] == entry_points["pwa"]["page_path"]
    assert entry_points["pwa"]["page_path"] in sw
    assert entry_points["pwa"]["request_path"] in sw
    assert entry_points["critical"]["page_path"] in sw
    assert "data.reason" in sw
    assert "body: reason" in sw
    assert entry_points["tray"]["page_path"] in tray
    assert "/feed?stream=critical_only" not in sw
