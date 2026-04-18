"""Integration test: verify all hedwig.saas modules import successfully.

This test ensures every module under hedwig/saas/ can be imported without
errors, that key classes/functions are accessible, and that the models
behave correctly with basic instantiation.
"""
from __future__ import annotations

import importlib
import pkgutil

import pytest


# ---------------------------------------------------------------------------
# 1. Smoke-test: every .py under hedwig/saas is importable
# ---------------------------------------------------------------------------

def _discover_saas_modules() -> list[str]:
    """Dynamically discover all modules under hedwig.saas."""
    import hedwig.saas as pkg

    modules = [pkg.__name__]  # the package itself
    for importer, modname, ispkg in pkgutil.walk_packages(
        pkg.__path__, prefix=pkg.__name__ + "."
    ):
        modules.append(modname)
    return sorted(modules)


SAAS_MODULES = _discover_saas_modules()


@pytest.mark.parametrize("module_name", SAAS_MODULES)
def test_import_saas_module(module_name: str):
    """Each saas sub-module should import without error."""
    mod = importlib.import_module(module_name)
    assert mod is not None


def test_auto_context_module_imports():
    """hedwig.saas.auto_context has an explicit import smoke test."""
    mod = importlib.import_module("hedwig.saas.auto_context")
    assert mod is not None


# ---------------------------------------------------------------------------
# 2. Key symbols are accessible after import
# ---------------------------------------------------------------------------

def test_models_exports():
    """hedwig.saas.models exports the expected Pydantic models and enums."""
    from hedwig.saas.models import (
        SubscriptionStatus,
        SubscriptionTier,
        TIER_LIMITS,
        TIER_PRICES,
    )

    # Enums have expected members
    assert set(SubscriptionTier) == {
        SubscriptionTier.FREE,
        SubscriptionTier.PRO,
        SubscriptionTier.TEAM,
    }
    assert set(SubscriptionStatus) >= {
        SubscriptionStatus.ACTIVE,
        SubscriptionStatus.CANCELED,
    }

    # TIER_LIMITS covers every tier
    for tier in SubscriptionTier:
        assert tier in TIER_LIMITS

    # TIER_PRICES covers every tier
    for tier in SubscriptionTier:
        assert tier in TIER_PRICES


def test_auth_exports():
    """hedwig.saas.auth exports the expected callables."""
    from hedwig.saas.auth import (
        AuthError,
        get_current_user,
        get_user,
        refresh_token,
        require_auth,
        sign_in,
        sign_out,
        sign_up,
    )

    assert issubclass(AuthError, Exception)
    for fn in (sign_up, sign_in, sign_out, get_user, refresh_token,
               get_current_user, require_auth):
        assert callable(fn)


def test_billing_exports():
    """hedwig.saas.billing exports the expected callables and constants."""
    from hedwig.saas.billing import (
        BillingError,
        STRIPE_API,
        TIER_TO_PRICE,
        create_checkout_session,
        create_customer_portal_session,
        handle_webhook,
    )

    assert issubclass(BillingError, Exception)
    assert STRIPE_API.startswith("https://")
    assert isinstance(TIER_TO_PRICE, dict)
    for fn in (create_checkout_session, create_customer_portal_session,
               handle_webhook):
        assert callable(fn)


def test_quota_exports():
    """hedwig.saas.quota exports the expected callables."""
    from hedwig.saas.quota import (
        QuotaExceeded,
        check_quota,
        enforce_limit,
        get_current_usage,
        increment_usage,
    )

    assert issubclass(QuotaExceeded, Exception)
    for fn in (check_quota, get_current_usage, increment_usage, enforce_limit):
        assert callable(fn)


def test_package_init_reexports():
    """hedwig.saas.__init__ re-exports the core model classes."""
    from hedwig.saas import Subscription, SubscriptionTier, Usage, UserProfile

    assert SubscriptionTier.FREE.value == "free"
    assert issubclass(UserProfile, object)
    assert issubclass(Subscription, object)
    assert issubclass(Usage, object)


# ---------------------------------------------------------------------------
# 3. Basic model instantiation & methods
# ---------------------------------------------------------------------------

def test_user_profile_creation():
    """UserProfile can be instantiated with minimal fields."""
    from hedwig.saas.models import UserProfile

    user = UserProfile(id="usr_123", email="test@example.com")
    assert user.id == "usr_123"
    assert user.email == "test@example.com"
    assert user.onboarding_complete is False
    assert user.criteria == {}


def test_subscription_defaults_and_methods():
    """Subscription defaults to FREE tier and helper methods work."""
    from hedwig.saas.models import Subscription, SubscriptionTier

    sub = Subscription(user_id="usr_123")
    assert sub.tier == SubscriptionTier.FREE
    assert sub.can_use_custom_sources() is False
    assert sub.can_run_weekly_evolution() is False

    limits = sub.get_limits()
    assert "sources" in limits
    assert "signals_per_day" in limits

    pro_sub = Subscription(user_id="usr_456", tier=SubscriptionTier.PRO)
    assert pro_sub.can_use_custom_sources() is True
    assert pro_sub.can_run_weekly_evolution() is True


def test_usage_is_over_limit():
    """Usage.is_over_limit works correctly."""
    from hedwig.saas.models import Usage

    usage = Usage(user_id="usr_123", metric="signals_collected", value=50)
    assert usage.is_over_limit(50) is True
    assert usage.is_over_limit(51) is False
    assert usage.is_over_limit(49) is True


def test_quota_enforce_limit_raises():
    """enforce_limit raises QuotaExceeded when not allowed."""
    from hedwig.saas.quota import QuotaExceeded, enforce_limit

    # Should not raise
    enforce_limit(allowed=True, metric="signals_per_day", current=5, limit=50)

    # Should raise
    with pytest.raises(QuotaExceeded, match="Quota exceeded"):
        enforce_limit(allowed=False, metric="signals_per_day", current=50, limit=50)


@pytest.mark.asyncio
async def test_check_quota_free_tier():
    """check_quota returns correct tuple for free tier without storage."""
    from hedwig.saas.models import Subscription, SubscriptionTier
    from hedwig.saas.quota import check_quota

    sub = Subscription(user_id="usr_free", tier=SubscriptionTier.FREE)
    allowed, current, limit = await check_quota(
        user_id="usr_free",
        metric="signals_per_day",
        subscription=sub,
        storage=None,
    )
    assert isinstance(allowed, bool)
    assert isinstance(current, int)
    assert isinstance(limit, int)
    assert limit == 50  # FREE tier limit


@pytest.mark.asyncio
async def test_check_quota_pro_tier_unlimited():
    """check_quota treats PRO tier as unlimited for signals."""
    from hedwig.saas.models import Subscription, SubscriptionTier
    from hedwig.saas.quota import check_quota

    sub = Subscription(user_id="usr_pro", tier=SubscriptionTier.PRO)
    allowed, current, limit = await check_quota(
        user_id="usr_pro",
        metric="signals_per_day",
        subscription=sub,
        storage=None,
    )
    assert allowed is True
    assert limit >= 999_999


# ---------------------------------------------------------------------------
# 4. Billing / Auth error paths (no external calls)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_billing_no_stripe_key():
    """BillingError raised when Stripe key is not set."""
    from hedwig.saas.billing import BillingError, create_checkout_session
    from hedwig.saas.models import SubscriptionTier

    # STRIPE_SECRET_KEY defaults to "" when env var not set
    with pytest.raises(BillingError, match="STRIPE_SECRET_KEY environment variable is not set"):
        await create_checkout_session(
            user_id="usr_test",
            user_email="t@t.com",
            tier=SubscriptionTier.PRO,
            success_url="http://localhost/ok",
            cancel_url="http://localhost/cancel",
        )


@pytest.mark.asyncio
async def test_auth_no_supabase_creds():
    """AuthError raised when Supabase credentials are not set."""
    from hedwig.saas.auth import AuthError, sign_up

    with pytest.raises(AuthError, match="Supabase credentials not configured"):
        await sign_up("test@example.com", "password123")


@pytest.mark.asyncio
async def test_webhook_handler_unknown_event():
    """handle_webhook returns None for unrecognized event types."""
    from hedwig.saas.billing import handle_webhook

    result = await handle_webhook({"type": "unknown.event", "data": {}})
    assert result is None


@pytest.mark.asyncio
async def test_webhook_handler_checkout_completed():
    """handle_webhook parses checkout.session.completed correctly."""
    from hedwig.saas.billing import handle_webhook

    event = {
        "type": "checkout.session.completed",
        "data": {
            "object": {
                "metadata": {"user_id": "usr_789", "tier": "pro"},
                "customer": "cus_abc",
                "subscription": "sub_xyz",
            }
        },
    }
    result = await handle_webhook(event)
    assert result is not None
    assert result["action"] == "activate_subscription"
    assert result["user_id"] == "usr_789"
    assert result["tier"] == "pro"
