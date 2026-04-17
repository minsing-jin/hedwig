from __future__ import annotations

from collections import Counter, defaultdict
import logging
from datetime import date, datetime, timedelta, timezone
from typing import Optional

from supabase import create_client

from hedwig.config import SUPABASE_KEY, SUPABASE_URL
from hedwig.models import (
    CriteriaVersion,
    EvolutionLog,
    Feedback,
    ScoredSignal,
    UserMemory,
    VoteType,
)

logger = logging.getLogger(__name__)

SIGNAL_EXPORT_FIELDS = (
    "id",
    "platform",
    "title",
    "url",
    "content",
    "author",
    "relevance_score",
    "urgency",
    "published_at",
    "collected_at",
)
SIGNAL_EXPORT_SELECT = ",".join(SIGNAL_EXPORT_FIELDS)
SINGLE_USER_SIGNAL_OWNER = ""
SIGNAL_UPSERT_CONFLICT_COLUMNS = "user_id,platform,external_id"


def _get_client():
    return create_client(SUPABASE_URL, SUPABASE_KEY)


def _normalize_user_id(user_id: str | None) -> str | None:
    if user_id is None:
        return None

    normalized = str(user_id).strip()
    if not normalized:
        raise ValueError("user_id must be non-empty when provided")
    return normalized


def _normalize_signal_url(url: object) -> str:
    return str(url or "").strip()


def _normalize_signal_owner(user_id: str | None) -> str:
    normalized_user_id = _normalize_user_id(user_id)
    if normalized_user_id is None:
        return SINGLE_USER_SIGNAL_OWNER
    return normalized_user_id


# ---------------------------------------------------------------------------
# Signals
# ---------------------------------------------------------------------------

def _lookup_existing_signal_urls(client, urls: list[str], signal_owner: str) -> list[dict]:
    if not urls:
        return []

    query = (
        client.table("signals")
        .select("url,platform,external_id")
        .eq("user_id", signal_owner)
    )
    result = query.in_("url", urls).execute()
    return result.data or []


def _build_signal_row(signal: ScoredSignal, signal_owner: str) -> dict:
    row = {
        "user_id": signal_owner,
        "platform": signal.raw.platform.value,
        "external_id": signal.raw.external_id,
        "title": signal.raw.title,
        "url": signal.raw.url,
        "content": signal.raw.content[:5000],
        "author": signal.raw.author,
        "platform_score": signal.raw.score,
        "comments_count": signal.raw.comments_count,
        "published_at": signal.raw.published_at.isoformat(),
        "relevance_score": signal.relevance_score,
        "urgency": signal.urgency.value,
        "why_relevant": signal.why_relevant,
        "devils_advocate": signal.devils_advocate,
        "opportunity_note": signal.opportunity_note,
        "exploration_tags": signal.exploration_tags,
        "extra": signal.raw.extra,
        "collected_at": datetime.now(tz=timezone.utc).isoformat(),
    }
    return row


def save_signals(signals: list[ScoredSignal], user_id: str | None = None) -> int:
    if not signals:
        return 0

    try:
        signal_owner = _normalize_signal_owner(user_id)
    except ValueError as e:
        logger.error(f"Failed to save signals: {e}")
        return 0

    client = _get_client()

    try:
        urls = []
        seen_lookup_urls: set[str] = set()
        for signal in signals:
            url = _normalize_signal_url(signal.raw.url)
            if url and url not in seen_lookup_urls:
                seen_lookup_urls.add(url)
                urls.append(url)

        existing_by_url: dict[str, list[tuple[str, str]]] = defaultdict(list)
        for row in _lookup_existing_signal_urls(client, urls=urls, signal_owner=signal_owner):
            existing_url = _normalize_signal_url(row.get("url"))
            if not existing_url:
                continue
            existing_by_url[existing_url].append(
                (
                    str(row.get("platform") or ""),
                    str(row.get("external_id") or ""),
                )
            )
    except Exception as e:
        logger.error(f"Failed to save signals: {e}")
        return 0

    rows = []
    seen_batch_urls: set[str] = set()
    for signal in signals:
        signal_url = _normalize_signal_url(signal.raw.url)
        signal_identity = (signal.raw.platform.value, signal.raw.external_id)

        if signal_url:
            existing_rows = existing_by_url.get(signal_url, [])
            if existing_rows and signal_identity not in existing_rows:
                continue
            if signal_url in seen_batch_urls:
                continue
            seen_batch_urls.add(signal_url)

        rows.append(_build_signal_row(signal, signal_owner=signal_owner))

    if not rows:
        return 0

    try:
        result = (
            client.table("signals")
            .upsert(rows, on_conflict=SIGNAL_UPSERT_CONFLICT_COLUMNS)
            .execute()
        )
        return len(result.data) if result.data else 0
    except Exception as e:
        logger.error(f"Failed to save signals: {e}")
        return 0


def get_recent_signals(days: int = 7) -> list[dict]:
    client = _get_client()
    cutoff = (datetime.now(tz=timezone.utc) - timedelta(days=days)).isoformat()
    try:
        result = (
            client.table("signals")
            .select("*")
            .gte("collected_at", cutoff)
            .order("relevance_score", desc=True)
            .limit(200)
            .execute()
        )
        return result.data or []
    except Exception as e:
        logger.error(f"Failed to get recent signals: {e}")
        return []


def get_signal_platforms(signal_ids: list[str]) -> dict[str, str]:
    normalized_ids = sorted({str(signal_id).strip() for signal_id in signal_ids if str(signal_id).strip()})
    if not normalized_ids:
        return {}

    if not SUPABASE_URL or not SUPABASE_KEY:
        return {}

    try:
        client = _get_client()
    except Exception as e:
        logger.error(f"Failed to create Supabase client for signal platform lookup: {e}")
        return {}

    rows: list[dict] = []
    try:
        id_rows = (
            client.table("signals")
            .select("id,external_id,platform")
            .in_("id", normalized_ids)
            .execute()
            .data
            or []
        )
        external_rows = (
            client.table("signals")
            .select("id,external_id,platform")
            .in_("external_id", normalized_ids)
            .execute()
            .data
            or []
        )
        rows = [*id_rows, *external_rows]
    except Exception as e:
        logger.error(f"Failed to resolve signal platforms: {e}")
        return {}

    mapping: dict[str, str] = {}
    for row in rows:
        platform = str(row.get("platform") or "").strip()
        if not platform:
            continue
        signal_id = str(row.get("id") or "").strip()
        external_id = str(row.get("external_id") or "").strip()
        if signal_id:
            mapping[signal_id] = platform
        if external_id:
            mapping[external_id] = platform
    return mapping


def get_latest_signals(limit: int = 100) -> list[dict]:
    if limit <= 0:
        return []

    client = _get_client()
    try:
        result = (
            client.table("signals")
            .select(SIGNAL_EXPORT_SELECT)
            .order("collected_at", desc=True)
            .limit(limit)
            .execute()
        )
        return result.data or []
    except Exception as e:
        logger.error(f"Failed to get latest signals: {e}")
        return []


def _escape_ilike_pattern(value: str) -> str:
    return (
        value
        .replace("\\", "\\\\")
        .replace("%", r"\%")
        .replace("_", r"\_")
    )


def _search_signal_field(client, field: str, pattern: str, limit: int) -> list[dict]:
    result = (
        client.table("signals")
        .select(SIGNAL_EXPORT_SELECT)
        .ilike(field, pattern)
        .order("collected_at", desc=True)
        .limit(limit)
        .execute()
    )
    return result.data or []


def _signal_search_key(signal: dict) -> tuple[object, ...]:
    return (
        signal.get("id"),
        signal.get("url"),
        signal.get("platform"),
        signal.get("title"),
        signal.get("collected_at"),
    )


def search_signals(query: str, limit: int = 100) -> list[dict]:
    search_term = query.strip()
    if not search_term or limit <= 0:
        return []

    client = _get_client()
    try:
        pattern = f"%{_escape_ilike_pattern(search_term)}%"
        matches_by_key: dict[tuple[object, ...], dict] = {}
        for field in ("title", "content"):
            for signal in _search_signal_field(client, field=field, pattern=pattern, limit=limit):
                matches_by_key[_signal_search_key(signal)] = signal

        return sorted(
            matches_by_key.values(),
            key=lambda signal: signal.get("collected_at") or "",
            reverse=True,
        )[:limit]
    except Exception as e:
        logger.error(f"Failed to search signals: {e}")
        return []


def is_duplicate(platform: str, external_id: str) -> bool:
    client = _get_client()
    try:
        result = (
            client.table("signals")
            .select("id")
            .eq("platform", platform)
            .eq("external_id", external_id)
            .limit(1)
            .execute()
        )
        return bool(result.data)
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Feedback (v2: boolean + natural language)
# ---------------------------------------------------------------------------

def save_feedback(feedback: Feedback, user_id: str | None = None) -> bool:
    try:
        user_id = _normalize_user_id(user_id)
    except ValueError as e:
        logger.error(f"Failed to save feedback: {e}")
        return False

    client = _get_client()
    row = {
        "signal_id": feedback.signal_id,
        "vote": feedback.vote.value,
        "natural_language": feedback.natural_language,
        "source_channel": feedback.source_channel,
        "captured_at": feedback.captured_at.isoformat(),
    }
    if user_id is not None:
        row["user_id"] = user_id
    try:
        client.table("feedback").insert(row).execute()
        return True
    except Exception as e:
        logger.error(f"Failed to save feedback: {e}")
        return False


async def save_feedback_batch(
    feedbacks: list[Feedback],
    user_id: str | None = None,
) -> int:
    if not feedbacks:
        return 0

    try:
        user_id = _normalize_user_id(user_id)
    except ValueError as e:
        logger.error(f"Failed to save feedback batch: {e}")
        return 0

    client = _get_client()
    rows = []
    for feedback in feedbacks:
        row = {
            "signal_id": feedback.signal_id,
            "vote": feedback.vote.value,
            "natural_language": feedback.natural_language,
            "source_channel": feedback.source_channel,
            "captured_at": feedback.captured_at.isoformat(),
        }
        if user_id is not None:
            row["user_id"] = user_id
        rows.append(row)
    try:
        result = client.table("feedback").insert(rows).execute()
        return len(result.data) if result.data else 0
    except Exception as e:
        logger.error(f"Failed to save feedback batch: {e}")
        return 0


def get_feedback_since(days: int = 1) -> list[dict]:
    client = _get_client()
    cutoff = (datetime.now(tz=timezone.utc) - timedelta(days=days)).isoformat()
    try:
        result = (
            client.table("feedback")
            .select("*")
            .gte("captured_at", cutoff)
            .execute()
        )
        return result.data or []
    except Exception as e:
        logger.error(f"Failed to get feedback: {e}")
        return []


def _coerce_utc_date(value: object) -> date | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        parsed = value
    else:
        text = str(value).strip()
        if not text:
            return None
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            return None

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).date()


def _coerce_run_timestamp(value: object) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        parsed = value
    else:
        text = str(value).strip()
        if not text:
            return None
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            return None

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _empty_run_stats() -> dict[str, object]:
    return {
        "consecutive_daily_runs": 0,
        "total_daily_cycles": 0,
        "total_weekly_cycles": 0,
        "last_daily_at": None,
        "last_weekly_at": None,
    }


def _summarize_run_rows(rows: list[dict]) -> dict[str, object]:
    stats = _empty_run_stats()
    daily_times: list[datetime] = []
    weekly_times: list[datetime] = []

    for row in rows:
        cycle_type = str(row.get("cycle_type") or "").strip().lower()
        run_at = _coerce_run_timestamp(row.get("run_at"))
        if run_at is None:
            continue
        if cycle_type == "daily":
            daily_times.append(run_at)
        elif cycle_type == "weekly":
            weekly_times.append(run_at)

    if daily_times:
        stats["total_daily_cycles"] = len(daily_times)
        stats["last_daily_at"] = max(daily_times).isoformat()

        streak = 0
        expected_day = None
        for run_day in sorted({run_at.date() for run_at in daily_times}, reverse=True):
            if expected_day is None or run_day == expected_day:
                streak += 1
                expected_day = run_day - timedelta(days=1)
                continue
            break
        stats["consecutive_daily_runs"] = streak

    if weekly_times:
        stats["total_weekly_cycles"] = len(weekly_times)
        stats["last_weekly_at"] = max(weekly_times).isoformat()

    return stats


def _build_dashboard_query(client, table_name: str, fields: str, user_id: str | None):
    normalized_user_id = _normalize_user_id(user_id)
    query = client.table(table_name).select(fields)
    if normalized_user_id is not None:
        query = query.eq("user_id", normalized_user_id)
    return query


def get_dashboard_activity_stats(user_id: str | None = None) -> dict:
    """Aggregate dashboard activity metrics from Supabase rows.

    When ``user_id`` is provided, scope signals and feedback to that tenant.
    """
    client = _get_client()
    try:
        signal_rows = (
            _build_dashboard_query(
                client,
                table_name="signals",
                fields="platform,collected_at",
                user_id=user_id,
            )
            .execute()
            .data
            or []
        )
        feedback_rows = (
            _build_dashboard_query(
                client,
                table_name="feedback",
                fields="vote",
                user_id=user_id,
            )
            .execute()
            .data
            or []
        )
    except Exception as e:
        logger.error(f"Failed to get dashboard activity stats: {e}")
        return {
            "total_signals": 0,
            "upvote_ratio": 0.0,
            "top_5_sources": [],
            "days_active": 0,
        }

    total_signals = len(signal_rows)
    total_feedback = len(feedback_rows)
    upvotes = sum(1 for row in feedback_rows if row.get("vote") == VoteType.UP.value)
    upvote_ratio = (upvotes / total_feedback) if total_feedback else 0.0

    source_counts = Counter()
    active_days: set[date] = set()
    for row in signal_rows:
        platform = str(row.get("platform") or "").strip()
        if platform:
            source_counts[platform] += 1

        collected_day = _coerce_utc_date(row.get("collected_at"))
        if collected_day is not None:
            active_days.add(collected_day)

    top_5_sources = [
        {"source": source, "count": count}
        for source, count in sorted(
            source_counts.items(),
            key=lambda item: (-item[1], item[0]),
        )[:5]
    ]

    return {
        "total_signals": total_signals,
        "upvote_ratio": upvote_ratio,
        "top_5_sources": top_5_sources,
        "days_active": len(active_days),
    }


# ---------------------------------------------------------------------------
# User source settings
# ---------------------------------------------------------------------------

def load_user_source_settings(
    user_id: str,
    registry: dict[str, object],
) -> dict[str, bool]:
    """Load tenant-owned source enablement flags from Supabase."""
    try:
        normalized_user_id = _normalize_user_id(user_id)
    except ValueError as e:
        logger.error(f"Failed to load user source settings: {e}")
        return {plugin_id: True for plugin_id in registry}

    enabled = {plugin_id: True for plugin_id in registry}
    client = _get_client()

    try:
        rows = (
            client.table("user_sources")
            .select("plugin_id,enabled")
            .eq("user_id", normalized_user_id)
            .execute()
            .data
            or []
        )
    except Exception as e:
        logger.error(f"Failed to load user source settings: {e}")
        return enabled

    for row in rows:
        plugin_id = str(row.get("plugin_id") or "").strip()
        if plugin_id in enabled:
            enabled[plugin_id] = bool(row.get("enabled"))

    return enabled


def save_user_source_settings(user_id: str, enabled: dict[str, bool]) -> bool:
    """Persist tenant-owned source enablement flags to Supabase."""
    try:
        normalized_user_id = _normalize_user_id(user_id)
    except ValueError as e:
        logger.error(f"Failed to save user source settings: {e}")
        return False

    client = _get_client()
    rows = [
        {
            "user_id": normalized_user_id,
            "plugin_id": plugin_id,
            "enabled": bool(enabled[plugin_id]),
            "updated_at": datetime.now(tz=timezone.utc).isoformat(),
        }
        for plugin_id in sorted(enabled)
    ]

    try:
        client.table("user_sources").upsert(
            rows,
            on_conflict="user_id,plugin_id",
        ).execute()
        return True
    except Exception as e:
        logger.error(f"Failed to save user source settings: {e}")
        return False


# ---------------------------------------------------------------------------
# Evolution logs
# ---------------------------------------------------------------------------

def save_evolution_log(log: EvolutionLog) -> bool:
    client = _get_client()
    try:
        run_at = _coerce_run_timestamp(log.timestamp)
        run_at_text = run_at.isoformat() if run_at is not None else datetime.now(tz=timezone.utc).isoformat()
        client.table("evolution_logs").insert({
            "cycle_type": log.cycle_type.value,
            "cycle_number": log.cycle_number,
            "criteria_version_before": log.criteria_version_before,
            "criteria_version_after": log.criteria_version_after,
            "mutations_applied": log.mutations_applied,
            "fitness_before": log.fitness_before,
            "fitness_after": log.fitness_after,
            "kept": log.kept,
            "analysis_summary": log.analysis_summary,
            "timestamp": run_at_text,
        }).execute()
        client.table("run_history").insert({
            "cycle_type": log.cycle_type.value,
            "run_at": run_at_text,
        }).execute()
        return True
    except Exception as e:
        logger.error(f"Failed to save evolution log: {e}")
        return False


def get_run_stats() -> dict[str, object]:
    client = _get_client()
    rows: list[dict] = []

    try:
        rows = (
            client.table("run_history")
            .select("cycle_type,run_at")
            .order("run_at", desc=True)
            .limit(5000)
            .execute()
            .data
            or []
        )
    except Exception as e:
        logger.warning(f"Failed to read run_history stats: {e}")

    if not rows:
        try:
            legacy_rows = (
                client.table("evolution_logs")
                .select("cycle_type,timestamp")
                .order("timestamp", desc=True)
                .limit(5000)
                .execute()
                .data
                or []
            )
            rows = [
                {
                    "cycle_type": row.get("cycle_type"),
                    "run_at": row.get("timestamp"),
                }
                for row in legacy_rows
            ]
        except Exception as e:
            logger.error(f"Failed to get run stats: {e}")
            return _empty_run_stats()

    return _summarize_run_rows(rows)


# ---------------------------------------------------------------------------
# Criteria versions
# ---------------------------------------------------------------------------

def save_criteria_version(cv: CriteriaVersion) -> bool:
    client = _get_client()
    try:
        client.table("criteria_versions").insert({
            "version": cv.version,
            "criteria": cv.criteria,
            "created_at": cv.created_at.isoformat(),
            "created_by": cv.created_by,
            "diff_from_previous": cv.diff_from_previous,
            "fitness_score": cv.fitness_score,
        }).execute()
        return True
    except Exception as e:
        logger.error(f"Failed to save criteria version: {e}")
        return False


# ---------------------------------------------------------------------------
# User memory
# ---------------------------------------------------------------------------

def save_user_memory(memory: UserMemory) -> bool:
    client = _get_client()
    try:
        client.table("user_memory").insert({
            "snapshot_week": memory.snapshot_week,
            "confirmed_interests": memory.confirmed_interests,
            "rejected_topics": memory.rejected_topics,
            "taste_trajectory": memory.taste_trajectory,
            "context": memory.context,
            "natural_language_feedback": memory.natural_language_feedback,
            "created_at": memory.created_at.isoformat(),
        }).execute()
        return True
    except Exception as e:
        logger.error(f"Failed to save user memory: {e}")
        return False


# ---------------------------------------------------------------------------
# Source reliability
# ---------------------------------------------------------------------------

def save_source_reliability(scores: dict[str, float]) -> bool:
    if not scores:
        return True

    client = _get_client()
    rows = []
    updated_at = datetime.now(tz=timezone.utc).isoformat()
    for platform, score in scores.items():
        platform_name = str(platform or "").strip()
        if not platform_name:
            continue
        rows.append(
            {
                "platform": platform_name,
                "reliability_score": max(0.0, min(1.0, float(score))),
                "updated_at": updated_at,
            }
        )

    if not rows:
        return True

    try:
        client.table("source_reliability").upsert(
            rows,
            on_conflict="platform",
        ).execute()
        return True
    except Exception as e:
        logger.error(f"Failed to save source reliability: {e}")
        return False


def get_source_reliability() -> dict[str, float]:
    if not SUPABASE_URL or not SUPABASE_KEY:
        return {}

    try:
        client = _get_client()
    except Exception as e:
        logger.error(f"Failed to create Supabase client for source reliability lookup: {e}")
        return {}

    try:
        rows = (
            client.table("source_reliability")
            .select("platform,reliability_score")
            .order("updated_at", desc=True)
            .execute()
            .data
            or []
        )
    except Exception as e:
        logger.error(f"Failed to get source reliability: {e}")
        return {}

    scores: dict[str, float] = {}
    for row in rows:
        platform = str(row.get("platform") or "").strip()
        if not platform:
            continue
        scores[platform] = max(0.0, min(1.0, float(row.get("reliability_score") or 0.0)))
    return scores


# ---------------------------------------------------------------------------
# SaaS subscription persistence
# ---------------------------------------------------------------------------

def _coerce_subscription_timestamp(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        dt = value
    elif isinstance(value, (int, float)):
        dt = datetime.fromtimestamp(value, tz=timezone.utc)
    else:
        text = str(value).strip()
        if not text:
            return None
        if text.isdigit():
            dt = datetime.fromtimestamp(int(text), tz=timezone.utc)
        else:
            try:
                dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
            except ValueError:
                return text

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat()


def save_subscription_update(
    *,
    user_id: str | None = None,
    tier: str | None = None,
    stripe_customer_id: str | None = None,
    stripe_subscription_id: str | None = None,
    status: str | None = None,
    current_period_end: object | None = None,
    cancel_at_period_end: bool | None = None,
) -> bool:
    if not SUPABASE_URL or not SUPABASE_KEY:
        logger.warning("Skipping subscription persistence: Supabase credentials not configured")
        return False

    try:
        normalized_user_id = _normalize_user_id(user_id)
    except ValueError as e:
        logger.error(f"Failed to save subscription update: {e}")
        return False

    row: dict[str, object] = {
        "updated_at": datetime.now(tz=timezone.utc).isoformat(),
    }
    if normalized_user_id is not None:
        row["user_id"] = normalized_user_id
    if tier is not None:
        row["tier"] = str(tier)
    if stripe_customer_id is not None:
        row["stripe_customer_id"] = str(stripe_customer_id)
    if stripe_subscription_id is not None:
        row["stripe_subscription_id"] = str(stripe_subscription_id)
    if status is not None:
        row["status"] = str(status)
    if current_period_end is not None:
        row["current_period_end"] = _coerce_subscription_timestamp(current_period_end)
    if cancel_at_period_end is not None:
        row["cancel_at_period_end"] = bool(cancel_at_period_end)

    if normalized_user_id is None and "stripe_subscription_id" not in row:
        logger.error("Failed to save subscription update: missing user_id and stripe_subscription_id")
        return False

    client = _get_client()
    try:
        if normalized_user_id is not None:
            client.table("subscriptions").upsert(row, on_conflict="user_id").execute()
        else:
            client.table("subscriptions").update(row).eq(
                "stripe_subscription_id",
                row["stripe_subscription_id"],
            ).execute()
        return True
    except Exception as e:
        logger.error(f"Failed to save subscription update: {e}")
        return False


# ---------------------------------------------------------------------------
# Schema SQL — run in Supabase SQL editor
# ---------------------------------------------------------------------------

SCHEMA_SQL = """
-- Signals (extended with exploration_tags)
CREATE TABLE IF NOT EXISTS signals (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    user_id TEXT NOT NULL DEFAULT '',
    platform TEXT NOT NULL,
    external_id TEXT NOT NULL,
    title TEXT NOT NULL,
    url TEXT,
    content TEXT,
    author TEXT,
    platform_score INTEGER DEFAULT 0,
    comments_count INTEGER DEFAULT 0,
    published_at TIMESTAMPTZ,
    relevance_score FLOAT DEFAULT 0,
    urgency TEXT DEFAULT 'skip',
    why_relevant TEXT,
    devils_advocate TEXT,
    opportunity_note TEXT,
    exploration_tags JSONB DEFAULT '[]',
    extra JSONB DEFAULT '{}',
    collected_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(user_id, platform, external_id)
);

-- Feedback (v2: boolean vote + natural language)
CREATE TABLE IF NOT EXISTS feedback (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    user_id TEXT,
    signal_id TEXT NOT NULL,
    vote TEXT NOT NULL CHECK (vote IN ('up', 'down')),
    natural_language TEXT,
    source_channel TEXT DEFAULT '',
    captured_at TIMESTAMPTZ DEFAULT NOW()
);

-- Evolution logs
CREATE TABLE IF NOT EXISTS evolution_logs (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    cycle_type TEXT NOT NULL CHECK (cycle_type IN ('daily', 'weekly')),
    cycle_number INTEGER NOT NULL,
    criteria_version_before INTEGER,
    criteria_version_after INTEGER,
    mutations_applied JSONB DEFAULT '[]',
    fitness_before FLOAT,
    fitness_after FLOAT,
    kept BOOLEAN DEFAULT TRUE,
    analysis_summary TEXT,
    timestamp TIMESTAMPTZ DEFAULT NOW()
);

-- Criteria version history
CREATE TABLE IF NOT EXISTS criteria_versions (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    version INTEGER NOT NULL UNIQUE,
    criteria JSONB NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    created_by TEXT DEFAULT 'system',
    diff_from_previous TEXT,
    fitness_score FLOAT
);

-- User memory (long-horizon preference model)
CREATE TABLE IF NOT EXISTS user_memory (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    snapshot_week TEXT NOT NULL,
    confirmed_interests JSONB DEFAULT '[]',
    rejected_topics JSONB DEFAULT '[]',
    taste_trajectory TEXT,
    context JSONB DEFAULT '{}',
    natural_language_feedback JSONB DEFAULT '[]',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS source_reliability (
    platform TEXT PRIMARY KEY,
    reliability_score FLOAT NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS user_sources (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    user_id TEXT NOT NULL,
    plugin_id TEXT NOT NULL,
    enabled BOOLEAN DEFAULT TRUE,
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(user_id, plugin_id)
);

CREATE TABLE IF NOT EXISTS subscriptions (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    user_id TEXT NOT NULL UNIQUE,
    tier TEXT NOT NULL DEFAULT 'free',
    status TEXT NOT NULL DEFAULT 'active',
    stripe_customer_id TEXT,
    stripe_subscription_id TEXT,
    current_period_end TIMESTAMPTZ,
    cancel_at_period_end BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS run_history (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    cycle_type TEXT NOT NULL CHECK (cycle_type IN ('daily', 'weekly')),
    run_at TIMESTAMPTZ DEFAULT NOW()
);

ALTER TABLE signals
    ADD COLUMN IF NOT EXISTS user_id TEXT;

ALTER TABLE feedback
    ADD COLUMN IF NOT EXISTS user_id TEXT;

UPDATE signals
SET user_id = ''
WHERE user_id IS NULL;

ALTER TABLE signals
    ALTER COLUMN user_id SET DEFAULT '';

ALTER TABLE signals
    ALTER COLUMN user_id SET NOT NULL;

ALTER TABLE signals
    DROP CONSTRAINT IF EXISTS signals_platform_external_id_key;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'signals_user_id_platform_external_id_key'
    ) THEN
        ALTER TABLE signals
            ADD CONSTRAINT signals_user_id_platform_external_id_key
            UNIQUE (user_id, platform, external_id);
    END IF;
END $$;

-- Indexes
CREATE INDEX IF NOT EXISTS idx_signals_collected ON signals(collected_at DESC);
CREATE INDEX IF NOT EXISTS idx_signals_relevance ON signals(relevance_score DESC);
CREATE INDEX IF NOT EXISTS idx_signals_platform ON signals(platform);
CREATE INDEX IF NOT EXISTS idx_signals_user_id ON signals(user_id);
CREATE INDEX IF NOT EXISTS idx_feedback_captured ON feedback(captured_at DESC);
CREATE INDEX IF NOT EXISTS idx_feedback_signal ON feedback(signal_id);
CREATE INDEX IF NOT EXISTS idx_feedback_user_id ON feedback(user_id);
CREATE INDEX IF NOT EXISTS idx_user_sources_user_id ON user_sources(user_id);
CREATE INDEX IF NOT EXISTS idx_user_sources_plugin_id ON user_sources(plugin_id);
CREATE INDEX IF NOT EXISTS idx_subscriptions_stripe_subscription_id ON subscriptions(stripe_subscription_id);
CREATE INDEX IF NOT EXISTS idx_run_history_run_at ON run_history(run_at DESC);
CREATE INDEX IF NOT EXISTS idx_run_history_cycle_type ON run_history(cycle_type);
CREATE INDEX IF NOT EXISTS idx_evolution_timestamp ON evolution_logs(timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_criteria_version ON criteria_versions(version DESC);
CREATE INDEX IF NOT EXISTS idx_memory_week ON user_memory(snapshot_week);
CREATE INDEX IF NOT EXISTS idx_source_reliability_updated_at ON source_reliability(updated_at DESC);
"""
