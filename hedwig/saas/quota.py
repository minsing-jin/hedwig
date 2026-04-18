"""
Quota enforcement — track usage and enforce tier limits.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from hedwig.saas.models import Subscription, TIER_LIMITS

logger = logging.getLogger(__name__)


class QuotaExceeded(Exception):
    pass


async def check_quota(
    user_id: str,
    metric: str,
    subscription: Subscription,
    storage=None,
) -> tuple[bool, int, int]:
    """Check if user is within quota for a metric.

    Returns (allowed, current_usage, limit).
    """
    limits = TIER_LIMITS[subscription.tier]

    limit_map = {
        "signals_per_day": limits.get("signals_per_day", 0),
        "sources": limits.get("sources", 0),
    }

    limit = limit_map.get(metric, 999_999_999)
    if limit >= 999_999:
        return True, 0, limit  # Unlimited

    current = await get_current_usage(user_id, metric, storage)
    allowed = current < limit
    return allowed, current, limit


async def get_current_usage(user_id: str, metric: str, storage=None) -> int:
    """Get current usage for a metric in the current period (daily)."""
    if not storage:
        return 0

    period_start = datetime.now(tz=timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)

    try:
        result = (
            storage.table("usage_tracking")
            .select("value")
            .eq("user_id", user_id)
            .eq("metric", metric)
            .gte("period_start", period_start.isoformat())
            .execute()
        )
        if result.data:
            return sum(row.get("value", 0) for row in result.data)
    except Exception as e:
        logger.warning(f"Failed to get usage: {e}")
    return 0


async def increment_usage(
    user_id: str,
    metric: str,
    amount: int = 1,
    storage=None,
) -> int:
    """Increment usage counter for a metric."""
    if not storage:
        return 0

    period_start = datetime.now(tz=timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    period_end = period_start + timedelta(days=1)

    try:
        # Try upsert
        existing = (
            storage.table("usage_tracking")
            .select("*")
            .eq("user_id", user_id)
            .eq("metric", metric)
            .gte("period_start", period_start.isoformat())
            .execute()
        )

        if existing.data:
            row = existing.data[0]
            new_value = row.get("value", 0) + amount
            storage.table("usage_tracking").update({"value": new_value}).eq("id", row["id"]).execute()
            return new_value
        else:
            storage.table("usage_tracking").insert({
                "user_id": user_id,
                "metric": metric,
                "value": amount,
                "period_start": period_start.isoformat(),
                "period_end": period_end.isoformat(),
            }).execute()
            return amount
    except Exception as e:
        logger.warning(f"Failed to increment usage: {e}")
        return 0


def enforce_limit(allowed: bool, metric: str, current: int, limit: int):
    """Raise QuotaExceeded if not allowed."""
    if not allowed:
        raise QuotaExceeded(
            f"Quota exceeded for {metric}: {current}/{limit}. Upgrade to Pro for unlimited."
        )
