"""Ambient delivery surface entry points.

This module stays downstream of ranking: callers pass already-ranked items and
the ambient layer only selects, routes, and explains delivery metadata.
"""
from __future__ import annotations

import copy
import re
from datetime import datetime
from typing import Any

from hedwig.models import (
    AmbientDeliveryItem,
    AmbientDeliveryItemSet,
    AmbientPreLayerRankingSnapshot,
    DeliveryPolicyConfig,
)
from hedwig.personal_algorithm import (
    classify_policy_edit,
    get_delivery_policy_config,
    get_personal_algorithm_policy,
    route_items_after_ranking,
)


SURFACE_ALIASES = {
    "native": "tray",
    "native_notification": "tray",
    "notification": "critical",
    "digest": "daily",
}

AMBIENT_SURFACE_ENTRY_POINTS: dict[str, dict[str, Any]] = {
    "critical": {
        "surface": "critical",
        "label": "Critical alerts",
        "entry_kind": "receiver",
        "page_path": "/ambient/critical",
        "request_path": "/ambient/critical/api",
        "contract_schema": "ambient_delivery_item_set.v1",
        "contract_model": "AmbientDeliveryItemSet",
        "delivery_semantics": "Immediate high-urgency item handoff for notification-capable clients.",
        "selection_rule": "delivery_decision.surface == critical",
        "default_limit": 3,
        "manual_feed_entry_required": False,
        "post_ranking_only": True,
    },
    "daily": {
        "surface": "daily",
        "label": "Daily digest",
        "entry_kind": "receiver",
        "page_path": "/ambient/daily",
        "request_path": "/ambient/daily/api",
        "contract_schema": "ambient_delivery_item_set.v1",
        "contract_model": "AmbientDeliveryItemSet",
        "delivery_semantics": "Next digest batch for high-value non-critical items.",
        "selection_rule": "delivery_decision.surface == daily",
        "cadence": "next daily digest run",
        "item_selection_inputs": [
            "completed ensemble_score",
            "completed final_score",
            "urgency",
            "pre_layer_ranking rank identity",
            "delivery_decision.surface",
        ],
        "default_limit": 5,
        "manual_feed_entry_required": False,
        "post_ranking_only": True,
    },
    "weekly": {
        "surface": "weekly",
        "label": "Weekly digest",
        "entry_kind": "receiver",
        "page_path": "/ambient/weekly",
        "request_path": "/ambient/weekly/api",
        "contract_schema": "ambient_delivery_item_set.v1",
        "contract_model": "AmbientDeliveryItemSet",
        "delivery_semantics": "Lower-urgency catch-up batch for weekly review.",
        "selection_rule": "delivery_decision.surface == weekly",
        "cadence": "next weekly review run",
        "aggregation_behavior": "group already-ranked lower-urgency catch-up items into a compact weekly review batch",
        "item_selection_inputs": [
            "completed ensemble_score",
            "completed final_score",
            "urgency",
            "pre_layer_ranking rank identity",
            "delivery_decision.surface",
        ],
        "default_limit": 8,
        "manual_feed_entry_required": False,
        "post_ranking_only": True,
    },
    "pwa": {
        "surface": "pwa",
        "label": "PWA ambient shelf",
        "entry_kind": "requester",
        "page_path": "/ambient/pwa",
        "request_path": "/ambient/pwa/api",
        "contract_schema": "ambient_delivery_item_set.v1",
        "contract_model": "AmbientDeliveryItemSet",
        "delivery_semantics": "Installable app shell requests currently routable ambient cards.",
        "selection_rule": "delivery_decision.surface == pwa",
        "installed_display_modes": ["standalone", "fullscreen", "minimal-ui", "window-controls-overlay"],
        "unsupported_browser_fallback_surface": "daily",
        "unsupported_browser_fallback_path": "/ambient/daily",
        "default_limit": 5,
        "manual_feed_entry_required": False,
        "post_ranking_only": True,
    },
    "tray": {
        "surface": "tray",
        "label": "Tray/native glance",
        "entry_kind": "requester",
        "page_path": "/ambient/tray",
        "request_path": "/ambient/tray/api",
        "contract_schema": "ambient_delivery_item_set.v1",
        "contract_model": "AmbientDeliveryItemSet",
        "delivery_semantics": "Native tray requests a compact glance of immediately useful items.",
        "selection_rule": "delivery_decision.surface in {critical, daily, pwa}, preserving pre-layer rank order",
        "aliases": ["native", "native_notification"],
        "eligible_surfaces": ["critical", "daily", "pwa"],
        "item_selection_inputs": [
            "completed ensemble_score",
            "completed final_score",
            "pre_layer_ranking rank identity",
            "delivery_decision.surface",
        ],
        "default_limit": 4,
        "manual_feed_entry_required": False,
        "post_ranking_only": True,
    },
}


def normalize_ambient_surface(surface: str) -> str:
    normalized = str(surface or "").strip().lower().replace("-", "_")
    return SURFACE_ALIASES.get(normalized, normalized)


def ambient_surface_entry_points(policy: dict | None = None) -> list[dict[str, Any]]:
    """Return configured ambient surfaces and their request/receive semantics."""
    p = policy or get_personal_algorithm_policy()
    delivery = p.get("delivery") or {}
    delivery_enabled = bool(delivery.get("enabled", True))
    configured = set(delivery.get("surfaces") or [])
    if not configured:
        configured = set(AMBIENT_SURFACE_ENTRY_POINTS)

    entry_points: list[dict[str, Any]] = []
    for surface, spec in AMBIENT_SURFACE_ENTRY_POINTS.items():
        row = copy.deepcopy(spec)
        row["enabled"] = delivery_enabled and surface in configured
        row["post_ranking_boundary"] = {
            "layer": "ambient_delivery",
            "mutates_scores": False,
            "mutates_rank_identity": False,
            "immutable_fields": ["ensemble_score", "final_score", "pre_layer_ranking"],
        }
        entry_points.append(row)
    return entry_points


def get_ambient_surface_entry_point(surface: str, policy: dict | None = None) -> dict[str, Any] | None:
    normalized = normalize_ambient_surface(surface)
    for entry in ambient_surface_entry_points(policy):
        if entry["surface"] == normalized:
            return entry
    return None


def _client_flag(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if value is None:
        return None
    normalized = str(value).strip().lower()
    if normalized in {"1", "true", "yes", "y", "on"}:
        return True
    if normalized in {"0", "false", "no", "n", "off"}:
        return False
    return None


def resolve_ambient_surface_for_client(
    surface: str,
    client_context: dict[str, Any] | None = None,
    policy: dict | None = None,
) -> dict[str, Any]:
    """Resolve requester-surface routing without changing ranked item identity.

    PWA clients can explicitly report installed/standalone mode or unsupported
    browser capabilities. Unsupported browsers fall back to another ambient
    surface, never to the manual web feed.
    """
    requested = normalize_ambient_surface(surface)
    entry = get_ambient_surface_entry_point(requested, policy)
    if entry is None:
        raise ValueError(f"unknown ambient surface: {surface}")
    context = client_context or {}
    if requested == "tray":
        native_available = _client_flag(
            context.get("native_available")
            or context.get("supports_native")
            or context.get("native_bridge_available")
        )
        notification_permission = str(
            context.get("notification_permission")
            or context.get("native_notification_permission")
            or ""
        ).strip().lower() or None

        if native_available is False:
            fallback_surface = "pwa"
            pwa_route = resolve_ambient_surface_for_client(
                "pwa",
                client_context=context,
                policy=policy,
            )
            if pwa_route["fallback"]:
                fallback_surface = pwa_route["resolved_surface"]
            return {
                "requested_surface": requested,
                "resolved_surface": fallback_surface,
                "fallback": True,
                "reason": "native tray unavailable uses ambient fallback instead of manual feed",
                "manual_feed_entry_required": False,
                "native_available": False,
                "native_notification_permission": notification_permission,
            }

        if notification_permission == "denied":
            return {
                "requested_surface": requested,
                "resolved_surface": requested,
                "fallback": False,
                "reason": "native notification permission denied; tray glance remains available",
                "manual_feed_entry_required": False,
                "native_available": native_available,
                "native_notification_permission": "denied",
                "native_notifications_enabled": False,
            }

        return {
            "requested_surface": requested,
            "resolved_surface": requested,
            "fallback": False,
            "reason": "native tray ambient glance is available",
            "manual_feed_entry_required": False,
            "native_available": native_available,
            "native_notification_permission": notification_permission,
            "native_notifications_enabled": notification_permission in {"granted", "authorized"},
        }
    if requested != "pwa":
        return {
            "requested_surface": requested,
            "resolved_surface": requested,
            "fallback": False,
            "reason": "requested ambient surface is directly routable",
            "manual_feed_entry_required": False,
        }

    display_mode = str(context.get("display_mode") or context.get("display") or "").strip().lower()
    installed_modes = set(entry.get("installed_display_modes") or [])
    installed = _client_flag(context.get("installed") or context.get("is_installed"))
    standalone = _client_flag(context.get("standalone"))
    is_installed_context = (
        installed is True
        or standalone is True
        or display_mode in installed_modes
    )
    unsupported_flags = [
        _client_flag(context.get("unsupported_browser")),
        _client_flag(context.get("supports_service_worker")) is False,
        _client_flag(context.get("supports_manifest")) is False,
    ]
    unsupported_browser = any(flag is True for flag in unsupported_flags)
    if unsupported_browser and not is_installed_context:
        fallback_surface = normalize_ambient_surface(entry["unsupported_browser_fallback_surface"])
        return {
            "requested_surface": requested,
            "resolved_surface": fallback_surface,
            "fallback": True,
            "reason": "unsupported browser uses ambient fallback instead of manual feed",
            "manual_feed_entry_required": False,
        }

    return {
        "requested_surface": requested,
        "resolved_surface": requested,
        "fallback": False,
        "reason": "installed or supported PWA ambient shelf",
        "manual_feed_entry_required": False,
        "display_mode": display_mode or None,
    }


def ambient_item_set_schema() -> dict[str, Any]:
    """Return the versioned JSON schema consumed by ambient delivery clients."""
    schema = AmbientDeliveryItemSet.model_json_schema()
    defs = schema.setdefault("$defs", {})
    defs.setdefault("AmbientDeliveryItemSet", {
        key: value for key, value in schema.items()
        if key not in {"$defs", "$schema"}
    })
    return schema


def delivery_policy_config_schema() -> dict[str, Any]:
    """Return the versioned schema for steerable ambient delivery policy."""
    return DeliveryPolicyConfig.model_json_schema()


def delivery_policy_config(policy: dict | None = None) -> dict[str, Any]:
    """Return normalized timing/repeat/quiet-hours/urgency/surface policy."""
    return get_delivery_policy_config(policy).model_dump(mode="json")


DELIVERY_POLICY_STEERING_INTERFACE: dict[str, Any] = {
    "schema_version": "delivery_policy_steering_interface.v1",
    "input": "natural_language_user_intent",
    "output": "json_patch_like_changes",
    "allowed_path_prefix": "personal_algorithm.delivery",
    "target_schema": "delivery_policy_config.v1",
    "supported_intents": [
        {
            "intent": "set_daily_digest_time",
            "paths": ["personal_algorithm.delivery.timing.daily_digest_time"],
            "examples": ["daily digest at 08:30", "send my daily update at 7:05"],
        },
        {
            "intent": "set_weekly_digest_schedule",
            "paths": [
                "personal_algorithm.delivery.timing.weekly_digest_day",
                "personal_algorithm.delivery.timing.weekly_digest_time",
            ],
            "examples": ["weekly review on Friday at 17:30"],
        },
        {
            "intent": "set_quiet_hours",
            "paths": [
                "personal_algorithm.delivery.quiet_hours.enabled",
                "personal_algorithm.delivery.quiet_hours.start",
                "personal_algorithm.delivery.quiet_hours.end",
            ],
            "examples": ["quiet hours from 22:00 to 07:00"],
        },
        {
            "intent": "set_preferred_surfaces",
            "paths": ["personal_algorithm.delivery.preferred_surfaces"],
            "examples": ["prefer tray and PWA", "use native notifications first"],
        },
        {
            "intent": "set_repeat_policy",
            "paths": [
                "personal_algorithm.delivery.repeat.enabled",
                "personal_algorithm.delivery.repeat.max_count",
                "personal_algorithm.delivery.repeat.min_interval_minutes",
                "personal_algorithm.delivery.repeat.snooze_minutes",
            ],
            "examples": ["do not repeat notifications", "snooze for 30 minutes"],
        },
        {
            "intent": "set_post_ranking_urgency_thresholds",
            "paths": [
                "personal_algorithm.delivery.urgency.critical_score_threshold",
                "personal_algorithm.delivery.urgency.daily_score_threshold",
            ],
            "examples": ["only critical alerts above 90%", "daily digest threshold 70%"],
        },
    ],
    "ranking_boundary": {
        "post_ranking_only": True,
        "ranking_input": False,
        "mutates_scores": False,
        "mutates_rank_identity": False,
        "forbidden_paths": [
            "ranking",
            "retrieval",
            "fitness",
            "meta_evolution",
            "personal_algorithm.delivery.ranking_input",
            "personal_algorithm.delivery.mutates_scores",
            "personal_algorithm.delivery.mutates_rank_identity",
            "ensemble_score",
            "final_score",
            "pre_layer_ranking",
        ],
    },
}

_WEEKDAYS = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")
_SURFACE_WORDS = ("critical", "daily", "weekly", "pwa", "tray", "native", "digest")
_WEEKDAY_BY_INDEX = {
    0: "monday",
    1: "tuesday",
    2: "wednesday",
    3: "thursday",
    4: "friday",
    5: "saturday",
    6: "sunday",
}
_FORBIDDEN_STEERING_TERMS = (
    "ranking",
    "rank ",
    "re-rank",
    "rerank",
    "ensemble",
    "final_score",
    "ensemble_score",
    "pre_layer_ranking",
    "retrieval",
    "fitness",
    "train",
    "model",
    "score field",
)


def delivery_policy_steering_interface() -> dict[str, Any]:
    """Describe the supported NL-to-delivery-policy steering contract."""
    return copy.deepcopy(DELIVERY_POLICY_STEERING_INTERFACE)


def _parse_time_to_hhmm(value: str) -> str | None:
    text = str(value or "").strip().lower()
    match = re.fullmatch(r"(\d{1,2})(?::(\d{2}))?\s*(am|pm)?", text)
    if not match:
        return None
    hour = int(match.group(1))
    minute = int(match.group(2) or 0)
    meridiem = match.group(3)
    if meridiem:
        if hour < 1 or hour > 12:
            return None
        if meridiem == "pm" and hour != 12:
            hour += 12
        if meridiem == "am" and hour == 12:
            hour = 0
    if hour > 23 or minute > 59:
        return None
    return f"{hour:02d}:{minute:02d}"


def _hhmm_to_minutes(value: str) -> int:
    hour, minute = str(value).split(":", 1)
    return int(hour) * 60 + int(minute)


def _weekday_name(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, int):
        return _WEEKDAY_BY_INDEX.get(value)
    text = str(value).strip().lower()
    if text.isdigit():
        return _WEEKDAY_BY_INDEX.get(int(text))
    return text if text in _WEEKDAYS else None


def _quiet_hours_active(start: str, end: str, current_minute: int) -> bool:
    start_minute = _hhmm_to_minutes(start)
    end_minute = _hhmm_to_minutes(end)
    if start_minute < end_minute:
        return start_minute <= current_minute < end_minute
    return current_minute >= start_minute or current_minute < end_minute


def _delivery_schedule_context(client_context: dict[str, Any] | None) -> dict[str, Any] | None:
    """Return explicit scheduler time context, or None for preview/requester reads."""
    context = client_context or {}
    enforced = _client_flag(context.get("enforce_delivery_schedule") or context.get("scheduler"))
    has_schedule_time = any(
        key in context
        for key in ("now", "current_datetime", "schedule_at", "current_time", "local_time", "weekday")
    )
    if enforced is not True and not has_schedule_time:
        return None

    raw_datetime = context.get("now") or context.get("current_datetime") or context.get("schedule_at")
    if raw_datetime:
        parsed = datetime.fromisoformat(str(raw_datetime).replace("Z", "+00:00"))
        return {
            "enforced": True,
            "current_time": f"{parsed.hour:02d}:{parsed.minute:02d}",
            "current_minute": parsed.hour * 60 + parsed.minute,
            "weekday": _WEEKDAY_BY_INDEX[parsed.weekday()],
        }

    current_time = _parse_time_to_hhmm(str(context.get("current_time") or context.get("local_time") or ""))
    if current_time is None:
        parsed = datetime.now()
        current_time = f"{parsed.hour:02d}:{parsed.minute:02d}"
        weekday = _WEEKDAY_BY_INDEX[parsed.weekday()]
    else:
        weekday = _weekday_name(context.get("weekday"))

    return {
        "enforced": True,
        "current_time": current_time,
        "current_minute": _hhmm_to_minutes(current_time),
        "weekday": weekday,
    }


def _naive_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value.replace(tzinfo=None)
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).replace(tzinfo=None)
    except ValueError:
        return None


def _history_timestamp(entry: dict[str, Any], *keys: str) -> str:
    for key in keys:
        if entry.get(key):
            return str(entry[key])
    return ""


def _delivery_history_entries_for_signal(
    client_context: dict[str, Any] | None,
    signal_id: str,
) -> list[dict[str, Any]]:
    """Return raw delivery history entries for one signal from caller context."""
    context = client_context or {}
    history = (
        context.get("delivery_history")
        or context.get("ambient_delivery_history")
        or context.get("delivery_events")
        or context.get("ambient_delivery_events")
        or []
    )
    if isinstance(history, dict):
        direct = history.get(signal_id)
        if direct is not None:
            values = direct if isinstance(direct, list) else [direct]
            return [
                {"signal_id": signal_id, "delivered_count": int(value)}
                if isinstance(value, int)
                else dict(value, signal_id=signal_id) if isinstance(value, dict)
                else {"signal_id": signal_id}
                for value in values
            ]
        values = list(history.values())
    elif isinstance(history, list):
        values = history
    else:
        return []

    entries: list[dict[str, Any]] = []
    for value in values:
        if not isinstance(value, dict):
            continue
        if str(value.get("signal_id") or "") == signal_id:
            entries.append(value)
    return entries


def _delivery_repeat_state(
    signal_id: str,
    policy_config: DeliveryPolicyConfig,
    client_context: dict[str, Any] | None,
) -> dict[str, Any]:
    """Summarize repeat/frequency state from raw delivery events only."""
    repeat = policy_config.repeat
    schedule_context = _delivery_schedule_context(client_context)
    now = _naive_datetime(
        (client_context or {}).get("now")
        or (client_context or {}).get("current_datetime")
        or (client_context or {}).get("schedule_at")
    )
    current_minute = int(schedule_context["current_minute"]) if schedule_context else None
    entries = _delivery_history_entries_for_signal(client_context, signal_id)
    delivered_count = 0
    last_delivered_at = ""
    last_snoozed_at = ""
    seen_delivered_event_ids: set[str] = set()

    for entry in entries:
        event_type = str(entry.get("event_type") or "").strip().lower()
        delivery_event_id = str(entry.get("id") or entry.get("event_id") or "").strip()
        duplicate_delivered_event = (
            event_type == "delivered"
            and bool(delivery_event_id)
            and delivery_event_id in seen_delivered_event_ids
        )
        if duplicate_delivered_event:
            continue
        delivered_count += int(
            entry.get("delivered_count")
            or entry.get("delivery_count")
            or entry.get("count")
            or 0
        )
        if event_type == "delivered":
            if delivery_event_id:
                seen_delivered_event_ids.add(delivery_event_id)
            delivered_count += 1
            candidate = _history_timestamp(entry, "last_delivered_at", "delivered_at", "captured_at", "occurred_at", "timestamp")
            if candidate and (not last_delivered_at or candidate > last_delivered_at):
                last_delivered_at = candidate
        elif event_type == "snoozed":
            candidate = _history_timestamp(entry, "last_snoozed_at", "snoozed_at", "captured_at", "occurred_at", "timestamp")
            if candidate and (not last_snoozed_at or candidate > last_snoozed_at):
                last_snoozed_at = candidate
        if entry.get("last_delivered_at") and str(entry["last_delivered_at"]) > last_delivered_at:
            last_delivered_at = str(entry["last_delivered_at"])
        if entry.get("last_snoozed_at") and str(entry["last_snoozed_at"]) > last_snoozed_at:
            last_snoozed_at = str(entry["last_snoozed_at"])

    def minutes_since(value: str) -> int | None:
        parsed = _naive_datetime(value)
        if now and parsed:
            return max(0, int((now - parsed).total_seconds() // 60))
        if current_minute is not None:
            parsed_time = _parse_time_to_hhmm(value)
            if parsed_time:
                return max(0, current_minute - _hhmm_to_minutes(parsed_time))
        return None

    minutes_since_delivery = minutes_since(last_delivered_at)
    minutes_since_snooze = minutes_since(last_snoozed_at)
    max_count_reached = bool(delivered_count and delivered_count >= repeat.max_count)
    repeat_disabled = not repeat.enabled or repeat.max_count == 0
    interval_active = (
        minutes_since_delivery is not None
        and minutes_since_delivery < repeat.min_interval_minutes
    )
    snooze_active = (
        minutes_since_snooze is not None
        and minutes_since_snooze < repeat.snooze_minutes
    )
    return {
        "schema_version": "ambient_delivery_repeat_state.v1",
        "post_ranking_only": True,
        "ranking_input": False,
        "mutates_scores": False,
        "mutates_rank_identity": False,
        "history_observed": bool(entries),
        "delivered_count": delivered_count,
        "max_count": int(repeat.max_count),
        "repeat_enabled": bool(repeat.enabled),
        "min_interval_minutes": int(repeat.min_interval_minutes),
        "snooze_minutes": int(repeat.snooze_minutes),
        "last_delivered_at": last_delivered_at,
        "last_snoozed_at": last_snoozed_at,
        "minutes_since_last_delivery": minutes_since_delivery,
        "minutes_since_last_snooze": minutes_since_snooze,
        "max_count_reached": max_count_reached,
        "frequency_cap_deferred": interval_active or snooze_active,
        "frequency_cap_suppressed": bool(delivered_count and (repeat_disabled or max_count_reached)),
        "defer_reason": "snoozed" if snooze_active else "repeat_min_interval" if interval_active else "",
    }


def _delivery_scheduling_priority(decision: dict[str, Any]) -> dict[str, Any]:
    """Return post-ranking queue priority metadata for the delivery scheduler.

    Lower numeric values mean the scheduler should consider the item sooner.
    This is routing metadata only; it is never written back to ranking scores
    or used as a ranking-layer input.
    """
    surface = normalize_ambient_surface(str(decision.get("surface") or ""))
    urgency = str(decision.get("urgency") or "").strip().lower()
    timing = str(decision.get("timing") or "").strip().lower()
    base_priority = {
        "critical": 10,
        "daily": 50,
        "tray": 55,
        "pwa": 60,
        "weekly": 80,
    }.get(surface, 70)
    urgency_adjustment = {
        "alert": -10,
        "digest": 0,
        "skip": 15,
    }.get(urgency, 0)
    priority = max(0, min(100, base_priority + urgency_adjustment))
    if surface == "critical" or timing == "now":
        tier = "immediate"
    elif surface in {"daily", "tray", "pwa"}:
        tier = "digest"
    else:
        tier = "background"

    return {
        "schema_version": "ambient_delivery_scheduling_priority.v1",
        "post_ranking_only": True,
        "ranking_input": False,
        "mutates_scores": False,
        "mutates_rank_identity": False,
        "urgency": urgency,
        "surface": surface,
        "tier": tier,
        "priority": priority,
        "lower_value_delivers_sooner": True,
    }


def _time_matches(text: str) -> list[str]:
    matches: list[str] = []
    for raw in re.findall(r"\b\d{1,2}(?::\d{2})?\s*(?:am|pm)?\b", text):
        parsed = _parse_time_to_hhmm(raw)
        if parsed and parsed not in matches:
            matches.append(parsed)
    return matches


def _time_after_keyword(text: str, keywords: tuple[str, ...]) -> str | None:
    for keyword in keywords:
        match = re.search(rf"\b{keyword}\b(?P<context>.{{0,80}})", text)
        if not match:
            continue
        times = _time_matches(match.group("context"))
        if times:
            return times[0]
    return None


def _times_after_keyword(text: str, keywords: tuple[str, ...]) -> list[str]:
    for keyword in keywords:
        match = re.search(rf"\b{keyword}\b(?P<context>.{{0,100}})", text)
        if not match:
            continue
        times = _time_matches(match.group("context"))
        if times:
            return times
    return []


def _percentage_after(text: str, keywords: tuple[str, ...]) -> float | None:
    for keyword in keywords:
        for keyword_match in re.finditer(rf"\b{keyword}\b(?P<context>.{{0,50}})", text):
            context = keyword_match.group("context")
            match = re.search(r"\b(\d{1,3})\s*(?:%|percent\b)", context)
            if not match:
                continue
            value = int(match.group(1))
            if 0 <= value <= 100:
                return round(value / 100, 4)
    return None


def _surface_preferences(text: str) -> list[str]:
    surfaces: list[str] = []
    scoped = text
    for keyword in ("prefer", "preferred", "use", "surface", "surfaces"):
        match = re.search(rf"\b{keyword}\b(?P<context>[^.;,]*)", text)
        if match:
            scoped = match.group("context")
            break
    for surface in _SURFACE_WORDS:
        if re.search(rf"\b{re.escape(surface)}(?:s| notifications?)?\b", scoped):
            normalized = normalize_ambient_surface(surface)
            if normalized not in surfaces:
                surfaces.append(normalized)
    return surfaces


def _append_change(changes: list[dict[str, Any]], path: str, value: Any) -> None:
    change = {"op": "set", "path": path, "value": value}
    if change not in changes:
        changes.append(change)


def _delivery_overlay_from_changes(changes: list[dict[str, Any]]) -> dict[str, Any]:
    overlay: dict[str, Any] = {}
    prefix = "personal_algorithm.delivery."
    for change in changes:
        path = str(change.get("path") or "")
        if not path.startswith(prefix):
            continue
        cursor = overlay
        parts = path[len(prefix):].split(".")
        for part in parts[:-1]:
            cursor = cursor.setdefault(part, {})
        cursor[parts[-1]] = change.get("value")
    return overlay


def parse_delivery_policy_updates(user_intent: str) -> dict[str, Any]:
    """Map supported natural-language delivery intents onto DeliveryPolicyConfig.

    The parser intentionally emits only ``personal_algorithm.delivery`` changes.
    Requests that mention ranking/score mutation are reported as unsupported
    boundary violations instead of being translated into policy changes.
    All emitted changes are validated through ``DeliveryPolicyConfig`` before
    callers receive them.
    """
    text = " ".join(str(user_intent or "").strip().lower().split())
    if not text:
        return {"ok": False, "error": "empty intent", "changes": []}

    changes: list[dict[str, Any]] = []
    matched_intents: list[str] = []
    unsupported: list[dict[str, str]] = []

    if any(term in text for term in _FORBIDDEN_STEERING_TERMS):
        unsupported.append({
            "intent": "ranking_or_score_mutation",
            "reason": "Delivery steering cannot add ranking inputs, mutate score fields, or change rank identity.",
        })

    daily_time = _time_after_keyword(text, ("daily", "digest"))
    if "daily" in text and daily_time:
        _append_change(changes, "personal_algorithm.delivery.timing.daily_digest_time", daily_time)
        matched_intents.append("set_daily_digest_time")

    weekly_day = next((day for day in _WEEKDAYS if re.search(rf"\b{day}\b", text)), None)
    weekly_times = _times_after_keyword(text, ("weekly", "week"))
    if ("weekly" in text or "week" in text) and weekly_day:
        _append_change(changes, "personal_algorithm.delivery.timing.weekly_digest_day", weekly_day)
        matched_intents.append("set_weekly_digest_schedule")
        if weekly_times:
            _append_change(changes, "personal_algorithm.delivery.timing.weekly_digest_time", weekly_times[0])

    if "quiet" in text or "do not disturb" in text or "dnd" in text:
        _append_change(changes, "personal_algorithm.delivery.quiet_hours.enabled", True)
        matched_intents.append("set_quiet_hours")
        quiet_times = _times_after_keyword(text, ("quiet", "disturb", "dnd"))
        if len(quiet_times) >= 2:
            _append_change(changes, "personal_algorithm.delivery.quiet_hours.start", quiet_times[0])
            _append_change(changes, "personal_algorithm.delivery.quiet_hours.end", quiet_times[1])
        if "critical" in text and (
            "no override" in text
            or "never override" in text
            or re.search(r"\bno\b.{0,40}\boverride\b", text)
            or re.search(r"\bwithout\b.{0,40}\boverride\b", text)
        ):
            _append_change(changes, "personal_algorithm.delivery.quiet_hours.allow_critical_override", False)
        elif "critical" in text and ("override" in text or "allow" in text):
            _append_change(changes, "personal_algorithm.delivery.quiet_hours.allow_critical_override", True)

    if "prefer" in text or "use " in text or "surface" in text or "native" in text:
        surfaces = _surface_preferences(text)
        if surfaces:
            _append_change(changes, "personal_algorithm.delivery.preferred_surfaces", surfaces)
            matched_intents.append("set_preferred_surfaces")

    if "do not repeat" in text or "don't repeat" in text or "no repeat" in text:
        _append_change(changes, "personal_algorithm.delivery.repeat.enabled", False)
        _append_change(changes, "personal_algorithm.delivery.repeat.max_count", 0)
        matched_intents.append("set_repeat_policy")
    else:
        repeat_match = re.search(r"\b(?:repeat|max(?:imum)?)[^0-9]*(\d{1,2})\b", text)
        if repeat_match:
            _append_change(changes, "personal_algorithm.delivery.repeat.enabled", True)
            _append_change(changes, "personal_algorithm.delivery.repeat.max_count", int(repeat_match.group(1)))
            matched_intents.append("set_repeat_policy")
    snooze_match = re.search(r"\bsnooze[^0-9]*(\d{1,5})\s*(?:m|min|minute|minutes)?\b", text)
    if snooze_match:
        _append_change(changes, "personal_algorithm.delivery.repeat.snooze_minutes", int(snooze_match.group(1)))
        matched_intents.append("set_repeat_policy")
    interval_match = re.search(r"\b(?:interval|gap)[^0-9]*(\d{1,5})\s*(?:m|min|minute|minutes)?\b", text)
    if interval_match:
        _append_change(changes, "personal_algorithm.delivery.repeat.min_interval_minutes", int(interval_match.group(1)))
        matched_intents.append("set_repeat_policy")

    critical_threshold = _percentage_after(text, ("critical", "alert"))
    if critical_threshold is not None:
        _append_change(
            changes,
            "personal_algorithm.delivery.urgency.critical_score_threshold",
            critical_threshold,
        )
        matched_intents.append("set_post_ranking_urgency_thresholds")
    daily_threshold = _percentage_after(text, ("daily", "digest"))
    if daily_threshold is not None:
        _append_change(changes, "personal_algorithm.delivery.urgency.daily_score_threshold", daily_threshold)
        matched_intents.append("set_post_ranking_urgency_thresholds")

    matched_intents = sorted(set(matched_intents))
    if not changes:
        return {
            "ok": False,
            "error": "unsupported delivery steering intent",
            "changes": [],
            "unsupported_intents": unsupported or [{
                "intent": "unknown_delivery_policy_request",
                "reason": "No supported delivery policy fields were identified.",
            }],
            "interface": delivery_policy_steering_interface(),
        }

    forbidden_paths = [
        change["path"]
        for change in changes
        if not str(change.get("path") or "").startswith("personal_algorithm.delivery.")
    ]
    if forbidden_paths:
        raise ValueError(f"delivery steering produced forbidden paths: {forbidden_paths!r}")

    try:
        normalized_policy = get_delivery_policy_config({"delivery": _delivery_overlay_from_changes(changes)})
    except ValueError as exc:
        return {
            "ok": False,
            "error": "invalid delivery policy update",
            "changes": changes,
            "matched_intents": matched_intents,
            "unsupported_intents": unsupported,
            "validation_error": str(exc),
            "interface": delivery_policy_steering_interface(),
            "ranking_boundary": {
                "post_ranking_only": True,
                "ranking_input": False,
                "mutates_scores": False,
                "mutates_rank_identity": False,
                "new_ranking_inputs": [],
            },
        }
    classification = classify_policy_edit(changes, user_intent)
    return {
        "ok": True,
        "summary": "ambient delivery policy steering",
        "changes": changes,
        "matched_intents": matched_intents,
        "unsupported_intents": unsupported,
        "classification": classification,
        "risk_class": classification["risk_class"],
        "classification_reason": classification["reason"],
        "normalized_delivery_policy": normalized_policy.model_dump(mode="json"),
        "interface": delivery_policy_steering_interface(),
        "ranking_boundary": {
            "post_ranking_only": True,
            "ranking_input": False,
            "mutates_scores": False,
            "mutates_rank_identity": False,
            "new_ranking_inputs": [],
        },
    }


def propose_delivery_policy_steering(user_intent: str) -> dict[str, Any]:
    """Return a classified, schema-validated delivery policy steering proposal."""
    return parse_delivery_policy_updates(user_intent)


def _short_reason(text: str, limit: int = 160) -> str:
    cleaned = " ".join(str(text or "").split())
    if len(cleaned) <= limit:
        return cleaned
    return f"{cleaned[:limit - 3].rstrip()}..."


EXPLANATION_COPY_FORBIDDEN_PATTERNS = (
    re.compile(r"\b\d+(?:\.\d+)?\s*%", re.IGNORECASE),
    re.compile(r"\bconfidence\b", re.IGNORECASE),
    re.compile(r"\brank(?:ed|ing)?\b|#\s*\d+\b", re.IGNORECASE),
    re.compile(r"\b(?:ensemble|final|relevance)?\s*score(?:d|s)?\b", re.IGNORECASE),
    re.compile(r"\b\d+\.\d+\b", re.IGNORECASE),
    re.compile(r"\b(?:best|top|highest|lowest|authoritative|must\s+read)\b", re.IGNORECASE),
)

AMBIENT_EXPLANATION_METADATA_CONTRACT: dict[str, Any] = {
    "schema_version": "ambient_explanation_metadata.v1",
    "approved_item_fields": [
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
    ],
    "approved_delivery_fields": [
        "surface",
        "timing",
        "channel",
    ],
    "forbidden_ranking_fields": [
        "score",
        "relevance_score",
        "ensemble_score",
        "final_score",
        "ensemble_rank",
        "rank",
        "rank_position",
        "feed_position",
        "pre_layer_ranking",
        "ranking_snapshot",
        "component_scores",
        "ranking_features",
        "ranking_trace",
        "debug",
        "debug_fields",
        "debug_trace",
        "ranking_debug",
        "weights",
        "llm_judge",
        "bandit_state",
    ],
    "boundary": {
        "display_only": True,
        "ranking_input": False,
        "score_like_authority": False,
        "excludes_raw_pr18_gen9_internals": True,
    },
}


def ambient_explanation_metadata_contract() -> dict[str, Any]:
    """Return the allow-list contract for ambient explanation generation."""
    return copy.deepcopy(AMBIENT_EXPLANATION_METADATA_CONTRACT)


def _forbidden_explanation_ranking_keys() -> set[str]:
    return set(AMBIENT_EXPLANATION_METADATA_CONTRACT["forbidden_ranking_fields"]) | {
        "input_ensemble_score",
        "input_final_score",
        "input_ensemble_rank",
        "input_order",
        "rank_identifiers",
        "ranking_internals",
        "raw_ranking",
        "pre_layer_identity",
    }


def explanation_payload_is_serialization_safe(payload: Any) -> bool:
    """Return whether an explanation payload excludes raw ranking internals."""
    forbidden = _forbidden_explanation_ranking_keys()

    def walk(value: Any) -> bool:
        if isinstance(value, dict):
            for key, nested in value.items():
                if str(key) in forbidden:
                    return False
                if not walk(nested):
                    return False
        elif isinstance(value, list):
            return all(walk(item) for item in value)
        return True

    return walk(payload)


def sanitize_ambient_explanation_payload(payload: Any, fallback_text: str = "") -> dict[str, Any]:
    """Serialize explanation metadata through a strict display-only allow-list.

    Delivery decisions may carry ranking snapshots elsewhere for boundary
    audits, but the explanation payload is intentionally copy-only.
    """
    source = payload if isinstance(payload, dict) else {}
    text = _safe_display_reason(str(source.get("text") or ""), fallback_text)
    if not text:
        text = _safe_display_reason(fallback_text, "Selected by ambient delivery context.")
    sanitized = {
        "text": text,
        "display_only": True,
        "ranking_input": False,
        "score_like_authority": False,
    }
    if not explanation_payload_is_serialization_safe(sanitized):
        raise ValueError("ambient explanation payload contains raw ranking internals")
    return sanitized


def ambient_explanation_context(item: dict[str, Any], decision: dict[str, Any]) -> dict[str, Any]:
    """Build the only ranked-item metadata visible to explanation generation.

    Ambient explanations may use user-facing copy and coarse routing context,
    but not score, rank, component, or snapshot internals from PR #18 / Gen 9.
    """
    anomaly_reason = ""
    if isinstance(item.get("anomaly_label"), dict):
        anomaly_reason = str(item["anomaly_label"].get("reason") or "")

    reason = _safe_display_reason(str(item.get("reason") or ""), "")
    why_relevant = _safe_display_reason(str(item.get("why_relevant") or ""), "")
    anomaly_reason = _safe_display_reason(anomaly_reason, "")

    return {
        "schema_version": AMBIENT_EXPLANATION_METADATA_CONTRACT["schema_version"],
        "item": {
            "id": str(item.get("id") or item.get("signal_id") or ""),
            "title": str(item.get("title") or ""),
            "url": str(item.get("url") or ""),
            "platform": item.get("platform"),
            "author": item.get("author"),
            "urgency": str(item.get("urgency") or ""),
            "reason": reason,
            "why_relevant": why_relevant,
            "anomaly_reason": anomaly_reason,
            "is_exploration": bool(item.get("is_exploration")),
        },
        "delivery": {
            "surface": str(decision.get("surface") or "ambient"),
            "timing": str(decision.get("timing") or ""),
            "channel": str(decision.get("channel") or ""),
        },
        "boundary": copy.deepcopy(AMBIENT_EXPLANATION_METADATA_CONTRACT["boundary"]),
    }


def explanation_copy_is_surface_safe(text: str) -> bool:
    """Return whether ambient explanation copy avoids score-like authority."""
    copy_text = str(text or "")
    if not copy_text.strip():
        return False
    return not any(pattern.search(copy_text) for pattern in EXPLANATION_COPY_FORBIDDEN_PATTERNS)


def _safe_display_reason(text: str, fallback: str, limit: int = 160) -> str:
    """Keep ambient explanations non-numeric and non-authoritative."""
    cleaned = _short_reason(text, limit=limit)
    if explanation_copy_is_surface_safe(cleaned):
        return cleaned

    clauses = [
        clause.strip(" \t\n\r.;")
        for clause in re.split(r"(?<=[.!?])\s+|;\s+|\s+-\s+|\s+\|\s+", str(text or ""))
    ]
    safe_clauses = [
        clause
        for clause in clauses
        if clause and explanation_copy_is_surface_safe(clause)
    ]
    if safe_clauses:
        return _short_reason(". ".join(safe_clauses), limit=limit)
    return fallback


def _ambient_reason_fallback_from_context(context: dict[str, Any]) -> str:
    """Stable display copy when delivered items do not carry safe reason text."""
    surface = context["delivery"]["surface"]
    urgency = context["item"]["urgency"].strip().lower()
    if context["item"]["is_exploration"] or surface == "pwa":
        return "Exploration item reserved for ambient discovery."
    if urgency == "alert" or surface == "critical":
        return "Critical context routed this item to immediate ambient delivery."
    if surface == "daily":
        return "Relevant digest item selected for today."
    if surface == "weekly":
        return "Lower-urgency item kept for weekly ambient review."
    return "Selected by ambient delivery context."


def ambient_display_reason_from_context(context: dict[str, Any]) -> str:
    """Generate user-facing explanation copy from the approved context only."""
    if context.get("schema_version") != AMBIENT_EXPLANATION_METADATA_CONTRACT["schema_version"]:
        raise ValueError("ambient explanation context must use the approved metadata contract")
    if set(context.get("item") or {}) != set(AMBIENT_EXPLANATION_METADATA_CONTRACT["approved_item_fields"]):
        raise ValueError("ambient explanation item context contains unapproved fields")
    if set(context.get("delivery") or {}) != set(AMBIENT_EXPLANATION_METADATA_CONTRACT["approved_delivery_fields"]):
        raise ValueError("ambient explanation delivery context contains unapproved fields")

    item_context = context["item"]
    fallback = _ambient_reason_fallback_from_context(context)
    item_reason = _short_reason(item_context["reason"])
    if item_reason:
        return _safe_display_reason(item_reason, fallback)

    why_relevant = _short_reason(item_context["why_relevant"])
    if why_relevant:
        return _safe_display_reason(why_relevant, fallback)

    anomaly_reason = _short_reason(item_context["anomaly_reason"])
    if anomaly_reason:
        return _safe_display_reason(anomaly_reason, fallback)

    return fallback


def _ambient_item_reason(item: dict[str, Any], decision: dict[str, Any]) -> str:
    """Build display-only delivery copy from approved metadata context."""
    return ambient_display_reason_from_context(ambient_explanation_context(item, decision))


def _contract_item(item: dict[str, Any]) -> AmbientDeliveryItem:
    decision = item.get("delivery_decision") or {}
    ranking = item.get("pre_layer_ranking") or {}
    decision_snapshot = (
        decision.get("ranking_snapshot")
        if isinstance(decision.get("ranking_snapshot"), dict)
        else {}
    )
    reason = _ambient_item_reason(item, decision)
    explanation = sanitize_ambient_explanation_payload(
        {"text": reason},
        fallback_text=reason,
    )
    decision_payload = copy.deepcopy(decision)
    decision_payload["explanation"] = explanation
    explanation_context = ambient_explanation_context(item, decision)
    return AmbientDeliveryItem(
        id=str(item.get("id") or item.get("signal_id") or ""),
        title=str(item.get("title") or ""),
        url=str(item.get("url") or ""),
        reason=reason,
        platform=item.get("platform"),
        author=item.get("author"),
        surface=decision.get("surface"),
        delivery_timing=decision.get("timing"),
        delivery_channel=decision.get("channel"),
        ensemble_score=float(item.get("ensemble_score") or 0),
        final_score=float(item.get("final_score") or 0),
        pre_layer_ranking=AmbientPreLayerRankingSnapshot(
            ensemble_score=float(ranking.get("ensemble_score") or item.get("ensemble_score") or 0),
            final_score=float(ranking.get("final_score") or item.get("final_score") or 0),
            input_rank=ranking.get("input_rank"),
            input_order=ranking.get("input_order"),
            rank_identifiers=decision_snapshot.get("rank_identifiers") or ranking.get("rank_identifiers") or {},
            immutable=bool(ranking.get("immutable", True)),
        ),
        delivery_decision=decision_payload,
        explanation=explanation,
        why_relevant=explanation_context["item"]["why_relevant"],
    )


AMBIENT_DELIVERY_EVENT_TYPES = {
    "delivered",
    "opened",
    "dismissed",
    "snoozed",
    "saved",
    "clicked",
}
AMBIENT_DELIVERY_REWARD_RULE_VERSION = "ambient_delivery_reward_v1"
AMBIENT_DELIVERY_REWARD_MODEL: dict[str, dict[str, Any] | None] = {
    "delivered": None,
    "opened": {
        "reward_value": 0.55,
        "signal_strength": "strong_positive",
        "confidence": 0.75,
        "uncertainty_reason": "",
    },
    "clicked": {
        "reward_value": 0.45,
        "signal_strength": "strong_positive",
        "confidence": 0.70,
        "uncertainty_reason": "",
    },
    "saved": {
        "reward_value": 0.80,
        "signal_strength": "strong_positive",
        "confidence": 0.85,
        "uncertainty_reason": "",
    },
    "dismissed": {
        "reward_value": -0.20,
        "signal_strength": "weak_negative",
        "confidence": 0.45,
        "uncertainty_reason": "delivery dismissal is a noisy exposure signal",
    },
    "snoozed": {
        "reward_value": -0.05,
        "signal_strength": "weak_negative",
        "confidence": 0.35,
        "uncertainty_reason": "snooze may reflect timing rather than item preference",
    },
}


def ambient_delivery_reward_mapping() -> dict[str, dict[str, Any] | None]:
    """Return the PR #18 delivery-event reward mapping without score inputs."""
    return copy.deepcopy(AMBIENT_DELIVERY_REWARD_MODEL)


def is_ambient_delivery_event(event: dict[str, Any]) -> bool:
    """Return True for raw delivery-surface behavior events.

    Ambient delivery events are observations of surface handling, not reward
    derivation requests. Keeping this classifier here gives every caller the
    same boundary between raw delivery events and later reward interpretation.
    """
    event_type = str(event.get("event_type") or "").strip().lower()
    feed_id = str(event.get("feed_id") or "")
    feed_mode = str(event.get("feed_mode") or event.get("mode") or "")
    has_ambient_context = (
        event.get("raw_delivery_event") is True
        or bool(event.get("ambient_surface"))
        or bool(event.get("delivery_surface"))
        or feed_id.startswith("ambient:")
        or feed_mode.startswith("ambient_")
    )
    return bool(has_ambient_context and event_type)


def interpret_ambient_delivery_event(event: dict[str, Any], policy: dict | None = None) -> dict[str, Any] | None:
    """Convert one raw ambient delivery event into a separate delivery reward.

    This intentionally does not call ``interpret_behavior_event``: delivery
    surfaces have different semantics than feed/open-web behavior. Exposure-only
    ``delivered`` events remain raw behavior observations and derive no reward.
    """
    if not is_ambient_delivery_event(event):
        return None

    event_type = str(event.get("event_type") or "").strip().lower()
    mapping = AMBIENT_DELIVERY_REWARD_MODEL.get(event_type)
    if mapping is None:
        return None

    signal_id = event.get("signal_id")
    if not signal_id:
        return None

    value = float(mapping["reward_value"])
    signal_strength = str(mapping["signal_strength"])
    confidence = float(mapping["confidence"])
    uncertainty = str(mapping["uncertainty_reason"])
    p = policy or get_personal_algorithm_policy()
    polarity = "positive" if value > 0 else "negative" if value < 0 else "neutral"
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
        "derivation_rule_version": AMBIENT_DELIVERY_REWARD_RULE_VERSION,
        "policy_version": p.get("version") or 1,
        "feed_mode": event.get("feed_mode") or event.get("mode") or "ambient",
        "source": "ambient_delivery",
    }


def ambient_delivery_rewards_from_events(
    events: list[dict[str, Any]],
    policy: dict | None = None,
) -> list[dict[str, Any]]:
    """Derive ambient delivery rewards from raw events without mixing schemas."""
    return [
        reward
        for event in events or []
        if (reward := interpret_ambient_delivery_event(event, policy=policy))
    ]


def ambient_delivery_events(
    payload: dict[str, Any],
    event_type: str = "delivered",
    device: str = "server_api",
) -> list[dict[str, Any]]:
    """Build raw PR #18 behavior events for ambient API/background paths.

    These rows intentionally use only the existing behavior_events columns.
    Derived rewards remain a separate concern and are not produced here.
    """
    normalized_event_type = str(event_type or "").strip().lower()
    if normalized_event_type not in AMBIENT_DELIVERY_EVENT_TYPES:
        raise ValueError(f"unsupported ambient delivery event_type: {event_type}")

    surface = normalize_ambient_surface(str(payload.get("surface") or "ambient"))
    events: list[dict[str, Any]] = []
    for idx, item in enumerate(payload.get("items") or []):
        signal_id = item.get("id") or item.get("signal_id")
        if not signal_id:
            continue
        pre_layer = item.get("pre_layer_ranking") if isinstance(item.get("pre_layer_ranking"), dict) else {}
        position = pre_layer.get("input_order")
        if position is None:
            position = idx
        events.append({
            "signal_id": str(signal_id),
            "event_type": normalized_event_type,
            "position_in_feed": position,
            "feed_id": f"ambient:{surface}",
            "feed_mode": f"ambient_{surface}",
            "device": device,
        })
    return events


def record_ambient_delivery_events(
    payload: dict[str, Any],
    event_type: str = "delivered",
    device: str = "server_api",
) -> int:
    """Persist ambient events and derived rewards through existing pipelines."""
    from hedwig.storage import save_behavior_events_batch, save_behavior_rewards_batch

    events = ambient_delivery_events(payload, event_type=event_type, device=device)
    saved_events = save_behavior_events_batch(events)
    rewards = ambient_delivery_rewards_from_events(events) if saved_events else []
    if rewards:
        save_behavior_rewards_batch(rewards)
    return saved_events


def emit_ambient_delivery_rewards(events: list[dict[str, Any]]) -> int:
    """Persist derived ambient rewards when raw events were saved elsewhere."""
    from hedwig.storage import save_behavior_rewards_batch

    rewards = ambient_delivery_rewards_from_events(events)
    return save_behavior_rewards_batch(rewards) if rewards else 0


def delivery_schedule_for_decision(
    decision: dict[str, Any],
    policy_config: DeliveryPolicyConfig,
    client_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Evaluate post-ranking delivery timing without touching rank scores."""
    surface = normalize_ambient_surface(str(decision.get("surface") or ""))
    schedule_context = _delivery_schedule_context(client_context)
    scheduling_priority = _delivery_scheduling_priority(decision)
    schedule = {
        "schema_version": "ambient_delivery_schedule.v1",
        "post_ranking_only": True,
        "ranking_input": False,
        "mutates_scores": False,
        "mutates_rank_identity": False,
        "enforced": bool(schedule_context),
        "surface": surface,
        "urgency": scheduling_priority["urgency"],
        "priority": scheduling_priority["priority"],
        "priority_tier": scheduling_priority["tier"],
        "scheduling_priority": scheduling_priority,
        "eligible_now": True,
        "defer_reason": "",
        "quiet_hours_active": False,
        "quiet_hours_deferred": False,
        "current_time": None,
        "weekday": None,
        "target_time": None,
        "target_day": None,
    }
    repeat_state = _delivery_repeat_state(
        str(decision.get("signal_id") or ""),
        policy_config,
        client_context,
    )
    schedule["repeat_state"] = repeat_state
    if repeat_state["frequency_cap_suppressed"]:
        schedule["eligible_now"] = False
        schedule["defer_reason"] = "repeat_max_count"
        schedule["frequency_cap_suppressed"] = True
        schedule["frequency_cap_deferred"] = False
        return schedule
    if repeat_state["frequency_cap_deferred"]:
        schedule["eligible_now"] = False
        schedule["defer_reason"] = repeat_state["defer_reason"]
        schedule["frequency_cap_suppressed"] = False
        schedule["frequency_cap_deferred"] = True
        return schedule
    schedule["frequency_cap_suppressed"] = False
    schedule["frequency_cap_deferred"] = False
    if not schedule_context:
        return schedule

    current_minute = int(schedule_context["current_minute"])
    schedule["current_time"] = schedule_context["current_time"]
    schedule["weekday"] = schedule_context.get("weekday")

    quiet = policy_config.quiet_hours
    if (
        policy_config.timing.defer_to_quiet_hours
        and quiet.enabled
        and _quiet_hours_active(quiet.start, quiet.end, current_minute)
    ):
        schedule["quiet_hours_active"] = True
        critical_override = surface == "critical" and quiet.allow_critical_override
        if not critical_override:
            schedule["eligible_now"] = False
            schedule["quiet_hours_deferred"] = True
            schedule["defer_reason"] = "quiet_hours"
            return schedule
        schedule["defer_reason"] = "critical_quiet_hours_override"

    if surface == "daily":
        target = policy_config.timing.daily_digest_time
        schedule["target_time"] = target
        if current_minute < _hhmm_to_minutes(target):
            schedule["eligible_now"] = False
            schedule["defer_reason"] = "before_daily_digest_time"
    elif surface == "weekly":
        target_day = str(policy_config.timing.weekly_digest_day)
        target = policy_config.timing.weekly_digest_time
        schedule["target_day"] = target_day
        schedule["target_time"] = target
        if schedule.get("weekday") != target_day:
            schedule["eligible_now"] = False
            schedule["defer_reason"] = "outside_weekly_digest_day"
        elif current_minute < _hhmm_to_minutes(target):
            schedule["eligible_now"] = False
            schedule["defer_reason"] = "before_weekly_digest_time"

    return schedule


def _policy_for_resolved_ambient_route(
    policy: dict | None,
    route: dict[str, Any],
) -> dict | None:
    """Return request-local policy that does not prefer unavailable surfaces."""
    if not route.get("fallback"):
        return policy
    if policy is None:
        return None

    requested = normalize_ambient_surface(route.get("requested_surface") or "")
    resolved = normalize_ambient_surface(route.get("resolved_surface") or "")
    if not requested or not resolved or requested == resolved:
        return policy

    effective = copy.deepcopy(policy)
    delivery = effective.setdefault("delivery", {})
    normalized = get_delivery_policy_config(effective)
    surfaces = [str(surface) for surface in normalized.surfaces]
    preferred = [
        str(surface)
        for surface in normalized.preferred_surfaces
        if str(surface) != requested
    ]
    if resolved in surfaces and resolved not in preferred:
        preferred.insert(0, resolved)
    if not preferred:
        preferred = [surface for surface in surfaces if surface != requested] or surfaces

    delivery["surfaces"] = surfaces
    delivery["preferred_surfaces"] = preferred
    return effective


def select_ambient_items(
    items: list[dict[str, Any]],
    surface: str,
    policy: dict | None = None,
    limit: int | None = None,
    client_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Select already-ranked items for one ambient surface.

    The returned items are copies with post-ranking delivery metadata. Incoming
    items are not mutated, and selection never writes to ranking score fields.
    """
    route = resolve_ambient_surface_for_client(surface, client_context=client_context, policy=policy)
    normalized = route["resolved_surface"]
    entry = get_ambient_surface_entry_point(normalized, policy)
    if entry is None:
        raise ValueError(f"unknown ambient surface: {surface}")

    effective_policy = _policy_for_resolved_ambient_route(policy, route)
    default_limit = int(entry.get("default_limit") or 5)
    resolved_limit = max(1, min(50, int(limit or default_limit)))
    delivery_policy = get_delivery_policy_config(effective_policy)
    if not delivery_policy.enabled or not entry.get("enabled", True):
        contract = AmbientDeliveryItemSet(
            surface=normalized,
            limit=resolved_limit,
            count=0,
            items=[],
        )
        payload = contract.model_dump(mode="json")
        payload["entry_point"] = entry
        payload["requested_surface"] = route["requested_surface"]
        payload["client_route"] = route
        payload["selection_suppression"] = {
            "schema_version": "ambient_surface_selection_suppression.v1",
            "reason": "delivery_policy_disabled" if not delivery_policy.enabled else "surface_disabled",
            "surface": normalized,
            "post_ranking_only": True,
            "ranking_input": False,
            "mutates_scores": False,
            "mutates_rank_identity": False,
        }
        return payload

    routed = route_items_after_ranking([copy.deepcopy(item) for item in items], effective_policy)
    for item in routed:
        decision = item.get("delivery_decision") or {}
        schedule = delivery_schedule_for_decision(
            decision,
            delivery_policy,
            client_context=client_context,
        )
        decision["delivery_schedule"] = schedule
        decision["scheduling_priority"] = schedule["scheduling_priority"]
        decision["eligible_now"] = bool(schedule["eligible_now"])
        decision["defer_reason"] = str(schedule["defer_reason"] or "")
        item["delivery_decision"] = decision
        item["delivery_policy"] = decision
        if isinstance(item.get("post_ranking_decisions"), dict):
            item["post_ranking_decisions"]["delivery"] = decision

    if normalized == "tray":
        selected = [
            item for item in routed
            if (item.get("delivery_decision") or {}).get("surface") in {"critical", "daily", "pwa", "tray"}
            and (item.get("delivery_decision") or {}).get("eligible_now", True)
        ]
    else:
        selected = [
            item for item in routed
            if (item.get("delivery_decision") or {}).get("surface") == normalized
            and (item.get("delivery_decision") or {}).get("eligible_now", True)
        ]

    contract = AmbientDeliveryItemSet(
        surface=normalized,
        limit=resolved_limit,
        count=min(len(selected), resolved_limit),
        items=[_contract_item(item) for item in selected[:resolved_limit]],
    )
    payload = contract.model_dump(mode="json")
    payload["entry_point"] = entry
    payload["requested_surface"] = route["requested_surface"]
    payload["client_route"] = route
    return payload
