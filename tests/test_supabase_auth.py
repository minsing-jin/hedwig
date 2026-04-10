"""
Tests for hedwig.saas.auth — Supabase auth error handling.

Verifies that all auth functions raise a clear, actionable AuthError
when SUPABASE_URL and/or SUPABASE_KEY are not set.
"""
from __future__ import annotations

import pytest


# ---------------------------------------------------------------------------
# Credential validation helper
# ---------------------------------------------------------------------------


def test_require_supabase_credentials_raises_when_both_missing():
    """_require_supabase_credentials names both missing env vars."""
    from hedwig.saas.auth import AuthError, _require_supabase_credentials

    with pytest.raises(AuthError, match="SUPABASE_URL") as exc_info:
        _require_supabase_credentials()
    msg = str(exc_info.value)
    assert "SUPABASE_URL" in msg
    assert "SUPABASE_KEY" in msg
    assert "environment variable" in msg.lower()


def test_require_supabase_credentials_mentions_dashboard():
    """Error message tells users where to find the credentials."""
    from hedwig.saas.auth import AuthError, _require_supabase_credentials

    with pytest.raises(AuthError) as exc_info:
        _require_supabase_credentials()
    msg = str(exc_info.value)
    assert "supabase" in msg.lower()
    assert "dashboard" in msg.lower() or "project" in msg.lower()


# ---------------------------------------------------------------------------
# sign_up
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_signup_raises_clear_error_without_credentials():
    """sign_up raises AuthError naming missing env vars."""
    from hedwig.saas.auth import AuthError, sign_up

    with pytest.raises(AuthError, match="SUPABASE_URL") as exc_info:
        await sign_up(email="test@example.com", password="secret123")
    msg = str(exc_info.value)
    assert "SUPABASE_URL" in msg
    assert "SUPABASE_KEY" in msg


# ---------------------------------------------------------------------------
# sign_in
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_signin_raises_clear_error_without_credentials():
    """sign_in raises AuthError naming missing env vars."""
    from hedwig.saas.auth import AuthError, sign_in

    with pytest.raises(AuthError, match="SUPABASE_URL") as exc_info:
        await sign_in(email="test@example.com", password="secret123")
    msg = str(exc_info.value)
    assert "SUPABASE_URL" in msg


# ---------------------------------------------------------------------------
# sign_out
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_signout_raises_clear_error_without_credentials():
    """sign_out raises AuthError when credentials are missing."""
    from hedwig.saas.auth import AuthError, sign_out

    with pytest.raises(AuthError, match="SUPABASE_URL"):
        await sign_out(access_token="fake_token")


# ---------------------------------------------------------------------------
# get_user
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_user_raises_clear_error_without_credentials():
    """get_user raises AuthError when credentials are missing."""
    from hedwig.saas.auth import AuthError, get_user

    with pytest.raises(AuthError, match="SUPABASE_URL"):
        await get_user(access_token="fake_token")


# ---------------------------------------------------------------------------
# refresh_token
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_refresh_token_raises_clear_error_without_credentials():
    """refresh_token raises AuthError when credentials are missing."""
    from hedwig.saas.auth import AuthError, refresh_token

    with pytest.raises(AuthError, match="SUPABASE_URL"):
        await refresh_token(refresh_token="fake_refresh_token")


# ---------------------------------------------------------------------------
# AuthError is a proper Exception subclass
# ---------------------------------------------------------------------------


def test_auth_error_is_exception_subclass():
    """AuthError is a proper Exception subclass."""
    from hedwig.saas.auth import AuthError

    assert issubclass(AuthError, Exception)
    err = AuthError("test message")
    assert str(err) == "test message"


# ---------------------------------------------------------------------------
# Only SUPABASE_URL missing
# ---------------------------------------------------------------------------


def test_require_credentials_only_url_missing(monkeypatch):
    """When only SUPABASE_URL is missing, error lists it as the missing var."""
    import hedwig.saas.auth as auth_mod

    monkeypatch.setattr(auth_mod, "SUPABASE_URL", "")
    monkeypatch.setattr(auth_mod, "SUPABASE_KEY", "some-valid-key")

    from hedwig.saas.auth import AuthError

    with pytest.raises(AuthError) as exc_info:
        auth_mod._require_supabase_credentials()
    msg = str(exc_info.value)
    assert "SUPABASE_URL" in msg
    # The "not configured:" preamble only lists SUPABASE_URL, not SUPABASE_KEY
    preamble = msg.split("must be set")[0]
    assert "SUPABASE_URL" in preamble
    assert "SUPABASE_KEY" not in preamble


# ---------------------------------------------------------------------------
# Only SUPABASE_KEY missing
# ---------------------------------------------------------------------------


def test_require_credentials_only_key_missing(monkeypatch):
    """When only SUPABASE_KEY is missing, error lists it as the missing var."""
    import hedwig.saas.auth as auth_mod

    monkeypatch.setattr(auth_mod, "SUPABASE_URL", "https://test.supabase.co")
    monkeypatch.setattr(auth_mod, "SUPABASE_KEY", "")

    from hedwig.saas.auth import AuthError

    with pytest.raises(AuthError) as exc_info:
        auth_mod._require_supabase_credentials()
    msg = str(exc_info.value)
    assert "SUPABASE_KEY" in msg
    # The "not configured:" preamble only lists SUPABASE_KEY, not SUPABASE_URL
    preamble = msg.split("must be set")[0]
    assert "SUPABASE_KEY" in preamble
    assert "SUPABASE_URL" not in preamble


# ---------------------------------------------------------------------------
# Both credentials present — no error
# ---------------------------------------------------------------------------


def test_require_credentials_passes_when_both_set(monkeypatch):
    """No error raised when both SUPABASE_URL and SUPABASE_KEY are set."""
    import hedwig.saas.auth as auth_mod

    monkeypatch.setattr(auth_mod, "SUPABASE_URL", "https://test.supabase.co")
    monkeypatch.setattr(auth_mod, "SUPABASE_KEY", "eyJ-valid-key")

    # Should not raise
    auth_mod._require_supabase_credentials()
