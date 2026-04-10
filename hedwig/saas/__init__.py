"""
Hedwig SaaS module — multi-tenant infrastructure.

Submodules:
  - auth: Supabase Auth integration
  - billing: Stripe subscription management
  - quota: Usage tracking and tier enforcement
  - models: SaaS-specific data models (User, Subscription, Usage)
"""
from hedwig.saas.models import Subscription, SubscriptionTier, Usage, UserProfile  # noqa: F401
