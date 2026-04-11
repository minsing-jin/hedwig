"""Test hedwig.saas.operator_keys — quotas defined for all tiers."""

from hedwig.saas.models import SubscriptionTier
from hedwig.saas.operator_keys import (
    TIER_TOKEN_QUOTAS,
    get_quota_status,
    _next_tier,
)


class TestTierTokenQuotas:
    """Every SubscriptionTier must have a quota entry."""

    def test_all_tiers_have_quotas(self):
        for tier in SubscriptionTier:
            assert tier in TIER_TOKEN_QUOTAS, f"Missing quota for tier: {tier.value}"

    def test_quotas_are_positive_integers(self):
        for tier, quota in TIER_TOKEN_QUOTAS.items():
            assert isinstance(quota, int), f"Quota for {tier.value} is not int"
            assert quota > 0, f"Quota for {tier.value} must be positive"

    def test_free_quota_value(self):
        assert TIER_TOKEN_QUOTAS[SubscriptionTier.FREE] == 50_000

    def test_pro_quota_value(self):
        assert TIER_TOKEN_QUOTAS[SubscriptionTier.PRO] == 2_000_000

    def test_team_quota_value(self):
        assert TIER_TOKEN_QUOTAS[SubscriptionTier.TEAM] == 5_000_000

    def test_tier_ordering(self):
        """Higher tiers must have strictly larger quotas."""
        free = TIER_TOKEN_QUOTAS[SubscriptionTier.FREE]
        pro = TIER_TOKEN_QUOTAS[SubscriptionTier.PRO]
        team = TIER_TOKEN_QUOTAS[SubscriptionTier.TEAM]
        assert free < pro < team


class TestGetQuotaStatus:
    def test_returns_expected_keys(self):
        status = get_quota_status(SubscriptionTier.FREE, 10_000)
        assert set(status.keys()) == {"tier", "used", "limit", "percent", "remaining"}

    def test_percent_calculation(self):
        status = get_quota_status(SubscriptionTier.FREE, 25_000)
        assert status["percent"] == 50.0

    def test_remaining_calculation(self):
        status = get_quota_status(SubscriptionTier.PRO, 500_000)
        assert status["remaining"] == 1_500_000

    def test_remaining_never_negative(self):
        status = get_quota_status(SubscriptionTier.FREE, 999_999)
        assert status["remaining"] == 0


class TestNextTier:
    def test_free_suggests_pro(self):
        assert "Pro" in _next_tier(SubscriptionTier.FREE)

    def test_pro_suggests_team(self):
        assert "Team" in _next_tier(SubscriptionTier.PRO)

    def test_team_suggests_enterprise(self):
        assert "Enterprise" in _next_tier(SubscriptionTier.TEAM)
