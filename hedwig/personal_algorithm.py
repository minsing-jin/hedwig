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
    "feed": {
        "default_mode": "grid",
        "available_modes": ["grid", "detail_swipe", "dense_reader"],
    },
    "swipe_policy": {
        "left": {"action": "save_later", "reward": 0.8, "strength": "strong_positive"},
        "right": {"action": "skip", "reward": -0.1, "strength": "weak_negative"},
        "next": {"action": "skip", "reward": 0.0, "strength": "weak_neutral"},
        "skip_strength": "weak",
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
        "full_understanding_enabled": False,
    },
    "delivery": {
        "enabled": True,
        "surfaces": ["critical", "daily", "weekly", "pwa", "tray"],
        "channels": ["dashboard", "email", "slack", "discord", "pwa", "tray"],
        "default_channel": "dashboard",
        "repeat": {"enabled": True, "max_count": 2},
    },
}

STRONG_EVENTS = {"save", "open", "not_interested", "down", "up"}
WEAK_EVENTS = {"dwell", "skip", "swipe_left", "swipe_right", "swipe_next", "view_end"}
RISKY_POLICY_ROOTS = {"ranking", "retrieval", "reward_weights", "swipe_policy", "fitness"}


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
    if os.getenv("HEDWIG_FULL_MEDIA_UNDERSTANDING", "").strip().lower() in {"1", "true", "yes", "on"}:
        policy.setdefault("media", {})["full_understanding_enabled"] = True
    return policy


def clamp_exploration_rate(policy: dict | None = None) -> float:
    p = policy or get_personal_algorithm_policy()
    exp = p.get("exploration") or {}
    rate = float(exp.get("rate", 0.10))
    return max(float(exp.get("min_rate", 0.05)), min(float(exp.get("max_rate", 0.15)), rate))


def media_profile_for_item(item: dict, policy: dict | None = None) -> dict:
    p = policy or get_personal_algorithm_policy()
    media = p.get("media") or {}
    return {
        "strategy": media.get("default_strategy", "text_thumbnail_transcript"),
        "has_text": bool(item.get("content") or item.get("title")),
        "has_thumbnail": bool((item.get("extra") or {}).get("thumbnail_url")) if isinstance(item.get("extra"), dict) else False,
        "has_transcript": bool((item.get("extra") or {}).get("transcript")) if isinstance(item.get("extra"), dict) else False,
        "full_understanding_enabled": bool(media.get("full_understanding_enabled", False)),
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

    return {
        "signal_id": str(signal_id),
        "raw_event_id": event.get("id"),
        "event_type": event_type,
        "reward_value": value,
        "signal_strength": signal_strength,
        "policy_version": p.get("version") or load_algorithm_config().get("version", 1),
        "feed_mode": event.get("feed_mode") or event.get("mode") or "grid",
        "source": "personal_algorithm",
    }


def apply_exploration_layer(items: list[dict], policy: dict | None = None) -> list[dict]:
    """Annotate a bounded 5-15% of already-ranked items as exploration."""
    p = policy or get_personal_algorithm_policy()
    if not (p.get("exploration") or {}).get("enabled", True):
        return [dict(item, is_exploration=False) for item in items]
    rate = clamp_exploration_rate(p)
    target = max(1, round(len(items) * rate)) if items else 0
    labels = (p.get("exploration") or {}).get("labels") or ["anomaly"]
    out: list[dict] = []
    for idx, item in enumerate(items):
        row = dict(item)
        row["ensemble_score"] = item.get("score", item.get("relevance_score", 0))
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
        out.append(row)
    return out


def choose_delivery(item: dict, policy: dict | None = None) -> dict:
    p = policy or get_personal_algorithm_policy()
    score = float(item.get("score", item.get("relevance_score", 0)) or 0)
    urgency = str(item.get("urgency") or "")
    if urgency == "alert" or score >= 0.85:
        surface, timing = "critical", "now"
    elif score >= 0.65:
        surface, timing = "daily", "next_digest"
    else:
        surface, timing = "weekly", "weekly_digest"
    if item.get("is_exploration"):
        surface = "pwa"
    return {
        "surface": surface,
        "channel": (p.get("delivery") or {}).get("default_channel", "dashboard"),
        "timing": timing,
        "repeat": bool(((p.get("delivery") or {}).get("repeat") or {}).get("enabled", True)),
        "post_ranking": True,
    }


def route_items_after_ranking(items: list[dict], policy: dict | None = None) -> list[dict]:
    routed = apply_exploration_layer(items, policy)
    return [dict(item, delivery_policy=choose_delivery(item, policy)) for item in routed]


def is_risky_policy_change(changes: list[dict]) -> bool:
    for change in changes or []:
        root = str(change.get("path") or "").split(".", 1)[0]
        if root in RISKY_POLICY_ROOTS:
            return True
    return False


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
    digest = hashlib.sha256(repr(changes).encode()).hexdigest()[:12]
    return {
        "shadow_test": True,
        "status": "pending_apply",
        "id": f"shadow-{digest}",
        "intent": intent,
        "composite_fitness": composite_fitness(),
        "created_at": datetime.now(tz=timezone.utc).isoformat(),
    }
