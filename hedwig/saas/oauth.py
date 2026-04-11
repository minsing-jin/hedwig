"""
OAuth providers integration via Supabase Auth.

Supabase Auth natively supports many OAuth providers. We just need to:
1. Redirect user to Supabase's OAuth URL with provider name
2. Supabase handles the OAuth flow with the provider
3. User comes back with a session token

This module provides URL builders for each supported provider.
Provider activation happens in Supabase Dashboard → Authentication → Providers.
"""
from __future__ import annotations

import logging
from typing import Optional

from hedwig.config import SUPABASE_URL

logger = logging.getLogger(__name__)


# Providers natively supported by Supabase Auth
SUPPORTED_PROVIDERS = {
    "google": {
        "label": "Google",
        "icon": "G",
        "color": "#4285F4",
    },
    "github": {
        "label": "GitHub",
        "icon": "GH",
        "color": "#181717",
    },
    "twitter": {
        "label": "X (Twitter)",
        "icon": "X",
        "color": "#000000",
    },
    "discord": {
        "label": "Discord",
        "icon": "D",
        "color": "#5865F2",
    },
    "linkedin_oidc": {
        "label": "LinkedIn",
        "icon": "in",
        "color": "#0A66C2",
    },
    "facebook": {
        "label": "Facebook",
        "icon": "f",
        "color": "#1877F2",
    },
    "apple": {
        "label": "Apple",
        "icon": "A",
        "color": "#000000",
    },
    "azure": {
        "label": "Microsoft",
        "icon": "M",
        "color": "#0078D4",
    },
    "spotify": {
        "label": "Spotify",
        "icon": "S",
        "color": "#1DB954",
    },
    "slack_oidc": {
        "label": "Slack",
        "icon": "Sl",
        "color": "#4A154B",
    },
    "twitch": {
        "label": "Twitch",
        "icon": "Tw",
        "color": "#9146FF",
    },
    "notion": {
        "label": "Notion",
        "icon": "N",
        "color": "#000000",
    },
}


def build_oauth_url(provider: str, redirect_to: str) -> Optional[str]:
    """Build the Supabase OAuth authorize URL for a given provider."""
    if not SUPABASE_URL:
        return None
    if provider not in SUPPORTED_PROVIDERS:
        return None

    return (
        f"{SUPABASE_URL}/auth/v1/authorize"
        f"?provider={provider}"
        f"&redirect_to={redirect_to}"
    )


def get_provider_metadata(provider: str) -> Optional[dict]:
    return SUPPORTED_PROVIDERS.get(provider)


def list_providers() -> list[dict]:
    return [
        {"id": pid, **meta} for pid, meta in SUPPORTED_PROVIDERS.items()
    ]
