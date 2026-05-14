"""Personal algorithm policy, reward, feed, and delivery helpers.

This module is intentionally additive: it consumes already-ranked Hedwig
signals and appends user-owned feed, reward, exploration, and delivery metadata
without changing the hybrid ensemble's final score.
"""
from __future__ import annotations

import copy
import hashlib
import os
from datetime import datetime, timezone
from typing import Any

from hedwig.config import load_algorithm_config


DEFAULT_PERSONAL_ALGORITHM: dict[str, Any] = {
    "ranking_boundary": {
        "canonical_pre_layer_score": "final_score",
        "immutable_fields": ["ensemble_score", "final_score"],
        "post_ranking_layers": ["feed", "exploration", "media", "delivery", "reward"],
        "contract": "Post-ranking layers may annotate, reserve slots, route, and measure; they must not overwrite ensemble_score/final_score.",
    },
    "feed": {
        "default_mode": "grid",
        "available_modes": ["grid", "detail_swipe", "dense_reader"],
    },
    "swipe_policy": {
        "immutable_defaults": {
            "left": {"action": "save_later", "reward": 0.8, "strength": "strong_positive"},
            "right": {"action": "skip", "reward": -0.1, "strength": "weak_negative"},
            "next": {"action": "skip", "reward": 0.0, "strength": "weak_neutral"},
        },
        "user_overrides": {},
        "left": {"action": "save_later", "reward": 0.8, "strength": "strong_positive"},
        "right": {"action": "skip", "reward": -0.1, "strength": "weak_negative"},
        "next": {"action": "skip", "reward": 0.0, "strength": "weak_neutral"},
        "skip_strength": "weak",
        "shadow_test_required_for_semantic_change": True,
    },
    "reward_weights": {
        "save": 1.0,
        "open": 0.8,
        "not_interested": -1.0,
        "dwell": 0.2,
        "skip": -0.1,
        "swipe": 0.1,
    },
    "exploration": {
        "enabled": True,
        "rate": 0.10,
        "min_rate": 0.05,
        "max_rate": 0.15,
        "labels": ["anomaly", "contrarian", "critical", "opposing"],
    },
    "media": {
        "default_strategy": "text_thumbnail_transcript",
        "default_media_mode": {
            "active_mode": "Text+Thumbnail+Transcript",
            "text": True,
            "thumbnail": True,
            "transcript": True,
        },
        "advanced_media_capability": {
            "name": "Full Media Understanding",
            "enabled": False,
            "required_env_flag": "HEDWIG_FULL_MEDIA_UNDERSTANDING",
            "policy_enabled": False,
            "extracted_features": [],
        },
    },
    "delivery": {
        "schema_version": "delivery_policy_config.v1",
        "enabled": True,
        "surfaces": ["critical", "daily", "weekly", "pwa", "tray"],
        "preferred_surfaces": ["daily"],
        "channels": ["dashboard", "email", "slack", "discord", "pwa", "tray"],
        "default_channel": "dashboard",
        "timing": {
            "critical_timing": "now",
            "daily_digest_time": "09:00",
            "weekly_digest_day": "monday",
            "weekly_digest_time": "09:00",
            "timezone": "local",
            "defer_to_quiet_hours": True,
        },
        "repeat": {"enabled": True, "max_count": 2, "min_interval_minutes": 240, "snooze_minutes": 60},
        "quiet_hours": {
            "enabled": False,
            "start": "22:00",
            "end": "07:00",
            "timezone": "local",
            "allow_critical_override": True,
        },
        "urgency": {
            "critical_urgencies": ["alert"],
            "critical_score_threshold": 0.85,
            "daily_score_threshold": 0.65,
            "exploration_surface": "pwa",
        },
        "policy_layer": "post_ranking_delivery",
        "post_ranking_only": True,
        "ranking_input": False,
        "mutates_scores": False,
        "mutates_rank_identity": False,
    },
    "active_post_ranking_policy": {},
    "safe_preferences": {},
    "risky_pending_policy": [],
    "future_ranking_experiments": [],
    "composite_fitness": {
        "optimization_enabled": False,
        "current_generation_role": "shadow_test_evaluation_metric_only",
        "future_experiment_link": "Composite Fitness future work",
    },
}

STRONG_EVENTS = {"save", "open", "not_interested", "down", "up"}
WEAK_EVENTS = {"dwell", "skip", "swipe_left", "swipe_right", "swipe_next", "view_end"}
RISKY_POLICY_SCOPES = {
    "personal_algorithm.reward_weights",
    "personal_algorithm.swipe_policy",
    "personal_algorithm.exploration",
    "personal_algorithm.delivery",
    "personal_algorithm.preferences",
}
FUTURE_RANKING_ROOTS = {"ranking", "retrieval", "fitness", "meta_evolution"}
RISK_CLASS_ORDER = {
    "safe": 0,
    "risky_post_ranking": 1,
    "future_ranking_experimental": 2,
}
SAFE_DELIVERY_POLICY_PATHS = {
    "personal_algorithm.delivery.schema_version",
    "personal_algorithm.delivery.timing.daily_digest_time",
    "personal_algorithm.delivery.timing.weekly_digest_day",
    "personal_algorithm.delivery.timing.weekly_digest_time",
    "personal_algorithm.delivery.timing.timezone",
    "personal_algorithm.delivery.quiet_hours.start",
    "personal_algorithm.delivery.quiet_hours.end",
    "personal_algorithm.delivery.quiet_hours.timezone",
    "personal_algorithm.delivery.policy_layer",
    "personal_algorithm.delivery.post_ranking_only",
    "personal_algorithm.delivery.ranking_input",
    "personal_algorithm.delivery.mutates_scores",
    "personal_algorithm.delivery.mutates_rank_identity",
}
RISKY_DELIVERY_POLICY_PREFIXES = (
    "personal_algorithm.delivery.enabled",
    "personal_algorithm.delivery.surfaces",
    "personal_algorithm.delivery.preferred_surfaces",
    "personal_algorithm.delivery.channels",
    "personal_algorithm.delivery.default_channel",
    "personal_algorithm.delivery.timing.critical_timing",
    "personal_algorithm.delivery.timing.defer_to_quiet_hours",
    "personal_algorithm.delivery.repeat",
    "personal_algorithm.delivery.quiet_hours.enabled",
    "personal_algorithm.delivery.quiet_hours.allow_critical_override",
    "personal_algorithm.delivery.urgency",
)
FUTURE_DELIVERY_POLICY_PATHS = {
    "personal_algorithm.delivery.ranking_input",
    "personal_algorithm.delivery.mutates_scores",
    "personal_algorithm.delivery.mutates_rank_identity",
}
DERIVATION_RULE_VERSION = "personal_algorithm_reward_v1"
RANKING_COMPLETION_SCORE_FIELDS = ("ensemble_score", "final_score")
RANKING_COMPLETION_RANK_FIELDS = ("ensemble_rank", "rank", "rank_position")
READ_ONLY_DELIVERY_SCORE_FIELDS = RANKING_COMPLETION_SCORE_FIELDS
RANKING_IDENTITY_FIELDS = (
    "id",
    "signal_id",
    "ensemble_rank",
    "rank",
    "rank_position",
    "feed_position",
)


def _deep_merge(base: dict, overlay: dict) -> dict:
    out = copy.deepcopy(base)
    for key, value in (overlay or {}).items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _deep_merge(out[key], value)
        else:
            out[key] = copy.deepcopy(value)
    return out


def _normalize_delivery_surface(value: object) -> str:
    normalized = str(value or "").strip().lower().replace("-", "_")
    return {
        "native": "tray",
        "native_notification": "tray",
        "notification": "critical",
        "digest": "daily",
    }.get(normalized, normalized)


def _unique_text_values(value: object, *, surface_aliases: bool = False) -> list[str]:
    values = value if isinstance(value, list) else [value]
    normalized: list[str] = []
    for item in values:
        text = _normalize_delivery_surface(item) if surface_aliases else str(item or "").strip().lower()
        if text and text not in normalized:
            normalized.append(text)
    return normalized


def _merged_delivery_policy_config(delivery_overlay: dict | None) -> dict:
    """Merge partial delivery policy overlays while preserving valid defaults."""
    base = DEFAULT_PERSONAL_ALGORITHM["delivery"]
    overlay = delivery_overlay or {}
    merged = _deep_merge(base, overlay)

    if "surfaces" in overlay and "preferred_surfaces" not in overlay:
        surfaces = _unique_text_values(overlay.get("surfaces"), surface_aliases=True)
        default_preferred = _unique_text_values(base.get("preferred_surfaces"), surface_aliases=True)
        merged["preferred_surfaces"] = [surface for surface in default_preferred if surface in surfaces]
        if not merged["preferred_surfaces"] and surfaces:
            merged["preferred_surfaces"] = [surfaces[0]]

    if "channels" in overlay and "default_channel" not in overlay:
        channels = _unique_text_values(overlay.get("channels"))
        if channels and str(merged.get("default_channel") or "").strip().lower() not in channels:
            merged["default_channel"] = channels[0]

    return merged


def get_personal_algorithm_policy() -> dict:
    cfg = load_algorithm_config() or {}
    policy = _deep_merge(DEFAULT_PERSONAL_ALGORITHM, cfg.get("personal_algorithm") or {})
    media = policy.setdefault("media", {})
    advanced = media.setdefault("advanced_media_capability", {})
    env_enabled = os.getenv("HEDWIG_FULL_MEDIA_UNDERSTANDING", "").strip().lower() in {"1", "true", "yes", "on"}
    policy_enabled = bool(advanced.get("policy_enabled") or media.get("full_understanding_enabled", False))
    advanced["enabled"] = bool(env_enabled and policy_enabled)
    media["full_understanding_enabled"] = advanced["enabled"]
    return policy


def get_delivery_policy_config(policy: dict | None = None):
    """Return the typed ambient delivery policy config with defaults applied."""
    from hedwig.models import DeliveryPolicyConfig

    p = policy or get_personal_algorithm_policy()
    return DeliveryPolicyConfig.model_validate(_merged_delivery_policy_config(p.get("delivery") or {}))


def clamp_exploration_rate(policy: dict | None = None) -> float:
    p = policy or get_personal_algorithm_policy()
    exp = p.get("exploration") or {}
    rate = float(exp.get("rate", 0.10))
    return max(float(exp.get("min_rate", 0.05)), min(float(exp.get("max_rate", 0.15)), rate))


def media_profile_for_item(item: dict, policy: dict | None = None) -> dict:
    p = policy or get_personal_algorithm_policy()
    media = p.get("media") or {}
    default_mode = media.get("default_media_mode") or {}
    advanced = media.get("advanced_media_capability") or {}
    return {
        "strategy": media.get("default_strategy", "text_thumbnail_transcript"),
        "default_media_mode": {
            "active_mode": default_mode.get("active_mode", "Text+Thumbnail+Transcript"),
            "text": bool(default_mode.get("text", True)),
            "thumbnail": bool(default_mode.get("thumbnail", True)),
            "transcript": bool(default_mode.get("transcript", True)),
        },
        "has_text": bool(item.get("content") or item.get("title")),
        "has_thumbnail": bool((item.get("extra") or {}).get("thumbnail_url")) if isinstance(item.get("extra"), dict) else False,
        "has_transcript": bool((item.get("extra") or {}).get("transcript")) if isinstance(item.get("extra"), dict) else False,
        "full_understanding_enabled": bool(media.get("full_understanding_enabled", False)),
        "advanced_media_capability": {
            "name": advanced.get("name", "Full Media Understanding"),
            "enabled": bool(advanced.get("enabled", False)),
            "required_env_flag": advanced.get("required_env_flag", "HEDWIG_FULL_MEDIA_UNDERSTANDING"),
            "extracted_features": list(advanced.get("extracted_features") or []),
            "provenance": "policy_and_env_gate",
        },
    }


def _escalate_risk(current: str, candidate: str) -> str:
    return candidate if RISK_CLASS_ORDER[candidate] > RISK_CLASS_ORDER[current] else current


def _delivery_policy_exposure_impact(change: dict) -> dict[str, str]:
    path = str(change.get("path") or "")
    normalized_path = path if path.startswith("personal_algorithm.") else f"personal_algorithm.{path}"
    value = change.get("value")

    if normalized_path in FUTURE_DELIVERY_POLICY_PATHS and value not in (False, None):
        return {
            "risk_class": "future_ranking_experimental",
            "scope": "delivery_policy_boundary",
            "reason": f"{normalized_path} would make delivery policy a ranking input or score/rank mutator.",
        }
    if normalized_path in SAFE_DELIVERY_POLICY_PATHS:
        timing_path = normalized_path.startswith(
            (
                "personal_algorithm.delivery.timing.",
                "personal_algorithm.delivery.quiet_hours.start",
                "personal_algorithm.delivery.quiet_hours.end",
            )
        )
        return {
            "risk_class": "safe",
            "scope": "delivery_policy_timing" if timing_path else "delivery_policy_metadata",
            "reason": (
                "Delivery schedule metadata changes timing only and does not change item eligibility or exposure distribution."
                if timing_path
                else "Delivery boundary metadata preserves post-ranking behavior and does not change item eligibility or exposure distribution."
            ),
        }
    if any(
        token in normalized_path
        for token in ("ranking", "ensemble_score", "final_score", "pre_layer_ranking", "fitness")
    ):
        return {
            "risk_class": "future_ranking_experimental",
            "scope": "delivery_policy_boundary",
            "reason": f"{normalized_path} crosses the delivery/ranking boundary.",
        }
    if any(
        normalized_path == prefix or normalized_path.startswith(f"{prefix}.")
        for prefix in RISKY_DELIVERY_POLICY_PREFIXES
    ):
        return {
            "risk_class": "risky_post_ranking",
            "scope": "delivery_policy",
            "reason": "Delivery policy change can alter post-ranking exposure, routing, urgency, quiet-hours gating, or repeat frequency.",
        }
    return {
        "risk_class": "risky_post_ranking",
        "scope": "delivery_policy",
        "reason": "Unrecognized delivery policy field is treated as exposure-impacting until explicitly classified safe.",
    }


def classify_policy_edit(changes: list[dict], intent: str = "") -> dict:
    """Classify a natural-language/settings policy edit before execution."""
    text = (intent or "").lower()
    scopes: set[str] = set()
    reasons: list[str] = []
    risk_class = "safe"

    for change in changes or []:
        path = str(change.get("path") or "")
        normalized_path = path if path.startswith("personal_algorithm.") else f"personal_algorithm.{path}"
        root = path.split(".", 1)[0]
        if root in FUTURE_RANKING_ROOTS or "ensemble_ranking_experiment" in path:
            risk_class = _escalate_risk(risk_class, "future_ranking_experimental")
            scopes.add("ensemble_ranking_experiment")
            reasons.append(f"{path} affects production ranking inputs or fitness.")
            continue

        if normalized_path.startswith("personal_algorithm.swipe_policy"):
            risk_class = _escalate_risk(risk_class, "risky_post_ranking")
            scopes.add("swipe_policy")
            reasons.append("Swipe mapping or reward semantic changes alter reward interpretation.")
        elif normalized_path.startswith("personal_algorithm.reward_weights"):
            risk_class = _escalate_risk(risk_class, "risky_post_ranking")
            scopes.add("reward_interpretation")
            reasons.append("Reward strength changes require shadow testing.")
        elif normalized_path.startswith("personal_algorithm.exploration"):
            risk_class = _escalate_risk(risk_class, "risky_post_ranking")
            scopes.add("exploration_policy")
            reasons.append("Exploration ratio changes alter exposure distribution.")
        elif normalized_path.startswith("personal_algorithm.delivery"):
            impact = _delivery_policy_exposure_impact(change)
            risk_class = _escalate_risk(risk_class, impact["risk_class"])
            scopes.add(impact["scope"])
            reasons.append(impact["reason"])
        elif normalized_path.startswith("personal_algorithm.preferences"):
            risk_class = _escalate_risk(risk_class, "risky_post_ranking")
            scopes.add("post_ranking_preference")
            reasons.append("Preference changes can alter exposure distribution.")
        elif normalized_path.startswith("personal_algorithm.feed"):
            scopes.add("feed_mode")
        else:
            scopes.add("post_ranking_preference")

    if any(token in text for token in ("replace ranking", "optimize ranking", "composite fitness optimization", "train ranking")):
        risk_class = _escalate_risk(risk_class, "future_ranking_experimental")
        scopes.add("ensemble_ranking_experiment")
        reasons.append("Intent requests ranking replacement or optimization, which is future experimental work.")

    if not reasons:
        reasons.append("Edit is limited to presentation or safe preference state and does not alter reward semantics, exposure distribution, exploration, delivery routing, or ranking inputs.")

    if "delivery_policy" in scopes:
        scopes.discard("delivery_policy_timing")

    return {
        "risk_class": risk_class,
        "policy_edit_risk_class": risk_class,
        "scopes": sorted(scopes) or ["post_ranking_preference"],
        "policy_edit_scope": sorted(scopes)[0] if scopes else "post_ranking_preference",
        "reason": " ".join(dict.fromkeys(reasons)),
    }


def interpret_behavior_event(event: dict, policy: dict | None = None) -> dict | None:
    """Convert one raw event into a derived reward row without mutating it."""
    p = policy or get_personal_algorithm_policy()
    weights = p.get("reward_weights") or {}
    swipe = p.get("swipe_policy") or {}
    event_type = str(event.get("event_type") or "")
    signal_id = event.get("signal_id")
    if not signal_id:
        return None

    if event_type == "swipe_left":
        value = float((swipe.get("left") or {}).get("reward", weights.get("swipe", 0.1)))
        signal_strength = str((swipe.get("left") or {}).get("strength", "strong_positive"))
    elif event_type == "swipe_right":
        value = float((swipe.get("right") or {}).get("reward", weights.get("skip", -0.1)))
        signal_strength = str((swipe.get("right") or {}).get("strength", "weak_negative"))
    elif event_type == "swipe_next":
        value = float((swipe.get("next") or {}).get("reward", 0.0))
        signal_strength = str((swipe.get("next") or {}).get("strength", "weak_neutral"))
    elif event_type == "dwell":
        dwell_ms = max(0, int(event.get("dwell_ms") or 0))
        value = min(0.35, dwell_ms / 30000.0) * float(weights.get("dwell", 0.2))
        signal_strength = "weak_positive"
    elif event_type == "skip":
        value = float(weights.get("skip", -0.1))
        signal_strength = "weak_negative"
    elif event_type == "save":
        value = float(weights.get("save", 1.0))
        signal_strength = "strong_positive"
    elif event_type == "open":
        value = float(weights.get("open", 0.8))
        signal_strength = "strong_positive"
    elif event_type == "not_interested":
        value = float(weights.get("not_interested", -1.0))
        signal_strength = "strong_negative"
    else:
        return None
    polarity = "positive" if value > 0 else "negative" if value < 0 else "neutral"
    confidence = 0.85 if signal_strength.startswith("strong") else 0.45
    uncertainty = "" if signal_strength.startswith("strong") else "weak/noisy signal; conservative reward derivation"

    return {
        "signal_id": str(signal_id),
        "raw_event_id": event.get("id"),
        "source_event_ids": [event.get("id")] if event.get("id") is not None else [],
        "event_type": event_type,
        "reward_value": value,
        "signal_strength": signal_strength,
        "strength_class": signal_strength,
        "polarity": polarity,
        "confidence": confidence,
        "uncertainty_reason": uncertainty,
        "derivation_rule_version": DERIVATION_RULE_VERSION,
        "policy_version": p.get("version") or load_algorithm_config().get("version", 1),
        "feed_mode": event.get("feed_mode") or event.get("mode") or "grid",
        "source": "personal_algorithm",
    }


def apply_exploration_layer(items: list[dict], policy: dict | None = None) -> list[dict]:
    """Annotate bounded exploration after ranking without mutating scores/order."""
    p = policy or get_personal_algorithm_policy()
    if not (p.get("exploration") or {}).get("enabled", True):
        return [
            dict(
                item,
                is_exploration=False,
                pre_layer_ranking=_pre_layer_ranking_snapshot(item, idx),
                media_profile=media_profile_for_item(item, p),
            )
            for idx, item in enumerate(items)
        ]
    rate = clamp_exploration_rate(p)
    target = max(1, round(len(items) * rate)) if items else 0
    existing_exploration = sum(1 for item in items if item.get("is_exploration"))
    remaining_exploration_slots = max(0, target - existing_exploration)
    labels = (p.get("exploration") or {}).get("labels") or ["anomaly"]
    out: list[dict] = []
    for idx, item in enumerate(items):
        row = dict(item)
        ensemble_score = item.get("ensemble_score")
        final_score = item.get("final_score")
        row["ensemble_score"] = ensemble_score
        row["final_score"] = final_score
        row["pre_layer_ranking"] = _pre_layer_ranking_snapshot(item, idx)
        preassigned_exploration = bool(item.get("is_exploration"))
        auto_exploration = (
            remaining_exploration_slots > 0
            and idx >= len(items) - remaining_exploration_slots
        )
        if preassigned_exploration or auto_exploration:
            label = labels[idx % len(labels)]
            row["is_exploration"] = True
            row["anomaly_label"] = {
                "type": label,
                "reason": f"{label} perspective to keep the feed diverse",
            }
            if auto_exploration:
                remaining_exploration_slots -= 1
        else:
            row["is_exploration"] = False
        row["media_profile"] = media_profile_for_item(row, p)
        row["post_ranking_decisions"] = row.get("post_ranking_decisions") or {}
        row["post_ranking_decisions"]["exploration"] = {
            "layer": "exploration",
            "target_ratio": rate,
            "method": "tail_slot_reservation",
            "preserves_non_exploration_order": True,
            "did_not_mutate_score": True,
        }
        out.append(row)
    return out


def _has_completed_ranking(item: dict) -> bool:
    """Return whether an item carries completed-ranking output fields."""
    has_score = all(item.get(field) is not None for field in RANKING_COMPLETION_SCORE_FIELDS)
    pre_layer = item.get("pre_layer_ranking") if isinstance(item.get("pre_layer_ranking"), dict) else {}
    has_rank = any(item.get(field) is not None for field in RANKING_COMPLETION_RANK_FIELDS)
    has_rank = has_rank or pre_layer.get("input_rank") is not None
    return has_score and has_rank


def _signal_identity(item: dict, idx: int) -> str:
    return str(item.get("id") or item.get("signal_id") or f"index:{idx}")


def _pre_layer_ranking_snapshot(item: dict, idx: int) -> dict[str, Any]:
    """Copy score, order, and rank identifiers observed before delivery."""
    existing = copy.deepcopy(item.get("pre_layer_ranking") or {})
    input_rank = (
        existing.get("input_rank")
        if existing.get("input_rank") is not None
        else item.get("ensemble_rank", item.get("rank", item.get("rank_position", idx + 1)))
    )
    rank_identifiers = {
        field: copy.deepcopy(item.get(field))
        for field in RANKING_IDENTITY_FIELDS
        if item.get(field) is not None
    }
    existing_rank_identifiers = existing.get("rank_identifiers")
    if isinstance(existing_rank_identifiers, dict):
        rank_identifiers = copy.deepcopy(existing_rank_identifiers)

    existing.update({
        "ensemble_score": copy.deepcopy(item.get("ensemble_score")),
        "final_score": copy.deepcopy(item.get("final_score")),
        "input_rank": copy.deepcopy(input_rank),
        "input_order": existing.get("input_order", idx),
        "rank_identifiers": rank_identifiers,
        "immutable": True,
    })
    return existing


def _delivery_score_snapshot(item: dict) -> dict[str, Any]:
    """Copy canonical ranking scores before delivery layers add metadata."""
    return {
        field: copy.deepcopy(item.get(field))
        for field in READ_ONLY_DELIVERY_SCORE_FIELDS
    }


def _delivery_rank_identity_snapshot(item: dict, idx: int) -> dict[str, Any]:
    pre_layer = item.get("pre_layer_ranking") if isinstance(item.get("pre_layer_ranking"), dict) else {}
    rank_identifiers = {
        field: copy.deepcopy(item.get(field))
        for field in RANKING_IDENTITY_FIELDS
        if item.get(field) is not None
    }
    if isinstance(pre_layer.get("rank_identifiers"), dict):
        rank_identifiers.update(copy.deepcopy(pre_layer["rank_identifiers"]))
    return {
        "signal_identity": _signal_identity(item, idx),
        "input_order": pre_layer.get("input_order", idx),
        "input_rank": pre_layer.get(
            "input_rank",
            item.get("ensemble_rank", item.get("rank", item.get("rank_position"))),
        ),
        "rank_identifiers": rank_identifiers,
    }


def assert_delivery_scores_unchanged(before: list[dict[str, Any]], after: list[dict[str, Any]]) -> None:
    """Guard delivery processing so ranking scores remain read-only inputs."""
    if len(before) != len(after):
        raise ValueError("delivery processing must not add or remove ranked items")
    for idx, (original, routed) in enumerate(zip(before, after)):
        original_scores = _delivery_score_snapshot(original)
        routed_scores = _delivery_score_snapshot(routed)
        if routed_scores != original_scores:
            signal_id = original.get("id") or original.get("signal_id") or f"index:{idx}"
            raise ValueError(
                "delivery processing treats ranking score fields as read-only; "
                f"score mutation detected for {signal_id}: "
                f"{original_scores!r} -> {routed_scores!r}"
            )


def assert_delivery_rank_identity_unchanged(before: list[dict[str, Any]], after: list[dict[str, Any]]) -> None:
    """Guard delivery processing so item order and rank identifiers are stable."""
    if len(before) != len(after):
        raise ValueError("delivery processing must not add or remove ranked items")
    for idx, (original, routed) in enumerate(zip(before, after)):
        original_identity = _delivery_rank_identity_snapshot(original, idx)
        routed_identity = _delivery_rank_identity_snapshot(routed, idx)
        if routed_identity != original_identity:
            signal_id = original.get("id") or original.get("signal_id") or f"index:{idx}"
            raise ValueError(
                "delivery processing treats pre-layer rank identity as read-only; "
                f"rank identity mutation detected for {signal_id}: "
                f"{original_identity!r} -> {routed_identity!r}"
            )


def assert_ranking_completed_for_delivery(items: list[dict]) -> None:
    """Guard delivery routing so decision metadata is only populated post-ranking."""
    for idx, item in enumerate(items):
        if not _has_completed_ranking(item):
            signal_id = item.get("id") or item.get("signal_id") or f"index:{idx}"
            raise ValueError(
                "delivery decisions require completed ranking output "
                f"before ambient routing; missing score/rank evidence for {signal_id}"
            )


def _delivery_policy_surface_values(delivery_policy) -> tuple[list[str], list[str]]:
    enabled = [str(surface) for surface in delivery_policy.surfaces]
    preferred = [str(surface) for surface in delivery_policy.preferred_surfaces]
    return enabled, preferred


def _compatible_delivery_surfaces(canonical_surface: str, delivery_policy) -> list[str]:
    """Return post-ranking surfaces eligible for the canonical delivery intent."""
    enabled, _ = _delivery_policy_surface_values(delivery_policy)
    compatibility = {
        "critical": ["critical", "tray", "pwa"],
        "daily": ["daily", "tray", "pwa"],
        "weekly": ["weekly"],
        "pwa": ["pwa", "tray"],
        "tray": ["tray", "pwa"],
    }
    candidates = [
        surface
        for surface in compatibility.get(canonical_surface, [canonical_surface])
        if surface in enabled
    ]
    if candidates:
        return candidates

    # If the canonical surface is disabled, keep exposure ambient by falling
    # back to enabled policy surfaces rather than the manual web feed.
    fallback_order = ["critical", "daily", "weekly", "pwa", "tray"]
    fallback = [surface for surface in fallback_order if surface in enabled]
    return fallback or [canonical_surface]


def _apply_surface_preferences(canonical_surface: str, delivery_policy) -> tuple[str, dict[str, Any]]:
    """Select a delivery surface from eligible surfaces using user preferences.

    Preferences are post-ranking delivery metadata. They choose only among
    compatible or explicitly enabled fallback surfaces and never alter the item
    score, order, or pre-layer ranking identity.
    """
    enabled, preferred = _delivery_policy_surface_values(delivery_policy)
    candidates = _compatible_delivery_surfaces(canonical_surface, delivery_policy)
    preferred_match = next((surface for surface in preferred if surface in candidates), None)
    resolved = preferred_match or (canonical_surface if canonical_surface in candidates else candidates[0])
    return resolved, {
        "canonical_surface": canonical_surface,
        "eligible_surfaces": candidates,
        "enabled_surfaces": enabled,
        "preferred_surfaces": preferred,
        "preference_matched": preferred_match == resolved,
        "selection_reason": (
            "matched_user_surface_preference"
            if preferred_match == resolved
            else "canonical_surface_enabled"
            if canonical_surface == resolved
            else "canonical_surface_disabled_fallback"
        ),
        "post_ranking_only": True,
        "ranking_input": False,
        "mutates_scores": False,
        "mutates_rank_identity": False,
    }


def choose_delivery(item: dict, policy: dict | None = None) -> dict:
    assert_ranking_completed_for_delivery([item])

    from hedwig.models import (
        AmbientSurface,
        DeliveryChannel,
        DeliveryDecisionMetadata,
        DeliveryExplanationMetadata,
        DeliveryRankingSnapshot,
        DeliveryTiming,
    )

    p = policy or get_personal_algorithm_policy()
    delivery_policy = get_delivery_policy_config(p)
    score = float(item.get("ensemble_score") or 0)
    final_score = float(item.get("final_score") or 0)
    pre_layer_ranking = (
        item.get("pre_layer_ranking")
        if isinstance(item.get("pre_layer_ranking"), dict)
        else _pre_layer_ranking_snapshot(item, 0)
    )
    urgency = str(item.get("urgency") or "")
    urgency_cfg = delivery_policy.urgency
    critical_urgencies = {
        value.value if hasattr(value, "value") else str(value)
        for value in urgency_cfg.critical_urgencies
    }
    if urgency in critical_urgencies or score >= float(urgency_cfg.critical_score_threshold):
        surface, timing = AmbientSurface.CRITICAL, DeliveryTiming(delivery_policy.timing.critical_timing)
    elif score >= float(urgency_cfg.daily_score_threshold):
        surface, timing = AmbientSurface.DAILY, DeliveryTiming.NEXT_DIGEST
    else:
        surface, timing = AmbientSurface.WEEKLY, DeliveryTiming.WEEKLY_DIGEST
    if item.get("is_exploration") and surface == AmbientSurface.WEEKLY:
        surface = AmbientSurface(urgency_cfg.exploration_surface)
    canonical_surface = str(surface.value if hasattr(surface, "value") else surface)
    selected_surface, surface_preference = _apply_surface_preferences(canonical_surface, delivery_policy)
    surface = AmbientSurface(selected_surface)
    signal_id = str(item.get("id") or item.get("signal_id") or "")
    channel = str(delivery_policy.default_channel)
    try:
        delivery_channel = DeliveryChannel(channel)
    except ValueError:
        delivery_channel = DeliveryChannel.DASHBOARD

    decision = DeliveryDecisionMetadata(
        signal_id=signal_id,
        surface=surface,
        channel=delivery_channel,
        timing=timing,
        urgency=urgency,
        repeat=bool(delivery_policy.repeat.enabled),
        repeat_rule=delivery_policy.repeat.model_dump(mode="json"),
        ranking_snapshot=DeliveryRankingSnapshot(
            input_ensemble_rank=pre_layer_ranking.get("input_rank"),
            input_order=pre_layer_ranking.get("input_order"),
            rank_identifiers=pre_layer_ranking.get("rank_identifiers") or {},
            input_ensemble_score=score,
            input_final_score=final_score,
            immutable=True,
        ),
        explanation=DeliveryExplanationMetadata(
            text="Routed by ambient delivery policy after selection completed.",
        ),
        emitted_event={
            "signal_id": signal_id,
            "event_type": "delivery_decision",
            "feed_id": "delivery_policy_v1",
        },
    )
    metadata = decision.model_dump(mode="json")
    # Backward-compatible aliases for existing feed consumers; the canonical
    # boundary-preserving values live under ranking_snapshot.
    metadata["input_ensemble_rank"] = metadata["ranking_snapshot"]["input_ensemble_rank"]
    metadata["input_ensemble_score"] = metadata["ranking_snapshot"]["input_ensemble_score"]
    metadata["surface_preference"] = surface_preference
    metadata["eligible_surfaces"] = surface_preference["eligible_surfaces"]
    metadata["preferred_surfaces"] = surface_preference["preferred_surfaces"]
    metadata["canonical_surface"] = surface_preference["canonical_surface"]
    return metadata


def route_items_after_ranking(items: list[dict], policy: dict | None = None) -> list[dict]:
    assert_ranking_completed_for_delivery(items)
    read_only_inputs = [copy.deepcopy(item) for item in items]
    routed = apply_exploration_layer(items, policy)
    assert_delivery_scores_unchanged(read_only_inputs, routed)
    assert_delivery_rank_identity_unchanged(read_only_inputs, routed)
    out: list[dict] = []
    for item in routed:
        delivery = choose_delivery(item, policy)
        row = dict(item, delivery_policy=delivery, delivery_decision=delivery)
        row.setdefault("post_ranking_decisions", {})["delivery"] = delivery
        out.append(row)
    assert_delivery_scores_unchanged(read_only_inputs, out)
    assert_delivery_rank_identity_unchanged(read_only_inputs, out)
    return out


def is_risky_policy_change(changes: list[dict]) -> bool:
    return classify_policy_edit(changes).get("risk_class") == "risky_post_ranking"


def composite_fitness(events: list[dict] | None = None, rewards: list[dict] | None = None) -> dict:
    events = events or []
    rewards = rewards or []
    count = lambda *types: sum(1 for ev in events if ev.get("event_type") in types)
    opens = count("open", "click_link")
    saves = count("save", "swipe_left")
    skips = count("skip", "swipe_right", "swipe_next")
    dwell_values = [int(ev.get("dwell_ms") or 0) for ev in events if ev.get("event_type") == "dwell"]
    diversity = len({ev.get("feed_id") for ev in events if ev.get("feed_id")}) / max(1, len(events))
    upvote_proxy = sum(1 for rw in rewards if float(rw.get("reward_value") or 0) > 0.5)
    score = (
        min(1.0, upvote_proxy / 10) * 0.20
        + min(1.0, saves / 10) * 0.20
        + min(1.0, opens / 10) * 0.20
        + min(1.0, (sum(dwell_values) / max(1, len(dwell_values))) / 10000) * 0.20
        + (1.0 - min(1.0, skips / max(1, len(events)))) * 0.10
        + min(1.0, diversity) * 0.10
    )
    return {
        "score": round(score, 4),
        "signals": {
            "upvote": upvote_proxy,
            "save": saves,
            "open": opens,
            "dwell": sum(dwell_values),
            "skip": skips,
            "diversity": round(diversity, 4),
        },
    }


def shadow_test_policy_edit(changes: list[dict], intent: str = "") -> dict:
    classification = classify_policy_edit(changes, intent)
    digest = hashlib.sha256(repr(changes).encode()).hexdigest()[:12]
    return {
        "shadow_test": True,
        "status": "pending_apply",
        "id": f"shadow-{digest}",
        "intent": intent,
        "risk_class": classification["risk_class"],
        "classification_reason": classification["reason"],
        "tested_policy_diff": changes,
        "composite_fitness": composite_fitness(),
        "composite_fitness_optimization_enabled": False,
        "guardrail_metrics": {
            "ensemble_mutation_allowed": False,
            "requires_user_approval": classification["risk_class"] == "risky_post_ranking",
        },
        "created_at": datetime.now(tz=timezone.utc).isoformat(),
    }
