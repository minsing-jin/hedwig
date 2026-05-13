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
        "enabled": True,
        "surfaces": ["critical", "daily", "weekly", "pwa", "tray"],
        "channels": ["dashboard", "email", "slack", "discord", "pwa", "tray"],
        "default_channel": "dashboard",
        "repeat": {"enabled": True, "max_count": 2},
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
DERIVATION_RULE_VERSION = "personal_algorithm_reward_v1"


def _deep_merge(base: dict, overlay: dict) -> dict:
    out = copy.deepcopy(base)
    for key, value in (overlay or {}).items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _deep_merge(out[key], value)
        else:
            out[key] = copy.deepcopy(value)
    return out


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
            risk_class = "future_ranking_experimental"
            scopes.add("ensemble_ranking_experiment")
            reasons.append(f"{path} affects production ranking inputs or fitness.")
            continue

        if normalized_path.startswith("personal_algorithm.swipe_policy"):
            risk_class = "risky_post_ranking"
            scopes.add("swipe_policy")
            reasons.append("Swipe mapping or reward semantic changes alter reward interpretation.")
        elif normalized_path.startswith("personal_algorithm.reward_weights"):
            risk_class = "risky_post_ranking"
            scopes.add("reward_interpretation")
            reasons.append("Reward strength changes require shadow testing.")
        elif normalized_path.startswith("personal_algorithm.exploration"):
            risk_class = "risky_post_ranking"
            scopes.add("exploration_policy")
            reasons.append("Exploration ratio changes alter exposure distribution.")
        elif normalized_path.startswith("personal_algorithm.delivery"):
            risk_class = "risky_post_ranking"
            scopes.add("delivery_policy")
            reasons.append("Delivery routing/timing changes require shadow testing.")
        elif normalized_path.startswith("personal_algorithm.preferences"):
            risk_class = "risky_post_ranking"
            scopes.add("post_ranking_preference")
            reasons.append("Preference changes can alter exposure distribution.")
        elif normalized_path.startswith("personal_algorithm.feed"):
            scopes.add("feed_mode")
        else:
            scopes.add("post_ranking_preference")

    if any(token in text for token in ("replace ranking", "optimize ranking", "composite fitness optimization", "train ranking")):
        risk_class = "future_ranking_experimental"
        scopes.add("ensemble_ranking_experiment")
        reasons.append("Intent requests ranking replacement or optimization, which is future experimental work.")

    if not reasons:
        reasons.append("Edit is limited to presentation or safe preference state and does not alter reward semantics, exposure distribution, exploration, delivery routing, or ranking inputs.")

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
        return [dict(item, is_exploration=False) for item in items]
    rate = clamp_exploration_rate(p)
    target = max(1, round(len(items) * rate)) if items else 0
    labels = (p.get("exploration") or {}).get("labels") or ["anomaly"]
    out: list[dict] = []
    for idx, item in enumerate(items):
        row = dict(item)
        ensemble_score = item.get("ensemble_score", item.get("final_score", item.get("score", item.get("relevance_score", 0))))
        row["ensemble_score"] = ensemble_score
        row["final_score"] = item.get("final_score", ensemble_score)
        row["pre_layer_ranking"] = {
            "ensemble_score": ensemble_score,
            "final_score": row["final_score"],
            "input_rank": item.get("ensemble_rank", idx + 1),
            "immutable": True,
        }
        if idx >= len(items) - target:
            label = labels[idx % len(labels)]
            row["is_exploration"] = True
            row["anomaly_label"] = {
                "type": label,
                "reason": f"{label} perspective to keep the feed diverse",
            }
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


def choose_delivery(item: dict, policy: dict | None = None) -> dict:
    p = policy or get_personal_algorithm_policy()
    score = float(item.get("ensemble_score", item.get("final_score", item.get("score", item.get("relevance_score", 0)))) or 0)
    urgency = str(item.get("urgency") or "")
    if urgency == "alert" or score >= 0.85:
        surface, timing = "critical", "now"
    elif score >= 0.65:
        surface, timing = "daily", "next_digest"
    else:
        surface, timing = "weekly", "weekly_digest"
    if item.get("is_exploration"):
        surface = "pwa"
    signal_id = str(item.get("id") or item.get("signal_id") or "")
    return {
        "signal_id": signal_id,
        "input_ensemble_rank": item.get("pre_layer_ranking", {}).get("input_rank"),
        "input_ensemble_score": score,
        "surface": surface,
        "channel": (p.get("delivery") or {}).get("default_channel", "dashboard"),
        "timing": timing,
        "repeat": bool(((p.get("delivery") or {}).get("repeat") or {}).get("enabled", True)),
        "repeat_rule": (p.get("delivery") or {}).get("repeat") or {"enabled": True, "max_count": 2},
        "reason": "post-ranking delivery policy v1",
        "emitted_event": {
            "signal_id": signal_id,
            "event_type": "delivery_decision",
            "feed_id": "delivery_policy_v1",
        },
        "post_ranking": True,
        "does_not_mutate_ensemble": True,
    }


def route_items_after_ranking(items: list[dict], policy: dict | None = None) -> list[dict]:
    routed = apply_exploration_layer(items, policy)
    out: list[dict] = []
    for item in routed:
        delivery = choose_delivery(item, policy)
        row = dict(item, delivery_policy=delivery, delivery_decision=delivery)
        row.setdefault("post_ranking_decisions", {})["delivery"] = delivery
        out.append(row)
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
