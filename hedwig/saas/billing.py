"""
Stripe billing integration for Hedwig SaaS.

Handles checkout sessions, webhooks, and subscription management.
"""
from __future__ import annotations

import logging
import os
from typing import Optional

import httpx

from hedwig.saas.models import SubscriptionTier

logger = logging.getLogger(__name__)

STRIPE_API = "https://api.stripe.com/v1"
STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY", "")
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET", "")

# Stripe Price IDs — set via env after creating in Stripe Dashboard
STRIPE_PRICE_PRO = os.getenv("STRIPE_PRICE_PRO", "")
STRIPE_PRICE_TEAM = os.getenv("STRIPE_PRICE_TEAM", "")

TIER_TO_PRICE = {
    SubscriptionTier.PRO: STRIPE_PRICE_PRO,
    SubscriptionTier.TEAM: STRIPE_PRICE_TEAM,
}


class BillingError(Exception):
    pass


async def create_checkout_session(
    user_id: str,
    user_email: str,
    tier: SubscriptionTier,
    success_url: str,
    cancel_url: str,
) -> dict:
    """Create a Stripe Checkout session for upgrading to a paid tier."""
    if not STRIPE_SECRET_KEY:
        raise BillingError("Stripe not configured")

    price_id = TIER_TO_PRICE.get(tier)
    if not price_id:
        raise BillingError(f"No Stripe price ID for tier {tier}")

    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(
            f"{STRIPE_API}/checkout/sessions",
            headers={
                "Authorization": f"Bearer {STRIPE_SECRET_KEY}",
                "Content-Type": "application/x-www-form-urlencoded",
            },
            data={
                "payment_method_types[]": "card",
                "line_items[0][price]": price_id,
                "line_items[0][quantity]": "1",
                "mode": "subscription",
                "success_url": success_url,
                "cancel_url": cancel_url,
                "client_reference_id": user_id,
                "customer_email": user_email,
                "metadata[user_id]": user_id,
                "metadata[tier]": tier.value,
            },
        )
        if resp.status_code != 200:
            raise BillingError(f"Checkout session creation failed: {resp.text}")
        return resp.json()


async def create_customer_portal_session(
    stripe_customer_id: str,
    return_url: str,
) -> dict:
    """Create a Stripe Customer Portal session for managing subscription."""
    if not STRIPE_SECRET_KEY:
        raise BillingError("Stripe not configured")

    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(
            f"{STRIPE_API}/billing_portal/sessions",
            headers={
                "Authorization": f"Bearer {STRIPE_SECRET_KEY}",
                "Content-Type": "application/x-www-form-urlencoded",
            },
            data={
                "customer": stripe_customer_id,
                "return_url": return_url,
            },
        )
        if resp.status_code != 200:
            raise BillingError(f"Portal session creation failed: {resp.text}")
        return resp.json()


async def handle_webhook(event: dict) -> Optional[dict]:
    """Handle a Stripe webhook event. Returns subscription update or None."""
    event_type = event.get("type")
    data = event.get("data", {}).get("object", {})

    if event_type == "checkout.session.completed":
        user_id = data.get("metadata", {}).get("user_id")
        tier = data.get("metadata", {}).get("tier")
        return {
            "action": "activate_subscription",
            "user_id": user_id,
            "tier": tier,
            "stripe_customer_id": data.get("customer"),
            "stripe_subscription_id": data.get("subscription"),
        }

    elif event_type == "customer.subscription.updated":
        return {
            "action": "update_subscription",
            "stripe_subscription_id": data.get("id"),
            "status": data.get("status"),
            "current_period_end": data.get("current_period_end"),
            "cancel_at_period_end": data.get("cancel_at_period_end", False),
        }

    elif event_type == "customer.subscription.deleted":
        return {
            "action": "cancel_subscription",
            "stripe_subscription_id": data.get("id"),
        }

    return None
