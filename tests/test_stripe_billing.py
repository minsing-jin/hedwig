"""
Tests for hedwig.saas.billing — Stripe billing error handling.

Verifies that all billing functions raise a clear, actionable BillingError
when STRIPE_SECRET_KEY is not set.
"""
from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_checkout_raises_clear_error_without_stripe_key():
    """create_checkout_session raises BillingError naming STRIPE_SECRET_KEY."""
    from hedwig.saas.billing import BillingError, create_checkout_session
    from hedwig.saas.models import SubscriptionTier

    with pytest.raises(BillingError, match="STRIPE_SECRET_KEY") as exc_info:
        await create_checkout_session(
            user_id="usr_test",
            user_email="t@t.com",
            tier=SubscriptionTier.PRO,
            success_url="http://localhost/ok",
            cancel_url="http://localhost/cancel",
        )
    # Verify the message is actionable — mentions the env var name
    msg = str(exc_info.value)
    assert "STRIPE_SECRET_KEY" in msg
    assert "environment variable" in msg.lower() or "env" in msg.lower()


@pytest.mark.asyncio
async def test_portal_raises_clear_error_without_stripe_key():
    """create_customer_portal_session raises BillingError naming STRIPE_SECRET_KEY."""
    from hedwig.saas.billing import BillingError, create_customer_portal_session

    with pytest.raises(BillingError, match="STRIPE_SECRET_KEY") as exc_info:
        await create_customer_portal_session(
            stripe_customer_id="cus_test",
            return_url="http://localhost/settings",
        )
    msg = str(exc_info.value)
    assert "STRIPE_SECRET_KEY" in msg


@pytest.mark.asyncio
async def test_require_stripe_key_helper():
    """_require_stripe_key raises BillingError with clear guidance."""
    from hedwig.saas.billing import BillingError, _require_stripe_key

    with pytest.raises(BillingError) as exc_info:
        _require_stripe_key()
    msg = str(exc_info.value)
    assert "STRIPE_SECRET_KEY" in msg
    assert "sk_live" in msg or "sk_test" in msg  # mentions expected format


@pytest.mark.asyncio
async def test_billing_error_is_exception_subclass():
    """BillingError is a proper Exception subclass."""
    from hedwig.saas.billing import BillingError

    assert issubclass(BillingError, Exception)
    err = BillingError("test message")
    assert str(err) == "test message"


@pytest.mark.asyncio
async def test_webhook_does_not_require_stripe_key():
    """handle_webhook works without STRIPE_SECRET_KEY (no outbound calls)."""
    from hedwig.saas.billing import handle_webhook

    # Should NOT raise — webhooks are inbound events, no key needed
    result = await handle_webhook({"type": "unknown.event", "data": {}})
    assert result is None


@pytest.mark.asyncio
async def test_webhook_checkout_persists_subscription_update(monkeypatch):
    """checkout.session.completed persists subscription state via storage helper."""
    from hedwig.saas.billing import handle_webhook
    from hedwig.storage import supabase as supabase_mod

    captured: dict[str, object] = {}

    def fake_save_subscription_update(**kwargs):
        captured.update(kwargs)
        return True

    monkeypatch.setattr(
        supabase_mod,
        "save_subscription_update",
        fake_save_subscription_update,
    )

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
    assert captured == {
        "user_id": "usr_789",
        "tier": "pro",
        "stripe_customer_id": "cus_abc",
        "stripe_subscription_id": "sub_xyz",
        "status": "active",
    }
