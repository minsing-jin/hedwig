"""SaaS-specific data models for multi-tenancy."""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class SubscriptionTier(str, Enum):
    FREE = "free"
    PRO = "pro"
    TEAM = "team"


class SubscriptionStatus(str, Enum):
    ACTIVE = "active"
    CANCELED = "canceled"
    PAST_DUE = "past_due"
    INCOMPLETE = "incomplete"


TIER_LIMITS = {
    SubscriptionTier.FREE: {
        "sources": 5,
        "signals_per_day": 50,
        "evolution_cycles": "daily_only",
        "user_memory_weeks": 2,
        "custom_sources": False,
    },
    SubscriptionTier.PRO: {
        "sources": 999,
        "signals_per_day": 999_999,
        "evolution_cycles": "daily_weekly",
        "user_memory_weeks": 999,
        "custom_sources": True,
    },
    SubscriptionTier.TEAM: {
        "sources": 999,
        "signals_per_day": 999_999,
        "evolution_cycles": "daily_weekly",
        "user_memory_weeks": 999,
        "custom_sources": True,
        "shared_criteria": True,
        "team_channels": 5,
        "users_per_team": 10,
    },
}

TIER_PRICES = {
    SubscriptionTier.FREE: 0,
    SubscriptionTier.PRO: 19,
    SubscriptionTier.TEAM: 49,
}


class UserProfile(BaseModel):
    id: str
    email: str
    display_name: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    onboarding_complete: bool = False
    criteria: dict = Field(default_factory=dict)
    settings: dict = Field(default_factory=dict)


class Subscription(BaseModel):
    user_id: str
    tier: SubscriptionTier = SubscriptionTier.FREE
    status: SubscriptionStatus = SubscriptionStatus.ACTIVE
    stripe_customer_id: Optional[str] = None
    stripe_subscription_id: Optional[str] = None
    stripe_price_id: Optional[str] = None
    current_period_start: Optional[datetime] = None
    current_period_end: Optional[datetime] = None
    cancel_at_period_end: bool = False

    def get_limits(self) -> dict:
        return TIER_LIMITS[self.tier]

    def can_use_custom_sources(self) -> bool:
        return TIER_LIMITS[self.tier].get("custom_sources", False)

    def can_run_weekly_evolution(self) -> bool:
        return TIER_LIMITS[self.tier]["evolution_cycles"] == "daily_weekly"


class Usage(BaseModel):
    user_id: str
    metric: str  # "signals_collected", "llm_tokens", "evolution_cycles"
    value: int = 0
    period_start: datetime = Field(default_factory=datetime.utcnow)
    period_end: Optional[datetime] = None

    def is_over_limit(self, limit: int) -> bool:
        return self.value >= limit
