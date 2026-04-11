"""
Operator-owned API key pool — SaaS users don't need their own OpenAI key.

The operator (you, the SaaS host) provides the OpenAI key. Users pay for
their subscription, which includes API costs. Quota tracking ensures
free-tier users don't burn through unlimited tokens.

Models:
- Free tier: 50K tokens/day
- Pro tier: 2M tokens/day
- Team tier: 5M tokens/day per user
"""
from __future__ import annotations

import logging
import os
from typing import Optional

from hedwig.saas.models import SubscriptionTier

logger = logging.getLogger(__name__)

# Operator-owned keys (loaded once at startup)
OPERATOR_OPENAI_KEY = os.getenv("OPERATOR_OPENAI_KEY", "") or os.getenv("OPENAI_API_KEY", "")
OPERATOR_EXA_KEY = os.getenv("OPERATOR_EXA_KEY", "") or os.getenv("EXA_API_KEY", "")
OPERATOR_SCRAPECREATORS_KEY = os.getenv("OPERATOR_SCRAPECREATORS_KEY", "") or os.getenv("SCRAPECREATORS_API_KEY", "")

# Daily token quotas per tier
TIER_TOKEN_QUOTAS = {
    SubscriptionTier.FREE: 50_000,
    SubscriptionTier.PRO: 2_000_000,
    SubscriptionTier.TEAM: 5_000_000,
}


class QuotaExhausted(Exception):
    """Raised when user has consumed their daily LLM quota."""


def get_operator_openai_key() -> str:
    """Return the operator's OpenAI key, or raise if not configured."""
    if not OPERATOR_OPENAI_KEY:
        raise RuntimeError(
            "OPERATOR_OPENAI_KEY environment variable not set. "
            "In SaaS mode, the operator must provide a shared OpenAI key. "
            "Set OPERATOR_OPENAI_KEY to a valid sk-... key."
        )
    return OPERATOR_OPENAI_KEY


def get_operator_exa_key() -> Optional[str]:
    return OPERATOR_EXA_KEY or None


def get_operator_scrapecreators_key() -> Optional[str]:
    return OPERATOR_SCRAPECREATORS_KEY or None


async def get_llm_client_for_user(user_id: str, tier: SubscriptionTier, storage=None):
    """Return an OpenAI client for the user, after checking quota.

    Raises QuotaExhausted if the user has hit their daily token limit.
    """
    from hedwig.saas.quota import get_current_usage

    quota = TIER_TOKEN_QUOTAS[tier]
    current = await get_current_usage(user_id, "llm_tokens", storage)
    if current >= quota:
        raise QuotaExhausted(
            f"Daily LLM quota exhausted: {current:,}/{quota:,} tokens used. "
            f"Resets at midnight UTC. Upgrade to {_next_tier(tier)} for more."
        )

    from openai import AsyncOpenAI
    return AsyncOpenAI(api_key=get_operator_openai_key())


async def record_llm_usage(user_id: str, tokens: int, storage=None):
    """Record LLM token usage for quota tracking."""
    from hedwig.saas.quota import increment_usage
    await increment_usage(user_id, "llm_tokens", tokens, storage)


def _next_tier(current: SubscriptionTier) -> str:
    if current == SubscriptionTier.FREE:
        return "Pro ($19/mo)"
    if current == SubscriptionTier.PRO:
        return "Team ($49/mo)"
    return "Enterprise"


def get_quota_status(tier: SubscriptionTier, current_usage: int) -> dict:
    """Return quota status for display in dashboard."""
    quota = TIER_TOKEN_QUOTAS[tier]
    return {
        "tier": tier.value,
        "used": current_usage,
        "limit": quota,
        "percent": round(current_usage / quota * 100, 1) if quota else 0,
        "remaining": max(0, quota - current_usage),
    }
