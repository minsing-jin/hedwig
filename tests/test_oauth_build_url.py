"""Test build_oauth_url returns None when SUPABASE_URL is missing."""

from unittest.mock import patch

from hedwig.saas.oauth import build_oauth_url


def test_build_oauth_url_returns_none_when_supabase_url_missing():
    """build_oauth_url must return None when SUPABASE_URL is not set."""
    with patch("hedwig.saas.oauth.SUPABASE_URL", ""):
        result = build_oauth_url("google", "http://localhost/callback")
        assert result is None, (
            "Expected None when SUPABASE_URL is empty/missing, "
            f"got {result!r}"
        )


def test_build_oauth_url_returns_none_when_supabase_url_is_none():
    """build_oauth_url must return None when SUPABASE_URL is None."""
    with patch("hedwig.saas.oauth.SUPABASE_URL", None):
        result = build_oauth_url("google", "http://localhost/callback")
        assert result is None, (
            "Expected None when SUPABASE_URL is None, "
            f"got {result!r}"
        )
